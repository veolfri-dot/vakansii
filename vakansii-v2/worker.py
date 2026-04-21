import asyncio
import logging
import os
from datetime import datetime
from typing import List

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aggregator.engine import MultiSourceFetcher
from bot.config import TELEGRAM_BOT_TOKEN
from bot.services.job_service import JobService
from services.ai_classifier import OpenRouterJobTagger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None


async def run_pipeline():
    """Основной пайплайн: сбор -> обогащение -> сохранение -> рассылка."""
    logger.info("Воркер запущен")

    fetcher = MultiSourceFetcher()
    sources = [
        "remotive",
        "himalayas",
        "remoteok",
        "jobicy",
        "workingnomads",
        "wellfound",
        "weworkremotely",
        "ycombinator",
        "headhunter",
        "superjob",
        "adzuna",
        "habr_career",
        "telegram_channels",
    ]
    raw_jobs = await fetcher.fetch_all(sources)
    tagger = OpenRouterJobTagger()

    for job in raw_jobs:
        try:
            enriched = await tagger.classify_job(job.title, job.description)
            await JobService.insert_job(
                title=job.title,
                company=job.company,
                location=job.location,
                remote_type=job.remote_type,
                salary_min_usd=enriched.salary_usd,
                salary_max_usd=enriched.salary_usd,
                salary_currency=None,
                category=enriched.category,
                source_url=job.url,
                published_at=job.published_at.isoformat()
                if job.published_at
                else datetime.utcnow().isoformat(),
                description=job.description,
                required_skills=enriched.required_skills,
                source=job.source,
            )
        except Exception as exc:
            logger.error("Ошибка обработки вакансии %s: %s", job.url, exc)
            continue

    if bot:
        subs = await JobService.get_subscriptions()
        for sub in subs:
            try:
                matched = await JobService.get_unsent_jobs_for_user(
                    user_id=sub["user_id"],
                    keywords=sub["keywords"],
                    min_salary=sub["min_salary"],
                    limit=3,
                )
                for job in matched:
                    try:
                        await bot.send_message(
                            chat_id=sub["user_id"],
                            text=(
                                f"<b>{job['title']}</b> в {job['company']}\n"
                                f"{job['source_url']}"
                            ),
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                        )
                        await JobService.mark_sent(
                            user_id=sub["user_id"], job_id=str(job["id"])
                        )
                        await asyncio.sleep(0.5)
                    except Exception as exc:
                        logger.error("Ошибка отправки %s: %s", sub["user_id"], exc)
            except Exception as exc:
                logger.error("Ошибка рассылки для %s: %s", sub["user_id"], exc)

    logger.info("Воркер завершил цикл")


async def main():
    """Запуск планировщика воркера."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        minutes=15,
        next_run_time=datetime.now(),
    )
    scheduler.start()
    logger.info("Планировщик запущен (интервал 15 минут)")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
