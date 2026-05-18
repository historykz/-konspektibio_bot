import aiosqlite
import os
import logging
import shutil
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

DATABASE_PATH = "database.db"


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                added_by INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_blocked INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                last_active_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS conspects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial_number INTEGER UNIQUE NOT NULL,
                topic TEXT NOT NULL,
                file_id TEXT,
                file_path TEXT NOT NULL,
                original_filename TEXT,
                uploaded_by INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                is_active INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                telegram_id INTEGER NOT NULL,
                username TEXT,
                serial_number INTEGER NOT NULL,
                conspect_topic TEXT,
                conspect_id INTEGER,
                downloaded_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                reason TEXT,
                blocked_by INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)

        await db.commit()
        logger.info("Database initialized successfully")


# âââ ADMINS ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def is_admin(telegram_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM admins WHERE telegram_id = ?", (telegram_id,)
        )
        return await cur.fetchone() is not None


async def add_admin(telegram_id: int, username: str, added_by: int) -> bool:
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO admins (telegram_id, username, added_by) VALUES (?,?,?)",
                (telegram_id, username, added_by),
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"add_admin error: {e}")
        return False


async def remove_admin(telegram_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT COUNT(*) as cnt FROM admins")
        row = await cur.fetchone()
        if row["cnt"] <= 1:
            return False
        await db.execute("DELETE FROM admins WHERE telegram_id = ?", (telegram_id,))
        await db.commit()
        return True


async def get_all_admins() -> List[Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM admins ORDER BY created_at")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# âââ USERS âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def upsert_user(telegram_id: int, username: str, first_name: str, last_name: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_name)
            VALUES (?,?,?,?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                last_active_at=datetime('now','localtime')
        """, (telegram_id, username, first_name, last_name))
        await db.commit()


async def is_blocked(telegram_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT is_blocked FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        return bool(row["is_blocked"]) if row else False


async def block_user(telegram_id: int, username: str, reason: str, blocked_by: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET is_blocked=1 WHERE telegram_id=?", (telegram_id,)
        )
        await db.execute("""
            INSERT OR REPLACE INTO blocked_users (telegram_id, username, reason, blocked_by)
            VALUES (?,?,?,?)
        """, (telegram_id, username, reason, blocked_by))
        await db.commit()
        return True


async def unblock_user(telegram_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET is_blocked=0 WHERE telegram_id=?", (telegram_id,)
        )
        await db.execute(
            "DELETE FROM blocked_users WHERE telegram_id=?", (telegram_id,)
        )
        await db.commit()
        return True


async def get_all_users() -> List[Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_blocked_users() -> List[Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM blocked_users ORDER BY created_at DESC")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# âââ CONSPECTS ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def add_conspect(
    serial_number: int, topic: str, file_id: str,
    file_path: str, original_filename: str, uploaded_by: int
) -> bool:
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO conspects
                    (serial_number, topic, file_id, file_path, original_filename, uploaded_by)
                VALUES (?,?,?,?,?,?)
            """, (serial_number, topic, file_id, file_path, original_filename, uploaded_by))
            await db.commit()
            return True
    except aiosqlite.IntegrityError:
        return False


async def get_conspect_by_number(serial_number: int) -> Optional[Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM conspects WHERE serial_number=? AND is_active=1",
            (serial_number,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_all_conspects() -> List[Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM conspects WHERE is_active=1 ORDER BY serial_number"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def delete_conspect(serial_number: int) -> Optional[str]:
    """Returns file_path if found, else None."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT file_path FROM conspects WHERE serial_number=?", (serial_number,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        file_path = row["file_path"]
        await db.execute(
            "DELETE FROM conspects WHERE serial_number=?", (serial_number,)
        )
        await db.commit()
        return file_path


async def update_conspect_topic(serial_number: int, new_topic: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "UPDATE conspects SET topic=?, updated_at=datetime('now','localtime') WHERE serial_number=? AND is_active=1",
            (new_topic, serial_number)
        )
        await db.commit()
        return cur.rowcount > 0


async def update_conspect_file(
    serial_number: int, file_id: str, file_path: str, original_filename: str
) -> Optional[str]:
    """Returns old file_path."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT file_path FROM conspects WHERE serial_number=? AND is_active=1",
            (serial_number,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        old_path = row["file_path"]
        await db.execute("""
            UPDATE conspects SET file_id=?, file_path=?, original_filename=?,
            updated_at=datetime('now','localtime')
            WHERE serial_number=? AND is_active=1
        """, (file_id, file_path, original_filename, serial_number))
        await db.commit()
        return old_path


async def update_conspect_number(old_number: int, new_number: int) -> str:
    """Returns 'ok', 'not_found', or 'duplicate'."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM conspects WHERE serial_number=? AND is_active=1", (old_number,)
        )
        if not await cur.fetchone():
            return "not_found"
        cur2 = await db.execute(
            "SELECT id FROM conspects WHERE serial_number=?", (new_number,)
        )
        if await cur2.fetchone():
            return "duplicate"
        await db.execute(
            "UPDATE conspects SET serial_number=?, updated_at=datetime('now','localtime') WHERE serial_number=?",
            (new_number, old_number)
        )
        await db.commit()
        return "ok"


async def conspect_number_exists(serial_number: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM conspects WHERE serial_number=?", (serial_number,)
        )
        return await cur.fetchone() is not None


# âââ DOWNLOADS âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def log_download(
    user_id: int, telegram_id: int, username: str,
    serial_number: int, conspect_topic: str, conspect_id: int
):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO downloads
                (user_id, telegram_id, username, serial_number, conspect_topic, conspect_id)
            VALUES (?,?,?,?,?,?)
        """, (user_id, telegram_id, username, serial_number, conspect_topic, conspect_id))
        await db.commit()


async def get_downloads(
    period: str = "all",
    serial_number: Optional[int] = None,
    telegram_id: Optional[int] = None
) -> List[Dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        where = []
        params = []

        if period == "today":
            where.append("date(downloaded_at) = date('now','localtime')")
        elif period == "week":
            where.append("downloaded_at >= datetime('now','-7 days','localtime')")
        elif period == "month":
            where.append("downloaded_at >= datetime('now','-30 days','localtime')")

        if serial_number is not None:
            where.append("serial_number = ?")
            params.append(serial_number)

        if telegram_id is not None:
            where.append("telegram_id = ?")
            params.append(telegram_id)

        sql = "SELECT * FROM downloads"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY downloaded_at DESC"

        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_stats_summary() -> Dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        cur = await db.execute("SELECT COUNT(*) as cnt FROM users")
        total_users = (await cur.fetchone())["cnt"]

        cur = await db.execute("SELECT COUNT(*) as cnt FROM conspects WHERE is_active=1")
        total_conspects = (await cur.fetchone())["cnt"]

        cur = await db.execute("SELECT COUNT(*) as cnt FROM downloads")
        total_downloads = (await cur.fetchone())["cnt"]

        cur = await db.execute(
            "SELECT COUNT(*) as cnt FROM downloads WHERE date(downloaded_at)=date('now','localtime')"
        )
        today_downloads = (await cur.fetchone())["cnt"]

        return {
            "total_users": total_users,
            "total_conspects": total_conspects,
            "total_downloads": total_downloads,
            "today_downloads": today_downloads,
        }


# âââ ADMIN LOGS ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def log_admin_action(admin_id: int, action: str, details: str = ""):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO admin_logs (admin_id, action, details) VALUES (?,?,?)",
            (admin_id, action, details)
        )
        await db.commit()


# âââ BACKUP ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

async def create_backup() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("backups", exist_ok=True)
    backup_path = f"backups/database_{ts}.db"
    async with aiosqlite.connect(DATABASE_PATH) as src:
        async with aiosqlite.connect(backup_path) as dst:
            await src.backup(dst)
    return backup_path
