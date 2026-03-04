from aiogram.fsm.state import State, StatesGroup


class SettingsFlow(StatesGroup):
    choosing_country = State()
    choosing_city = State()
    choosing_center = State()
    choosing_visa_type = State()
    choosing_date_from = State()
    choosing_date_to = State()
    choosing_weekdays = State()
    choosing_time_from = State()
    choosing_time_to = State()
    choosing_applicants = State()


class CredentialsFlow(StatesGroup):
    entering_email = State()
    entering_password = State()


class VfsTokenFlow(StatesGroup):
    entering_authorize = State()
    entering_clientsource = State()


class BookingFlow(StatesGroup):
    waiting_user_action = State()
    entering_code = State()
