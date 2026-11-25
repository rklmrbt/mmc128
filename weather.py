"""
Погода через Open-Meteo — бесплатный сервис без API-ключа:
https://open-meteo.com/

1) геокодинг: название города -> координаты
2) прогноз: координаты -> текущая погода + прогноз на сегодня
"""

import asyncio
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Коды погоды WMO -> (текст, эмодзи)
WEATHER_CODES = {
    0: ("ясно", "☀️"),
    1: ("преимущественно ясно", "🌤"),
    2: ("переменная облачность", "⛅"),
    3: ("пасмурно", "☁️"),
    45: ("туман", "🌫"),
    48: ("изморозь", "🌫"),
    51: ("лёгкая морось", "🌦"),
    53: ("морось", "🌦"),
    55: ("сильная морось", "🌧"),
    61: ("небольшой дождь", "🌧"),
    63: ("дождь", "🌧"),
    65: ("сильный дождь", "🌧"),
    71: ("небольшой снег", "🌨"),
    73: ("снег", "🌨"),
    75: ("сильный снег", "❄️"),
    77: ("снежная крупа", "🌨"),
    80: ("ливень", "🌧"),
    81: ("сильный ливень", "🌧"),
    82: ("очень сильный ливень", "⛈"),
    85: ("снегопад", "🌨"),
    86: ("сильный снегопад", "❄️"),
    95: ("гроза", "⛈"),
    96: ("гроза с градом", "⛈"),
    99: ("сильная гроза с градом", "⛈"),
}


def describe_code(code: int) -> tuple[str, str]:
    return WEATHER_CODES.get(code, ("погода", "🌡"))


async def geocode_city(session: aiohttp.ClientSession, city: str) -> Optional[dict]:
    params = {"name": city, "count": 1, "language": "ru", "format": "json"}
    try:
        async with session.get(GEOCODE_URL, params=params, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("Geocoding request failed for %r: %s", city, type(exc).__name__)
        return None

    results = data.get("results")
    if not results:
        return None

    first = results[0]
    return {
        "name": first.get("name"),
        "country": first.get("country"),
        "lat": first["latitude"],
        "lon": first["longitude"],
    }


async def fetch_weather(session: aiohttp.ClientSession, lat: float, lon: float) -> Optional[dict]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",
    }
    try:
        async with session.get(FORECAST_URL, params=params, timeout=10) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("Forecast request failed for (%s, %s): %s", lat, lon, type(exc).__name__)
        return None


def format_weather_message(geo: dict, weather: dict) -> str:
    current = weather.get("current_weather", {})
    daily = weather.get("daily", {})

    temp_now = current.get("temperature")
    wind = current.get("windspeed")
    code = current.get("weathercode", 0)
    desc, emoji = describe_code(code)

    today_max = daily.get("temperature_2m_max", [None])[0]
    today_min = daily.get("temperature_2m_min", [None])[0]
    rain_chance = daily.get("precipitation_probability_max", [None])[0]

    location = geo["name"]
    if geo.get("country"):
        location = f"{location}, {geo['country']}"

    lines = [
        f"{emoji} <b>Погода — {location}</b>",
        f"Сейчас: {temp_now}°C, {desc}, ветер {wind} км/ч",
    ]
    if today_max is not None and today_min is not None:
        lines.append(f"Сегодня: от {today_min}°C до {today_max}°C")
    if rain_chance is not None:
        lines.append(f"Вероятность осадков: {rain_chance}%")

    return "\n".join(lines)
