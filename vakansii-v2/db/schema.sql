-- Расширение для UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ENUM для типа удаленной работы
DO $$ BEGIN
    CREATE TYPE remote_type_enum AS ENUM ('FULLY_REMOTE', 'HYBRID', 'ONSITE');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- ENUM для категории вакансии
DO $$ BEGIN
    CREATE TYPE category_enum AS ENUM (
        'Backend', 'Frontend', 'Fullstack', 'DevOps',
        'Data Science', 'QA', 'Design', 'PM',
        'Prompt Engineering', 'Other'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Таблица вакансий
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    remote_type remote_type_enum DEFAULT 'FULLY_REMOTE',
    salary_min_usd INTEGER,
    salary_max_usd INTEGER,
    salary_currency TEXT,
    category category_enum DEFAULT 'Other',
    source_url TEXT UNIQUE NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    description TEXT,
    required_skills TEXT[],
    source TEXT
);

-- Таблица подписок пользователей бота
CREATE TABLE IF NOT EXISTS user_subscriptions (
    user_id BIGINT PRIMARY KEY,
    keywords TEXT NOT NULL DEFAULT '',
    min_salary INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица отправленных уведомлений (анти-спам)
CREATE TABLE IF NOT EXISTS sent_notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id BIGINT NOT NULL,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, job_id)
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_jobs_remote_category
    ON jobs(remote_type, category)
    WHERE remote_type = 'FULLY_REMOTE';

CREATE INDEX IF NOT EXISTS idx_jobs_published_at
    ON jobs(published_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_source_url
    ON jobs(source_url);

CREATE INDEX IF NOT EXISTS idx_jobs_title_search
    ON jobs USING gin(to_tsvector('russian', title));

CREATE INDEX IF NOT EXISTS idx_sent_notifications_user
    ON sent_notifications(user_id);
