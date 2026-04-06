"""
Salary Insights Module - Аналитика зарплат по специальностям и технологиям
Версия: 1.0.0

Функционал:
- Статистика по категориям и уровням
- Статистика по технологиям
- Сравнение зарплат
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SalaryStats:
    """Статистика зарплат"""
    category: str
    level: str
    avg_min: int
    avg_max: int
    median: int
    sample_size: int
    currency: str = "USD"
    
    def format_range(self) -> str:
        """Форматирование диапазона зарплат"""
        return f"${self.avg_min:,} - ${self.avg_max:,}"
    
    def format_short(self) -> str:
        """Краткое форматирование"""
        return f"${self.avg_min:,}-${self.avg_max:,} ({self.sample_size} вак.)"


@dataclass
class TechSalaryStats:
    """Статистика зарплат по технологии"""
    technology: str
    average_salary: int
    sample_size: int
    currency: str = "USD"
    
    def formatted(self) -> str:
        """Форматированная строка"""
        return f"${self.average_salary:,} ({self.sample_size} вак.)"


class SalaryAnalyzer:
    """
    Анализатор зарплат с использованием SQLite базы данных.
    
    Требует подключения к DatabaseConnection для выполнения запросов.
    """
    
    # Стандартные категории для анализа
    DEFAULT_CATEGORIES = [
        'development', 'qa', 'devops', 'data', 'design', 
        'pm', 'marketing', 'security'
    ]
    
    # Стандартные уровни
    DEFAULT_LEVELS = ['junior', 'middle', 'senior']
    
    def __init__(self, db):
        """
        Инициализация анализатора.
        
        Args:
            db: DatabaseConnection или совместимый объект с методами
                fetchone() и fetchall()
        """
        self.db = db
    
    async def get_stats_by_category(
        self, 
        category: str, 
        level: str = None,
        days: int = 30
    ) -> SalaryStats:
        """
        Статистика зарплат по категории и уровню.
        
        Args:
            category: Категория (development, qa, devops, etc.)
            level: Уровень (junior, middle, senior) или None для всех
            days: Период в днях (по умолчанию 30)
        
        Returns:
            SalaryStats объект
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        query = """
        SELECT 
            AVG(CAST(salary_min AS INTEGER)) as avg_min,
            AVG(CAST(salary_max AS INTEGER)) as avg_max,
            COUNT(*) as count
        FROM posted_jobs 
        WHERE category = ? 
        AND salary_min IS NOT NULL
        AND salary_max IS NOT NULL
        AND CAST(salary_min AS INTEGER) > 0
        AND CAST(salary_max AS INTEGER) > 0
        AND date(posted_at) >= ?
        """
        params = [category, cutoff_date]
        
        if level:
            query += " AND lower(level) = lower(?)"
            params.append(level)
        
        row = await self.db.fetchone(query, tuple(params))
        
        avg_min = int(row[0]) if row[0] else 0
        avg_max = int(row[1]) if row[1] else 0
        
        return SalaryStats(
            category=category,
            level=level or "all",
            avg_min=avg_min,
            avg_max=avg_max,
            median=int((avg_min + avg_max) / 2) if avg_min and avg_max else 0,
            sample_size=row[2] if row else 0
        )
    
    async def get_stats_by_technology(
        self, 
        technology: str,
        days: int = 30
    ) -> TechSalaryStats:
        """
        Статистика зарплат по конкретной технологии.
        
        Ищет технологию в заголовке и описании вакансий.
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        tech_pattern = f"%{technology}%"
        
        query = """
        SELECT 
            AVG((CAST(salary_min AS INTEGER) + CAST(salary_max AS INTEGER)) / 2) as avg,
            COUNT(*) as count
        FROM posted_jobs 
        WHERE (title LIKE ? OR description LIKE ?)
        AND salary_min IS NOT NULL
        AND CAST(salary_min AS INTEGER) > 0
        AND date(posted_at) >= ?
        """
        
        row = await self.db.fetchone(query, (tech_pattern, tech_pattern, cutoff_date))
        
        return TechSalaryStats(
            technology=technology,
            average_salary=int(row[0]) if row[0] else 0,
            sample_size=row[1] if row else 0
        )
    
    async def get_tech_comparison(
        self, 
        technologies: List[str],
        days: int = 30
    ) -> List[TechSalaryStats]:
        """
        Сравнение зарплат по нескольким технологиям.
        
        Returns:
            Список TechSalaryStats, отсортированный по убыванию зарплаты
        """
        results = []
        for tech in technologies:
            stats = await self.get_stats_by_technology(tech, days)
            if stats.sample_size > 0:
                results.append(stats)
        
        # Сортируем по убыванию зарплаты
        results.sort(key=lambda x: x.average_salary, reverse=True)
        return results
    
    async def get_category_comparison(
        self,
        categories: List[str] = None,
        days: int = 30
    ) -> Dict[str, Dict[str, SalaryStats]]:
        """
        Сравнение зарплат по категориям и уровням.
        
        Returns:
            Словарь {category: {level: SalaryStats}}
        """
        categories = categories or self.DEFAULT_CATEGORIES
        result = {}
        
        for category in categories:
            result[category] = {}
            for level in self.DEFAULT_LEVELS:
                stats = await self.get_stats_by_category(category, level, days)
                if stats.sample_size > 0:
                    result[category][level] = stats
        
        return result
    
    async def get_top_paying_technologies(
        self,
        limit: int = 10,
        min_sample_size: int = 5,
        days: int = 30
    ) -> List[TechSalaryStats]:
        """
        Получение топ-N технологий по уровню зарплат.
        
        Args:
            limit: Количество результатов
            min_sample_size: Минимальная выборка для включения
            days: Период в днях
        """
        # Популярные технологии для анализа
        popular_techs = [
            'python', 'javascript', 'typescript', 'react', 'vue', 'angular',
            'nodejs', 'django', 'flask', 'fastapi', 'express', 'nextjs',
            'postgresql', 'mongodb', 'mysql', 'redis',
            'docker', 'kubernetes', 'aws', 'azure', 'gcp',
            'java', 'go', 'rust', 'php', 'ruby', 'swift', 'kotlin',
            'machine learning', 'ai', 'data science', 'tensorflow', 'pytorch',
            'react native', 'flutter', 'ios', 'android',
            'selenium', 'playwright', 'cypress',
        ]
        
        results = []
        for tech in popular_techs:
            stats = await self.get_stats_by_technology(tech, days)
            if stats.sample_size >= min_sample_size:
                results.append(stats)
        
        results.sort(key=lambda x: x.average_salary, reverse=True)
        return results[:limit]
    
    async def get_salary_trends(
        self,
        category: str = None,
        technology: str = None,
        weeks: int = 8
    ) -> List[Dict]:
        """
        Получение трендов зарплат за последние N недель.
        
        Returns:
            Список {week, avg_salary, sample_size}
        """
        results = []
        
        for week_offset in range(weeks):
            week_start = datetime.now() - timedelta(weeks=week_offset + 1)
            week_end = datetime.now() - timedelta(weeks=week_offset)
            
            query = """
            SELECT AVG((CAST(salary_min AS INTEGER) + CAST(salary_max AS INTEGER)) / 2) as avg,
                   COUNT(*) as count
            FROM posted_jobs
            WHERE salary_min IS NOT NULL
            AND CAST(salary_min AS INTEGER) > 0
            AND date(posted_at) >= ?
            AND date(posted_at) < ?
            """
            params = [week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')]
            
            if category:
                query += " AND category = ?"
                params.append(category)
            
            if technology:
                query += " AND (title LIKE ? OR description LIKE ?)"
                tech_pattern = f"%{technology}%"
                params.extend([tech_pattern, tech_pattern])
            
            row = await self.db.fetchone(query, tuple(params))
            
            results.append({
                'week': week_start.strftime('%Y-%m-%d'),
                'avg_salary': int(row[0]) if row[0] else 0,
                'sample_size': row[1] if row else 0
            })
        
        # Реверсируем, чтобы шло от старого к новому
        return list(reversed(results))
    
    @staticmethod
    def format_salary_message(stats: SalaryStats) -> str:
        """Форматирование сообщения со статистикой"""
        if stats.sample_size == 0:
            return f"😕 Недостаточно данных для {stats.category}"
        
        lines = [
            f"📊 *{stats.category.capitalize()}* — {stats.level.capitalize()}",
            f"",
            f"💰 Средняя зарплата: ${stats.median:,}",
            f"📈 Диапазон: ${stats.avg_min:,} - ${stats.avg_max:,}",
            f"📋 Выборка: {stats.sample_size} вакансий",
        ]
        return '\n'.join(lines)
    
    @staticmethod
    def format_category_overview(
        stats_by_category: Dict[str, Dict[str, SalaryStats]],
        show_levels: List[str] = None
    ) -> str:
        """
        Форматирование обзора по категориям.
        
        Args:
            stats_by_category: Результат get_category_comparison()
            show_levels: Какие уровни показывать ['junior', 'middle']
        """
        show_levels = show_levels or ['junior', 'middle']
        
        lines = ["💰 *Зарплатная статистика*\n"]
        
        has_data = False
        for category, levels in stats_by_category.items():
            category_lines = []
            category_name = category.capitalize()
            
            for level in show_levels:
                if level in levels and levels[level].sample_size > 0:
                    has_data = True
                    stats = levels[level]
                    emoji = "🟢" if level == 'junior' else "🔵" if level == 'middle' else "🔴"
                    category_lines.append(
                        f"  {emoji} {level.capitalize()}: ${stats.avg_min:,}-${stats.avg_max:,} "
                        f"({stats.sample_size} вак.)"
                    )
            
            if category_lines:
                lines.append(f"📊 *{category_name}*")
                lines.extend(category_lines)
                lines.append("")
        
        if not has_data:
            return "😕 Пока недостаточно данных для статистики."
        
        return '\n'.join(lines)
    
    @staticmethod
    def format_tech_comparison(tech_stats: List[TechSalaryStats]) -> str:
        """Форматирование сравнения технологий"""
        if not tech_stats:
            return "😕 Недостаточно данных для сравнения."
        
        lines = ["💰 *Зарплаты по технологиям*\n"]
        
        medals = ["🥇", "🥈", "🥉"]
        
        for i, stat in enumerate(tech_stats[:10]):
            medal = medals[i] if i < 3 else "📌"
            lines.append(
                f"{medal} *{stat.technology.capitalize()}*: "
                f"${stat.average_salary:,} ({stat.sample_size} вак.)"
            )
        
        return '\n'.join(lines)


# Категории и их переводы для отображения
CATEGORY_NAMES_RU = {
    'development': 'Разработка',
    'qa': 'QA',
    'devops': 'DevOps',
    'data': 'Данные',
    'design': 'Дизайн',
    'pm': 'Менеджмент',
    'marketing': 'Маркетинг',
    'sales': 'Продажи',
    'support': 'Поддержка',
    'security': 'Безопасность',
    'other': 'Другое',
}


def get_category_name_ru(category: str) -> str:
    """Получение русского названия категории"""
    return CATEGORY_NAMES_RU.get(category, category.capitalize())


# Функции для быстрого использования
async def get_quick_salary_stats(db, category: str, level: str = None) -> Optional[SalaryStats]:
    """Быстрое получение статистики"""
    analyzer = SalaryAnalyzer(db)
    stats = await analyzer.get_stats_by_category(category, level)
    return stats if stats.sample_size > 0 else None


async def get_tech_salary_ranking(db, technologies: List[str]) -> List[TechSalaryStats]:
    """Ранжирование технологий по зарплатам"""
    analyzer = SalaryAnalyzer(db)
    return await analyzer.get_tech_comparison(technologies)


if __name__ == '__main__':
    import asyncio
    
    # Mock DB для тестирования
    class MockDB:
        async def fetchone(self, query, params=()):
            # Симуляция данных
            if 'python' in str(params).lower():
                return (5500, 8)  # avg salary, count
            elif 'javascript' in str(params).lower():
                return (4800, 12)
            elif 'react' in str(params).lower():
                return (5200, 10)
            else:
                return (3000, 5)
        
        async def fetchall(self, query, params=()):
            return []
    
    async def test():
        db = MockDB()
        analyzer = SalaryAnalyzer(db)
        
        print("=" * 60)
        print("SALARY ANALYZER TEST")
        print("=" * 60)
        
        # Тест сравнения технологий
        techs = ['python', 'javascript', 'react', 'golang']
        comparison = await analyzer.get_tech_comparison(techs)
        
        print("\n📊 Tech Comparison:")
        for stat in comparison:
            print(f"  {stat.technology}: ${stat.average_salary:,} ({stat.sample_size} вак.)")
        
        # Тест форматирования
        print("\n" + "=" * 60)
        print(formatted := analyzer.format_tech_comparison(comparison))
        print("=" * 60)
    
    asyncio.run(test())
