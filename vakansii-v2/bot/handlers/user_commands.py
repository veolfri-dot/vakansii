import logging
import os
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from bot.config import WEBAPP_URL
from bot.services.job_service import JobService

router = Router()
logger = logging.getLogger(__name__)


class SubscribeForm(StatesGroup):
    """Состояния машины состояний для команды /subscribe."""

    keywords = State()
    min_salary = State()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик /start с кнопкой открытия WebApp."""
    web_app_button = InlineKeyboardButton(
        text="🌐 Открыть дашборд",
        web_app=WebAppInfo(url=WEBAPP_URL),
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[web_app_button]])
    await message.answer(
        "Добро пожаловать в агрегатор удаленных IT-вакансий. "
        "Нажмите кнопку ниже, чтобы открыть дашборд, или используйте /subscribe для настройки уведомлений.",
        reply_markup=keyboard,
    )


@router.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message, state: FSMContext):
    """Начало диалога подписки. Запрос ключевых слов."""
    await state.set_state(SubscribeForm.keywords)
    await message.answer(
        "Введите ключевые слова через запятую (например: Python, удаленка, Senior):"
    )


@router.message(SubscribeForm.keywords)
async def process_keywords(message: types.Message, state: FSMContext):
    """Сохранение ключевых слов и переход к запросу зарплаты."""
    await state.update_data(keywords=message.text)
    await state.set_state(SubscribeForm.min_salary)
    await message.answer("Введите минимальную зарплату в USD (0 — не важно):")


@router.message(SubscribeForm.min_salary)
async def process_min_salary(message: types.Message, state: FSMContext):
    """Сохранение подписки в БД и завершение диалога."""
    data = await state.get_data()
    keywords = data.get("keywords", "")
    try:
        min_salary = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")
        return

    user_id = message.from_user.id
    await JobService.save_subscription(
        user_id=user_id,
        keywords=keywords,
        min_salary=min_salary,
    )
    await state.clear()
    await message.answer(
        f"✅ Подписка активна!\nКлючевые слова: {keywords}\nМинимальная зарплата: ${min_salary}"
    )


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: types.Message):
    """Удаление подписки пользователя."""
    await JobService.delete_subscription(user_id=message.from_user.id)
    await message.answer("❌ Подписка удалена. Вы больше не будете получать уведомления.")


@router.message(Command("jobs"))
async def cmd_jobs(message: types.Message):
    """Вывод последних 5 вакансий из БД."""
    jobs = await JobService.get_filtered_jobs({"limit": 5})
    if not jobs:
        await message.answer("Вакансий пока нет.")
        return

    for job in jobs:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Открыть", url=job["source_url"]),
                    InlineKeyboardButton(text="Скрыть", callback_data="hide"),
                ]
            ]
        )
        text = (
            f"<b>{job['title']}</b>\n"
            f"🏢 {job['company']}\n"
            f"📍 {job['location'] or 'Remote'}\n"
            f"💰 ${job['salary_min_usd'] or '?'} — ${job['salary_max_usd'] or '?'}\n"
            f"🏷 {job['category']}"
        )
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "hide")
async def process_hide(callback: types.CallbackQuery):
    """Удаление сообщения по кнопке 'Скрыть'."""
    try:
        await callback.message.delete()
    except Exception as exc:
        logger.warning("Не удалось удалить сообщение: %s", exc)
    await callback.answer()
