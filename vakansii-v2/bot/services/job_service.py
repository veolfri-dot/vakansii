import logging
import os
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("Переменная окружения DB_URL не задана")

engine = create_async_engine(DB_URL, echo=False, future=True)


class JobService:
    """Сервис для работы с вакансиями и подписками в PostgreSQL."""

    @staticmethod
    async def get_filtered_jobs(filters: dict) -> List[dict]:
        """Получить вакансии с фильтрацией через parameterized query."""
        conditions = ["1=1"]
        params: dict = {}

        if filters.get("category"):
            conditions.append("category = :category")
            params["category"] = filters["category"]

        if filters.get("remote_type"):
            conditions.append("remote_type = :remote_type")
            params["remote_type"] = filters["remote_type"]

        if filters.get("min_salary"):
            conditions.append("salary_max_usd >= :min_salary")
            params["min_salary"] = filters["min_salary"]

        if filters.get("source"):
            conditions.append("source = :source")
            params["source"] = filters["source"]

        if filters.get("keywords"):
            conditions.append("title ILIKE :keywords")
            params["keywords"] = f"%{filters['keywords']}%"

        limit = filters.get("limit", 50)
        offset = filters.get("offset", 0)

        query = f"""
            SELECT * FROM jobs
            WHERE {' AND '.join(conditions)}
            ORDER BY published_at DESC
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = limit
        params["offset"] = offset

        async with engine.connect() as conn:
            result = await conn.execute(text(query), params)
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    @staticmethod
    async def get_unsent_jobs_for_user(
        user_id: int, keywords: str, min_salary: int, limit: int = 3
    ) -> List[dict]:
        """Выбрать вакансии, подходящие под фильтр, но еще не отправленные пользователю."""
        keyword_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
        conditions = ["1=1"]
        params: dict = {"user_id": user_id, "limit": limit}

        if min_salary > 0:
            conditions.append("j.salary_max_usd >= :min_salary")
            params["min_salary"] = min_salary

        if keyword_list:
            or_clauses = []
            for i, kw in enumerate(keyword_list):
                key = f"kw_{i}"
                or_clauses.append(f"j.title ILIKE :{key}")
                params[key] = f"%{kw}%"
            conditions.append(f"({' OR '.join(or_clauses)})")

        query = f"""
            SELECT j.* FROM jobs j
            WHERE {' AND '.join(conditions)}
              AND j.published_at > NOW() - INTERVAL '7 days'
              AND NOT EXISTS (
                  SELECT 1 FROM sent_notifications sn
                  WHERE sn.user_id = :user_id AND sn.job_id = j.id
              )
            ORDER BY j.published_at DESC
            LIMIT :limit
        """

        async with engine.connect() as conn:
            result = await conn.execute(text(query), params)
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    @staticmethod
    async def mark_sent(user_id: int, job_id: str):
        """Отметить вакансию как отправленную пользователю."""
        async with engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO sent_notifications (user_id, job_id)
                    VALUES (:user_id, :job_id)
                    ON CONFLICT (user_id, job_id) DO NOTHING
                """),
                {"user_id": user_id, "job_id": job_id},
            )

    @staticmethod
    async def save_subscription(user_id: int, keywords: str, min_salary: int):
        """Сохранить или обновить подписку пользователя."""
        async with engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO user_subscriptions (
                        user_id, keywords, min_salary, created_at, updated_at
                    ) VALUES (
                        :user_id, :keywords, :min_salary, NOW(), NOW()
                    )
                    ON CONFLICT (user_id) DO UPDATE SET
                        keywords = EXCLUDED.keywords,
                        min_salary = EXCLUDED.min_salary,
                        updated_at = NOW()
                """),
                {
                    "user_id": user_id,
                    "keywords": keywords,
                    "min_salary": min_salary,
                },
            )

    @staticmethod
    async def delete_subscription(user_id: int):
        """Удалить подписку пользователя."""
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM user_subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id},
            )

    @staticmethod
    async def get_subscriptions() -> List[dict]:
        """Получить все подписки для рассылки."""
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT * FROM user_subscriptions"))
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    @staticmethod
    async def insert_job(
        title: str,
        company: str,
        location: str,
        remote_type: str,
        salary_min_usd: Optional[int],
        salary_max_usd: Optional[int],
        salary_currency: Optional[str],
        category: str,
        source_url: str,
        published_at: Optional[str],
        description: str,
        required_skills: List[str],
        source: str,
    ):
        """Вставить вакансию с обработкой конфликта по уникальному URL."""
        async with engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO jobs (
                        title, company, location, remote_type, salary_min_usd,
                        salary_max_usd, salary_currency, category, source_url, published_at,
                        description, required_skills, source
                    ) VALUES (
                        :title, :company, :location, :remote_type, :salary_min_usd,
                        :salary_max_usd, :salary_currency, :category, :source_url, :published_at,
                        :description, :required_skills, :source
                    )
                    ON CONFLICT (source_url) DO NOTHING
                """),
                {
                    "title": title,
                    "company": company,
                    "location": location,
                    "remote_type": remote_type,
                    "salary_min_usd": salary_min_usd,
                    "salary_max_usd": salary_max_usd,
                    "salary_currency": salary_currency,
                    "category": category,
                    "source_url": source_url,
                    "published_at": published_at,
                    "description": description,
                    "required_skills": required_skills,
                    "source": source,
                },
            )
