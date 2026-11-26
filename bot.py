import asyncio
import logging
import os

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
        Message,
    WebAppInfo,
)

import storage
import weather

logging.basicConfig(level=logging.INFO)
RADIO_WEBAPP_URL = "https://rklmrbt.github.io/mmc128/radio.html"
# Токен бота — получи у @BotFather в Telegram (или задай переменную окружения BOT_TOKEN)
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН")

# Картинка главного меню — положи файл рядом со скриптом под этим именем
MENU_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "media_center.jpg")

MENU_TEXT = (
    "✨ <b>MY MEDIA CENTER</b>\n"
    "Твоё личное медиапространство\n\n"
    "Выбери нужный раздел:"
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Общая aiohttp-сессия для запросов к погодному API
http_session: aiohttp.ClientSession | None = None


class WeatherStates(StatesGroup):
    waiting_for_city = State()


# ──────────────────────────────────────────────────────────────────────────
# ГЛАВНОЕ МЕНЮ
#
# Музыка / Видео / Фото / Файлы / Заметки — ссылки на соответствующие ветки
# (топики) в твоей группе. ЗАМЕНИ плейсхолдеры ниже на реальные ссылки —
# в Telegram Desktop/Web открой нужную ветку → "⋮" → "Копировать ссылку".
#
# Радио — пока тоже плейсхолдер: пришли мне тот html-файл, и я решим,
# вшить ли его как Telegram Web App (откроется прямо внутри бота) или
# просто повесить ссылку на уже готовую страницу.
#
# Погода — уже рабочая, через callback-кнопку (см. ниже).
# ──────────────────────────────────────────────────────────────────────────

TOPIC_LINKS = {
    "music": "https://t.me/c/3991721169/3",
    "video": "https://t.me/c/3991721169/4",
    "photo": "https://t.me/c/3991721169/5",
    "files": "https://t.me/c/3991721169/6",
    "notes": "https://t.me/c/3991721169/7",
    # Временно — ссылка на ветку "Радио" в группе. Как только пришлёшь html-файл,
    # заменим эту кнопку на Web App, который откроется прямо внутри бота.
    
}


def build_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🎵 Музыка", url=TOPIC_LINKS["music"]),
            InlineKeyboardButton(text="🎬 Видео", url=TOPIC_LINKS["video"]),
        ],
        [
            InlineKeyboardButton(text="📷 Фото", url=TOPIC_LINKS["photo"]),
            InlineKeyboardButton(text="📁 Файлы", url=TOPIC_LINKS["files"]),
        ],
        [
            InlineKeyboardButton(text="📝 Заметки", url=TOPIC_LINKS["notes"]),
            InlineKeyboardButton(text="📻 Радио", web_app=WebAppInfo(url=RADIO_WEBAPP_URL)),
        ],
        [
            InlineKeyboardButton(text="☀️ Погода", callback_data="weather"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart())
async def send_main_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    keyboard = build_menu_keyboard()

    if os.path.exists(MENU_IMAGE_PATH):
        photo = FSInputFile(MENU_IMAGE_PATH)
        await message.answer_photo(photo=photo, caption=MENU_TEXT, reply_markup=keyboard)
    else:
        await message.answer(MENU_TEXT, reply_markup=keyboard)


# ──────────────────────────────────────────────────────────────────────────
# ПОГОДА
# ──────────────────────────────────────────────────────────────────────────

def change_city_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📍 Сменить город", callback_data="weather_setcity")]
        ]
    )


async def send_weather_for_city(chat_id: int, city: str) -> str:
    """Запрашивает погоду и возвращает готовый текст сообщения (или текст ошибки)."""
    geo = await weather.geocode_city(http_session, city)
    if geo is None:
        return f"Не нашёл город «{city}». Попробуй написать по-другому."

    data = await weather.fetch_weather(http_session, geo["lat"], geo["lon"])
    if data is None:
        return "Сервис погоды сейчас недоступен, попробуй чуть позже."

    return weather.format_weather_message(geo, data)


@dp.callback_query(F.data == "weather")
async def on_weather_button(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    saved_city = storage.get_city(callback.from_user.id)

    if saved_city is None:
        await state.set_state(WeatherStates.waiting_for_city)
        await callback.message.answer("Напиши название своего города — сохраню и буду присылать погоду по нему.")
        return

    text = await send_weather_for_city(callback.message.chat.id, saved_city)
    await callback.message.answer(text, reply_markup=change_city_keyboard())


@dp.callback_query(F.data == "weather_setcity")
async def on_change_city(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(WeatherStates.waiting_for_city)
    await callback.message.answer("Напиши новый город:")


@dp.message(WeatherStates.waiting_for_city)
async def on_city_input(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    text = await send_weather_for_city(message.chat.id, city)

    if text.startswith("Не нашёл город"):
        # остаёмся в том же состоянии, пусть попробует ещё раз
        await message.answer(text)
        return

    storage.set_city(message.from_user.id, city)
    await state.clear()
    await message.answer(text, reply_markup=change_city_keyboard())


# ──────────────────────────────────────────────────────────────────────────

async def main() -> None:
    global http_session
    http_session = aiohttp.ClientSession()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await http_session.close()


if __name__ == "__main__":
    asyncio.run(main())
