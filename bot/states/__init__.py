from aiogram.fsm.state import State, StatesGroup


class AccountStates(StatesGroup):
    choosing_method = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()
    waiting_qr = State()
    waiting_tdata = State()


class AdminStates(StatesGroup):
    waiting_start_message = State()
    waiting_start_preview_confirm = State()
    waiting_access_search = State()


class BroadcastStates(StatesGroup):
    waiting_message = State()
    waiting_confirm = State()


class SettingsStates(StatesGroup):
    waiting_delay = State()
    waiting_hourly = State()
    waiting_daily = State()
