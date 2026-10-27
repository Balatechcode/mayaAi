"""
SQLite-backed memory store for Jarvis.
Prepared for Phase 3: persistent storage of user preferences, conversation history, and reminders.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from jarvis.config import BASE_DIR

DB_PATH = BASE_DIR / "jarvis_memory.db"

class MemoryStore:
    """
    Interface for SQLite memory storage.
    Ready for Phase 3 activation.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def init_db(self) -> None:
        """Initializes tables for preferences, conversation logs, and reminders."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reminder_text TEXT,
                    due_time TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
            """)
            conn.commit()

    def get_preference(self, key: str) -> Optional[str]:
        """Fetch preference value by key."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def set_preference(self, key: str, value: str) -> None:
        """Store or update a user preference."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO preferences (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, (key, value))
            conn.commit()
