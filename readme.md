# GoldForum Telegram Bot

Telegram-бот для взаимодействия с GoldForum API: чтение постов, комментариев, управление избранным и авторизация — всё через мессенджер.

## Как это работает

```
Telegram  ←→  app.py (python-telegram-bot)  ←→  src/client.py (aiohttp)  ←→  GoldForum API
                                                 ↓
                                            src/database/ (aiosqlite)
```

1. **app.py** — точка входа. Регистрирует обработчики команд Telegram, управляет жизненным циклом бота.
2. **src/client.py** — асинхронный HTTP-клиент к GoldForum REST API. Поддерживает cookie-сессии (Flask-Login), авторизацию, авто-реавторизацию при 401.
3. **src/database/models.py** — лёгкая прослойка над SQLite. Хранит `telegram_id`, `username`, `password` и `phone` пользователей бота (нужно для авто-реавторизации).

## Структура проекта

```
TG-repository/
├── app.py                  # Точка входа — регистрация команд и запуск бота
├── src/
│   ├── __init__.py
│   ├── client.py           # Асинхронный HTTP-клиент GoldForum API
│   └── database/
│       ├── __init__.py
│       └── models.py       # SQLite-модели (таблица users)
├── data/                   # SQLite БД (bot.db) — создаётся автоматически
├── .env.example            # Шаблон переменных окружения
├── API_DOCUMENTATION.md    # Документация GoldForum REST API
├── requirements.txt        # Зависимости Python
└── readme.md               # Этот файл
```

## Установка

```bash
# 1. Клонировать репозиторий
cd TG-repository

# 2. Создать виртуальное окружение
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate   # Linux/macOS

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Настроить переменные окружения
cp .env.example .env
# Отредактировать .env — подставить реальные значения
```

## Переменные окружения (.env)

| Переменная    | Назначение                                      | Обязательно |
|---------------|-------------------------------------------------|-------------|
| `BOT_TOKEN`   | Токен Telegram-бота (получить у @BotFather)      | Да          |
| `API_BASE_URL`| Базовый URL GoldForum API                       | Да          |
| `PROXY_URL`   | HTTP/HTTPS/SOCKS5-прокси для обхода блокировок   | Нет         |

Пример `.env`:
```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
API_BASE_URL=https://api.goldforum.example.com
PROXY_URL=socks5://127.0.0.1:9150
```

## Запуск

```bash
python app.py
```

Бот запустится в режиме long polling. При успешном подключении в логах появится:
```
Connected as @your_bot_name (id=...)
Bot started
```

## Команды бота

| Команда                      | Описание                                  | Требует авторизации |
|------------------------------|-------------------------------------------|---------------------|
| `/start`                     | Главное меню, статус и список команд       | Нет                 |
| `/login <пароль> <username>` | Вход в GoldForum API                      | Нет                 |
| `/favorites`                 | Список избранных постов                   | Да                  |
| `/post <ID>`                 | Метаданные и содержимое поста по номеру    | Да                  |
| `/comments <ID>`             | Комментарии к посту                       | Нет                 |
| `/addcomment <ID> <текст>`   | Добавить комментарий к посту              | Да                  |

### Примеры использования

```
/login mypassword myusername
/favorites
/post 42
/comments 42
/addcomment 42 Отличный пост, спасибо!
```

## Авторизация и сессии

- Бот использует cookie-сессию aiohttp (`CookieJar`) — аналог браузерной сессии.
- После `/login` учётные данные сохраняются в SQLite и используются для автоматической реавторизации при 401.
- Если сессия протухла, клиент сам перелогинится прозрачно для пользователя.

## База данных

SQLite-файл `data/bot.db`, таблица `users`:

| Поле          | Тип     | Описание                           |
|---------------|---------|------------------------------------|
| `telegram_id` | INTEGER | PRIMARY KEY — ID пользователя в TG |
| `phone`       | TEXT    | Номер телефона (если был передан)   |
| `username`    | TEXT    | Логин в GoldForum API              |
| `password`    | TEXT    | Пароль в GoldForum API             |
| `is_registered`| BOOLEAN| Зарезервировано                    |

База создаётся автоматически при первом запуске (`data/` тоже).

## HTTP-клиент (src/client.py)

`APIClient` — основной класс для взаимодействия с API.

### Методы

| Метод                | HTTP-запрос                                     | Описание                              |
|----------------------|-------------------------------------------------|---------------------------------------|
| `auth_user(u, p)`    | `POST /api/v1/auth/login`                       | Вход, сохраняет учётные данные         |
| `get_post(id)`       | `GET /api/v1/posts/<id>/metadata` + `/export`   | Метаданные + контент поста (из zip)    |
| `get_comments(id)`   | `GET /api/v1/posts/<id>/comments`               | Список комментариев                    |
| `add_comment(id, t)` | `POST /api/v1/posts/<id>/comments`              | Добавить комментарий                   |
| `get_favorites(u, p)`| `POST /api/v1/users/<u>/favorites/export`       | Экспорт избранного (zip)               |

### Особенности

- **`get_post`** делает два запроса: metadata (без авторизации) и export (zip-архив с `post.md` и вложениями). Клиент извлекает текст поста из архива в поле `content`.
- **`get_favorites`** парсит zip-архив и извлекает список постов из `metadata.json`, либо — запасной вариант — из структуры директорий архива.
- **`_ensure_auth()`** — проверяет активность сессии и при необходимости перелогинивается. Вызывается внутри методов, требующих авторизации.

## Полный сценарий использования

```python
import asyncio
from src.client import APIClient

async def main():
    client = APIClient("https://api.goldforum.example.com")

    # 1. Вход
    ok, data = await client.auth_user("myuser", "mypassword")
    print("Авторизован:", ok, data)

    # 2. Получить пост
    post = await client.get_post(42)
    print("Заголовок:", post.get("title"))
    print("Контент:", post.get("content", "")[:200])

    # 3. Комментарии
    comments = await client.get_comments(42)
    print("Комментариев:", len(comments))

    # 4. Избранное
    favs = await client.get_favorites("myuser", "mypassword")
    print("Избранное:", favs)

    await client.close()

asyncio.run(main())
```

## Требования

- Python 3.9+
- Зависимости из `requirements.txt`:
  - `python-telegram-bot[socks]>=22.0` — фреймворк для Telegram Bot API (с опциональной поддержкой SOCKS-прокси)
  - `aiohttp==3.9.1` — асинхронный HTTP-клиент
  - `aiosqlite==0.19.0` — асинхронный драйвер SQLite
  - `python-dotenv==1.0.0` — загрузка `.env`

## Устранение неполадок

| Симптом                                  | Вероятная причина / Решение                              |
|------------------------------------------|----------------------------------------------------------|
| Бот не отвечает на команды               | Проверить `BOT_TOKEN` в `.env` и интернет-соединение     |
| `ProxyError` или таймаут при запуске     | Указать `PROXY_URL` в `.env` (РФ-блокировки TG)          |
| `❌ Неверный пароль` после `/post`       | Пароль изменён на сервере — выполнить `/login` заново    |
| `❌ Сначала авторизуйтесь`               | Выполнить `/login <пароль> <username>`                   |
| `❌ Ошибка` без деталей                  | Проверить `API_BASE_URL`, доступность сервера и логи     |
