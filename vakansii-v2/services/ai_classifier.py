import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional

import aiohttp
import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_redis_client = None


async def _get_redis():
    """Ленивая инициализация Redis с обработкой ошибок подключения."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            await _redis_client.ping()
        except Exception as exc:
            logger.warning("Redis недоступен: %s", exc)
            _redis_client = False
    return _redis_client if _redis_client is not False else None


@dataclass
class CategoryResult:
    """Результат классификации вакансии ИИ-моделью."""

    category: str
    salary_usd: Optional[int]
    required_skills: List[str]


RULE_MAP = {
    "python": "Backend",
    "django": "Backend",
    "flask": "Backend",
    "fastapi": "Backend",
    "go": "Backend",
    "golang": "Backend",
    "rust": "Backend",
    "node.js": "Backend",
    "nodejs": "Backend",
    "backend": "Backend",
    "react": "Frontend",
    "vue": "Frontend",
    "angular": "Frontend",
    "svelte": "Frontend",
    "frontend": "Frontend",
    "devops": "DevOps",
    "docker": "DevOps",
    "kubernetes": "DevOps",
    "aws": "DevOps",
    "terraform": "DevOps",
    "ci/cd": "DevOps",
    "data science": "Data Science",
    "machine learning": "Data Science",
    "ml": "Data Science",
    "data engineer": "Data Science",
    "qa": "QA",
    "test": "QA",
    "automation": "QA",
    "design": "Design",
    "ux": "Design",
    "ui": "Design",
    "product manager": "PM",
    "project manager": "PM",
    "pm": "PM",
    "llm": "Prompt Engineering",
    "prompt": "Prompt Engineering",
    "fullstack": "Fullstack",
    "full-stack": "Fullstack",
}


class OpenRouterJobTagger:
    """Классификатор вакансий через OpenRouter с кэшированием в Redis."""

    # Free tier на OpenRouter: 20 RPM / 200 RPD для бесплатного ключа
    MODEL = "google/gemini-flash-1.5-8b"
    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY не задан")

    async def classify_job(self, title: str, desc: str) -> CategoryResult:
        """Классифицировать вакансию с кэшированием и fallback."""
        redis_client = await _get_redis()
        cache_key = f"job_class:{hashlib.md5((title + desc).encode()).hexdigest()}"

        if redis_client:
            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    try:
                        data = json.loads(cached)
                        return CategoryResult(**data)
                    except Exception as exc:
                        logger.debug("Ошибка парсинга кэша Redis: %s", exc)
            except Exception as exc:
                logger.warning("Ошибка чтения из Redis: %s", exc)

        truncated = desc[:300]
        prompt = (
            "Ты — инструмент извлечения структурированных данных из вакансий. "
            "Выведи ТОЛЬКО валидный JSON без markdown-форматирования.\n"
            "{\n"
            '  "category": "Backend" | "Frontend" | "Fullstack" | "DevOps" | '
            '"Data Science" | "QA" | "Design" | "PM" | "Prompt Engineering" | "Other",\n'
            '  "salary_usd": число или null,\n'
            '  "required_skills": ["skill1", "skill2"]\n'
            "}\n"
            f"Входные данные:\nНазвание: {title}\nОписание: {truncated}"
        )

        try:
            result = await self._call_openrouter(prompt)
            if redis_client:
                try:
                    await redis_client.setex(
                        cache_key,
                        30 * 24 * 60 * 60,  # TTL 30 дней
                        json.dumps(result),
                    )
                except Exception as exc:
                    logger.warning("Ошибка записи в Redis: %s", exc)
            return CategoryResult(**result)
        except Exception as exc:
            logger.error("Ошибка OpenRouter, переключаемся на rule-based: %s", exc)
            return self._rule_based_classify(title, desc)

    async def _call_openrouter(self, prompt: str) -> dict:
        """Отправить запрос к OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("SITE_URL", "https://example.com"),
            "X-Title": "10X Job Aggregator",
        }
        payload = {
            "model": self.MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.API_URL, headers=headers, json=payload) as resp:
                if resp.status >= 500:
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=resp.status,
                        message="Ошибка сервера OpenRouter",
                    )
                resp.raise_for_status()
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return {
                    "category": parsed.get("category", "Other"),
                    "salary_usd": parsed.get("salary_usd"),
                    "required_skills": parsed.get("required_skills", []),
                }

    def _rule_based_classify(self, title: str, desc: str) -> CategoryResult:
        """Резервная классификация по ключевым словам."""
        text = f"{title} {desc}".lower()
        scores: dict = {}
        for keyword, category in RULE_MAP.items():
            if keyword in text:
                scores[category] = scores.get(category, 0) + 1
        category = max(scores, key=scores.get) if scores else "Other"

        salary = None
        match = re.search(r"\$([\d\s,]{3,8})|(\d{3,6})\s*(USD|usd|\$)", text)
        if match:
            sal_str = (match.group(1) or match.group(2)).replace(",", "").replace(" ", "")
            salary = int(sal_str)

        skills = [k for k in RULE_MAP if k in text][:5]
        return CategoryResult(category=category, salary_usd=salary, required_skills=skills)
