import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "bot.db")


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self._create_tables()
    
    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                password TEXT NOT NULL
            )
        """)
        self.conn.commit()
    
    def get_user(self, email):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT username, password FROM users WHERE email = ?",
            (email,)
        )
        return cursor.fetchone()
    
    def save_user(self, email, username, password):
        self.conn.execute(
            "INSERT OR REPLACE INTO users (email, username, password) VALUES (?, ?, ?)",
            (email, username, password)
        )
        self.conn.commit()
    
    def close(self):
        self.conn.close()
