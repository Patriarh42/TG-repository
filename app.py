import os
import logging
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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

db = Database()
api_client = APIClient(API_BASE_URL)

ROADMAP = """
🗺️ ДОРОЖНАЯ КАРТА ФУНКЦИЙ

1️⃣ Старт - это сообщение
2️⃣ Проверка телефона: /phone <номер>
   Пример: /phone +79991234567

3️⃣ Авторизация: "запомни меня"
   Формат:
   запомни меня
   <пароль>, <username>

4️⃣ Избранные: /favorites
5️⃣ Пост по ID: /post <ID>
6️⃣ Комментарии: /comments <ID>
7️⃣ Добавить комментарий: /addcomment <ID> <текст>
"""

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    
    status_msg = "📱 Статус: Не зарегистрирован"
    if user and user.get('username'):
        status_msg = f"👤 Авторизован: {user['username']}"
    
    await update.message.reply_text(f"{ROADMAP}\n{status_msg}")

async def phone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используйте: /phone <номер>")
        return
    
    phone = context.args[0]
    user_id = update.effective_user.id
    
    try:
        is_registered = await api_client.check_phone_registered(phone)
        await db.save_user(user_id, phone=phone)
        status = "✅ Зарегистрирован" if is_registered else "❌ Не зарегистрирован"
        await update.message.reply_text(f"📱 {phone}: {status}")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Ошибка")

async def remember_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lines = text.split('\n')
    
    if len(lines) < 2 or lines[0].lower() != 'запомни меня':
        return
    
    try:
        credentials = lines[1].split(',')
        if len(credentials) != 2:
            raise ValueError("Invalid format")
        
        password = credentials[0].strip()
        username = credentials[1].strip()
        
        if not password or not username:
            raise ValueError("Empty values")
        
        is_valid = await api_client.auth_user(username, password)
        
        if is_valid:
            user_id = update.effective_user.id
            await db.save_user(user_id, username=username, password=password)
            await update.message.reply_text(f"✅ Успешно: {username}")
        else:
            await update.message.reply_text("❌ Неверный логин или пароль")
    
    except Exception:
        await update.message.reply_text("❌ Ошибка формата: запомни меня\\n<пароль>, <username>")

async def favorites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    
    if not user or not user.get('username'):
        await update.message.reply_text("❌ Сначала авторизуйтесь")
        return
    
    try:
        favorites = await api_client.get_favorites(user['username'])
        if not favorites:
            await update.message.reply_text("📭 Пусто")
            return
        
        msg = "📚 Избранные:\n\n"
        for post in favorites:
            msg += f"🔹 ID: {post['id']} - {post.get('title', 'No title')}\n"
        await update.message.reply_text(msg)
    except Exception:
        await update.message.reply_text("❌ Ошибка")

async def get_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используйте: /post <ID>")
        return
    
    post_id = context.args[0]
    try:
        post = await api_client.get_post(post_id)
        msg = f" Пост #{post['id']}\n👤 {post.get('author', '?')}\n📝 {post.get('content', '')}"
        await update.message.reply_text(msg)
    except Exception:
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
            msg += f"👤 {c.get('author', '?')}: {c.get('text', '')}\n"
        await update.message.reply_text(msg)
    except Exception:
        await update.message.reply_text("❌ Ошибка")

async def add_comment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    
    if not user or not user.get('username'):
        await update.message.reply_text("❌ Сначала авторизуйтесь")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Используйте: /addcomment <ID> <текст>")
        return
    
    post_id = context.args[0]
    text = ' '.join(context.args[1:])
    
    try:
        success = await api_client.add_comment(post_id, text, user['username'])
        if success:
            await update.message.reply_text("✅ Добавлено")
        else:
            await update.message.reply_text("❌ Не удалось")
    except Exception:
        await update.message.reply_text("❌ Ошибка")

def create_data_folder():
    Path('data').mkdir(exist_ok=True)

def main():
    create_data_folder()
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN missing")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("phone", phone_command))
    application.add_handler(CommandHandler("favorites", favorites_command))
    application.add_handler(CommandHandler("post", get_post_command))
    application.add_handler(CommandHandler("comments", get_comments_command))
    application.add_handler(CommandHandler("addcomment", add_comment_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, remember_me))
    
    logger.info("Bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
