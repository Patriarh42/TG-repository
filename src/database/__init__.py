import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "bot.db")


class UserDatabase:
    def __init__(self, path=None):
        self.path = path or DB_PATH
        self._init()
    
    def _init(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL
                )
            """)
    
    def get(self, email):
        with sqlite3.connect(self.path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT username, password FROM users WHERE email = ?",
                (email,)
            )
            return cur.fetchone()
    
    def save(self, email, username, password):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO users (email, username, password) VALUES (?, ?, ?)",
                (email, username, password)
            )
