import os
import re
import time
import sqlite3
import requests
import imaplib
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import decode_header

BOT_EMAIL = os.getenv("BOT_EMAIL", "yourbot@gmail.com")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "your_app_password")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
API_BASE = "http://23.111.103.231"
DB_FILE = "bot.db"
TEMP_DIR = "tmp_exports"

os.makedirs(TEMP_DIR, exist_ok=True)

ROADMAP = """Добро пожаловать в GoldForum Email Bot!

ДОРОЖНАЯ КАРТА КОМАНД
(Команда пишется в ТЕМУ письма. Аргументы указываются в ТЕЛЕ письма через запятую и пробел: `, `)

1. запомни меня
   Порядок аргументов: username, password
   Проверяет данные через API и сохраняет их в боте.

2. скачать избранные посты
   Порядок аргументов: нет
   Отправляет ZIP-архив со всеми вашими избранными постами.

3. скачать пост по id
   Порядок аргументов: post_id
   Отправляет ZIP-архив с указанным постом.

4. получить комментарии к посту
   Порядок аргументов: post_id
   Отправляет список комментариев текстом.

5. добавить свой комментарий к посту
   Порядок аргументов: post_id, текст_комментария
   Публикует комментарий от вашего имени.

Все команды регистронезависимы.
"""

def init_database():
    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, username TEXT, password TEXT)")
    connection.commit()
    connection.close()

def get_user(email_address):
    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()
    cursor.execute("SELECT username, password FROM users WHERE email = ?", (email_address,))
    result = cursor.fetchone()
    connection.close()
    return result

def save_user(email_address, username, password):
    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (email, username, password) VALUES (?, ?, ?)", (email_address, username, password))
    connection.commit()
    connection.close()

def api_login(username, password):
    session = requests.Session()
    response = session.post(f"{API_BASE}/api/v1/auth/login", json={"username": username, "password": password}, timeout=10)
    data = response.json()
    if data.get("success"):
        return session
    return None

def send_email(to_address, subject, body, attachment_path=None):
    message = MIMEMultipart()
    message["From"] = BOT_EMAIL
    message["To"] = to_address
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(attachment_path)}"'
        message.attach(part)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, 465) as server:
            server.login(BOT_EMAIL, BOT_PASSWORD)
            server.send_message(message)
    except Exception as e:
        print(f"Error sending email: {e}")

def get_body_content(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
    return ""

def process_remember_me(sender_email, body_args):
    if len(body_args) != 2:
        return "Ошибка: формат команды `запомни меня` требует username и password через запятую.", None
    
    username = body_args[0]
    password = body_args[1]
    
    session = api_login(username, password)
    if not session:
        return "Ошибка: Неверный логин или пароль.", None
    
    save_user(sender_email, username, password)
    session.close()
    
    return "Профиль успешно сохранен.", None

def process_favorites(sender_email):
    user_data = get_user(sender_email)
    if not user_data:
        return "Вы не зарегистрированы. Используйте команду `запомни меня`.", None
    
    username = user_data[0]
    password = user_data[1]
    
    session = api_login(username, password)
    if not session:
        return "Ошибка авторизации.", None
    
    url = f"{API_BASE}/api/v1/users/{username}/favorites/export"
    response = session.post(url, json={"password": password}, timeout=60)
    session.close()
    
    if response.status_code != 200:
        return "Ошибка при экспорте избранного.", None
    
    file_path = os.path.join(TEMP_DIR, f"{username}_favorites.zip")
    with open(file_path, "wb") as f:
        f.write(response.content)
    
    return "Ваши избранные посты готовы.", file_path

def process_download_post(sender_email, body_args):
    user_data = get_user(sender_email)
    if not user_data:
        return "Вы не зарегистрированы.", None
    
    if len(body_args) != 1 or not body_args[0].isdigit():
        return "Ошибка: укажите корректный post_id.", None
    
    post_id = body_args[0]
    username = user_data[0]
    password = user_data[1]
    
    session = api_login(username, password)
    if not session:
        return "Ошибка авторизации.", None
    
    url = f"{API_BASE}/api/v1/posts/{post_id}/export"
    response = session.get(url, timeout=60)
    session.close()
    
    if response.status_code != 200:
        return f"Ошибка: пост с ID {post_id} не найден.", None
    
    file_path = os.path.join(TEMP_DIR, f"post_{post_id}.zip")
    with open(file_path, "wb") as f:
        f.write(response.content)
    
    return f"Пост {post_id} экспортирован.", file_path

def process_get_comments(sender_email, body_args):
    user_data = get_user(sender_email)
    if not user_data:
        return "Вы не зарегистрированы.", None
    
    if len(body_args) != 1 or not body_args[0].isdigit():
        return "Ошибка: укажите корректный post_id.", None
    
    post_id = body_args[0]
    username = user_data[0]
    password = user_data[1]
    
    session = api_login(username, password)
    if not session:
        return "Ошибка авторизации.", None
    
    url = f"{API_BASE}/api/v1/posts/{post_id}/comments"
    response = session.get(url, timeout=30)
    session.close()
    
    if response.status_code != 200:
        return "Не удалось получить комментарии.", None
    
    data = response.json()
    if not data.get("success"):
        return "Ошибка API при получении комментариев.", None
    
    comments = data.get("comments", [])
    if not comments:
        return f"К посту {post_id} нет комментариев.", None
    
    message_text = f"Комментарии к посту {post_id}:\n\n"
    for item in comments:
        message_text += f"{item['username']}: {item['content']}\n"
    
    return message_text, None

def process_add_comment(sender_email, body_args):
    user_data = get_user(sender_email)
    if not user_data:
        return "Вы не зарегистрированы.", None
    
    if len(body_args) < 2:
        return "Ошибка: формат `post_id, текст`.", None
    
    post_id = body_args[0]
    comment_text = ", ".join(body_args[1:])
    
    if not post_id.isdigit():
        return "Ошибка: post_id должен быть числом.", None
    
    username = user_data[0]
    password = user_data[1]
    
    session = api_login(username, password)
    if not session:
        return "Ошибка авторизации.", None
    
    url = f"{API_BASE}/api/v1/posts/{post_id}/comments"
    response = session.post(url, json={"content": comment_text}, timeout=30)
    session.close()
    
    if response.status_code != 200:
        return "Не удалось добавить комментарий.", None
    
    data = response.json()
    if data.get("success"):
        return f"Комментарий добавлен к посту {post_id}.", None
    else:
        return data.get("error", "Ошибка публикации."), None

def run_bot():
    init_database()
    print("Бот запущен.")
    
    while True:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST)
            mail.login(BOT_EMAIL, BOT_PASSWORD)
            mail.select("inbox")
            
            status, message_ids = mail.search(None, "UNSEEN")
            if status == "OK":
                for msg_id in message_ids[0].split():
                    status, msg_data = mail.fetch(msg_id, "(RFC822)")
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    from_header = msg.get("From")
                    decoded_from = decode_header(from_header)[0][0]
                    if isinstance(decoded_from, bytes):
                        decoded_from = decoded_from.decode("utf-8", errors="ignore")
                    
                    email_match = re.search(r"[\w\.-]+@[\w\.-]+", decoded_from)
                    sender_email = email_match.group(0) if email_match else decoded_from
                    
                    subject = msg.get("Subject")
                    decoded_subject = decode_header(subject)[0][0]
                    if isinstance(decoded_subject, bytes):
                        decoded_subject = decoded_subject.decode("utf-8", errors="ignore")
                    subject = decoded_subject.strip().lower()
                    
                    body = get_body_content(msg).strip()
                    body_args = [arg.strip() for arg in body.split(",")] if body else []
                    
                    user_data = get_user(sender_email)
                    
                    if not user_data:
                        send_email(sender_email, "GoldForum Bot", f"Вы не зарегистрированы.\n\n{ROADMAP}")
                        mail.store(msg_id, "+FLAGS", "\\Seen")
                        continue
                    
                    if subject == "запомни меня":
                        reply, file = process_remember_me(sender_email, body_args)
                    elif subject == "скачать избранные посты":
                        reply, file = process_favorites(sender_email)
                    elif subject == "скачать пост по id":
                        reply, file = process_download_post(sender_email, body_args)
                    elif subject == "получить комментарии к посту":
                        reply, file = process_get_comments(sender_email, body_args)
                    elif subject == "добавить свой комментарий к посту":
                        reply, file = process_add_comment(sender_email, body_args)
                    else:
                        reply = f"Неизвестная команда.\n\n{ROADMAP}"
                        file = None
                    
                    send_email(sender_email, f"Ответ: {subject}", reply, file)
                    
                    if file and os.path.exists(file):
                        os.remove(file)
                        
                    mail.store(msg_id, "+FLAGS", "\\Seen")
            
            mail.logout()
        except Exception as e:
            print(f"Ошибка: {e}")
        
        time.sleep(10)

if __name__ == "__main__":
    run_bot()
