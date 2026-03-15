"""SQLite singleton that provides the local offline cache.

Schema mirrors Supabase with two extra columns on every table:
- sync_status: 'synced' | 'pending' | 'conflict'
- updated_at:  Unix timestamp float, used for last-write-wins resolution

All reads go through this module; Supabase is only written to (not read from)
during normal operation. Remote pull results are merged here by SyncManager.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Optional

import config


class CacheDB:
    """Thread-safe SQLite singleton.

    Usage:
        db = CacheDB.get_instance()
        with db.connection() as conn:
            conn.execute(...)

    The singleton is initialised once per process; subsequent calls to
    get_instance() return the same object.
    """

    _instance: Optional["CacheDB"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, db_path: str = config.SQLITE_DB_PATH) -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._init_schema()

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "CacheDB":
        """Return the process-wide CacheDB singleton, creating it if needed.

        Returns:
            The shared CacheDB instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connection(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection, creating it if needed.

        Returns:
            An open sqlite3.Connection with row_factory set to Row.
        """
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create all tables and indexes if they do not already exist."""
        conn = self.connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id          TEXT PRIMARY KEY,
                email       TEXT,
                height_cm   REAL,
                weight_kg   REAL,
                age         INTEGER,
                sex         TEXT,
                activity    TEXT,
                goal        TEXT,
                unit_system TEXT DEFAULT 'metric',
                updated_at  REAL NOT NULL DEFAULT 0,
                sync_status TEXT NOT NULL DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS goals (
                id              TEXT PRIMARY KEY,
                profile_id      TEXT NOT NULL,
                protein_pct     REAL NOT NULL DEFAULT 30,
                carbs_pct       REAL NOT NULL DEFAULT 40,
                fat_pct         REAL NOT NULL DEFAULT 30,
                diet_type       TEXT DEFAULT 'balanced',
                meals_per_day   INTEGER DEFAULT 3,
                calorie_target  REAL,
                updated_at      REAL NOT NULL DEFAULT 0,
                sync_status     TEXT NOT NULL DEFAULT 'pending',
                FOREIGN KEY (profile_id) REFERENCES profiles(id)
            );

            CREATE TABLE IF NOT EXISTS foods (
                id              TEXT PRIMARY KEY,
                barcode         TEXT,
                name            TEXT NOT NULL,
                brand           TEXT,
                source          TEXT DEFAULT 'manual',
                calories        REAL,
                protein_g       REAL,
                carbs_g         REAL,
                fat_g           REAL,
                fiber_g         REAL,
                sugar_g         REAL,
                sodium_mg       REAL,
                serving_size_g  REAL DEFAULT 100,
                created_by      TEXT,
                updated_at      REAL NOT NULL DEFAULT 0,
                sync_status     TEXT NOT NULL DEFAULT 'pending'
            );

            CREATE INDEX IF NOT EXISTS idx_foods_barcode ON foods(barcode);
            CREATE INDEX IF NOT EXISTS idx_foods_name    ON foods(name);

            CREATE TABLE IF NOT EXISTS meals (
                id          TEXT PRIMARY KEY,
                profile_id  TEXT NOT NULL,
                date        TEXT NOT NULL,
                meal_number INTEGER NOT NULL,
                label       TEXT,
                updated_at  REAL NOT NULL DEFAULT 0,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                FOREIGN KEY (profile_id) REFERENCES profiles(id),
                UNIQUE(profile_id, date, meal_number)
            );

            CREATE TABLE IF NOT EXISTS meal_items (
                id          TEXT PRIMARY KEY,
                meal_id     TEXT NOT NULL,
                food_id     TEXT NOT NULL,
                quantity_g  REAL NOT NULL DEFAULT 100,
                updated_at  REAL NOT NULL DEFAULT 0,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                FOREIGN KEY (meal_id) REFERENCES meals(id) ON DELETE CASCADE,
                FOREIGN KEY (food_id) REFERENCES foods(id)
            );

            CREATE TABLE IF NOT EXISTS recipes (
                id          TEXT PRIMARY KEY,
                profile_id  TEXT NOT NULL,
                name        TEXT NOT NULL,
                servings    INTEGER DEFAULT 1,
                updated_at  REAL NOT NULL DEFAULT 0,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                FOREIGN KEY (profile_id) REFERENCES profiles(id)
            );

            CREATE TABLE IF NOT EXISTS recipe_ingredients (
                id          TEXT PRIMARY KEY,
                recipe_id   TEXT NOT NULL,
                food_id     TEXT NOT NULL,
                quantity_g  REAL NOT NULL DEFAULT 100,
                updated_at  REAL NOT NULL DEFAULT 0,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
                FOREIGN KEY (food_id) REFERENCES foods(id)
            );

            -- Operation queue drained by SyncManager
            CREATE TABLE IF NOT EXISTS sync_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name  TEXT NOT NULL,
                row_id      TEXT NOT NULL,
                operation   TEXT NOT NULL,   -- 'insert' | 'update' | 'delete'
                payload     TEXT NOT NULL,   -- JSON-encoded row data
                retries     INTEGER NOT NULL DEFAULT 0,
                created_at  REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            -- Audit log for conflict resolution losers
            CREATE TABLE IF NOT EXISTS conflict_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name      TEXT NOT NULL,
                row_id          TEXT NOT NULL,
                local_payload   TEXT NOT NULL,
                remote_payload  TEXT NOT NULL,
                resolved_at     REAL NOT NULL DEFAULT (strftime('%s','now'))
            );
        """)
        conn.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the per-thread connection if open."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
