import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RawVacancy:
    """Модель сырых данных вакансии, полученных из источников."""

    source: str
    external_id: str
    title: str
    company: str
    description: str
    url: str
    location: str = "Worldwide"
    salary_min_usd: Optional[int] = None
    salary_max_usd: Optional[int] = None
    salary_currency: Optional[str] = None
    remote_type: str = "FULLY_REMOTE"
    published_at: Optional[datetime] = None
    raw_data: Optional[dict] = None

    @property
    def dedup_hash(self) -> str:
        """Быстрый хеш для дедупликации на основе названия и компании."""
        normalized = f"{self.title.lower().strip()}|{self.company.lower().strip()}"
        return hashlib.md5(normalized.encode()).hexdigest()
