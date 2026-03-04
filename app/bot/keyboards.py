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
            [KeyboardButton(text="Фильтры"), KeyboardButton(text="Статус")],
            [KeyboardButton(text="Включить мониторинг"), KeyboardButton(text="Выключить мониторинг")],
            [KeyboardButton(text="Автозапись: Вкл"), KeyboardButton(text="Автозапись: Выкл")],
            [KeyboardButton(text="История попыток")],
        ],
        resize_keyboard=True,
    )


def countries_kb() -> InlineKeyboardMarkup:
    countries = [
        "Germany", "France", "Italy", "Spain", "Netherlands",
        "Austria", "Poland", "Czech Republic", "Greece", "Portugal",
    ]
    buttons = [
        [InlineKeyboardButton(text=c, callback_data=f"country:{c}")]
        for c in countries
    ]
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
