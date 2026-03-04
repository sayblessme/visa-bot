from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Выбрать провайдера"), KeyboardButton(text="Выбрать страну")],
            [KeyboardButton(text="Фильтры"), KeyboardButton(text="Учётные данные")],
            [KeyboardButton(text="Включить мониторинг"), KeyboardButton(text="Выключить мониторинг")],
            [KeyboardButton(text="Автозапись: Вкл"), KeyboardButton(text="Автозапись: Выкл")],
            [KeyboardButton(text="Статус"), KeyboardButton(text="История попыток")],
        ],
        resize_keyboard=True,
    )


def countries_kb() -> InlineKeyboardMarkup:
    countries = [
        ("Германия", "Germany"),
        ("Франция", "France"),
        ("Италия", "Italy"),
        ("Испания", "Spain"),
        ("Нидерланды", "Netherlands"),
        ("Австрия", "Austria"),
        ("Польша", "Poland"),
        ("Чехия", "Czech Republic"),
        ("Греция", "Greece"),
        ("Португалия", "Portugal"),
    ]
    buttons = [
        [InlineKeyboardButton(text=ru, callback_data=f"country:{en}")]
        for ru, en in countries
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cities_kb(country: str) -> InlineKeyboardMarkup:
    """Dynamic city keyboard based on selected country."""
    from app.utils.i18n import CITIES_EN_TO_RU

    city_map: dict[str, list[str]] = {
        "Germany": ["Berlin", "Munich", "Frankfurt", "Hamburg", "Dusseldorf"],
        "France": ["Paris", "Lyon", "Marseille"],
        "Italy": ["Rome", "Milan"],
        "Spain": ["Madrid", "Barcelona"],
        "Netherlands": ["The Hague", "Amsterdam"],
        "Austria": ["Vienna"],
        "Poland": ["Warsaw", "Krakow"],
        "Czech Republic": ["Prague"],
        "Greece": ["Athens", "Thessaloniki"],
        "Portugal": ["Lisbon"],
    }
    cities = city_map.get(country, [])
    buttons = []
    for city_en in cities:
        city_ru = CITIES_EN_TO_RU.get(city_en, city_en)
        buttons.append(
            [InlineKeyboardButton(text=city_ru, callback_data=f"city:{city_en}")]
        )
    buttons.append(
        [InlineKeyboardButton(text="Ввести вручную", callback_data="city:manual")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def filters_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Город", callback_data="filter:city")],
            [InlineKeyboardButton(text="Визовый центр", callback_data="filter:center")],
            [InlineKeyboardButton(text="Тип визы", callback_data="filter:visa_type")],
            [InlineKeyboardButton(text="Дата от", callback_data="filter:date_from")],
            [InlineKeyboardButton(text="Дата до", callback_data="filter:date_to")],
            [InlineKeyboardButton(text="Дни недели", callback_data="filter:weekdays")],
            [InlineKeyboardButton(text="Кол-во заявителей", callback_data="filter:applicants")],
            [InlineKeyboardButton(text="Готово", callback_data="filter:done")],
        ]
    )


def providers_kb() -> InlineKeyboardMarkup:
    providers = [
        ("VFS Global", "vfs_global"),
        ("TLScontact", "tlscontact"),
        ("BLS Spain", "bls_spain"),
        ("Mock (тест)", "mock"),
    ]
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"provider:{value}")]
        for label, value in providers
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def booking_action_kb(attempt_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Готово / Продолжить",
                    callback_data=f"booking_continue:{attempt_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Ввести код",
                    callback_data=f"booking_code:{attempt_id}",
                )
            ],
        ]
    )
