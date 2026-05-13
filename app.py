import os
import logging
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.database.models import Database
from src.client import APIClient

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_BASE_URL = os.getenv('API_BASE_URL', 'https://api.example.com')
PROXY_URL = os.getenv('PROXY_URL')

db = Database()
api_client = APIClient(API_BASE_URL)

ROADMAP = """
🗺️ *ДОРОЖНАЯ КАРТА ФУНКЦИЙ*

📱 */start* — главное меню и статус

🔑 */login <пароль> <username>* — авторизация
   _Пример:_ `/login mypass myuser`

⭐ */favorites* — избранные посты

📝 */post <ID>* — пост по номеру
   _Пример:_ `/post 123`

💬 */comments <ID>* — комментарии к посту
   _Пример:_ `/comments 123`

✍️ */addcomment <ID> <текст>* — добавить комментарий
   _Пример:_ `/addcomment 123 Привет!`
"""

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("/start from user %s", update.effective_user.id)
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    
    status_msg = "📱 Статус: Не зарегистрирован"
    if user and user.get('username'):
        status_msg = f"👤 Авторизован: {user['username']}"
    
    await update.message.reply_text(
        f"{ROADMAP}\n{status_msg}",
        parse_mode="Markdown",
    )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Используйте: /login <пароль> <username>\n"
            "Пример: /login mypass myuser",
        )
        return

    password = context.args[0]
    username = context.args[1]

    try:
        is_valid, auth_data = await api_client.auth_user(username, password)

        if is_valid:
            await db.save_user(user_id, username=username, password=password)
            await update.message.reply_text(f"✅ Успешная авторизация: {username}")
        else:
            await update.message.reply_text("❌ Неверный логин или пароль")
    except Exception as e:
        logger.error("Login error: %s", e)
        await update.message.reply_text("❌ Ошибка авторизации")

async def favorites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)

    if not user or not user.get('username'):
        await update.message.reply_text("❌ Сначала авторизуйтесь — /login")
        return

    try:
        favorites = await api_client.get_favorites(user['username'], user['password'])

        # Авто-реавторизация при None (401 — неверный пароль)
        if favorites is None:
            ok, _ = await api_client.auth_user(user['username'], user['password'])
            if ok:
                favorites = await api_client.get_favorites(user['username'], user['password'])

        if favorites is None:
            await update.message.reply_text(
                "❌ Неверный пароль. Пройдите /login заново"
            )
            return
        if not favorites:
            await update.message.reply_text("📭 Пусто")
            return

        msg = "📚 Избранные:\n\n"
        for post in favorites:
            if isinstance(post, dict):
                pid = post.get('id', '?')
                title = post.get('title', '')
                line = f"🔹 ID: {pid}"
                if title:
                    line += f" — {title}"
                msg += line + "\n"
            else:
                msg += f"🔹 {post}\n"
        await update.message.reply_text(msg)
    except Exception:
        await update.message.reply_text("❌ Ошибка")

async def get_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используйте: /post <ID>")
        return

    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    if not user or not user.get('username'):
        await update.message.reply_text("❌ Сначала авторизуйтесь — /login")
        return

    post_id = context.args[0]
    try:
        post = await api_client.get_post(post_id)

        # Авто-реавторизация при 401
        if 'error' in post and '401' in str(post['error']):
            ok, _ = await api_client.auth_user(user['username'], user['password'])
            if ok:
                post = await api_client.get_post(post_id)

        if 'error' in post:
            err = post['error']
            if '401' in str(err):
                await update.message.reply_text("❌ Неверный пароль. Пройдите /login заново")
            else:
                await update.message.reply_text(f"❌ Ошибка: {err}")
            return

        content = post.get('content', '')
        if '401' in content:
            ok, _ = await api_client.auth_user(user['username'], user['password'])
            if ok:
                post = await api_client.get_post(post_id)
                content = post.get('content', '')

        if '401' in content:
            await update.message.reply_text("❌ Неверный пароль. Пройдите /login заново")
            return

        # Telegram-сообщение не может быть длиннее 4096 символов
        if len(content) > 3800:
            content = content[:3800] + "\n\n...(обрезано)"

        images = post.get('attached_images', [])
        files = post.get('attached_files', [])

        msg = (
            f"📝 Пост #{post.get('id')}\n"
            f"📌 {post.get('title', 'Без названия')}\n"
            f"👤 {post.get('author', '?')}\n"
            f"🕐 {post.get('created_at', '?')}\n"
            f"📎 Изображений: {len(images)}, Файлов: {len(files)}"
        )
        if images:
            msg += f"\n🖼 {', '.join(images)}"
        if files:
            msg += f"\n📄 {', '.join(files)}"
        msg += f"\n\n{content}"

        await update.message.reply_text(msg)
    except Exception as e:
        logger.error("get_post_command error: %s", e)
        await update.message.reply_text("❌ Ошибка")

async def get_comments_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используйте: /comments <ID>")
        return
    
    post_id = context.args[0]
    try:
        comments = await api_client.get_comments(post_id)
        if not comments:
            await update.message.reply_text("💬 Нет комментариев")
            return
        
        msg = f"💬 Комментарии к #{post_id}:\n\n"
        for c in comments:
            msg += f"👤 {c.get('username', '?')}: {c.get('content', '')}\n"
        await update.message.reply_text(msg)
    except Exception:
        await update.message.reply_text("❌ Ошибка")

async def add_comment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    
    if not user or not user.get('username'):
        await update.message.reply_text("❌ Сначала авторизуйтесь — /login")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Используйте: /addcomment <ID> <текст>")
        return
    
    post_id = context.args[0]
    text = ' '.join(context.args[1:])
    
    try:
        success = await api_client.add_comment(post_id, text)

        # Авто-реавторизация при неудаче
        if not success:
            ok, _ = await api_client.auth_user(user['username'], user['password'])
            if ok:
                success = await api_client.add_comment(post_id, text)

        if success:
            await update.message.reply_text("✅ Добавлено")
        else:
            await update.message.reply_text("❌ Не удалось")
    except Exception:
        await update.message.reply_text("❌ Ошибка")

async def post_init(application: Application):
    bot_info = await application.bot.get_me()
    logger.info("Connected as @%s (id=%s)", bot_info.username, bot_info.id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Update %s caused error: %s", update, context.error)

def create_data_folder():
    Path('data').mkdir(exist_ok=True)

def main():
    create_data_folder()
    asyncio.run(db.init_db())

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing. Create a .env file (see .env.example)")
        return

    builder = Application.builder().token(BOT_TOKEN)
    builder = builder.connect_timeout(30).read_timeout(30).write_timeout(30)
    if PROXY_URL:
        os.environ['HTTPS_PROXY'] = PROXY_URL
        os.environ['HTTP_PROXY'] = PROXY_URL
        logger.info("Using proxy: %s", PROXY_URL)
    application = builder.build()
    application.post_init = post_init
    application.add_error_handler(error_handler)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("favorites", favorites_command))
    application.add_handler(CommandHandler("post", get_post_command))
    application.add_handler(CommandHandler("comments", get_comments_command))
    application.add_handler(CommandHandler("addcomment", add_comment_command))

    logger.info("Bot started")
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            close_loop=False,
            bootstrap_retries=5,
            timeout=0,
            poll_interval=1.0,
        )
    except Exception as e:
        logger.error("Bot error: %s", e)
    finally:
        asyncio.run(api_client.close())

if __name__ == '__main__':
    main()
