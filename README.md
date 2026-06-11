# Telegram DM Bot

Бот для безопасной рассылки сообщений в личные сообщения Telegram через Pyrogram.

## Требования

- Python 3.11+
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- Telegram API ID / API Hash ([my.telegram.org](https://my.telegram.org))
- Telegram Premium у владельца бота (для premium-эмодзи в кнопках)

## Установка (Windows)

```powershell
cd telegram_dm_bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Заполните `.env`:

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен бота |
| `ADMIN_IDS` | Telegram ID админов через запятую |
| `TELEGRAM_API_ID` | API ID |
| `TELEGRAM_API_HASH` | API Hash |
| `PRIVATE_CHANNEL_ID` | ID приватного канала для статистики (опционально) |

## Запуск

```powershell
.venv\Scripts\activate
python main.py
```

## Команды

- `/start` — приветствие и главное меню
- `/admin` — админ-панель (только для ADMIN_IDS)

## Функции

- Вход в аккаунт: телефон, QR-код, TData (opentele)
- Загрузка списка получателей (.txt)
- Настройка КД между сообщениями и лимитов
- Рассылка в ЛС с защитой от FloodWait
- Админка: статистика, стартовое сообщение, выдача доступа

## Структура меню

| Кнопка | Описание |
|--------|----------|
| Профиль | Статус аккаунта и рассылки |
| Аккаунт | Подключение Pyrogram-сессии |
| Люди | Загрузка списка @username |
| Настройки | КД и лимиты |
| Рассылка | Запуск/остановка рассылки |

## TData

Отправьте ZIP-архив с папкой `tdata` из Telegram Desktop через меню «Аккаунт → Через TData».

## Безопасность

- Используйте КД 60–180 сек между сообщениями
- Не превышайте лимиты в час/день
- Temp-файлы сессий хранятся в `sessions/` и не должны попадать в git
