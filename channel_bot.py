#!/usr/bin/env python3
"""
Telegram Channel Bot for Junior/Middle Remote IT Jobs
VERSION 6.0 - С улучшенными источниками, классификацией и форматированием

Новые возможности:
- 10 Telegram-каналов в качестве источников (Telethon)
- Автоматическая классификация по 7+ категориям
- MarkdownV2 форматирование с inline-кнопками
- Избранное и настройки пользователей
"""
import os
import time
import random
import aiosqlite
import hashlib
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import signal
import asyncio
import re
import aiohttp
import feedparser
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, filters, ConversationHandler
)

# Import onboarding module
try:
    from onboarding import (
        get_onboarding_manager, OnboardingStep,
        LEVEL_OPTIONS, CATEGORY_OPTIONS, WORK_FORMAT_OPTIONS,
        TECHNOLOGY_OPTIONS, FREQUENCY_OPTIONS,
        format_user_preferences
    )
    ONBOARDING_AVAILABLE = True
except ImportError:
    ONBOARDING_AVAILABLE = False
    logging.warning("⚠️ onboarding module not found, onboarding flow disabled")
from telegram.error import RetryAfter, TimedOut
from telegram.constants import ParseMode
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Импорт новых модулей (с fallback)
try:
    from job_classifier import JobClassifier, get_job_category_info
    CLASSIFIER_AVAILABLE = True
except ImportError:
    CLASSIFIER_AVAILABLE = False
    logging.warning("⚠️ job_classifier не найден, классификация отключена")

try:
    from telegram_job_parser import TelegramJobParser, fetch_telegram_jobs
    TELEGRAM_PARSER_AVAILABLE = True
except ImportError:
    TELEGRAM_PARSER_AVAILABLE = False
    logging.warning("⚠️ telegram_job_parser не найден, Telegram-каналы отключены")

try:
    from message_formatter import JobMessageFormatter, format_job_message
    FORMATTER_AVAILABLE = True
except ImportError:
    FORMATTER_AVAILABLE = False
    logging.warning("⚠️ message_formatter не найден, используется стандартное форматирование")

try:
    from smart_matching import SmartMatcher, create_user_profile, get_recommendations
    SMART_MATCHING_AVAILABLE = True
except ImportError:
    SMART_MATCHING_AVAILABLE = False
    logging.warning("⚠️ smart_matching не найден, Smart Matching отключен")

try:
    from salary_analyzer import SalaryAnalyzer, get_category_name_ru
    SALARY_ANALYZER_AVAILABLE = True
except ImportError:
    SALARY_ANALYZER_AVAILABLE = False
    logging.warning("⚠️ salary_analyzer не найден, Salary Insights отключен")

# ==================== CONFIGURATION ====================
class Config:
    """Application configuration with validation"""
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    CHANNEL_ID = os.getenv('CHANNEL_ID', '')
    SUPERJOB_API_KEY = os.getenv('SUPERJOB_API_KEY')
    ADZUNA_APP_ID = os.getenv('ADZUNA_APP_ID')
    ADZUNA_APP_KEY = os.getenv('ADZUNA_APP_KEY')
    TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
    TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '1800'))
    MAX_POSTS_PER_CYCLE = int(os.getenv('MAX_POSTS_PER_CYCLE', '15'))
    ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
    ENABLE_TELEGRAM_CHANNELS = os.getenv('ENABLE_TELEGRAM_CHANNELS', 'true').lower() == 'true'
    ENABLE_MARKDOWN_V2 = os.getenv('ENABLE_MARKDOWN_V2', 'true').lower() == 'true'

    @classmethod
    def validate(cls) -> bool:
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("❌ TELEGRAM_BOT_TOKEN is required")
        if not cls.CHANNEL_ID:
            errors.append("❌ CHANNEL_ID is required")
        if cls.CHANNEL_ID and not (cls.CHANNEL_ID.startswith('@') or cls.CHANNEL_ID.startswith('-')):
            errors.append(f"❌ CHANNEL_ID should start with '@' or '-', got: {cls.CHANNEL_ID}")

        # Validate ADMIN_USER_ID
        if cls.ADMIN_USER_ID:
            try:
                cls.ADMIN_USER_ID = int(cls.ADMIN_USER_ID)
            except ValueError:
                errors.append("❌ ADMIN_USER_ID must be numeric")
                cls.ADMIN_USER_ID = None

        if errors:
            for err in errors:
                print(err)
            return False
        return True

if not Config.validate():
    sys.exit(1)

# ==================== LOGGING SETUP ====================
def setup_logger():
    """Setup structured logging to console and file"""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_file = os.getenv('LOG_FILE', 'bot.log')

    # Create logs directory
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(__name__)
    logger.setLevel(getattr(logging, log_level))

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()

# ==================== CONSTANTS ====================
DELAYS = {
    'between_apis': 5,
    'random_jitter': 2,
    'after_error': 30,
    'between_posts': 3
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
]

JUNIOR_SIGNALS = [
    "junior", "jr", "jr.", "entry level", "entry-level", "entry",
    "trainee", "graduate", "начинающий", "начальный",
    "0-1 year", "0-2 years", "1 year", "1+ year", "1-2 years",
    "no experience", "без опыта", "beginner"
]

MIDDLE_SIGNALS = [
    "middle", "mid-level", "mid level", "intermediate",
    "2-3 years", "2-4 years", "3-5 years", "2+ years", "3+ years"
]

EXCLUDE_SIGNALS = [
    "senior", "sr.", "sr ", "lead", "principal", "staff engineer",
    "architect", "head of", "director", "manager", "vp",
    "vice president", "cto", "cfo", "chief", "c-level",
    "старший", "ведущий", "руководитель", "главный"
]

IT_ROLES = [
    "developer", "engineer", "programmer", "designer", "qa", "tester",
    "analyst", "frontend", "backend", "full-stack", "fullstack",
    "devops", "product manager", "data scientist", "data analyst",
    "mobile", "ios", "android", "react", "vue", "angular",
    "python", "javascript", "java", "php", "ruby", "go", "rust",
    "node", "web developer", "software", "support engineer",
    "разработчик", "программист", "инженер", "тестировщик",
    "менеджер проекта", "product owner", "scrum master"
]

REMOTE_KEYWORDS = ["remote", "удаленно", "удалённо", "work from home", "дистанционно", "wfh"]

TECH_STACK = [
    'Python', 'JavaScript', 'TypeScript', 'React', 'Vue', 'Angular',
    'Node.js', 'Django', 'Flask', 'FastAPI', 'Express', 'Next.js',
    'PostgreSQL', 'MongoDB', 'MySQL', 'Redis', 'SQLite',
    'Docker', 'Kubernetes', 'AWS', 'Azure', 'GCP',
    'Git', 'CI/CD', 'REST API', 'GraphQL',
    'HTML', 'CSS', 'SASS', 'Tailwind',
    'Figma', 'Sketch',
    'Java', 'C#', 'Go', 'Rust', 'PHP', 'Ruby', 'Swift', 'Kotlin'
]

# RSS Feeds для парсинга
RSS_FEEDS = {
    "remotive": "https://remotive.com/feed",
    "weworkremotely": "https://weworkremotely.com/remote-jobs.rss",
    "remoteok": "https://remoteok.io/remote-jobs.rss",
    "himalayas": "https://himalayas.app/jobs/rss",
    "jobicy_rss": "https://jobicy.com/?feed=job_feed",
}

CATEGORY_NAMES_RU = {
    'development': 'Разработка',
    'qa': 'QA',
    'devops': 'DevOps',
    'data': 'Данные',
    'marketing': 'Маркетинг',
    'sales': 'Продажи',
    'pm': 'Менеджмент',
    'design': 'Дизайн',
    'support': 'Поддержка',
    'security': 'Безопасность',
    'other': 'Другое',
}

# ==================== CIRCUIT BREAKER ====================
class CircuitBreaker:
    """Circuit breaker to prevent cascade failures"""
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._state = "closed"
        self._lock = asyncio.Lock()
        self._last_failure_time = None

    async def call(self, func, *args, **kwargs):
        async with self._lock:
            if self._state == "open":
                # Check if we should try to recover
                if self._last_failure_time and (time.time() - self._last_failure_time) > self.recovery_timeout:
                    self._state = "half-open"
                    logger.info("🔄 Circuit breaker entering half-open state")
                else:
                    raise Exception(f"Circuit breaker OPEN for {func.__name__}")

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                self._failure_count = 0
                if self._state == "half-open":
                    self._state = "closed"
                    logger.info("✅ Circuit breaker closed")
            return result
        except Exception as e:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()
                if self._failure_count >= self.failure_threshold:
                    self._state = "open"
                    logger.error(f"🔴 Circuit breaker OPEN for {func.__name__}")
            raise

# Create circuit breakers for each API
CIRCUIT_BREAKERS = {
    'remotive': CircuitBreaker(),
    'remoteok': CircuitBreaker(),
    'arbeitnow': CircuitBreaker(),
    'himalayas': CircuitBreaker(),
    'weworkremotely': CircuitBreaker(),
    'jobicy': CircuitBreaker(failure_threshold=5, recovery_timeout=60),
    'adzuna': CircuitBreaker(),
    'headhunter': CircuitBreaker(),
    'superjob': CircuitBreaker(),
    # RSS feed circuit breakers (мягче - RSS чаще недоступен)
    'rss_remotive': CircuitBreaker(failure_threshold=3, recovery_timeout=30),
    'rss_weworkremotely': CircuitBreaker(failure_threshold=3, recovery_timeout=30),
    'rss_remoteok': CircuitBreaker(failure_threshold=3, recovery_timeout=30),
    'rss_himalayas': CircuitBreaker(failure_threshold=3, recovery_timeout=30),
}

# ==================== DATABASE ====================
class DatabaseConnection:
    """Async SQLite database connection with enhanced schema"""
    def __init__(self, db_path: str = 'jobs.db'):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database schema with migrations"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                # Main jobs table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS posted_jobs (
                        hash TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        company TEXT NOT NULL,
                        level TEXT,
                        url TEXT,
                        source TEXT,
                        category TEXT DEFAULT 'other',
                        posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # User favorites
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS user_favorites (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        job_hash TEXT NOT NULL,
                        saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, job_hash)
                    )
                """)

                # User settings
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INTEGER PRIMARY KEY,
                        enabled_categories TEXT DEFAULT 'development,qa,devops,data,marketing,sales,pm,design,other',
                        hide_senior BOOLEAN DEFAULT 1,
                        min_salary_filter INTEGER DEFAULT 0,
                        level_preference TEXT DEFAULT 'both',
                        work_format TEXT DEFAULT 'remote',
                        technologies TEXT DEFAULT '',
                        notification_frequency TEXT DEFAULT 'instant',
                        onboarding_completed BOOLEAN DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Telegram content hashes for dedup
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS telegram_content_hashes (
                        hash TEXT PRIMARY KEY,
                        source TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Indexes
                await db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_category ON posted_jobs(category)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON posted_jobs(posted_at)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user ON user_favorites(user_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_tg_hashes_created ON telegram_content_hashes(created_at)")

                # Migration: add category if not exists
                try:
                    await db.execute("SELECT category FROM posted_jobs LIMIT 1")
                except aiosqlite.OperationalError:
                    await db.execute("ALTER TABLE posted_jobs ADD COLUMN category TEXT DEFAULT 'other'")

                # Migrations for user_settings new fields
                for column, col_type in [
                    ('level_preference', 'TEXT DEFAULT \'both\''),
                    ('work_format', 'TEXT DEFAULT \'remote\''),
                    ('technologies', 'TEXT DEFAULT \'\''),
                    ('notification_frequency', 'TEXT DEFAULT \'instant\''),
                    ('onboarding_completed', 'BOOLEAN DEFAULT 0'),
                ]:
                    try:
                        await db.execute(f"SELECT {column} FROM user_settings LIMIT 1")
                    except aiosqlite.OperationalError:
                        await db.execute(f"ALTER TABLE user_settings ADD COLUMN {column} {col_type}")
                        logger.info(f"✅ Added column {column} to user_settings")

                await db.commit()

        logger.info("✅ Database initialized")

    async def execute(self, query: str, params: tuple = ()):
        """Execute query with commit"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(query, params)
                await db.commit()
                return cursor

    async def fetchone(self, query: str, params: tuple = ()):
        """Execute query and fetch one row"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(query, params)
                return await cursor.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        """Execute query and fetch all rows"""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(query, params)
                return await cursor.fetchall()

    async def close(self):
        """Close database connection"""
        logger.info("🔌 Database connection closed")

    # User favorites methods
    async def add_favorite(self, user_id: int, job_hash: str) -> bool:
        """Add job to user favorites"""
        try:
            await self.execute(
                'INSERT OR IGNORE INTO user_favorites (user_id, job_hash) VALUES (?, ?)',
                (user_id, job_hash)
            )
            return True
        except Exception as e:
            logger.error(f"Error adding favorite: {e}")
            return False

    async def remove_favorite(self, user_id: int, job_hash: str) -> bool:
        """Remove job from user favorites"""
        try:
            await self.execute(
                'DELETE FROM user_favorites WHERE user_id = ? AND job_hash = ?',
                (user_id, job_hash)
            )
            return True
        except Exception as e:
            logger.error(f"Error removing favorite: {e}")
            return False

    async def get_user_favorites(self, user_id: int) -> List[Dict]:
        """Get user's favorite jobs"""
        results = await self.fetchall("""
            SELECT j.hash, j.title, j.company, j.level, j.category, j.url
            FROM user_favorites f
            JOIN posted_jobs j ON f.job_hash = j.hash
            WHERE f.user_id = ?
            ORDER BY f.saved_at DESC
        """, (user_id,))

        return [
            {
                'hash': row[0],
                'title': row[1],
                'company': row[2],
                'level': row[3],
                'category': row[4],
                'url': row[5],
            }
            for row in results
        ]

    # User settings methods
    async def get_user_settings(self, user_id: int) -> Dict:
        """Get user settings"""
        result = await self.fetchone(
            'SELECT enabled_categories, hide_senior, min_salary_filter, level_preference, work_format, technologies, notification_frequency, onboarding_completed FROM user_settings WHERE user_id = ?',
            (user_id,)
        )

        if result:
            return {
                'enabled_categories': result[0].split(',') if result[0] else list(CATEGORY_NAMES_RU.keys()),
                'hide_senior': bool(result[1]),
                'min_salary_filter': result[2],
                'level_preference': result[3] or 'both',
                'work_format': result[4] or 'remote',
                'technologies': result[5].split(',') if result[5] else [],
                'notification_frequency': result[6] or 'instant',
                'onboarding_completed': bool(result[7]),
            }

        # Default settings
        return {
            'enabled_categories': list(CATEGORY_NAMES_RU.keys()),
            'hide_senior': True,
            'min_salary_filter': 0,
            'level_preference': 'both',
            'work_format': 'remote',
            'technologies': [],
            'notification_frequency': 'instant',
            'onboarding_completed': False,
        }

    async def save_user_onboarding(self, user_id: int, level: str, categories: List[str], 
                                   work_format: str, technologies: List[str], 
                                   frequency: str) -> bool:
        """Save user onboarding preferences"""
        try:
            await self.execute("""
                INSERT OR REPLACE INTO user_settings 
                (user_id, enabled_categories, level_preference, work_format, technologies, 
                 notification_frequency, onboarding_completed, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            """, (
                user_id,
                ','.join(categories),
                level,
                work_format,
                ','.join(technologies),
                frequency
            ))
            return True
        except Exception as e:
            logger.error(f"Error saving onboarding: {e}")
            return False

    async def update_notification_frequency(self, user_id: int, frequency: str) -> bool:
        """Update user notification frequency"""
        try:
            await self.execute("""
                INSERT OR REPLACE INTO user_settings 
                (user_id, notification_frequency, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                notification_frequency = excluded.notification_frequency,
                updated_at = CURRENT_TIMESTAMP
            """, (user_id, frequency))
            return True
        except Exception as e:
            logger.error(f"Error updating frequency: {e}")
            return False

    async def get_today_stats(self) -> Dict:
        """Get today's job posting statistics"""
        from datetime import datetime, timedelta
        today = datetime.now().strftime('%Y-%m-%d')
        hour_ago = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Total today
        result = await self.fetchone(
            "SELECT COUNT(*) FROM posted_jobs WHERE date(posted_at) = ?",
            (today,)
        )
        total_today = result[0] if result else 0
        
        # Hot jobs (posted within last hour)
        result = await self.fetchone(
            "SELECT COUNT(*) FROM posted_jobs WHERE posted_at >= ?",
            (hour_ago,)
        )
        hot_count = result[0] if result else 0
        
        return {
            'total_today': total_today,
            'hot_count': hot_count,
            'new_hour_count': hot_count
        }

    async def update_user_categories(self, user_id: int, categories: List[str]) -> bool:
        """Update user's enabled categories"""
        try:
            await self.execute("""
                INSERT OR REPLACE INTO user_settings (user_id, enabled_categories, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (user_id, ','.join(categories)))
            return True
        except Exception as e:
            logger.error(f"Error updating categories: {e}")
            return False

    async def hide_category_for_user(self, user_id: int, category: str) -> bool:
        """Hide category for user"""
        settings = await self.get_user_settings(user_id)
        enabled = [c for c in settings['enabled_categories'] if c != category]
        return await self.update_user_categories(user_id, enabled)


async def init_database() -> DatabaseConnection:
    """Initialize and return database connection"""
    db = DatabaseConnection()
    await db.initialize()
    return db


def generate_job_hash(job: Dict) -> str:
    """Generate robust hash using URL (primary) or title+company (fallback)"""
    url = job.get('url', '').strip()
    if url:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    title = job.get('title', '').lower()
    company = job.get('company', '').lower()
    return hashlib.md5(f"{title}_{company}".encode()).hexdigest()


async def is_duplicate_job(job: Dict, db: DatabaseConnection) -> bool:
    """Check and register job deduplication with cleanup"""
    # Cleanup old records (>7 days)
    cleanup_threshold = datetime.now() - timedelta(days=7)
    await db.execute('DELETE FROM posted_jobs WHERE posted_at < ?', (cleanup_threshold,))

    job_hash = generate_job_hash(job)
    job['hash'] = job_hash  # Сохраняем hash в job для дальнейшего использования

    # Check if exists
    result = await db.fetchone('SELECT 1 FROM posted_jobs WHERE hash = ?', (job_hash,))
    if result:
        logger.debug(f"⏭️ Duplicate skipped: {job.get('title', 'N/A')}")
        return True

    # Register new job
    await db.execute(
        'INSERT INTO posted_jobs (hash, title, company, level, url, source, category) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (
            job_hash,
            job.get('title', ''),
            job.get('company', ''),
            job.get('level', 'Junior'),
            job.get('url', ''),
            job.get('source', ''),
            job.get('category', 'other')
        )
    )
    logger.debug(f"💾 Saved new job: {job.get('title', 'N/A')}")
    return False

# ==================== UTILS ====================
def get_headers() -> Dict[str, str]:
    return {"User-Agent": random.choice(USER_AGENTS)}


def escape_html(text: str) -> str:
    """Escape HTML special characters safely"""
    if not text:
        return ''
    return (
        text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
    )


async def safe_fetch_with_retry(fetch_func, source_name: str, max_retries: int = 3) -> List[Dict]:
    """Async retry wrapper with exponential backoff and circuit breaker"""
    circuit_breaker = CIRCUIT_BREAKERS.get(source_name.lower().replace(' ', ''), CircuitBreaker())
    
    for attempt in range(max_retries):
        try:
            result = await circuit_breaker.call(fetch_func)
            await asyncio.sleep(DELAYS['between_apis'] + random.uniform(0, DELAYS['random_jitter']))
            return result
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                wait = int(e.headers.get('Retry-After', 60))
                logger.warning(f"⏳ {source_name} rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(wait)
            else:
                logger.error(f"❌ {source_name} HTTP error {e.status}")
                break
        except Exception as e:
            logger.error(f"❌ {source_name} error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(DELAYS['after_error'] * (attempt + 1))
    return []

# ==================== JOB PROCESSING ====================
def classify_job_level(job_data: Dict) -> Optional[str]:
    """Classify job level with exclusion logic"""
    full_text = f"{job_data.get('title', '')} {job_data.get('description', '')}".lower()

    # Exclude senior+ roles first
    if any(word in full_text for word in EXCLUDE_SIGNALS):
        return None

    if any(signal in full_text for signal in JUNIOR_SIGNALS):
        return "Junior"
    if any(signal in full_text for signal in MIDDLE_SIGNALS):
        return "Middle"
    if any(role in full_text for role in IT_ROLES):
        return "Junior"
    return None


def auto_classify_category(job: Dict) -> str:
    """Автоматическая классификация категории"""
    if CLASSIFIER_AVAILABLE:
        try:
            classifier = JobClassifier()
            return classifier.classify(job)
        except Exception as e:
            logger.error(f"Error classifying job: {e}")
    return 'other'


def extract_salary(job: Dict) -> str:
    """Extract and format salary"""
    salary_raw = job.get('salary', '')
    if salary_raw and salary_raw not in ['', 'Not specified', 'Не указана']:
        return salary_raw

    min_sal = job.get('minSalary', 0) or job.get('salary_min', 0)
    max_sal = job.get('maxSalary', 0) or job.get('salary_max', 0)
    if min_sal and max_sal and (min_sal > 0 or max_sal > 0):
        currency = job.get('currency', 'USD')
        if min_sal > 0 and max_sal > 0:
            return f"${min_sal:,}-${max_sal:,} {currency}"
        elif max_sal > 0:
            return f"до ${max_sal:,} {currency}"
    return 'Не указана'


def extract_skills(job: Dict) -> List[str]:
    """Extract skills from tags and description"""
    skills = set()
    tags = job.get('tags', [])
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and len(tag) < 25:
                skills.add(tag.strip().title())

    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    for tech in TECH_STACK:
        if tech.lower() in text:
            skills.add(tech)

    return sorted(list(skills))[:5]


def extract_posted_date(job: Dict) -> str:
    """Extract and format publication date"""
    date_raw = job.get('published') or job.get('created') or job.get('publication_date') or job.get('date_published')
    if not date_raw:
        return "Недавно"

    try:
        dt = datetime.fromisoformat(str(date_raw).replace('Z', '+00:00'))
        months_ru = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
        return f"{dt.day} {months_ru[dt.month-1]}"
    except:
        try:
            dt = datetime.strptime(str(date_raw)[:10], '%Y-%m-%d')
            months_ru = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
            return f"{dt.day} {months_ru[dt.month-1]}"
        except:
            return "Недавно"


def extract_employment_type(job: Dict) -> str:
    """Extract employment type"""
    emp = job.get('employment_type', '') or job.get('type', '') or job.get('job_type', '') or job.get('contract_type', '')
    emp_lower = str(emp).lower()
    if 'full' in emp_lower or 'полная' in emp_lower:
        return "⏰ Полная"
    elif 'part' in emp_lower or 'частичная' in emp_lower:
        return "⏱ Частичная"
    elif 'contract' in emp_lower or 'контракт' in emp_lower:
        return "📝 Контракт"
    elif emp:
        return f"⏰ {emp}"
    return "⏰ Не указана"


def extract_description(job: Dict, max_length: int = 350) -> str:
    """Extract and sanitize description"""
    desc = job.get('description', '')
    desc = re.sub(r'<[^>]+>', '', desc)
    desc = ' '.join(desc.split())
    if len(desc) > max_length:
        desc = desc[:max_length].rsplit(' ', 1)[0] + '...'
    return desc or "Описание не указано"


def is_suitable_job(job: Dict) -> bool:
    """Check if job matches criteria (remote + IT role)"""
    text = f"{job['title']} {job.get('description', '')}".lower()
    has_remote = any(kw in text for kw in REMOTE_KEYWORDS)
    has_it_role = any(role in text for role in IT_ROLES)
    return has_remote and has_it_role


def format_job_message_legacy(job: Dict) -> str:
    """Legacy HTML formatter (fallback)"""
    level = job.get('level', 'Junior')
    emoji = "🟢" if level == "Junior" else "🟡" if level == "Middle" else "🔵"
    salary = extract_salary(job)
    skills = extract_skills(job)
    posted_date = extract_posted_date(job)
    employment = extract_employment_type(job)
    description = extract_description(job)

    title = escape_html(job['title'])
    company = escape_html(job['company'])
    location = escape_html(job.get('location', 'Remote'))
    source = escape_html(job['source'])
    category = job.get('category', 'other')
    cat_emoji = {'development': '💻', 'qa': '🧪', 'devops': '🔧', 'data': '📊',
                 'marketing': '📢', 'sales': '💼', 'pm': '📋', 'design': '🎨'}.get(category, '📌')

    url = job.get('url', '').strip()
    if not url or not url.startswith('http'):
        url = 'https://example.com'

    parts = [
        f"{cat_emoji} <b>{title}</b>",
        "",
        f"🏢 <b>Компания:</b> {company}",
        f"📍 <b>Локация:</b> {location}",
        f"💵 <b>Зарплата:</b> {salary}",
        f"🎯 <b>Уровень:</b> {level}",
        f"📅 <b>Дата:</b> {posted_date} | {employment}",
        "",
        f"📋 <b>Описание:</b>",
        description,
        "",
        "<b>🛠 Навыки:</b>"
    ]

    if skills:
        for skill in skills:
            parts.append(f"  • {escape_html(skill)}")
    else:
        parts.append("  Не указаны")

    parts.extend([
        "",
        f"🔗 <a href=\"{url}\">Откликнуться на вакансию</a>",
        f"📌 Источник: {source}"
    ])

    message = "\n".join(parts)

    if len(message) > 4096:
        message = message[:4090] + "...\n<i>(сообщение сокращено)</i>"

    return message

# ==================== API FETCHERS ====================
async def fetch_remotive() -> List[Dict]:
    """Remotive API - 100% remote"""
    try:
        url = "https://remotive.com/api/remote-jobs?category=software-dev"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as response:
                response.raise_for_status()
                data = await response.json()
                
                jobs = []
                for job in data.get('jobs', []):
                    jobs.append({
                        'title': job.get('title', ''),
                        'company': job.get('company_name', ''),
                        'description': job.get('description', ''),
                        'url': job.get('url', ''),
                        'salary': job.get('salary', ''),
                        'location': job.get('candidate_required_location', 'Remote'),
                        'published': job.get('publication_date', ''),
                        'employment_type': job.get('job_type', ''),
                        'source': 'Remotive',
                        'tags': job.get('tags', [])
                    })
                
                return jobs
    except Exception as e:
        logger.error(f"❌ Remotive error: {e}")
        return []


async def fetch_remoteok() -> List[Dict]:
    """RemoteOK API"""
    try:
        url = "https://remoteok.com/api"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as response:
                response.raise_for_status()
                data = await response.json()
                
                jobs = []
                for job in data[1:]:
                    jobs.append({
                        'title': job.get('position', ''),
                        'company': job.get('company', ''),
                        'description': job.get('description', ''),
                        'url': job.get('url', ''),
                        'salary': job.get('salary', ''),
                        'location': job.get('location', 'Remote'),
                        'published': job.get('date', ''),
                        'employment_type': job.get('position_type', ''),
                        'source': 'RemoteOK',
                        'tags': job.get('tags', [])
                    })
                
                return jobs
    except Exception as e:
        logger.error(f"❌ RemoteOK error: {e}")
        return []


async def fetch_arbeitnow() -> List[Dict]:
    """Arbeitnow API"""
    try:
        url = "https://www.arbeitnow.com/api/job-board-api"
        params = {'page': 1, 'limit': 50, 'tags': 'it,software,developer,engineer'}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as response:
                response.raise_for_status()
                data = await response.json()
                
                jobs = []
                for job in data.get('data', []):
                    salary = 'Не указана'
                    if job.get('salary_min') and job.get('salary_max'):
                        salary = f"${job['salary_min']:,}-${job['salary_max']:}"
                    elif job.get('salary_min'):
                        salary = f"от ${job['salary_min']:,}"
                    
                    jobs.append({
                        'title': job.get('title', ''),
                        'company': job.get('company_name', ''),
                        'description': job.get('description', ''),
                        'url': job.get('url', ''),
                        'salary': salary,
                        'location': job.get('location', 'Remote'),
                        'published': job.get('created_at', ''),
                        'employment_type': job.get('employment_type', ''),
                        'source': 'Arbeitnow',
                        'tags': job.get('tags', [])
                    })
                
                return jobs
    except Exception as e:
        logger.error(f"❌ Arbeitnow error: {e}")
        return []


async def fetch_himalayas() -> List[Dict]:
    """Himalayas API"""
    try:
        url = "https://himalayas.app/api/v1/jobs"
        params = {'limit': 30, 'remote': 'true'}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as response:
                response.raise_for_status()
                data = await response.json()
                
                jobs = []
                for job in data.get('jobs', []):
                    salary = 'Не указана'
                    if job.get('minSalary') and job.get('maxSalary'):
                        currency = job.get('salaryCurrency', 'USD')
                        salary = f"{job['minSalary']:,}-{job['maxSalary']:,} {currency}"
                    
                    jobs.append({
                        'title': job.get('title', ''),
                        'company': job.get('company', {}).get('name', ''),
                        'description': job.get('description', ''),
                        'url': job.get('applicationUrl', ''),
                        'salary': salary,
                        'location': 'Remote',
                        'published': job.get('createdAt', ''),
                        'employment_type': job.get('employmentType', ''),
                        'source': 'Himalayas',
                        'tags': job.get('tags', [])
                    })
                
                return jobs
    except Exception as e:
        logger.error(f"❌ Himalayas error: {e}")
        return []


async def fetch_weworkremotely() -> List[Dict]:
    """We Work Remotely JSON API"""
    try:
        url = "https://weworkremotely.com/remote-jobs.json"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as response:
                response.raise_for_status()
                data = await response.json()
                
                jobs = []
                for job in data.get('jobs', [])[:20]:
                    jobs.append({
                        'title': job.get('title', ''),
                        'company': job.get('company', {}).get('name', ''),
                        'description': job.get('description', ''),
                        'url': f"https://weworkremotely.com{job.get('url', '')}",
                        'salary': 'Не указана',
                        'location': 'Remote',
                        'published': job.get('date', ''),
                        'employment_type': '',
                        'source': 'We Work Remotely',
                        'tags': []
                    })
                
                return jobs
    except Exception as e:
        logger.error(f"❌ We Work Remotely error: {e}")
        return []


async def fetch_jobicy(count: int = 50, geo: str = None, industry: str = None) -> List[Dict]:
    """Jobicy API - remote jobs with improved field mapping"""
    try:
        base_url = "https://jobicy.com/api/v2/remote-jobs"
        params = {"count": min(count, 100)}
        if geo:
            params["geo"] = geo
        if industry:
            params["industry"] = industry
        
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params, headers=get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as response:
                response.raise_for_status()
                data = await response.json()
                
                jobs = []
                for job in data.get("jobs", []):
                    jobs.append({
                        "title": job.get("jobTitle", ""),
                        "company": job.get("companyName", ""),
                        "description": job.get("jobDescription", ""),
                        "url": job.get("url", ""),
                        "salary": job.get("salary", ""),
                        "location": job.get("jobGeo", "Remote"),
                        "published": job.get("pubDate", ""),
                        "employment_type": job.get("jobType", ""),
                        "source": "Jobicy",
                        "tags": job.get("tags", []),
                    })
                return jobs
    except Exception as e:
        logger.error(f"Jobicy error: {e}")
        return []


def extract_company_from_title(title: str) -> str:
    """Extract company name from job title (common RSS pattern: 'Job Title at Company')"""
    if not title:
        return "Unknown"
    
    # Common patterns: "at Company", "@ Company", "- Company", "| Company"
    patterns = [
        r'\s+at\s+(.+)$',
        r'\s+@\s+(.+)$', 
        r'\s+[-|]\s+(.+)$',
        r'\s+\(([^)]+)\)$',  # Company in parentheses
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return "Unknown"


async def parse_rss_feed(feed_url: str, source_name: str) -> List[Dict]:
    """Parse RSS feed for job listings"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(feed_url, headers=get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    content = await response.text()
                    feed = feedparser.parse(content)
                    
                    jobs = []
                    for entry in feed.entries[:20]:  # Берём последние 20
                        job = {
                            "title": entry.get("title", ""),
                            "company": extract_company_from_title(entry.get("title", "")),
                            "description": entry.get("description", ""),
                            "url": entry.get("link", ""),
                            "published": entry.get("published", ""),
                            "source": source_name,
                            "tags": [],
                        }
                        jobs.append(job)
                    return jobs
                return []
    except Exception as e:
        logger.error(f"RSS {source_name} error: {e}")
        return []


async def fetch_adzuna() -> List[Dict]:
    """Adzuna API"""
    try:
        if not Config.ADZUNA_APP_ID or not Config.ADZUNA_APP_KEY:
            logger.warning("⚠️ Adzuna API keys not found, skipping")
            return []
        
        countries = ['us', 'gb']
        all_jobs = []
        
        async with aiohttp.ClientSession() as session:
            for country in countries:
                try:
                    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
                    params = {
                        'app_id': Config.ADZUNA_APP_ID,
                        'app_key': Config.ADZUNA_APP_KEY,
                        'results_per_page': 30,
                        'what': 'developer programmer engineer',
                        'where': 'remote',
                        'sort_by': 'date'
                    }
                    
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        response.raise_for_status()
                        data = await response.json()
                        
                        for job in data.get('results', []):
                            salary = 'Не указана'
                            if job.get('salary_min') and job.get('salary_max'):
                                salary = f"${job['salary_min']:,.0f}-${job['salary_max']:,.0f}"
                            elif job.get('salary_min'):
                                salary = f"от ${job['salary_min']:,.0f}"
                            
                            all_jobs.append({
                                'title': job.get('title', ''),
                                'company': job.get('company', {}).get('display_name', ''),
                                'description': job.get('description', ''),
                                'url': job.get('redirect_url', ''),
                                'salary': salary,
                                'location': job.get('location', {}).get('display_name', 'Remote'),
                                'published': job.get('created', ''),
                                'employment_type': job.get('contract_type', ''),
                                'source': 'Adzuna',
                                'tags': []
                            })
                    
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"❌ Adzuna {country} error: {e}")
                    continue
        
        return all_jobs
    except Exception as e:
        logger.error(f"❌ Adzuna general error: {e}")
        return []


async def fetch_headhunter() -> List[Dict]:
    """HeadHunter API"""
    try:
        url = "https://api.hh.ru/vacancies"
        params = {
            'text': 'программист разработчик developer remote удалённо',
            'per_page': 50,
            'page': 0,
            'schedule': 'remote'
        }
        
        headers = get_headers()
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                response.raise_for_status()
                data = await response.json()
                
                jobs = []
                for item in data.get('items', []):
                    salary_info = item.get('salary')
                    salary = 'Не указана'
                    
                    if salary_info:
                        currency = salary_info.get('currency', 'RUB')
                        if salary_info.get('from') and salary_info.get('to'):
                            salary = f"{salary_info['from']:,}-{salary_info['to']:,} {currency}"
                        elif salary_info.get('from'):
                            salary = f"от {salary_info['from']:,} {currency}"
                        elif salary_info.get('to'):
                            salary = f"до {salary_info['to']:,} {currency}"
                    
                    snippet = item.get('snippet', {})
                    description = f"{snippet.get('requirement', '')} {snippet.get('responsibility', '')}"
                    
                    employment = item.get('employment', {})
                    employment_name = employment.get('name', '') if isinstance(employment, dict) else ''
                    
                    jobs.append({
                        'title': item.get('name', ''),
                        'company': item.get('employer', {}).get('name', ''),
                        'description': description,
                        'url': item.get('alternate_url', ''),
                        'salary': salary,
                        'location': item.get('area', {}).get('name', 'Удалённо'),
                        'published': item.get('published_at', ''),
                        'employment_type': employment_name,
                        'source': 'HeadHunter',
                        'tags': []
                    })
                
                return jobs
    except Exception as e:
        logger.error(f"❌ HeadHunter error: {e}")
        return []


async def fetch_superjob() -> List[Dict]:
    """SuperJob API"""
    try:
        if not Config.SUPERJOB_API_KEY:
            logger.warning("⚠️ SuperJob API key not found, skipping")
            return []
        
        url = "https://api.superjob.ru/2.0/vacancies/"
        headers = {'X-Api-App-Id': Config.SUPERJOB_API_KEY, **get_headers()}
        params = {'keyword': 'программист разработчик', 'count': 20}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 403:
                    logger.error("❌ SuperJob 403: Check API key in .env")
                    return []
                
                response.raise_for_status()
                data = await response.json()
                
                jobs = []
                for item in data.get('objects', []):
                    salary = 'Не указана'
                    if item.get('payment_from') and item.get('payment_to'):
                        salary = f"{item['payment_from']:,}-{item['payment_to']:,} RUB"
                    elif item.get('payment_from'):
                        salary = f"от {item['payment_from']:,} RUB"
                    
                    employment_type = item.get('type_of_work', {})
                    employment_name = employment_type.get('title', '') if isinstance(employment_type, dict) else ''
                    
                    jobs.append({
                        'title': item.get('profession', ''),
                        'company': item.get('firm_name', ''),
                        'description': item.get('candidat', ''),
                        'url': item.get('link', ''),
                        'salary': salary,
                        'location': 'Удалённо',
                        'published': str(item.get('date_published', '')),
                        'employment_type': employment_name,
                        'source': 'SuperJob',
                        'tags': []
                    })
                
                return jobs
    except Exception as e:
        logger.error(f"❌ SuperJob error: {e}")
        return []


async def fetch_telegram_channels() -> List[Dict]:
    """Fetch jobs from Telegram channels"""
    if not Config.ENABLE_TELEGRAM_CHANNELS:
        return []

    if not TELEGRAM_PARSER_AVAILABLE:
        logger.debug("⚠️ Telegram parser not available")
        return []

    if not Config.TELEGRAM_API_ID or not Config.TELEGRAM_API_HASH:
        logger.debug("⚠️ Telegram API credentials not configured")
        return []

    try:
        # Для cron-запуска используем 1 час, для ручного - 24 часа
        hours_back = 1
        jobs = await fetch_telegram_jobs(hours_back=hours_back)
        logger.info(f"📥 Fetched {len(jobs)} jobs from Telegram channels")
        return jobs
    except Exception as e:
        logger.error(f"❌ Telegram channels error: {e}")
        return []

# ==================== TELEGRAM BOT ====================
class JobBot:
    """Telegram bot with enhanced features"""

    def __init__(self, application: Application, db: DatabaseConnection):
        self.application = application
        self.db = db
        self.is_paused = False
        self.formatter = JobMessageFormatter() if FORMATTER_AVAILABLE else None
        self.classifier = JobClassifier() if CLASSIFIER_AVAILABLE else None

    async def check_admin(self, update: Update) -> bool:
        """Check if user is admin"""
        if not Config.ADMIN_USER_ID:
            return True

        user_id = update.effective_user.id
        if user_id != Config.ADMIN_USER_ID:
            await update.message.reply_text("❌ У вас нет прав для этой команды")
            logger.warning(f"Unauthorized access attempt by user {user_id}")
            return False
        return True

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - Enhanced with stats and onboarding check"""
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        
        # Get user settings to check if onboarding is completed
        settings = await self.db.get_user_settings(user_id)
        
        # If onboarding not completed and onboarding module available, start it
        if not settings.get('onboarding_completed', False) and ONBOARDING_AVAILABLE:
            await self._start_onboarding(update, context)
            return
        
        # Get today's stats
        stats = await self.db.get_today_stats()
        
        # Format user preferences for display
        level_text = LEVEL_OPTIONS.get(settings.get('level_preference', 'both'), {}).get('text', '✅ Оба уровня')
        work_text = WORK_FORMAT_OPTIONS.get(settings.get('work_format', 'remote'), {}).get('text', '🏠 Удалённо')
        
        # Format categories
        categories = settings.get('enabled_categories', [])
        if categories and len(categories) < len(CATEGORY_NAMES_RU):
            cat_emojis = [CATEGORY_EMOJIS.get(c, '📌') for c in categories[:5]]
            cat_text = ' '.join(cat_emojis)
        else:
            cat_text = '💻 Все категории'
        
        welcome_text = (
            f"👋 *Привет, {first_name}!*\n\n"
            f"🚀 *Найди свою идеальную remote-работу в IT*\n\n"
            f"📊 *Сегодня добавлено:*\n"
            f"• Всего вакансий: `{stats['total_today']}`\n"
            f"• 🔥 Горячих: `{stats['hot_count']}`\n"
            f"• ⚡️ Новых за час: `{stats['new_hour_count']}`\n\n"
            f"💡 *Твои настройки:*\n"
            f"• Уровень: {level_text}\n"
            f"• Категории: {cat_text}\n"
            f"• Формат: {work_text}"
        )
        
        start_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Настроить предпочтения", callback_data="settings")],
            [InlineKeyboardButton("🔥 Горячие вакансии", callback_data="hot_jobs"),
             InlineKeyboardButton("⚡️ Новые за час", callback_data="recent_jobs")],
            [InlineKeyboardButton("📊 Зарплатная статистика", callback_data="salary_stats"),
             InlineKeyboardButton("❤️ Избранное", callback_data="favorites")],
        ])

        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=start_keyboard
        )

    async def _start_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start onboarding wizard"""
        if not ONBOARDING_AVAILABLE:
            return
            
        manager = get_onboarding_manager()
        state = manager.reset(update.effective_user.id)
        
        # Step 1: Level selection
        progress = manager.get_progress_text(update.effective_user.id)
        
        level_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Junior (0-2 года)", callback_data="onboard_level_junior")],
            [InlineKeyboardButton("🔵 Middle (2-5 лет)", callback_data="onboard_level_middle")],
            [InlineKeyboardButton("✅ Оба уровня", callback_data="onboard_level_both")],
        ])
        
        message = (
            f"👋 Привет! Давай настроим твой профиль\n\n"
            f"{progress}\n"
            f"*Уровень опыта*\n\n"
            f"Какой уровень вакансий тебе интересен?"
        )
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=level_keyboard
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not await self.check_admin(update):
            return
        
        result = await self.db.fetchone('SELECT COUNT(*) FROM posted_jobs')
        total_posted = result[0] if result else 0
        
        # Count by category
        cat_results = await self.db.fetchall(
            'SELECT category, COUNT(*) FROM posted_jobs GROUP BY category'
        )
        categories = {row[0]: row[1] for row in cat_results}

        stats = {
            'total_jobs': total_posted,
            'total_sources': 9 + (10 if Config.ENABLE_TELEGRAM_CHANNELS else 0),
            'is_paused': self.is_paused,
            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'categories': categories,
        }

        if self.formatter:
            message = self.formatter.format_status_message(stats)
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            message = (
                "📊 <b>Статистика бота:</b>\n\n"
                f"✅ Всего опубликовано: {total_posted}\n"
                f"⏸️ Статус: {'Приостановлен' if self.is_paused else 'Активен'}\n"
                f"🕐 Обновление: {stats['last_update']}"
            )
            await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /last N command"""
        if not await self.check_admin(update):
            return
        
        limit = 5
        if context.args:
            try:
                limit = int(context.args[0])
                limit = max(1, min(limit, 20))
            except ValueError:
                pass
        
        results = await self.db.fetchall(
            'SELECT title, company, level, category, posted_at, source FROM posted_jobs '
            'ORDER BY posted_at DESC LIMIT ?',
            (limit,)
        )

        if not results:
            await update.message.reply_text("📭 Нет опубликованных вакансий")
            return

        jobs = [
            {
                'title': row[0],
                'company': row[1],
                'level': row[2],
                'category': row[3],
            }
            for row in results
        ]

        if self.formatter:
            message = self.formatter.format_job_list(jobs, limit)
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            message = f"🆕 <b>Последние {len(results)} вакансий:</b>\n\n"
            for row in results:
                title, company, level, category, posted_at, source = row
                message += f"• {escape_html(title)}\n  🏢 {escape_html(company)} | 🎯 {level}\n\n"
            await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_favorites(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /favorites command"""
        user_id = update.effective_user.id
        favorites = await self.db.get_user_favorites(user_id)

        if self.formatter:
            message = self.formatter.format_favorites_list(favorites)
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            if not favorites:
                await update.message.reply_text("💾 Список избранного пуст")
            else:
                message = f"💾 <b>Избранное ({len(favorites)}):</b>\n\n"
                for job in favorites[:10]:
                    message += f"• {escape_html(job['title'])}\n  🏢 {escape_html(job['company'])}\n\n"
                await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /categories command"""
        user_id = update.effective_user.id
        settings = await self.db.get_user_settings(user_id)
        enabled = settings['enabled_categories']

        if self.formatter:
            keyboard = self.formatter.create_category_settings_keyboard(enabled)
            await update.message.reply_text(
                "📂 *Настройка категорий:*\n\n"
                "Выберите категории для отображения:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard['inline_keyboard'])
            )
        else:
            cat_list = "\n".join([f"  • {CATEGORY_NAMES_RU.get(c, c)}" for c in enabled])
            await update.message.reply_text(
                f"📂 Активные категории:\n{cat_list}\n\n"
                f"(Детальная настройка доступна с модулем форматирования)"
            )

    async def cmd_recommendations(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /recommendations command - Personal job recommendations"""
        user_id = update.effective_user.id
        
        # Проверяем, есть ли настройки пользователя
        settings = await self.db.get_user_settings(user_id)
        if not settings.get('onboarding_completed'):
            await update.message.reply_text(
                "⚙️ *Сначала настрой профиль!*\n\n"
                "Используй команду /start для настройки предпочтений",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if not SMART_MATCHING_AVAILABLE:
            await update.message.reply_text(
                "😕 *Smart Matching временно недоступен*\n\n"
                "Попробуй позже или используй /search для поиска вакансий",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Показываем, что идёт обработка
        processing_msg = await update.message.reply_text(
            "🔍 *Подбираю вакансии под твой профиль...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # Получаем свежие вакансии (за последние 7 дней)
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            results = await self.db.fetchall(
                'SELECT hash, title, company, level, category, url, description, posted_at '
                'FROM posted_jobs '
                'WHERE date(posted_at) >= ? '
                'ORDER BY posted_at DESC LIMIT 200',
                (week_ago,)
            )
            
            if not results:
                await processing_msg.edit_text(
                    "😕 *Пока нет подходящих вакансий*\n\n"
                    "Попробуй расширить критерии в /settings или проверь позже!",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Преобразуем в список словарей
            recent_jobs = []
            for row in results:
                recent_jobs.append({
                    'hash': row[0],
                    'title': row[1],
                    'company': row[2],
                    'level': row[3],
                    'category': row[4],
                    'url': row[5],
                    'description': row[6] or '',
                    'posted_at': row[7],
                    'tags': []
                })
            
            # Создаём профиль пользователя
            profile = create_user_profile(
                level_preference=settings.get('level_preference', 'both'),
                categories=settings.get('enabled_categories', []),
                technologies=settings.get('technologies', [])
            )
            
            # Фильтруем через Smart Matching
            matcher = SmartMatcher(profile)
            matched_jobs = matcher.filter_and_sort_jobs(recent_jobs, min_score=0.4)
            
            if not matched_jobs:
                await processing_msg.edit_text(
                    "😕 *Пока нет подходящих вакансий*\n\n"
                    "Попробуй расширить критерии в /settings или проверь позже!",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Форматируем результат
            if self.formatter:
                message = self.formatter.format_recommendations(matched_jobs, limit=5)
                await processing_msg.edit_text(
                    message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
            else:
                # Fallback форматирование
                lines = ["🔥 *Подборка для тебя:*\n"]
                for i, job in enumerate(matched_jobs[:5], 1):
                    score = job.get('match_score', 0)
                    emoji = "🟢" if score > 0.7 else "🟡" if score > 0.5 else "🟠"
                    lines.append(
                        f"{i}. {emoji} {job['title']} @ {job['company']} "
                        f"({int(score*100)}%)"
                    )
                await processing_msg.edit_text(
                    '\n'.join(lines),
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
                
        except Exception as e:
            logger.error(f"Error in recommendations: {e}")
            await processing_msg.edit_text(
                "❌ *Ошибка при подборе вакансий*\n\n"
                "Попробуй ещё раз позже",
                parse_mode=ParseMode.MARKDOWN
            )

    async def cmd_salary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /salary command - Salary statistics"""
        args = context.args
        
        if not SALARY_ANALYZER_AVAILABLE:
            await update.message.reply_text(
                "😕 *Salary Insights временно недоступен*\n\n"
                "Попробуй позже",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        analyzer = SalaryAnalyzer(self.db)
        
        if not args:
            # Показываем статистику по всем категориям для Junior/Middle
            message = "💰 *Зарплатная статистика (Junior/Middle, за 30 дней)*\n\n"
            
            categories = ['development', 'qa', 'devops', 'data', 'design']
            has_data = False
            
            for cat in categories:
                junior = await analyzer.get_stats_by_category(cat, 'junior')
                middle = await analyzer.get_stats_by_category(cat, 'middle')
                
                if junior.sample_size > 0 or middle.sample_size > 0:
                    has_data = True
                    cat_name = get_category_name_ru(cat)
                    message += f"📊 *{cat_name}*\n"
                    if junior.sample_size > 0:
                        message += f"  🟢 Junior: ${junior.avg_min:,} - ${junior.avg_max:,} ({junior.sample_size} вак.)\n"
                    if middle.sample_size > 0:
                        message += f"  🔵 Middle: ${middle.avg_min:,} - ${middle.avg_max:,} ({middle.sample_size} вак.)\n"
                    message += "\n"
            
            if not has_data:
                message = (
                    "😕 *Недостаточно данных для статистики*\n\n"
                    "Попробуй позже, когда накопится больше вакансий."
                )
            else:
                message += "\n💡 *Использование:*\n`/salary python` — статистика по Python\n`/salary react` — статистика по React"
        else:
            # Показываем по конкретной технологии
            tech = args[0].lower()
            stats = await analyzer.get_stats_by_technology(tech)
            
            if stats.sample_size > 0:
                message = (
                    f"💰 *{tech.capitalize()}*\n\n"
                    f"💵 Средняя зарплата: *${stats.average_salary:,}*\n"
                    f"📋 Выборка: {stats.sample_size} вакансий\n"
                    f"📅 Период: 30 дней"
                )
            else:
                message = f"😕 *Недостаточно данных для {tech}*\n\nПопробуй другую технологию."
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command"""
        if not await self.check_admin(update):
            return

        self.is_paused = True
        await update.message.reply_text("⏸️ Публикация приостановлена")
        logger.info("⏸️ Bot paused by admin")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command"""
        if not await self.check_admin(update):
            return

        self.is_paused = False
        await update.message.reply_text("▶️ Публикация возобновлена")
        logger.info("▶️ Bot resumed by admin")

    async def cmd_frequency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /frequency command - Notification frequency settings"""
        user_id = update.effective_user.id
        settings = await self.db.get_user_settings(user_id)
        current_freq = settings.get('notification_frequency', 'instant')
        
        keyboard_rows = []
        for freq_id, freq_data in FREQUENCY_OPTIONS.items():
            emoji = "✅" if freq_id == current_freq else ""
            keyboard_rows.append([InlineKeyboardButton(
                f"{emoji} {freq_data['text']}",
                callback_data=f"freq:{freq_id}"
            )])
        
        keyboard = InlineKeyboardMarkup(keyboard_rows)
        
        await update.message.reply_text(
            "🔔 *Настройка частоты уведомлений*\n\n"
            "Выбери, как часто получать новые вакансии:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

    async def cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command - Search jobs by query"""
        query = ' '.join(context.args) if context.args else None
        
        if not query:
            await update.message.reply_text(
                "🔍 *Поиск по вакансиям*\n\n"
                "Использование: `/search <запрос>`\n\n"
                "*Примеры:*\n"
                "• `/search python junior`\n"
                "• `/search react remote`\n"
                "• `/search golang middle`\n"
                "• `/search frontend`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Search in recent jobs (last 30 days)
        month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        results = await self.db.fetchall("""
            SELECT hash, title, company, level, category, url, posted_at 
            FROM posted_jobs 
            WHERE (title LIKE ? OR company LIKE ? OR description LIKE ?)
            AND posted_at >= ?
            ORDER BY posted_at DESC 
            LIMIT 20
        """, (f'%{query}%', f'%{query}%', f'%{query}%', month_ago))
        
        if not results:
            await update.message.reply_text(
                f"🔍 По запросу `'{query}'` ничего не найдено.\n\n"
                f"Попробуй другие ключевые слова или проверь позже!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Format results
        jobs = []
        for row in results:
            jobs.append({
                'hash': row[0],
                'title': row[1],
                'company': row[2],
                'level': row[3],
                'category': row[4],
                'url': row[5],
                'posted_at': row[6]
            })
        
        # Store in context for pagination
        context.user_data['search_results'] = jobs
        context.user_data['search_query'] = query
        context.user_data['search_page'] = 0
        
        await self._send_search_results(update, context, jobs[:5], query, 0, len(jobs))

    async def _send_search_results(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                   jobs: List[Dict], query: str, page: int, total: int):
        """Send search results with pagination"""
        total_pages = (total - 1) // 5 + 1
        current_page = page + 1
        
        lines = [
            f"🔍 *Результаты поиска: '{query}'*",
            f"📄 Страница {current_page} из {total_pages} ({total} найдено)\n"
        ]
        
        for job in jobs:
            cat_emoji = CATEGORY_EMOJIS.get(job['category'], '📌')
            level_emoji = LEVEL_EMOJIS.get(job.get('level', ''), '⚪')
            
            lines.append(
                f"{cat_emoji} *{self._escape_markdown_v2(job['title'])}*\n"
                f"🏢 _{self._escape_markdown_v2(job['company'])}_ | {level_emoji}\n"
                f"[🔗 Открыть]({self._escape_markdown_v2(job['url'])})\n"
            )
        
        # Build pagination keyboard
        keyboard_buttons = []
        nav_row = []
        
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"search_page:{page-1}"))
        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f"search_page:{page+1}"))
        
        if nav_row:
            keyboard_buttons.append(nav_row)
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None
        
        message_text = '\n'.join(lines)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            await update.message.reply_text(
                message_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )

    def _escape_markdown_v2(self, text: str) -> str:
        """Escape special characters for MarkdownV2"""
        if not text:
            return ''
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks - Enhanced with onboarding and search"""
        query = update.callback_query
        await query.answer()

        data = query.data
        user_id = update.effective_user.id

        # Onboarding callbacks
        if data.startswith('onboard_level_'):
            if ONBOARDING_AVAILABLE:
                level = data.replace('onboard_level_', '')
                manager = get_onboarding_manager()
                manager.update_state(user_id, level_preference=level)
                manager.next_step(user_id)
                await self._show_onboarding_categories(update, context)
            return

        elif data.startswith('onboard_cat_'):
            if ONBOARDING_AVAILABLE:
                category = data.replace('onboard_cat_', '')
                manager = get_onboarding_manager()
                manager.toggle_category(user_id, category)
                await self._show_onboarding_categories(update, context)
            return

        elif data == 'onboard_categories_next':
            if ONBOARDING_AVAILABLE:
                manager = get_onboarding_manager()
                manager.next_step(user_id)
                await self._show_onboarding_work_format(update, context)
            return

        elif data.startswith('onboard_work_'):
            if ONBOARDING_AVAILABLE:
                work_format = data.replace('onboard_work_', '')
                manager = get_onboarding_manager()
                manager.update_state(user_id, work_format=work_format)
                manager.next_step(user_id)
                await self._show_onboarding_technologies(update, context)
            return

        elif data.startswith('onboard_tech_'):
            if ONBOARDING_AVAILABLE:
                tech = data.replace('onboard_tech_', '')
                manager = get_onboarding_manager()
                manager.toggle_technology(user_id, tech)
                await self._show_onboarding_technologies(update, context)
            return

        elif data == 'onboard_technologies_next':
            if ONBOARDING_AVAILABLE:
                manager = get_onboarding_manager()
                manager.next_step(user_id)
                await self._show_onboarding_frequency(update, context)
            return

        elif data.startswith('onboard_freq_'):
            if ONBOARDING_AVAILABLE:
                frequency = data.replace('onboard_freq_', '')
                manager = get_onboarding_manager()
                manager.update_state(user_id, frequency=frequency)
                manager.complete_onboarding(user_id)
                
                # Save to database
                state = manager.get_state(user_id)
                await self.db.save_user_onboarding(
                    user_id, state.level_preference, state.categories,
                    state.work_format, state.technologies, state.frequency
                )
                
                # Show completion message
                await self._show_onboarding_complete(update, context, state)
            return

        elif data == 'settings':
            # Restart onboarding
            if ONBOARDING_AVAILABLE:
                await self._start_onboarding(update, context)
            return

        elif data == 'hot_jobs':
            await self._show_hot_jobs(update, context)
            return

        elif data == 'recent_jobs':
            await self._show_recent_jobs(update, context)
            return

        elif data == 'salary_stats':
            await self.cmd_salary(update, context)
            return

        elif data == 'favorites':
            await self.cmd_favorites(update, context)
            return

        # Frequency settings
        elif data.startswith('freq:'):
            frequency = data.replace('freq:', '')
            await self.db.update_notification_frequency(user_id, frequency)
            freq_text = FREQUENCY_OPTIONS.get(frequency, {}).get('text', frequency)
            await query.edit_message_text(
                f"🔔 *Настройка частоты уведомлений*\n\n"
                f"✅ Выбрано: {freq_text}\n\n"
                f"Настройки сохранены!",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Search pagination
        elif data.startswith('search_page:'):
            page = int(data.replace('search_page:', ''))
            jobs = context.user_data.get('search_results', [])
            query_text = context.user_data.get('search_query', '')
            
            if jobs:
                start = page * 5
                end = start + 5
                page_jobs = jobs[start:end]
                await self._send_search_results(update, context, page_jobs, query_text, page, len(jobs))
            return

        # Existing callbacks
        elif data.startswith('save:'):
            job_hash = data.split(':', 1)[1]
            await self.db.add_favorite(user_id, job_hash)
            await query.edit_message_text(
                query.message.text + "\n\n💾 *Сохранено в избранное*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=None
            )

        elif data.startswith('expand:'):
            await query.answer("Разворачиваю... (в разработке)")

        elif data.startswith('compact:'):
            await query.answer("Сворачиваю... (в разработке)")

        elif data.startswith('hide_cat:'):
            category = data.split(':', 1)[1]
            await self.db.hide_category_for_user(user_id, category)
            cat_name = CATEGORY_NAMES_RU.get(category, category)
            await query.answer(f"Категория {cat_name} скрыта")
            await query.edit_message_text(
                query.message.text + f"\n\n🚫 Категория '{cat_name}' скрыта",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=None
            )

        elif data.startswith('toggle_cat:'):
            category = data.split(':', 1)[1]
            settings = await self.db.get_user_settings(user_id)
            enabled = settings['enabled_categories']

            if category in enabled:
                enabled.remove(category)
            else:
                enabled.append(category)

            await self.db.update_user_categories(user_id, enabled)

            if self.formatter:
                keyboard = self.formatter.create_category_settings_keyboard(enabled)
                await query.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup(keyboard['inline_keyboard'])
                )

        elif data == 'close_settings':
            await query.delete_message()

    # Onboarding helper methods
    async def _show_onboarding_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show category selection step"""
        if not ONBOARDING_AVAILABLE:
            return
            
        manager = get_onboarding_manager()
        user_id = update.effective_user.id
        state = manager.get_state(user_id)
        progress = manager.get_progress_text(user_id)
        
        # Build category keyboard with checkmarks
        keyboard_rows = []
        row = []
        for cat_id, cat_data in CATEGORY_OPTIONS.items():
            is_selected = cat_id in state.categories
            emoji = "✅" if is_selected else "⬜️"
            row.append(InlineKeyboardButton(
                f"{emoji} {cat_data['text']}",
                callback_data=f"onboard_cat_{cat_id}"
            ))
            if len(row) == 2:
                keyboard_rows.append(row)
                row = []
        if row:
            keyboard_rows.append(row)
        
        # Add next button
        keyboard_rows.append([InlineKeyboardButton("Далее ➡️", callback_data="onboard_categories_next")])
        
        keyboard = InlineKeyboardMarkup(keyboard_rows)
        
        message = (
            f"👋 Давай настроим твой профиль\n\n"
            f"{progress}\n"
            f"*Категории вакансий*\n\n"
            f"Выбери интересующие категории (можно несколько):"
        )
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                message, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
            )

    async def _show_onboarding_work_format(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show work format selection step"""
        if not ONBOARDING_AVAILABLE:
            return
            
        manager = get_onboarding_manager()
        user_id = update.effective_user.id
        progress = manager.get_progress_text(user_id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Удалённо", callback_data="onboard_work_remote")],
            [InlineKeyboardButton("🔄 Гибрид", callback_data="onboard_work_hybrid")],
            [InlineKeyboardButton("🏢 В офисе", callback_data="onboard_work_office")],
        ])
        
        message = (
            f"👋 Давай настроим твой профиль\n\n"
            f"{progress}\n"
            f"*Формат работы*\n\n"
            f"Какой формат работы тебе интересен?"
        )
        
        await update.callback_query.edit_message_text(
            message, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )

    async def _show_onboarding_technologies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show technology selection step"""
        if not ONBOARDING_AVAILABLE:
            return
            
        manager = get_onboarding_manager()
        user_id = update.effective_user.id
        state = manager.get_state(user_id)
        progress = manager.get_progress_text(user_id)
        
        # Build tech keyboard
        keyboard_rows = []
        row = []
        for tech_id, tech_data in TECHNOLOGY_OPTIONS.items():
            is_selected = tech_id in state.technologies
            emoji = "✅" if is_selected else "⬜️"
            row.append(InlineKeyboardButton(
                f"{emoji} {tech_data['text']}",
                callback_data=f"onboard_tech_{tech_id}"
            ))
            if len(row) == 2:
                keyboard_rows.append(row)
                row = []
        if row:
            keyboard_rows.append(row)
        
        # Add next button
        keyboard_rows.append([InlineKeyboardButton("Далее ➡️", callback_data="onboard_technologies_next")])
        
        keyboard = InlineKeyboardMarkup(keyboard_rows)
        
        message = (
            f"👋 Давай настроим твой профиль\n\n"
            f"{progress}\n"
            f"*Технологии*\n\n"
            f"Выбери технологии (можно несколько или пропустить):"
        )
        
        await update.callback_query.edit_message_text(
            message, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )

    async def _show_onboarding_frequency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show frequency selection step"""
        if not ONBOARDING_AVAILABLE:
            return
            
        manager = get_onboarding_manager()
        user_id = update.effective_user.id
        progress = manager.get_progress_text(user_id)
        
        keyboard_rows = []
        for freq_id, freq_data in FREQUENCY_OPTIONS.items():
            keyboard_rows.append([InlineKeyboardButton(
                freq_data['text'],
                callback_data=f"onboard_freq_{freq_id}"
            )])
        
        keyboard = InlineKeyboardMarkup(keyboard_rows)
        
        message = (
            f"👋 Давай настроим твой профиль\n\n"
            f"{progress}\n"
            f"*Частота уведомлений*\n\n"
            f"Как часто присылать новые вакансии?"
        )
        
        await update.callback_query.edit_message_text(
            message, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )

    async def _show_onboarding_complete(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state):
        """Show onboarding completion message"""
        preferences_text = format_user_preferences(state)
        
        start_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Горячие вакансии", callback_data="hot_jobs"),
             InlineKeyboardButton("⚡️ Новые за час", callback_data="recent_jobs")],
            [InlineKeyboardButton("⚙️ Изменить настройки", callback_data="settings")],
        ])
        
        message = (
            f"🎉 *Профиль настроен!*\n\n"
            f"{preferences_text}\n\n"
            f"Теперь я буду подбирать вакансии под твои предпочтения!"
        )
        
        await update.callback_query.edit_message_text(
            message, parse_mode=ParseMode.MARKDOWN, reply_markup=start_keyboard
        )

    async def _show_hot_jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show hot jobs (recent)"""
        from datetime import datetime, timedelta
        hour_ago = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        
        results = await self.db.fetchall(
            'SELECT title, company, level, category, url FROM posted_jobs '
            'WHERE posted_at >= ? ORDER BY posted_at DESC LIMIT 10',
            (hour_ago,)
        )
        
        if not results:
            await update.callback_query.edit_message_text(
                "🔥 *Горячие вакансии*\n\n"
                "Пока нет новых вакансий за последние 24 часа.\n"
                "Загляни позже!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        lines = ["🔥 *Горячие вакансии (24ч):*\n"]
        for row in results[:5]:
            title, company, level, category, url = row
            cat_emoji = CATEGORY_EMOJIS.get(category, '📌')
            level_emoji = LEVEL_EMOJIS.get(level, '⚪')
            lines.append(
                f"{cat_emoji} *{self._escape_markdown_v2(title)}*\n"
                f"🏢 _{self._escape_markdown_v2(company)}_ | {level_emoji}\n"
                f"[🔗 Открыть]({self._escape_markdown_v2(url)})\n"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡️ Новые за час", callback_data="recent_jobs"),
             InlineKeyboardButton("🔍 Поиск", callback_data="search")],
        ])
        
        await update.callback_query.edit_message_text(
            '\n'.join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

    async def _show_recent_jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent jobs (last hour)"""
        from datetime import datetime, timedelta
        hour_ago = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        
        results = await self.db.fetchall(
            'SELECT title, company, level, category, url FROM posted_jobs '
            'WHERE posted_at >= ? ORDER BY posted_at DESC LIMIT 10',
            (hour_ago,)
        )
        
        if not results:
            await update.callback_query.edit_message_text(
                "⚡️ *Новые за час*\n\n"
                "Пока нет новых вакансий за последний час.\n"
                "Загляни позже!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        lines = [f"⚡️ *Новые вакансии ({len(results)} за час):*\n"]
        for row in results[:5]:
            title, company, level, category, url = row
            cat_emoji = CATEGORY_EMOJIS.get(category, '📌')
            level_emoji = LEVEL_EMOJIS.get(level, '⚪')
            lines.append(
                f"{cat_emoji} *{self._escape_markdown_v2(title)}*\n"
                f"🏢 _{self._escape_markdown_v2(company)}_ | {level_emoji}\n"
                f"[🔗 Открыть]({self._escape_markdown_v2(url)})\n"
            )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Горячие вакансии", callback_data="hot_jobs"),
             InlineKeyboardButton("🔍 Поиск", callback_data="search")],
        ])
        
        await update.callback_query.edit_message_text(
            '\n'.join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

    async def post_job(self, job: Dict) -> bool:
        """Post job to channel with enhanced formatting"""
        if self.is_paused:
            logger.info("⏸️ Skipped posting (bot is paused)")
            return False

        try:
            # Используем новый форматтер если доступен
            if Config.ENABLE_MARKDOWN_V2 and self.formatter:
                formatted = self.formatter.format_job(job, view_mode='compact')
                await self.application.bot.send_message(
                    chat_id=Config.CHANNEL_ID,
                    text=formatted.text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=InlineKeyboardMarkup(formatted.reply_markup['inline_keyboard']),
                    disable_web_page_preview=formatted.disable_web_page_preview
                )
            else:
                # Fallback на legacy HTML форматирование
                message = format_job_message_legacy(job)
                await self.application.bot.send_message(
                    chat_id=Config.CHANNEL_ID,
                    text=message,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

            logger.info(f"✅ Posted: {job.get('title', 'N/A')} [{job.get('category', 'other')}]")
            return True

        except RetryAfter as e:
            logger.warning(f"⏳ Telegram flood control: retry after {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            return await self.post_job(job)
        except TimedOut:
            logger.error("❌ Telegram timeout")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to post job: {e}")
            return False

# ==================== MAIN LOOP ====================
async def main():
    """Main application loop"""
    logger.info("=" * 60)
    logger.info("🚀 Job Bot Starting (v6.0 - Enhanced Edition)")
    logger.info(f"📡 Channel: {Config.CHANNEL_ID}")
    logger.info(f"⏱️ Check interval: {Config.CHECK_INTERVAL}s")
    logger.info(f"📊 Max posts per cycle: {Config.MAX_POSTS_PER_CYCLE}")
    logger.info(f"🤖 MarkdownV2: {Config.ENABLE_MARKDOWN_V2}")
    logger.info(f"📱 Telegram channels: {Config.ENABLE_TELEGRAM_CHANNELS}")
    logger.info(f"🧠 Classifier: {CLASSIFIER_AVAILABLE}")
    logger.info(f"🎨 Formatter: {FORMATTER_AVAILABLE}")
    logger.info(f"🎯 Smart Matching: {SMART_MATCHING_AVAILABLE}")
    logger.info(f"💰 Salary Insights: {SALARY_ANALYZER_AVAILABLE}")
    if Config.ADMIN_USER_ID:
        logger.info(f"👤 Admin user ID: {Config.ADMIN_USER_ID}")
    logger.info("=" * 60)

    # Initialize database
    db = await init_database()

    # Setup Telegram bot
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
    job_bot = JobBot(application, db)

    # Register command handlers
    application.add_handler(CommandHandler("start", job_bot.cmd_start))
    application.add_handler(CommandHandler("status", job_bot.cmd_status))
    application.add_handler(CommandHandler("last", job_bot.cmd_last))
    application.add_handler(CommandHandler("favorites", job_bot.cmd_favorites))
    application.add_handler(CommandHandler("categories", job_bot.cmd_categories))
    application.add_handler(CommandHandler("recommendations", job_bot.cmd_recommendations))
    application.add_handler(CommandHandler("salary", job_bot.cmd_salary))
    application.add_handler(CommandHandler("pause", job_bot.cmd_pause))
    application.add_handler(CommandHandler("resume", job_bot.cmd_resume))
    application.add_handler(CommandHandler("frequency", job_bot.cmd_frequency))
    application.add_handler(CommandHandler("search", job_bot.cmd_search))
    application.add_handler(CallbackQueryHandler(job_bot.handle_callback))

    # Start bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    logger.info("✅ Telegram bot started with admin commands")

    # Setup graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, application, db)))

    # Main collection loop
    api_fetch_functions = [
        (fetch_remotive, "Remotive"),
        (fetch_remoteok, "RemoteOK"),
        (fetch_arbeitnow, "Arbeitnow"),
        (fetch_himalayas, "Himalayas"),
        (fetch_weworkremotely, "We Work Remotely"),
        (fetch_jobicy, "Jobicy"),
        (fetch_headhunter, "HeadHunter"),
        (fetch_superjob, "SuperJob"),
        (fetch_adzuna, "Adzuna")
    ]
    
    # RSS feed fetchers
    rss_fetch_functions = [
        (parse_rss_feed, RSS_FEEDS["remotive"], "Remotive RSS"),
        (parse_rss_feed, RSS_FEEDS["weworkremotely"], "We Work Remotely RSS"),
        (parse_rss_feed, RSS_FEEDS["remoteok"], "RemoteOK RSS"),
        (parse_rss_feed, RSS_FEEDS["himalayas"], "Himalayas RSS"),
    ]
    
    while True:
        try:
            if job_bot.is_paused:
                logger.info("⏸️ Bot is paused, skipping collection cycle")
                await asyncio.sleep(60)
                continue
            
            logger.info("🔄 Starting job collection cycle...")
            
            # Fetch from API sources in parallel using asyncio.gather
            fetch_tasks = [
                safe_fetch_with_retry(fetch_func, source_name)
                for fetch_func, source_name in api_fetch_functions
            ]
            
            # Fetch from RSS feeds
            rss_tasks = [
                safe_fetch_with_retry(lambda url=url, name=name: fetch_func(url, name), f"rss_{name.lower().replace(' ', '_')}")
                for fetch_func, url, name in rss_fetch_functions
            ]
            
            # Add Telegram channels fetch if enabled
            telegram_task = fetch_telegram_channels() if Config.ENABLE_TELEGRAM_CHANNELS else []
            
            # Execute all fetch tasks concurrently
            all_results = await asyncio.gather(
                *fetch_tasks,
                *rss_tasks,
                return_exceptions=True
            )
            
            all_jobs = []
            api_results = all_results[:len(api_fetch_functions)]
            rss_results = all_results[len(api_fetch_functions):len(api_fetch_functions) + len(rss_fetch_functions)]
            
            # Process API results
            for i, result in enumerate(api_results):
                if isinstance(result, Exception):
                    logger.error(f"❌ API fetch error: {result}")
                    continue
                source_name = api_fetch_functions[i][1]
                all_jobs.extend(result)
                logger.info(f"📥 Fetched {len(result)} jobs from {source_name}")
            
            # Process RSS results
            for i, result in enumerate(rss_results):
                if isinstance(result, Exception):
                    logger.error(f"❌ RSS fetch error: {result}")
                    continue
                source_name = rss_fetch_functions[i][2]
                all_jobs.extend(result)
                logger.info(f"📥 Fetched {len(result)} jobs from {source_name}")
            
            # Process Telegram channels
            if Config.ENABLE_TELEGRAM_CHANNELS and telegram_task:
                try:
                    tg_jobs = await telegram_task
                    all_jobs.extend(tg_jobs)
                    logger.info(f"📥 Fetched {len(tg_jobs)} jobs from Telegram channels")
                except Exception as e:
                    logger.error(f"❌ Telegram channels error: {e}")
            
            logger.info(f"📊 Total jobs fetched: {len(all_jobs)}")
            
            # Filter, classify and process
            classified_jobs = []
            for job in all_jobs:
                if not is_suitable_job(job):
                    continue
                
                # Classify level
                level = classify_job_level(job)
                if level:
                    job['level'] = level
                else:
                    continue
                
                # Auto-classify category
                category = auto_classify_category(job)
                job['category'] = category
                
                classified_jobs.append(job)
            
            logger.info(f"🎯 Suitable Junior/Middle jobs: {len(classified_jobs)}")
            
            # Post jobs
            posted_count = 0
            for job in classified_jobs[:Config.MAX_POSTS_PER_CYCLE]:
                if not await is_duplicate_job(job, db):
                    if await job_bot.post_job(job):
                        posted_count += 1
                        await asyncio.sleep(DELAYS['between_posts'])
            
            logger.info(f"✅ Posted {posted_count} new jobs to channel")
            logger.info(f"⏳ Waiting {Config.CHECK_INTERVAL//60} minutes before next cycle...")
            await asyncio.sleep(Config.CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"❌ Error in main loop: {e}", exc_info=True)
            await asyncio.sleep(300)


async def shutdown(signal, application, db):
    """Graceful shutdown handler"""
    logger.info(f"🛑 Received exit signal {signal.name}")
    
    await application.stop()
    await application.shutdown()
    await db.close()
    logger.info("👋 Bot shutdown complete")
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
        sys.exit(0)
