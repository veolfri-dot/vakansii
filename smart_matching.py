"""
Smart Matching Module - Персональные подборки вакансий под профиль пользователя
Версия: 1.0.0

Алгоритм расчёта релевантности:
- Уровень (30%) - совпадение уровня junior/middle
- Категория (30%) - совпадение категории работы
- Технологии (40%) - совпадение технологий (max 40%)
"""
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class MatchResult:
    """Результат матчинга вакансии"""
    job: Dict
    match_score: float
    level_match: bool
    category_match: bool
    matching_technologies: List[str]


class SmartMatcher:
    """
    Класс для расчёта релевантности вакансий под профиль пользователя.
    
    Пример использования:
        profile = {
            'levels': ['junior', 'entry'],
            'categories': ['development', 'qa'],
            'technologies': ['python', 'django', 'react']
        }
        matcher = SmartMatcher(profile)
        matched_jobs = matcher.filter_and_sort_jobs(jobs, min_score=0.4)
    """
    
    # Веса для расчёта score
    LEVEL_WEIGHT = 0.30
    CATEGORY_WEIGHT = 0.30
    TECH_WEIGHT_PER_MATCH = 0.10
    MAX_TECH_WEIGHT = 0.40
    
    def __init__(self, user_profile: Dict):
        """
        Инициализация с профилем пользователя.
        
        Args:
            user_profile: {
                'levels': ['junior', 'entry', ...],
                'categories': ['development', 'qa', ...],
                'technologies': ['python', 'react', ...]
            }
        """
        self.profile = user_profile
        self._normalize_profile()
    
    def _normalize_profile(self):
        """Нормализация профиля для case-insensitive сравнения"""
        self.user_levels = [
            level.lower().strip() 
            for level in self.profile.get('levels', [])
        ]
        self.user_categories = [
            cat.lower().strip() 
            for cat in self.profile.get('categories', [])
        ]
        self.user_techs = [
            tech.lower().strip() 
            for tech in self.profile.get('technologies', [])
        ]
    
    def calculate_match_score(self, job: Dict) -> float:
        """
        Расчёт релевантности вакансии (0.0 - 1.0).
        
        Args:
            job: Данные вакансии с полями title, company, level, 
                 category, description, tags
        
        Returns:
            Score от 0.0 до 1.0
        """
        score = 0.0
        
        # Уровень (30%)
        job_level = job.get('level', '').lower()
        if self.user_levels and any(
            level in job_level for level in self.user_levels
        ):
            score += self.LEVEL_WEIGHT
        
        # Категория (30%)
        job_category = job.get('category', '').lower()
        if self.user_categories and job_category in self.user_categories:
            score += self.CATEGORY_WEIGHT
        
        # Технологии (40% max)
        if self.user_techs:
            score += self._calculate_tech_score(job)
        
        return min(score, 1.0)
    
    def _calculate_tech_score(self, job: Dict) -> float:
        """
        Расчёт score по технологиям.
        Каждое совпадение +10%, максимум 40%.
        """
        job_tags = [
            tag.lower().strip() 
            for tag in job.get('tags', []) 
            if isinstance(tag, str)
        ]
        job_desc = job.get('description', '').lower()
        job_title = job.get('title', '').lower()
        
        matching_techs = []
        for tech in self.user_techs:
            # Ищем в тегах, описании и заголовке
            if (tech in job_tags or 
                tech in job_desc or 
                tech in job_title):
                matching_techs.append(tech)
        
        # Каждое совпадение даёт 10%, но не более 40%
        tech_score = len(matching_techs) * self.TECH_WEIGHT_PER_MATCH
        return min(tech_score, self.MAX_TECH_WEIGHT)
    
    def get_matching_technologies(self, job: Dict) -> List[str]:
        """
        Получение списка совпадающих технологий.
        """
        job_tags = [
            tag.lower().strip() 
            for tag in job.get('tags', [])
            if isinstance(tag, str)
        ]
        job_desc = job.get('description', '').lower()
        job_title = job.get('title', '').lower()
        
        matching = []
        for tech in self.user_techs:
            if (tech in job_tags or 
                tech in job_desc or 
                tech in job_title):
                matching.append(tech)
        
        return matching
    
    def analyze_job(self, job: Dict) -> MatchResult:
        """
        Детальный анализ вакансии с возвратом полной информации.
        """
        job_level = job.get('level', '').lower()
        job_category = job.get('category', '').lower()
        
        level_match = self.user_levels and any(
            level in job_level for level in self.user_levels
        )
        
        category_match = (
            self.user_categories and 
            job_category in self.user_categories
        )
        
        matching_techs = self.get_matching_technologies(job)
        
        return MatchResult(
            job=job,
            match_score=self.calculate_match_score(job),
            level_match=level_match,
            category_match=category_match,
            matching_technologies=matching_techs
        )
    
    def filter_and_sort_jobs(
        self, 
        jobs: List[Dict], 
        min_score: float = 0.3
    ) -> List[Dict]:
        """
        Фильтрация и сортировка вакансий по релевантности.
        
        Args:
            jobs: Список вакансий
            min_score: Минимальный score для включения (0.0-1.0)
        
        Returns:
            Отсортированный список вакансий с добавленным полем match_score
        """
        scored_jobs = []
        
        for job in jobs:
            score = self.calculate_match_score(job)
            if score >= min_score:
                job_copy = job.copy()
                job_copy['match_score'] = score
                job_copy['matching_technologies'] = self.get_matching_technologies(job)
                scored_jobs.append(job_copy)
        
        # Сортируем по убыванию score
        scored_jobs.sort(key=lambda x: x['match_score'], reverse=True)
        return scored_jobs
    
    def get_top_recommendations(
        self, 
        jobs: List[Dict], 
        limit: int = 5,
        min_score: float = 0.4
    ) -> List[Dict]:
        """
        Получение топ-N рекомендаций.
        
        Args:
            jobs: Список вакансий
            limit: Количество результатов
            min_score: Минимальный порог релевантности
        
        Returns:
            Топ-N вакансий с highest match_score
        """
        sorted_jobs = self.filter_and_sort_jobs(jobs, min_score)
        return sorted_jobs[:limit]
    
    @staticmethod
    def get_score_emoji(score: float) -> str:
        """
        Получение эмодзи для отображения score.
        """
        if score >= 0.7:
            return "🟢"  # Отличное совпадение
        elif score >= 0.5:
            return "🟡"  # Хорошее совпадение
        elif score >= 0.4:
            return "🟠"  # Среднее совпадение
        else:
            return "⚪"  # Низкое совпадение
    
    @staticmethod
    def format_score_percentage(score: float) -> str:
        """Форматирование score в проценты"""
        return f"{int(score * 100)}%"


def create_user_profile(
    level_preference: str = 'both',
    categories: List[str] = None,
    technologies: List[str] = None
) -> Dict:
    """
    Создание профиля пользователя из настроек бота.
    
    Args:
        level_preference: 'junior', 'middle', 'both'
        categories: Список категорий
        technologies: Список технологий
    
    Returns:
        Профиль для SmartMatcher
    """
    levels = []
    if level_preference == 'junior' or level_preference == 'both':
        levels.extend(['junior', 'jr', 'entry', 'entry-level', 'trainee'])
    if level_preference == 'middle' or level_preference == 'both':
        levels.extend(['middle', 'mid', 'mid-level'])
    
    return {
        'levels': levels,
        'categories': categories or [],
        'technologies': technologies or []
    }


# Функции для быстрого использования
def get_recommendations(
    jobs: List[Dict],
    user_profile: Dict,
    limit: int = 5,
    min_score: float = 0.4
) -> List[Dict]:
    """
    Быстрое получение рекомендаций.
    
    Example:
        profile = {
            'levels': ['junior'],
            'categories': ['development'],
            'technologies': ['python', 'django']
        }
        recs = get_recommendations(jobs, profile, limit=3)
    """
    matcher = SmartMatcher(user_profile)
    return matcher.get_top_recommendations(jobs, limit, min_score)


def calculate_job_match(job: Dict, user_profile: Dict) -> MatchResult:
    """
    Расчёт совпадения для одной вакансии.
    """
    matcher = SmartMatcher(user_profile)
    return matcher.analyze_job(job)


if __name__ == '__main__':
    # Тестирование
    test_profile = {
        'levels': ['junior', 'entry'],
        'categories': ['development', 'qa'],
        'technologies': ['python', 'django', 'react', 'javascript']
    }
    
    test_jobs = [
        {
            'title': 'Junior Python Developer',
            'company': 'Tech Corp',
            'level': 'Junior',
            'category': 'development',
            'description': 'Looking for Python developer with Django experience',
            'tags': ['Python', 'Django', 'PostgreSQL'],
        },
        {
            'title': 'Senior Java Developer',
            'company': 'Big Corp',
            'level': 'Senior',
            'category': 'development',
            'description': 'Senior Java developer position',
            'tags': ['Java', 'Spring', 'Hibernate'],
        },
        {
            'title': 'QA Automation Engineer',
            'company': 'Test Inc',
            'level': 'Junior',
            'category': 'qa',
            'description': 'QA with Python and JavaScript experience',
            'tags': ['Python', 'Selenium', 'JavaScript'],
        },
    ]
    
    print("=" * 60)
    print("SMART MATCHING TEST")
    print("=" * 60)
    
    matcher = SmartMatcher(test_profile)
    
    for job in test_jobs:
        result = matcher.analyze_job(job)
        emoji = SmartMatcher.get_score_emoji(result.match_score)
        pct = SmartMatcher.format_score_percentage(result.match_score)
        
        print(f"\n{emoji} {job['title']} @ {job['company']}")
        print(f"   Score: {pct}")
        print(f"   Level match: {result.level_match}")
        print(f"   Category match: {result.category_match}")
        print(f"   Matching techs: {result.matching_technologies}")
    
    print("\n" + "=" * 60)
    print("FILTERED & SORTED (min_score=0.4):")
    print("=" * 60)
    
    matched = matcher.filter_and_sort_jobs(test_jobs, min_score=0.4)
    for job in matched:
        emoji = SmartMatcher.get_score_emoji(job['match_score'])
        pct = SmartMatcher.format_score_percentage(job['match_score'])
        print(f"{emoji} {job['title']} - {pct}")
