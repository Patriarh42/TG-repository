import aiosqlite
from pathlib import Path

class Database:
    def __init__(self, db_path="data/bot.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    phone TEXT,
                    username TEXT,
                    password TEXT,
                    is_registered BOOLEAN DEFAULT 0
                )
            """)
            await db.commit()
    
    async def get_user(self, telegram_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def save_user(self, telegram_id, phone=None, username=None, password=None, is_registered=None):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            existing = await cursor.fetchone()
            
            if existing:
                await db.execute("""
                    UPDATE users SET
                        phone=COALESCE(?, phone),
                        username=COALESCE(?, username),
                        password=COALESCE(?, password),
                        is_registered=COALESCE(?, is_registered)
                    WHERE telegram_id=?
                """, (phone, username, password, is_registered, telegram_id))
            else:
                await db.execute("""
                    INSERT INTO users (telegram_id, phone, username, password, is_registered) VALUES (?, ?, ?, ?, COALESCE(?, 0))
                """, (telegram_id, phone, username, password, is_registered))
            await db.commit()
