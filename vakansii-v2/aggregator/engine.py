import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import List, Optional

import aiohttp
import feedparser
from bs4 import BeautifulSoup
from pybloom_live import ScalableBloomFilter
from telethon import TelegramClient
from telethon.sessions import StringSession
from tenacity import retry, stop_after_attempt, wait_exponential

from aggregator.models import RawVacancy

logger = logging.getLogger(__name__)

TELEGRAM_CHANNELS = [
    "remotejobss",
    "remote_devops_jobs",
    "remotejobpositions",
    "it_expert_vacancies",
    "remote_web_dev_jobs",
    "it_remote_jobs_hidden_gurus",
]


class MultiSourceFetcher:
    """Асинхронный сборщик вакансий из 13 независимых источников."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self.session = session or aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "application/json, text/html, "
                    "application/xhtml+xml, application/rss+xml"
                ),
                "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            },
        )
        self.semaphore = asyncio.Semaphore(5)
        self.bloom = ScalableBloomFilter(mode=ScalableBloomFilter.SMALL_SET_GROWTH)
        self._seen_hashes: set = set()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _request(self, method: str, url: str, **kwargs) -> dict | str:
        """Базовый HTTP-запрос с семафором и retry-логикой."""
        async with self.semaphore:
            async with self.session.request(method, url, **kwargs) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await resp.json()
                return await resp.text()

    async def fetch_all(self, sources: List[str]) -> List[RawVacancy]:
        """Параллельный сбор вакансий из указанных источников с дедупликацией."""
        source_map = {
            "remotive": self._fetch_remotive,
            "himalayas": self._fetch_himalayas,
            "remoteok": self._fetch_remoteok,
            "jobicy": self._fetch_jobicy,
            "workingnomads": self._fetch_workingnomads,
            "wellfound": self._fetch_wellfound,
            "weworkremotely": self._fetch_weworkremotely,
            "ycombinator": self._fetch_ycombinator,
            "headhunter": self._fetch_headhunter,
            "superjob": self._fetch_superjob,
            "adzuna": self._fetch_adzuna,
            "habr_career": self._fetch_habr_career,
            "telegram_channels": self._fetch_telegram_channels,
        }

        tasks = []
        for name in sources:
            coro = source_map.get(name)
            if coro:
                tasks.append(coro())
            else:
                logger.warning("Неизвестный источник: %s", name)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        vacancies: List[RawVacancy] = []

        for result in results:
            if isinstance(result, Exception):
                logger.error("Ошибка при сборе из источника: %s", result)
                continue
            for vacancy in result:
                if vacancy.dedup_hash in self._seen_hashes:
                    continue
                if vacancy.dedup_hash in self.bloom:
                    continue
                self.bloom.add(vacancy.dedup_hash)
                self._seen_hashes.add(vacancy.dedup_hash)
                vacancies.append(vacancy)

        return vacancies

    # ---------- 1. Remotive ----------
    async def _fetch_remotive(self) -> List[RawVacancy]:
        url = "https://remotive.com/api/remote-jobs"
        data = await self._request("GET", url)
        jobs: List[RawVacancy] = []
        for item in data.get("jobs", []):
            jobs.append(
                RawVacancy(
                    source="remotive",
                    external_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    description=item.get("description", ""),
                    url=item.get("url", ""),
                    location=item.get("candidate_required_location", "Worldwide"),
                    remote_type="FULLY_REMOTE",
                    published_at=datetime.utcnow(),
                    raw_data=item,
                )
            )
        return jobs

    # ---------- 2. Himalayas ----------
    async def _fetch_himalayas(self) -> List[RawVacancy]:
        jobs: List[RawVacancy] = []
        for page in range(0, 3):
            offset = page * 20
            url = "https://himalayas.app/api/jobs"
            try:
                data = await self._request("GET", url, params={"offset": offset, "limit": 20})
                for item in data.get("jobs", []):
                    jobs.append(
                        RawVacancy(
                            source="himalayas",
                            external_id=str(item.get("id", "")),
                            title=item.get("title", ""),
                            company=item.get("company", {}).get("name", ""),
                            description=item.get("description", ""),
                            url=item.get("url", ""),
                            location=item.get("location", "Worldwide"),
                            raw_data=item,
                        )
                    )
            except Exception as exc:
                logger.error("Himalayas page %d: %s", page, exc)
                break
        return jobs

    # ---------- 3. RemoteOK ----------
    async def _fetch_remoteok(self) -> List[RawVacancy]:
        url = "https://remoteok.com/api"
        data = await self._request("GET", url)
        jobs: List[RawVacancy] = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                jobs.append(
                    RawVacancy(
                        source="remoteok",
                        external_id=str(item.get("id", "")),
                        title=item.get("position", ""),
                        company=item.get("company", ""),
                        description=item.get("description", ""),
                        url=f"https://remoteok.com/remote-jobs/{item.get('id', '')}",
                        location=item.get("location", "Worldwide"),
                        raw_data=item,
                    )
                )
        return jobs

    # ---------- 4. Jobicy ----------
    async def _fetch_jobicy(self) -> List[RawVacancy]:
        url = "https://jobicy.com/api/v2/remote-jobs"
        params = {"count": 50, "geo": "worldwide", "industry": "development"}
        data = await self._request("GET", url, params=params)
        jobs: List[RawVacancy] = []
        for item in data.get("jobs", []):
            jobs.append(
                RawVacancy(
                    source="jobicy",
                    external_id=str(item.get("id", "")),
                    title=item.get("jobTitle", ""),
                    company=item.get("companyName", ""),
                    description=item.get("jobDescription", ""),
                    url=item.get("url", ""),
                    location=item.get("jobGeo", "Worldwide"),
                    raw_data=item,
                )
            )
        return jobs

    # ---------- 5. Working Nomads (Stealth Scraping) ----------
    async def _fetch_workingnomads(self) -> List[RawVacancy]:
        url = "https://www.workingnomads.com/jobs"
        text = await self._request("GET", url)
        soup = BeautifulSoup(text, "html.parser")
        jobs: List[RawVacancy] = []
        scripts = soup.find_all("script", type="application/ld+json")
        if not scripts:
            logger.warning(
                "Working Nomads: не найдены JSON-LD теги. "
                "Возможно, изменилась верстка сайта."
            )
        for script in scripts:
            try:
                ld = json.loads(script.string)
                if isinstance(ld, dict) and ld.get("@type") == "JobPosting":
                    loc_obj = ld.get("jobLocation", {})
                    address = loc_obj.get("address", {}) if isinstance(loc_obj, dict) else {}
                    location = (
                        address.get("addressLocality", "Remote")
                        if isinstance(address, dict)
                        else "Remote"
                    )
                    jobs.append(
                        RawVacancy(
                            source="workingnomads",
                            external_id=ld.get("url", ""),
                            title=ld.get("title", ""),
                            company=ld.get("hiringOrganization", {}).get("name", ""),
                            description=ld.get("description", ""),
                            url=ld.get("url", ""),
                            location=location,
                            raw_data=ld,
                        )
                    )
            except Exception as exc:
                logger.debug("Ошибка парсинга JSON-LD Working Nomads: %s", exc)
                continue
        return jobs

    # ---------- 6. Wellfound (GraphQL) ----------
    async def _fetch_wellfound(self) -> List[RawVacancy]:
        url = "https://wellfound.com/graphql"
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://wellfound.com/jobs",
        }
        payload = {
            "operationName": "JobSearch",
            "variables": {"filter": {"remote": True, "jobType": "software-engineer"}},
            "query": (
                "query JobSearch($filter: JobSearchFilter!){"
                "  jobs(filter: $filter){"
                "    id title companyName description location url"
                "  }"
                "}"
            ),
        }
        async with self.semaphore:
            async with self.session.post(url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
        jobs: List[RawVacancy] = []
        for item in data.get("data", {}).get("jobs", []):
            jobs.append(
                RawVacancy(
                    source="wellfound",
                    external_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    company=item.get("companyName", ""),
                    description=item.get("description", ""),
                    url=item.get("url", ""),
                    location=item.get("location", ""),
                    raw_data=item,
                )
            )
        return jobs

    # ---------- 7. We Work Remotely (RSS) ----------
    async def _fetch_weworkremotely(self) -> List[RawVacancy]:
        url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
        text = await self._request("GET", url)
        parsed = feedparser.parse(text)
        jobs: List[RawVacancy] = []
        for entry in parsed.get("entries", []):
            title_raw = entry.get("title", "")
            company = ""
            title = title_raw
            if ":" in title_raw:
                parts = title_raw.split(":", 1)
                company = parts[0].strip()
                title = parts[1].strip()
            published = None
            if entry.get("published"):
                try:
                    published = datetime.strptime(
                        entry["published"], "%a, %d %b %Y %H:%M:%S %z"
                    )
                except ValueError:
                    pass
            jobs.append(
                RawVacancy(
                    source="weworkremotely",
                    external_id=entry.get("link", ""),
                    title=title,
                    company=company,
                    description=entry.get("summary", ""),
                    url=entry.get("link", ""),
                    location="Remote",
                    published_at=published,
                    raw_data=dict(entry),
                )
            )
        return jobs

    # ---------- 8. Y Combinator (GraphQL) ----------
    async def _fetch_ycombinator(self) -> List[RawVacancy]:
        url = "https://www.workatastartup.com/graphql"
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.workatastartup.com/jobs",
        }
        payload = {
            "operationName": "GetJobs",
            "variables": {"filter": {"remote": True, "role": "software-engineer"}},
            "query": (
                "query GetJobs($filter: JobFilter!){"
                "  jobs(filter: $filter){"
                "    id title company{name} description location url"
                "  }"
                "}"
            ),
        }
        async with self.semaphore:
            async with self.session.post(url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
        jobs: List[RawVacancy] = []
        for item in data.get("data", {}).get("jobs", []):
            company_name = ""
            if isinstance(item.get("company"), dict):
                company_name = item["company"].get("name", "")
            jobs.append(
                RawVacancy(
                    source="ycombinator",
                    external_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    company=company_name,
                    description=item.get("description", ""),
                    url=item.get("url", ""),
                    location=item.get("location", ""),
                    raw_data=item,
                )
            )
        return jobs

    # ---------- 9. HeadHunter (публичный API, без OAuth2) ----------
    async def _fetch_headhunter(self) -> List[RawVacancy]:
        jobs: List[RawVacancy] = []
        for page in range(0, 3):
            params = {
                "schedule": "remote",
                "text": "IT",
                "per_page": 50,
                "page": page,
            }
            try:
                data = await self._request(
                    "GET", "https://api.hh.ru/vacancies", params=params
                )
                for item in data.get("items", []):
                    salary = item.get("salary") or {}
                    currency = salary.get("currency")
                    min_sal = salary.get("from")
                    max_sal = salary.get("to")

                    # Сохраняем исходную валюту. USD сохраняем в usd-поля, RUR — только в currency.
                    salary_min_usd = None
                    salary_max_usd = None
                    if currency == "USD":
                        salary_min_usd = min_sal
                        salary_max_usd = max_sal

                    snippet = item.get("snippet", {})
                    desc = f"{snippet.get('responsibility', '')}\n{snippet.get('requirement', '')}"

                    jobs.append(
                        RawVacancy(
                            source="headhunter",
                            external_id=str(item.get("id", "")),
                            title=item.get("name", ""),
                            company=item.get("employer", {}).get("name", ""),
                            description=desc,
                            url=item.get("alternate_url", ""),
                            location=item.get("area", {}).get("name", ""),
                            salary_min_usd=salary_min_usd,
                            salary_max_usd=salary_max_usd,
                            salary_currency=currency,
                            raw_data=item,
                        )
                    )
            except Exception as exc:
                logger.error("HeadHunter page %d: %s", page, exc)
                break
        return jobs

    # ---------- 10. SuperJob ----------
    async def _fetch_superjob(self) -> List[RawVacancy]:
        api_key = os.getenv("SUPERJOB_SECRET_KEY")
        if not api_key:
            logger.warning("SUPERJOB_SECRET_KEY отсутствует")
            return []

        headers = {"X-Api-Key": api_key}
        jobs: List[RawVacancy] = []
        for page in range(0, 5):
            params = {
                "remote": 1,
                "keyword": "программист",
                "count": 100,
                "page": page,
            }
            try:
                data = await self._request(
                    "GET", "https://api.superjob.ru/2.0/vacancies/", headers=headers, params=params
                )
                for item in data.get("objects", []):
                    currency = item.get("currency")
                    min_sal = item.get("payment_from")
                    max_sal = item.get("payment_to")

                    salary_min_usd = None
                    salary_max_usd = None
                    if currency == "usd":
                        salary_min_usd = min_sal
                        salary_max_usd = max_sal

                    jobs.append(
                        RawVacancy(
                            source="superjob",
                            external_id=str(item.get("id", "")),
                            title=item.get("profession", ""),
                            company=item.get("firm_name", ""),
                            description=item.get("vacancyRichText", ""),
                            url=item.get("link", ""),
                            location=item.get("town", {}).get("title", ""),
                            salary_min_usd=salary_min_usd,
                            salary_max_usd=salary_max_usd,
                            salary_currency=currency,
                            raw_data=item,
                        )
                    )
            except Exception as exc:
                logger.error("SuperJob page %d: %s", page, exc)
                break
        return jobs

    # ---------- 11. Adzuna ----------
    async def _fetch_adzuna(self) -> List[RawVacancy]:
        app_id = os.getenv("ADZUNA_APP_ID")
        app_key = os.getenv("ADZUNA_APP_KEY")
        if not app_id or not app_key:
            logger.warning("Adzuna credentials отсутствуют")
            return []

        countries = [
            c.strip()
            for c in os.getenv("ADZUNA_COUNTRIES", "gb,us,de,ru").split(",")
            if c.strip()
        ]
        currency_map = {"gb": "GBP", "us": "USD", "de": "EUR", "ru": "RUB"}
        jobs: List[RawVacancy] = []
        for country in countries:
            try:
                params = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": "developer",
                    "where": "remote",
                    "max_days_old": 7,
                    "results_per_page": 50,
                }
                url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
                data = await self._request("GET", url, params=params)
                for item in data.get("results", []):
                    salary_min = item.get("salary_min")
                    salary_max = item.get("salary_max")

                    jobs.append(
                        RawVacancy(
                            source=f"adzuna:{country}",
                            external_id=str(item.get("id", "")),
                            title=item.get("title", ""),
                            company=item.get("company", {}).get("display_name", ""),
                            description=item.get("description", ""),
                            url=item.get("redirect_url", ""),
                            location=item.get("location", {}).get("display_name", ""),
                            salary_min_usd=int(salary_min) if salary_min else None,
                            salary_max_usd=int(salary_max) if salary_max else None,
                            salary_currency=currency_map.get(country),
                            raw_data=item,
                        )
                    )
            except Exception as exc:
                logger.error("Adzuna country %s: %s", country, exc)
                continue
        return jobs

    # ---------- 12. Habr Career ----------
    async def _fetch_habr_career(self) -> List[RawVacancy]:
        jobs: List[RawVacancy] = []
        for page in range(1, 6):
            params = {"type": "all", "remote": "1", "page": page, "per_page": 25}
            try:
                data = await self._request(
                    "GET", "https://career.habr.com/api/frontend/v1/vacancies", params=params
                )
                for item in data.get("vacancies", []):
                    jobs.append(
                        RawVacancy(
                            source="habr_career",
                            external_id=str(item.get("id", "")),
                            title=item.get("title", ""),
                            company=item.get("company", {}).get("name", ""),
                            description=item.get("description", ""),
                            url=f"https://career.habr.com/vacancies/{item.get('id', '')}",
                            location="Remote",
                            raw_data=item,
                        )
                    )
            except Exception as exc:
                logger.error("Habr Career page %d: %s", page, exc)
                break
        return jobs

    # ---------- 13. Telegram Channels ----------
    async def _fetch_telegram_channels(self) -> List[RawVacancy]:
        api_id = int(os.getenv("API_ID", "0"))
        api_hash = os.getenv("API_HASH", "")
        session_str = os.getenv("TELETHON_SESSION_STRING", "")
        if not api_id or not api_hash or not session_str:
            logger.warning("Telegram credentials отсутствуют; пропускаем Telegram-источники")
            return []

        client = TelegramClient(StringSession(session_str), api_id, api_hash)
        jobs: List[RawVacancy] = []
        url_pattern = re.compile(r"https?://\S+")

        await client.connect()
        try:
            for channel in TELEGRAM_CHANNELS:
                try:
                    entity = await client.get_entity(channel)
                    async for msg in client.iter_messages(entity, limit=20):
                        if not msg.text:
                            continue
                        urls = url_pattern.findall(msg.text)
                        url = urls[0] if urls else ""
                        jobs.append(
                            RawVacancy(
                                source=f"telegram:{channel}",
                                external_id=str(msg.id),
                                title=msg.text.split("\n")[0][:100],
                                company="",
                                description=msg.text,
                                url=url,
                                location="Remote",
                                published_at=msg.date,
                                raw_data={"channel": channel, "message_id": msg.id},
                            )
                        )
                except Exception as exc:
                    logger.error("Ошибка канала %s: %s", channel, exc)
        finally:
            await client.disconnect()
        return jobs
