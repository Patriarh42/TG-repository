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
from dotenv import load_dotenv

load_dotenv()

BOT_EMAIL = os.getenv("BOT_EMAIL")
BOT_PASSWORD = os.getenv("BOT_PASSWORD")
IMAP_HOST = os.getenv("IMAP_HOST")
SMTP_HOST = os.getenv("SMTP_HOST")
API_BASE = os.getenv("GOLDFORUM_URL", "http://23.111.103.231")
DB_FILE = "bot.db"
DATA_DIR = "data"

os.makedirs(DATA_DIR, exist_ok=True)

ROADMAP = """Добро пожаловать в GoldForum Email Bot!

ДОРОЖНАЯ КАРТА КОМАНД
Команда пишется в ТЕМУ письма.
Аргументы указываются в ТЕЛЕ письма через запятую и пробел: `, `

1. запомни меня
   Аргументы: username, password
   Проверяет данные через API и сохраняет профиль.

2. скачать избранные посты
   Аргументы: не требуются
   Отправляет ZIP-архив со всеми избранными постами.

3. скачать пост по id
   Аргументы: post_id
   Отправляет ZIP-архив с указанным постом.

4. получить комментарии к посту
   Аргументы: post_id
   Возвращает список комментариев текстом.

5. добавить свой комментарий к посту
   Аргументы: post_id, текст комментария
   Публикует комментарий от вашего имени.
"""

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, username TEXT, password TEXT)")
    conn.commit()
    conn.close()

def get_user(email_addr):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT username, password FROM users WHERE email = ?", (email_addr,))
    result = cur.fetchone()
    conn.close()
    return result

def save_user(email_addr, username, password):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (email_addr, username, password))
    conn.commit()
    conn.close()

def api_login(username, password):
    session = requests.Session()
    response = session.post(f"{API_BASE}/api/v1/auth/login", json={"username": username, "password": password}, timeout=10)
    data = response.json()
    if data.get("success"):
        return session
    return None

def send_email(to_addr, subject, body, attach_path=None):
    msg = MIMEMultipart()
    msg["From"] = BOT_EMAIL
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if attach_path and os.path.exists(attach_path):
        with open(attach_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(attach_path))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(attach_path)}"'
        msg.attach(part)
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, 465) as server:
            server.login(BOT_EMAIL, BOT_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"SMTP Error: {e}")

def get_body(msg):
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

def handle_remember(sender_email, args):
    if len(args) != 2:
        return "Ошибка: формат `username, password`", None
    username, password = args
    session = api_login(username, password)
    if not session:
        return "Ошибка: неверный логин или пароль", None
    save_user(sender_email, username, password)
    session.close()
    return "Профиль сохранён", None

def handle_favorites(sender_email):
    user = get_user(sender_email)
    if not user:
        return "Требуется регистрация", None
    session = api_login(user[0], user[1])
    if not session:
        return "Ошибка авторизации", None
    response = session.post(f"{API_BASE}/api/v1/users/{user[0]}/favorites/export", json={"password": user[1]}, timeout=60)
    session.close()
    if response.status_code != 200:
        return "Ошибка экспорта", None
    path = os.path.join(DATA_DIR, f"{user[0]}_favorites.zip")
    with open(path, "wb") as f:
        f.write(response.content)
    return "Избранное готово", path

def handle_download(sender_email, args):
    user = get_user(sender_email)
    if not user:
        return "Требуется регистрация", None
    if len(args) != 1 or not args[0].isdigit():
        return "Укажите корректный post_id", None
    session = api_login(user[0], user[1])
    if not session:
        return "Ошибка авторизации", None
    response = session.get(f"{API_BASE}/api/v1/posts/{args[0]}/export", timeout=60)
    session.close()
    if response.status_code != 200:
        return f"Пост #{args[0]} не найден", None
    path = os.path.join(DATA_DIR, f"post_{args[0]}.zip")
    with open(path, "wb") as f:
        f.write(response.content)
    return f"Пост #{args[0]} экспортирован", path

def handle_get_comments(sender_email, args):
    user = get_user(sender_email)
    if not user:
        return "Требуется регистрация", None
    if len(args) != 1 or not args[0].isdigit():
        return "Укажите post_id", None
    session = api_login(user[0], user[1])
    if not session:
        return "Ошибка авторизации", None
    response = session.get(f"{API_BASE}/api/v1/posts/{args[0]}/comments", timeout=30)
    session.close()
    if response.status_code != 200:
        return "Не удалось получить комментарии", None
    data = response.json()
    if not data.get("success"):
        return data.get("error", "Ошибка"), None
    comments = data.get("comments", [])
    if not comments:
        return f"К посту #{args[0]} нет комментариев", None
    text = f"Комментарии к посту #{args[0]}:\n\n"
    for c in comments:
        text += f"{c['username']}: {c['content']}\n"
    return text, None

def handle_add_comment(sender_email, args):
    user = get_user(sender_email)
    if not user:
        return "Требуется регистрация", None
    if len(args) < 2:
        return "Формат: `post_id, текст`", None
    post_id = args[0]
    comment_text = ", ".join(args[1:])
    if not post_id.isdigit():
        return "post_id должен быть числом", None
    session = api_login(user[0], user[1])
    if not session:
        return "Ошибка авторизации", None
    response = session.post(f"{API_BASE}/api/v1/posts/{post_id}/comments", json={"content": comment_text}, timeout=30)
    session.close()
    if response.status_code != 200:
        return "Не удалось добавить комментарий", None
    data = response.json()
    if data.get("success"):
        return f"Комментарий добавлен к посту #{post_id}", None
    return data.get("error", "Ошибка"), None

COMMANDS = {
    "запомни меня": handle_remember,
    "скачать избранные посты": handle_favorites,
    "скачать пост по id": handle_download,
    "получить комментарии к посту": handle_get_comments,
    "добавить свой комментарий к посту": handle_add_comment
}

def run():
    init_db()
    print("Бот запущен")
    while True:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST)
            mail.login(BOT_EMAIL, BOT_PASSWORD)
            mail.select("inbox")
            status, ids = mail.search(None, "UNSEEN")
            if status == "OK" and ids[0]:
                for msg_id in ids[0].split():
                    status, data = mail.fetch(msg_id, "(RFC822)")
                    msg = email.message_from_bytes(data[0][1])
                    from_raw = decode_header(msg.get("From"))[0][0]
                    from_addr = from_raw.decode("utf-8", errors="ignore") if isinstance(from_raw, bytes) else from_raw
                    email_match = re.search(r"[\w\.-]+@[\w\.-]+", from_addr)
                    sender = email_match.group(0) if email_match else from_addr
                    subject_raw = decode_header(msg.get("Subject"))[0][0]
                    subject = subject_raw.decode("utf-8", errors="ignore").strip().lower() if isinstance(subject_raw, bytes) else subject_raw.strip().lower()
                    body = get_body(msg).strip()
                    args = [a.strip() for a in body.split(", ")] if body else []
                    is_reg = get_user(sender) is not None
                    if not is_reg or subject not in COMMANDS:
                        status_msg = "✅ Зарегистрированы" if is_reg else "⚠️ Не зарегистрированы"
                        send_email(sender, "🤖 GoldForum Bot", f"{status_msg}\n\n{ROADMAP}")
                        mail.store(msg_id, "+FLAGS", "\\Seen")
                        continue
                    reply, attach = COMMANDS[subject](sender, args)
                    send_email(sender, f"🤖 Ответ: {subject}", reply, attach)
                    if attach and os.path.exists(attach):
                        os.remove(attach)
                    mail.store(msg_id, "+FLAGS", "\\Seen")
                    print(f"📨 {sender} | {subject}")
            mail.logout()
        except Exception as e:
            print(f"⚠️ {e}")
        time.sleep(10)

if __name__ == "__main__":
    run()
