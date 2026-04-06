"""
Onboarding Module - FSM для пошагового онбординга новых пользователей
Версия: 1.0.0
"""
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


class OnboardingStep(Enum):
    """Шаги онбординга"""
    LEVEL = 1
    CATEGORIES = 2
    WORK_FORMAT = 3
    TECHNOLOGIES = 4
    FREQUENCY = 5
    COMPLETED = 6


@dataclass
class OnboardingState:
    """Состояние онбординга пользователя"""
    user_id: int
    step: OnboardingStep = OnboardingStep.LEVEL
    level_preference: str = ""  # junior, middle, both
    categories: List[str] = field(default_factory=list)
    work_format: str = ""  # remote, hybrid, office
    technologies: List[str] = field(default_factory=list)
    frequency: str = ""  # instant, hourly, digest_morning, digest_evening, off
    completed: bool = False


# Опции для онбординга
LEVEL_OPTIONS = {
    "junior": {"text": "🟢 Junior (0-2 года)", "emoji": "🟢"},
    "middle": {"text": "🔵 Middle (2-5 лет)", "emoji": "🔵"},
    "both": {"text": "✅ Оба уровня", "emoji": "✅"},
}

CATEGORY_OPTIONS = {
    "development": {"text": "💻 Разработка", "emoji": "💻"},
    "qa": {"text": "🧪 QA / Тестирование", "emoji": "🧪"},
    "devops": {"text": "🔧 DevOps", "emoji": "🔧"},
    "data": {"text": "📊 Данные / Аналитика", "emoji": "📊"},
    "pm": {"text": "📋 Менеджмент", "emoji": "📋"},
    "design": {"text": "🎨 Дизайн", "emoji": "🎨"},
    "marketing": {"text": "📢 Маркетинг", "emoji": "📢"},
    "sales": {"text": "💼 Продажи", "emoji": "💼"},
    "support": {"text": "🎧 Поддержка", "emoji": "🎧"},
    "security": {"text": "🔒 Безопасность", "emoji": "🔒"},
}

WORK_FORMAT_OPTIONS = {
    "remote": {"text": "🏠 Удалённо", "emoji": "🏠"},
    "hybrid": {"text": "🔄 Гибрид", "emoji": "🔄"},
    "office": {"text": "🏢 В офисе", "emoji": "🏢"},
}

TECHNOLOGY_OPTIONS = {
    "python": {"text": "🐍 Python", "emoji": "🐍"},
    "javascript": {"text": "📜 JavaScript", "emoji": "📜"},
    "typescript": {"text": "📘 TypeScript", "emoji": "📘"},
    "react": {"text": "⚛️ React", "emoji": "⚛️"},
    "vue": {"text": "🟢 Vue.js", "emoji": "🟢"},
    "angular": {"text": "🔺 Angular", "emoji": "🔺"},
    "nodejs": {"text": "🟩 Node.js", "emoji": "🟩"},
    "go": {"text": "🐹 Go", "emoji": "🐹"},
    "java": {"text": "☕ Java", "emoji": "☕"},
    "csharp": {"text": "🔷 C#", "emoji": "🔷"},
    "php": {"text": "🐘 PHP", "emoji": "🐘"},
    "rust": {"text": "🦀 Rust", "emoji": "🦀"},
    "sql": {"text": "🗄️ SQL", "emoji": "🗄️"},
    "docker": {"text": "🐳 Docker", "emoji": "🐳"},
    "aws": {"text": "☁️ AWS", "emoji": "☁️"},
}

FREQUENCY_OPTIONS = {
    "instant": {"text": "⚡ Мгновенно (как появляется)", "emoji": "⚡"},
    "hourly": {"text": "🕐 Раз в час", "emoji": "🕐"},
    "digest_morning": {"text": "📰 Дайджест утром (9:00)", "emoji": "📰"},
    "digest_evening": {"text": "📰 Дайджест вечером (18:00)", "emoji": "📰"},
    "off": {"text": "🔕 Отключить", "emoji": "🔕"},
}


class OnboardingManager:
    """Менеджер состояний онбординга (in-memory storage)"""
    
    def __init__(self):
        self._states: Dict[int, OnboardingState] = {}
    
    def get_state(self, user_id: int) -> OnboardingState:
        """Получить или создать состояние пользователя"""
        if user_id not in self._states:
            self._states[user_id] = OnboardingState(user_id=user_id)
        return self._states[user_id]
    
    def update_state(self, user_id: int, **kwargs) -> OnboardingState:
        """Обновить состояние пользователя"""
        state = self.get_state(user_id)
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state
    
    def next_step(self, user_id: int) -> OnboardingStep:
        """Перейти к следующему шагу"""
        state = self.get_state(user_id)
        current = state.step
        
        if current == OnboardingStep.LEVEL:
            state.step = OnboardingStep.CATEGORIES
        elif current == OnboardingStep.CATEGORIES:
            state.step = OnboardingStep.WORK_FORMAT
        elif current == OnboardingStep.WORK_FORMAT:
            state.step = OnboardingStep.TECHNOLOGIES
        elif current == OnboardingStep.TECHNOLOGIES:
            state.step = OnboardingStep.FREQUENCY
        elif current == OnboardingStep.FREQUENCY:
            state.step = OnboardingStep.COMPLETED
            state.completed = True
        
        return state.step
    
    def prev_step(self, user_id: int) -> OnboardingStep:
        """Вернуться к предыдущему шагу"""
        state = self.get_state(user_id)
        current = state.step
        
        if current == OnboardingStep.CATEGORIES:
            state.step = OnboardingStep.LEVEL
        elif current == OnboardingStep.WORK_FORMAT:
            state.step = OnboardingStep.CATEGORIES
        elif current == OnboardingStep.TECHNOLOGIES:
            state.step = OnboardingStep.WORK_FORMAT
        elif current == OnboardingStep.FREQUENCY:
            state.step = OnboardingStep.TECHNOLOGIES
        elif current == OnboardingStep.COMPLETED:
            state.step = OnboardingStep.FREQUENCY
        
        return state.step
    
    def reset(self, user_id: int) -> OnboardingState:
        """Сбросить состояние онбординга"""
        self._states[user_id] = OnboardingState(user_id=user_id)
        return self._states[user_id]
    
    def is_completed(self, user_id: int) -> bool:
        """Проверить, завершён ли онбординг"""
        state = self._states.get(user_id)
        return state.completed if state else False
    
    def complete_onboarding(self, user_id: int) -> OnboardingState:
        """Завершить онбординг"""
        state = self.get_state(user_id)
        state.step = OnboardingStep.COMPLETED
        state.completed = True
        return state
    
    def toggle_category(self, user_id: int, category: str) -> List[str]:
        """Переключить категорию (добавить/удалить)"""
        state = self.get_state(user_id)
        if category in state.categories:
            state.categories.remove(category)
        else:
            state.categories.append(category)
        return state.categories
    
    def toggle_technology(self, user_id: int, technology: str) -> List[str]:
        """Переключить технологию (добавить/удалить)"""
        state = self.get_state(user_id)
        if technology in state.technologies:
            state.technologies.remove(technology)
        else:
            state.technologies.append(technology)
        return state.technologies
    
    def get_progress_text(self, user_id: int) -> str:
        """Получить текст прогресса онбординга"""
        state = self.get_state(user_id)
        step_num = state.step.value
        total_steps = 5
        
        progress_bar = "█" * step_num + "░" * (total_steps - step_num)
        return f"📊 *Шаг {step_num} из {total_steps}* {progress_bar}"


# Singleton instance
_onboarding_manager: Optional[OnboardingManager] = None


def get_onboarding_manager() -> OnboardingManager:
    """Получить singleton-экземпляр менеджера онбординга"""
    global _onboarding_manager
    if _onboarding_manager is None:
        _onboarding_manager = OnboardingManager()
    return _onboarding_manager


def format_user_preferences(state: OnboardingState) -> str:
    """Форматировать настройки пользователя для отображения"""
    lines = ["*Твои настройки:*"]
    
    # Уровень
    level_text = LEVEL_OPTIONS.get(state.level_preference, {}).get("text", "Не указан")
    lines.append(f"• Уровень: {level_text}")
    
    # Категории
    if state.categories:
        cat_texts = [CATEGORY_OPTIONS.get(c, {}).get("emoji", "📌") for c in state.categories]
        lines.append(f"• Категории: {' '.join(cat_texts)}")
    else:
        lines.append("• Категории: Все")
    
    # Формат работы
    work_text = WORK_FORMAT_OPTIONS.get(state.work_format, {}).get("text", "Не указан")
    lines.append(f"• Формат: {work_text}")
    
    # Технологии
    if state.technologies:
        tech_texts = [TECHNOLOGY_OPTIONS.get(t, {}).get("emoji", "🔧") for t in state.technologies]
        lines.append(f"• Технологии: {' '.join(tech_texts)}")
    else:
        lines.append("• Технологии: Любые")
    
    # Частота
    freq_text = FREQUENCY_OPTIONS.get(state.frequency, {}).get("text", "Мгновенно")
    lines.append(f"• Уведомления: {freq_text}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Тестирование
    manager = get_onboarding_manager()
    state = manager.get_state(12345)
    
    print("Initial state:")
    print(f"  Step: {state.step}")
    print(f"  Progress: {manager.get_progress_text(12345)}")
    
    # Симуляция онбординга
    manager.update_state(12345, level_preference="junior")
    manager.next_step(12345)
    manager.toggle_category(12345, "development")
    manager.toggle_category(12345, "qa")
    manager.next_step(12345)
    manager.update_state(12345, work_format="remote")
    manager.next_step(12345)
    manager.toggle_technology(12345, "python")
    manager.toggle_technology(12345, "javascript")
    manager.next_step(12345)
    manager.update_state(12345, frequency="digest_morning")
    manager.complete_onboarding(12345)
    
    print("\nFinal state:")
    print(format_user_preferences(state))
