"""
Простое хранилище "город пользователя" в JSON-файле.
Для личного/небольшого бота этого достаточно — не нужна база данных.
"""

import json
import os
from typing import Optional

STORAGE_PATH = os.path.join(os.path.dirname(__file__), "user_cities.json")


def _load() -> dict:
    if not os.path.exists(STORAGE_PATH):
        return {}
    try:
        with open(STORAGE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    with open(STORAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_city(user_id: int) -> Optional[str]:
    data = _load()
    return data.get(str(user_id))


def set_city(user_id: int, city: str) -> None:
    data = _load()
    data[str(user_id)] = city
    _save(data)
