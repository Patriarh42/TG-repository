import os
import re
import time
import imaplib
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import decode_header

from src import GoldForumClient, Database

BOT_EMAIL = os.getenv("BOT_EMAIL", "bot@example.com")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "app_password")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
TMP_DIR = os.getenv("TMP_DIR", "data")

os.makedirs(TMP_DIR, exist_ok=True)

ROADMAP = """Добро пожаловать в GoldForum Email Bot!

📋 ДОРОЖНАЯ КАРТА
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


def decode_text(raw_header):
    if not raw_header:
        return ""
    decoded_parts = decode_header(raw_header)
    return "".join(
        part.decode(encoding or "utf-8", errors="ignore") if isinstance(part, bytes) else str(part)
        for part, encoding in decoded_parts
    )


def extract_body(msg):
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


def send_reply(to_addr, subject, body, attach_path=None):
    msg = MIMEMultipart()
    msg["From"] = BOT_EMAIL
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attach_path and os.path.exists(attach_path):
        with open(attach_path, "rb") as f:
            file_part = MIMEApplication(f.read(), Name=os.path.basename(attach_path))
        file_part["Content-Disposition"] = f'attachment; filename="{os.path.basename(attach_path)}"'
        msg.attach(file_part)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, 465) as server:
            server.login(BOT_EMAIL, BOT_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Ошибка отправки: {e}")


def handle_remember(db, sender, args):
    if len(args) != 2:
        return "Ошибка: укажите логин и пароль через запятую. Пример: `ivan, mypass123`", None

    username, password = args
    client = GoldForumClient()
    if not client.login(username, password):
        return "Ошибка: неверный логин или пароль.", None

    db.save_user(sender, username, password)
    client.close()
    return "Профиль успешно сохранён.", None


def handle_favorites(db, sender, args):
    user = db.get_user(sender)
    if not user:
        return "Вы не зарегистрированы. Отправьте команду `запомни меня`.", None

    client = GoldForumClient(user[0], user[1])
    content = client.export_favorites(user[0], user[1])
    client.close()
    
    if not content:
        return "Не удалось экспортировать избранное.", None

    path = os.path.join(TMP_DIR, f"{user[0]}_favorites.zip")
    with open(path, "wb") as f:
        f.write(content)
    return "Избранные посты экспортированы. Файл прикреплён.", path


def handle_download_post(db, sender, args):
    user = db.get_user(sender)
    if not user:
        return "Вы не зарегистрированы.", None
    if len(args) != 1 or not args[0].isdigit():
        return "Укажите корректный ID поста. Пример: `42`", None

    client = GoldForumClient(user[0], user[1])
    content = client.export_post(args[0])
    client.close()
    
    if not content:
        return f"Пост #{args[0]} не найден.", None

    path = os.path.join(TMP_DIR, f"post_{args[0]}.zip")
    with open(path, "wb") as f:
        f.write(content)
    return f"Пост #{args[0]} экспортирован. Файл прикреплён.", path


def handle_get_comments(db, sender, args):
    user = db.get_user(sender)
    if not user:
        return "Вы не зарегистрированы.", None
    if len(args) != 1 or not args[0].isdigit():
        return "Укажите ID поста. Пример: `15`", None

    client = GoldForumClient(user[0], user[1])
    data = client.get_comments(args[0])
    client.close()
    
    if not data.get("success"):
        return data.get("error", "Неизвестная ошибка"), None

    comments = data.get("comments", [])
    if not comments:
        return f"К посту #{args[0]} нет комментариев.", None

    text = f"Комментарии к посту #{args[0]}:\n\n"
    for c in comments:
        text += f"👤 {c['username']}\n{c['content']}\n🕒 {c['created_at']}\n{'─' * 30}\n"
    return text, None


def handle_add_comment(db, sender, args):
    user = db.get_user(sender)
    if not user:
        return "Вы не зарегистрированы.", None
    if len(args) < 2:
        return "Формат: `post_id, текст комментария`", None

    post_id = args[0]
    comment_text = ", ".join(args[1:])
    if not post_id.isdigit():
        return "ID поста должен быть числом.", None

    client = GoldForumClient(user[0], user[1])
    result = client.add_comment(post_id, comment_text)
    client.close()
    
    if result.get("success"):
        return f"Комментарий добавлен к посту #{post_id}.", None
    return result.get("error", "Ошибка публикации"), None


COMMANDS = {
    "запомни меня": handle_remember,
    "скачать избранные посты": handle_favorites,
    "скачать пост по id": handle_download_post,
    "получить комментарии к посту": handle_get_comments,
    "добавить свой комментарий к посту": handle_add_comment
}


def run_bot():
    db = Database()
    print("📬 Бот запущен. Ожидание писем...")

    while True:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST)
            mail.login(BOT_EMAIL, BOT_PASSWORD)
            mail.select("inbox")

            status, message_ids = mail.search(None, "UNSEEN")
            if status == "OK" and message_ids[0]:
                for msg_id in message_ids[0].split():
                    status, msg_data = mail.fetch(msg_id, "(RFC822)")
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    sender_raw = decode_text(msg.get("From"))
                    subject = decode_text(msg.get("Subject")).strip().lower()
                    body = extract_body(msg).strip()

                    email_match = re.search(r"[\w\.-]+@[\w\.-]+", sender_raw)
                    sender_email = email_match.group(0) if email_match else sender_raw

                    is_registered = db.get_user(sender_email) is not None

                    if not is_registered or subject not in COMMANDS:
                        status_msg = "✅ Вы уже зарегистрированы." if is_registered else "⚠️ Вы ещё не зарегистрированы."
                        send_reply(sender_email, "🤖 GoldForum Bot", f"{status_msg}\n\n{ROADMAP}")
                        mail.store(msg_id, "+FLAGS", "\\Seen")
                        continue

                    args = [a.strip() for a in body.split(", ")] if body else []
                    handler = COMMANDS[subject]
                    reply_text, attach_path = handler(db, sender_email, args)

                    send_reply(sender_email, f"🤖 Ответ: {subject}", reply_text, attach_path)

                    if attach_path and os.path.exists(attach_path):
                        os.remove(attach_path)

                    mail.store(msg_id, "+FLAGS", "\\Seen")
                    print(f"Обработано: {sender_email} | {subject}")

            mail.logout()
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")

        time.sleep(10)


if __name__ == "__main__":
    run_bot()
