"""Russian <-> English mappings for countries and cities."""

COUNTRIES_RU_TO_EN: dict[str, str] = {
    "Германия": "Germany",
    "Франция": "France",
    "Италия": "Italy",
    "Испания": "Spain",
    "Нидерланды": "Netherlands",
    "Австрия": "Austria",
    "Польша": "Poland",
    "Чехия": "Czech Republic",
    "Греция": "Greece",
    "Португалия": "Portugal",
}

COUNTRIES_EN_TO_RU: dict[str, str] = {v: k for k, v in COUNTRIES_RU_TO_EN.items()}

CITIES_RU_TO_EN: dict[str, str] = {
    # Germany
    "Берлин": "Berlin",
    "Мюнхен": "Munich",
    "Франкфурт": "Frankfurt",
    "Гамбург": "Hamburg",
    "Дюссельдорф": "Dusseldorf",
    # France
    "Париж": "Paris",
    "Лион": "Lyon",
    "Марсель": "Marseille",
    # Italy
    "Рим": "Rome",
    "Милан": "Milan",
    # Spain
    "Мадрид": "Madrid",
    "Барселона": "Barcelona",
    # Netherlands
    "Гаага": "The Hague",
    "Амстердам": "Amsterdam",
    # Austria
    "Вена": "Vienna",
    # Poland
    "Варшава": "Warsaw",
    "Краков": "Krakow",
    # Czech Republic
    "Прага": "Prague",
    # Greece
    "Афины": "Athens",
    "Салоники": "Thessaloniki",
    # Portugal
    "Лиссабон": "Lisbon",
    # Russia (for TLScontact origin cities)
    "Москва": "Moscow",
    "Санкт-Петербург": "Saint Petersburg",
    "Новосибирск": "Novosibirsk",
    "Калининград": "Kaliningrad",
    "Екатеринбург": "Yekaterinburg",
}

CITIES_EN_TO_RU: dict[str, str] = {v: k for k, v in CITIES_RU_TO_EN.items()}


def normalize_country(text: str) -> str:
    """Convert Russian country name to English, or return as-is if already English."""
    text = text.strip()
    return COUNTRIES_RU_TO_EN.get(text, text)


def normalize_city(text: str) -> str:
    """Convert Russian city name to English, or return as-is if already English."""
    text = text.strip()
    return CITIES_RU_TO_EN.get(text, text)


def country_display(name: str) -> str:
    """Get Russian display name for a country."""
    ru = COUNTRIES_EN_TO_RU.get(name)
    return f"{ru} ({name})" if ru else name


def city_display(name: str) -> str:
    """Get Russian display name for a city."""
    ru = CITIES_EN_TO_RU.get(name)
    return f"{ru} ({name})" if ru else name
