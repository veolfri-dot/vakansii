import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com")
DB_PATH = os.getenv("DB_PATH", "jobs.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DEFAULT_FILTER_LIMIT = 50
