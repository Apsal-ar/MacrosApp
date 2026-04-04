"""SQLite singleton cache: JSON row payloads + sync_status + durable sync_queue."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SYNC_STATUSES = frozenset({"synced", "pending", "conflict"})

# Tables that store `synced` (0/1): local row is pushed until Supabase confirms.
_TABLES_WITH_SYNCED_FLAG = frozenset(
    {
        "foods",
        "recipes",
        "recipe_foods",
        "meals",
        "meal_items",
    }
)


class CacheDB:
    """Thread-safe local cache; mirrors Supabase rows as JSON with sync metadata."""

    _instance: Optional["CacheDB"] = None
    _lock_meta = threading.Lock()

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls, path: Optional[str] = None) -> "CacheDB":
        with cls._lock_meta:
            if cls._instance is None:
                if not path:
                    raise ValueError("CacheDB.get_instance(path) required on first call")
                cls._instance = cls(path)
                cls._instance.open()
            return cls._instance

    @classmethod
    def reset_instance_for_tests(cls) -> None:
        with cls._lock_meta:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None

    def open(self) -> None:
        with self._lock:
            if self._conn is not None:
                return
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_schema()
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _init_schema(self) -> None:
        assert self._conn is not None
        c = self._conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'synced'
            );

            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'synced'
            );
            CREATE INDEX IF NOT EXISTS idx_goals_profile ON goals(profile_id);

            CREATE TABLE IF NOT EXISTS foods (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'synced',
                synced INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS meals (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                date TEXT NOT NULL,
                meal_number INTEGER NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'synced',
                synced INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_meals_profile_date
                ON meals(profile_id, date);

            CREATE TABLE IF NOT EXISTS meal_items (
                id TEXT PRIMARY KEY,
                meal_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'synced',
                synced INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(meal_id) REFERENCES meals(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_meal_items_meal ON meal_items(meal_id);

            CREATE TABLE IF NOT EXISTS meal_date_cache (
                profile_id TEXT NOT NULL,
                date TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                PRIMARY KEY (profile_id, date)
            );

            CREATE TABLE IF NOT EXISTS recipes (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'synced',
                synced INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_recipes_profile ON recipes(profile_id);

            CREATE TABLE IF NOT EXISTS recipe_foods (
                id TEXT PRIMARY KEY,
                recipe_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'synced',
                synced INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_recipe_foods_recipe ON recipe_foods(recipe_id);

            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                operation TEXT NOT NULL,
                row_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL,
                retries INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sync_queue_created ON sync_queue(created_at);
            """
        )
        self._migrate_add_synced_column()
        self._migrate_recipe_foods_rename()

    def _migrate_add_synced_column(self) -> None:
        """Add ``synced`` to existing installs and align with ``sync_status``."""
        assert self._conn is not None
        c = self._conn
        for table in _TABLES_WITH_SYNCED_FLAG:
            try:
                c.execute(
                    f"ALTER TABLE {table} ADD COLUMN synced INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        for table in _TABLES_WITH_SYNCED_FLAG:
            c.execute(
                f"UPDATE {table} SET synced = 1 WHERE sync_status = 'synced'"
            )
        c.commit()

    def _migrate_recipe_foods_rename(self) -> None:
        """Rename legacy ``recipe_ingredients`` SQLite table to ``recipe_foods``."""
        assert self._conn is not None
        c = self._conn
        cur = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recipe_ingredients'"
        )
        if not cur.fetchone():
            return
        cur2 = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recipe_foods'"
        )
        if cur2.fetchone():
            return
        c.execute("ALTER TABLE recipe_ingredients RENAME TO recipe_foods")
        c.commit()

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    def mark_synced(self, table: str, row_id: str) -> None:
        """Set sync_status to 'synced' and ``synced=1`` after a successful Supabase write."""
        col = _pk_column_for(table)
        if not col:
            return
        if table in _TABLES_WITH_SYNCED_FLAG:
            sql = f"UPDATE {table} SET sync_status='synced', synced=1 WHERE {col}=?"
        else:
            sql = f"UPDATE {table} SET sync_status='synced' WHERE {col}=?"
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(sql, (row_id,))
            self._conn.commit()

    def mark_row_status(self, table: str, row_id: str, status: str) -> None:
        if status not in _SYNC_STATUSES:
            status = "pending"
        col = _pk_column_for(table)
        if not col:
            return
        with self._lock:
            if self._conn is None:
                return
            if table in _TABLES_WITH_SYNCED_FLAG:
                synced_val = 1 if status == "synced" else 0
                self._conn.execute(
                    f"UPDATE {table} SET sync_status=?, synced=? WHERE {col}=?",
                    (status, synced_val, row_id),
                )
            else:
                self._conn.execute(
                    f"UPDATE {table} SET sync_status=? WHERE {col}=?",
                    (status, row_id),
                )
            self._conn.commit()

    def is_cache_empty_for_user(self, profile_id: str) -> bool:
        """True if we have no profile row for this user (first launch / cleared)."""
        with self._lock:
            if self._conn is None:
                return True
            cur = self._conn.execute(
                "SELECT 1 FROM profiles WHERE id=? LIMIT 1", (profile_id,)
            )
            return cur.fetchone() is None

    def total_row_count(self) -> int:
        with self._lock:
            if self._conn is None:
                return 0
            n = 0
            for t in (
                "profiles",
                "goals",
                "foods",
                "meals",
                "meal_items",
                "recipes",
                "recipe_foods",
            ):
                cur = self._conn.execute(f"SELECT COUNT(*) FROM {t}")
                n += int(cur.fetchone()[0])
            return n

    def max_updated_at(self, table: str, where: str = "", args: Tuple[Any, ...] = ()) -> float:
        """Maximum updated_at in a table (optionally filtered)."""
        with self._lock:
            if self._conn is None:
                return 0.0
            sql = f"SELECT MAX(updated_at) FROM {table}"
            if where:
                sql += f" WHERE {where}"
            cur = self._conn.execute(sql, args)
            row = cur.fetchone()
            v = row[0] if row else None
            return float(v) if v is not None else 0.0

    # ------------------------------------------------------------------
    # Meta / user switch (same as LocalStore)
    # ------------------------------------------------------------------

    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            if self._conn is None:
                return None
            cur = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                (key, value),
            )
            self._conn.commit()

    def set_active_user(self, user_id: str) -> None:
        prev = self.get_meta("active_user_id")
        if prev is not None and prev != user_id:
            self._clear_user_data()
        self.set_meta("active_user_id", user_id)

    def _clear_user_data(self) -> None:
        logger.info("CacheDB: clearing cache (user switch)")
        with self._lock:
            if self._conn is None:
                return
            for table in (
                "profiles",
                "goals",
                "meals",
                "meal_items",
                "meal_date_cache",
                "recipes",
                "recipe_foods",
                "foods",
            ):
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.execute("DELETE FROM sync_queue")
            self._conn.commit()

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def upsert_profile(
        self, row: Dict[str, Any], *, from_remote: bool = False
    ) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        pid = row["id"]
        st = "synced" if from_remote else "pending"
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO profiles(id, payload, updated_at, sync_status)
                   VALUES(?,?,?,?)""",
                (pid, payload, ts, st),
            )
            self._conn.commit()

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._conn is None:
                return None
            cur = self._conn.execute(
                "SELECT payload FROM profiles WHERE id=?", (profile_id,)
            )
            r = cur.fetchone()
            if not r:
                return None
            return json.loads(r[0])

    def delete_profile(self, profile_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------

    def upsert_goals(
        self, row: Dict[str, Any], *, from_remote: bool = False
    ) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        gid = row["id"]
        profile_id = row["profile_id"]
        st = "synced" if from_remote else "pending"
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM goals WHERE profile_id=?", (profile_id,))
            self._conn.execute(
                """INSERT INTO goals(id, profile_id, payload, updated_at, sync_status)
                   VALUES(?,?,?,?,?)""",
                (gid, profile_id, payload, ts, st),
            )
            self._conn.commit()

    def get_goals_for_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._conn is None:
                return None
            cur = self._conn.execute(
                "SELECT payload FROM goals WHERE profile_id=? ORDER BY updated_at DESC LIMIT 1",
                (profile_id,),
            )
            r = cur.fetchone()
            if not r:
                return None
            return json.loads(r[0])

    def delete_goals_for_profile(self, profile_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM goals WHERE profile_id=?", (profile_id,))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Foods
    # ------------------------------------------------------------------

    def upsert_food(
        self, row: Dict[str, Any], *, from_remote: bool = False
    ) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        fid = row["id"]
        st = "synced" if from_remote else "pending"
        synced_val = 1 if from_remote else 0
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO foods(id, payload, updated_at, sync_status, synced)
                   VALUES(?,?,?,?,?)""",
                (fid, payload, ts, st, synced_val),
            )
            self._conn.commit()

    def get_food(self, food_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._conn is None:
                return None
            cur = self._conn.execute("SELECT payload FROM foods WHERE id=?", (food_id,))
            r = cur.fetchone()
            if not r:
                return None
            return json.loads(r[0])

    def delete_food(self, food_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM foods WHERE id=?", (food_id,))
            self._conn.commit()

    def get_manual_foods_local(self, profile_id: str) -> List[Dict[str, Any]]:
        """All foods owned by the profile (My Foods: manual, USDA, OFF copies, logged)."""
        out: List[Dict[str, Any]] = []
        with self._lock:
            if self._conn is None:
                return out
            cur = self._conn.execute("SELECT payload FROM foods")
            for (payload,) in cur.fetchall():
                try:
                    d = json.loads(payload)
                    if d.get("created_by") == profile_id:
                        out.append(d)
                except (json.JSONDecodeError, TypeError):
                    continue
        out.sort(key=lambda x: (x.get("name") or "").lower())
        return out

    def iter_food_ids_for_profile_meals(self, profile_id: str) -> List[str]:
        """Distinct ``food_id`` values from meal logs for this profile."""
        seen: set[str] = set()
        ordered: List[str] = []
        with self._lock:
            if self._conn is None:
                return ordered
            cur = self._conn.execute(
                """SELECT mi.payload FROM meal_items mi
                   INNER JOIN meals m ON m.id = mi.meal_id
                   WHERE m.profile_id=?""",
                (profile_id,),
            )
            for (payload,) in cur.fetchall():
                try:
                    d = json.loads(payload)
                    fid = d.get("food_id")
                    if isinstance(fid, str) and fid and fid not in seen:
                        seen.add(fid)
                        ordered.append(fid)
                except (json.JSONDecodeError, TypeError):
                    continue
        return ordered

    def get_all_food_payloads(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._lock:
            if self._conn is None:
                return rows
            cur = self._conn.execute("SELECT payload FROM foods")
            for (payload,) in cur.fetchall():
                try:
                    rows.append(json.loads(payload))
                except json.JSONDecodeError:
                    continue
        return rows

    # ------------------------------------------------------------------
    # Meals
    # ------------------------------------------------------------------

    def mark_meal_date_fetched(self, profile_id: str, date: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "INSERT OR REPLACE INTO meal_date_cache(profile_id, date, fetched_at) VALUES(?,?,?)",
                (profile_id, date, time.time()),
            )
            self._conn.commit()

    def is_meal_date_fetched(self, profile_id: str, date: str) -> bool:
        with self._lock:
            if self._conn is None:
                return False
            cur = self._conn.execute(
                "SELECT 1 FROM meal_date_cache WHERE profile_id=? AND date=?",
                (profile_id, date),
            )
            return cur.fetchone() is not None

    def upsert_meal(
        self, row: Dict[str, Any], *, from_remote: bool = False
    ) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        mid = row["id"]
        profile_id = row["profile_id"]
        date = row["date"]
        meal_number = int(row.get("meal_number") or 0)
        st = "synced" if from_remote else "pending"
        synced_val = 1 if from_remote else 0
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO meals
                (id, profile_id, date, meal_number, payload, updated_at, sync_status, synced)
                VALUES(?,?,?,?,?,?,?,?)""",
                (mid, profile_id, date, meal_number, payload, ts, st, synced_val),
            )
            self._conn.commit()

    def delete_meal(self, meal_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM meal_items WHERE meal_id=?", (meal_id,))
            self._conn.execute("DELETE FROM meals WHERE id=?", (meal_id,))
            self._conn.commit()

    def get_meals_for_date_rows(self, profile_id: str, date: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._lock:
            if self._conn is None:
                return rows
            cur = self._conn.execute(
                """SELECT payload FROM meals WHERE profile_id=? AND date=?
                   ORDER BY meal_number""",
                (profile_id, date),
            )
            for (payload,) in cur.fetchall():
                try:
                    rows.append(json.loads(payload))
                except json.JSONDecodeError:
                    continue
        return rows

    def get_all_meals_for_profile_rows(self, profile_id: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._lock:
            if self._conn is None:
                return rows
            cur = self._conn.execute(
                """SELECT payload FROM meals WHERE profile_id=?
                   ORDER BY date, meal_number""",
                (profile_id,),
            )
            for (payload,) in cur.fetchall():
                try:
                    rows.append(json.loads(payload))
                except json.JSONDecodeError:
                    continue
        return rows

    def upsert_meal_item(
        self, row: Dict[str, Any], *, from_remote: bool = False
    ) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        iid = row["id"]
        meal_id = row["meal_id"]
        st = "synced" if from_remote else "pending"
        synced_val = 1 if from_remote else 0
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO meal_items(id, meal_id, payload, updated_at, sync_status, synced)
                   VALUES(?,?,?,?,?,?)""",
                (iid, meal_id, payload, ts, st, synced_val),
            )
            self._conn.commit()

    def delete_meal_item(self, item_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM meal_items WHERE id=?", (item_id,))
            self._conn.commit()

    def get_meal_items_for_meal(self, meal_id: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._lock:
            if self._conn is None:
                return rows
            cur = self._conn.execute(
                "SELECT payload FROM meal_items WHERE meal_id=? ORDER BY id",
                (meal_id,),
            )
            for (payload,) in cur.fetchall():
                try:
                    rows.append(json.loads(payload))
                except json.JSONDecodeError:
                    continue
        return rows

    def get_meal_item_payload(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Return decoded meal_items row JSON, or None if missing."""
        with self._lock:
            if self._conn is None:
                return None
            cur = self._conn.execute(
                "SELECT payload FROM meal_items WHERE id=?",
                (item_id,),
            )
            r = cur.fetchone()
            if not r:
                return None
            try:
                return json.loads(r[0])
            except json.JSONDecodeError:
                return None

    def clear_meals_for_date(self, profile_id: str, date: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            cur = self._conn.execute(
                "SELECT id FROM meals WHERE profile_id=? AND date=?",
                (profile_id, date),
            )
            mids = [r[0] for r in cur.fetchall()]
            for mid in mids:
                self._conn.execute("DELETE FROM meal_items WHERE meal_id=?", (mid,))
                self._conn.execute("DELETE FROM meals WHERE id=?", (mid,))
            self._conn.execute(
                "DELETE FROM meal_date_cache WHERE profile_id=? AND date=?",
                (profile_id, date),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Recipes
    # ------------------------------------------------------------------

    def set_recipes_list_fetched(self, profile_id: str) -> None:
        self.set_meta(f"recipes_loaded:{profile_id}", "1")

    def is_recipes_list_fetched(self, profile_id: str) -> bool:
        return self.get_meta(f"recipes_loaded:{profile_id}") == "1"

    def clear_recipes_for_profile(self, profile_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            cur = self._conn.execute(
                "SELECT id FROM recipes WHERE profile_id=?", (profile_id,)
            )
            rids = [r[0] for r in cur.fetchall()]
            for rid in rids:
                self._conn.execute(
                    "DELETE FROM recipe_foods WHERE recipe_id=?", (rid,)
                )
            self._conn.execute("DELETE FROM recipes WHERE profile_id=?", (profile_id,))
            self._conn.commit()
        self.set_meta(f"recipes_loaded:{profile_id}", "")

    def upsert_recipe(
        self, row: Dict[str, Any], *, from_remote: bool = False
    ) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        rid = row["id"]
        profile_id = row["profile_id"]
        st = "synced" if from_remote else "pending"
        synced_val = 1 if from_remote else 0
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO recipes(id, profile_id, payload, updated_at, sync_status, synced)
                   VALUES(?,?,?,?,?,?)""",
                (rid, profile_id, payload, ts, st, synced_val),
            )
            self._conn.commit()

    def upsert_recipe_food(
        self, row: Dict[str, Any], *, from_remote: bool = False
    ) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        iid = row["id"]
        recipe_id = row["recipe_id"]
        st = "synced" if from_remote else "pending"
        synced_val = 1 if from_remote else 0
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO recipe_foods(id, recipe_id, payload, updated_at, sync_status, synced)
                   VALUES(?,?,?,?,?,?)""",
                (iid, recipe_id, payload, ts, st, synced_val),
            )
            self._conn.commit()

    def delete_recipe_food(self, ingredient_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "DELETE FROM recipe_foods WHERE id=?", (ingredient_id,)
            )
            self._conn.commit()

    def delete_recipe(self, recipe_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "DELETE FROM recipe_foods WHERE recipe_id=?", (recipe_id,)
            )
            self._conn.execute("DELETE FROM recipes WHERE id=?", (recipe_id,))
            self._conn.commit()

    def get_recipe_row(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._conn is None:
                return None
            cur = self._conn.execute(
                "SELECT payload FROM recipes WHERE id=?", (recipe_id,)
            )
            r = cur.fetchone()
            if not r:
                return None
            try:
                return json.loads(r[0])
            except json.JSONDecodeError:
                return None

    def get_recipes_for_profile_rows(self, profile_id: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._lock:
            if self._conn is None:
                return rows
            cur = self._conn.execute(
                "SELECT payload FROM recipes WHERE profile_id=?",
                (profile_id,),
            )
            for (payload,) in cur.fetchall():
                try:
                    rows.append(json.loads(payload))
                except json.JSONDecodeError:
                    continue
        return rows

    def get_recipe_food_rows(self, recipe_id: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._lock:
            if self._conn is None:
                return rows
            cur = self._conn.execute(
                "SELECT payload FROM recipe_foods WHERE recipe_id=?",
                (recipe_id,),
            )
            for (payload,) in cur.fetchall():
                try:
                    rows.append(json.loads(payload))
                except json.JSONDecodeError:
                    continue
        return rows

    # ------------------------------------------------------------------
    # Sync queue (durable ops log)
    # ------------------------------------------------------------------

    def enqueue_sync(
        self, table_name: str, operation: str, row_id: str, payload: Dict[str, Any]
    ) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT INTO sync_queue(table_name, operation, row_id, payload, created_at, retries, last_error)
                   VALUES(?,?,?,?,?,?,NULL)""",
                (
                    table_name,
                    operation,
                    row_id,
                    json.dumps(payload, default=str),
                    time.time(),
                    0,
                ),
            )
            self._conn.commit()

    def peek_sync_batch(self, limit: int = 50) -> List[sqlite3.Row]:
        with self._lock:
            if self._conn is None:
                return []
            cur = self._conn.execute(
                """SELECT * FROM sync_queue WHERE retries < 5
                   ORDER BY created_at ASC LIMIT ?""",
                (limit,),
            )
            return list(cur.fetchall())

    def dequeue_sync(self, op_id: int) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM sync_queue WHERE id=?", (op_id,))
            self._conn.commit()

    def record_sync_failure(self, op_id: int, error: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """UPDATE sync_queue SET retries = retries + 1, last_error = ?
                   WHERE id=?""",
                (error[:2000], op_id),
            )
            self._conn.commit()

    def sync_queue_has_pending(
        self, table: str, row_id: str, operation: str
    ) -> bool:
        """True if the durable queue already has this op (avoid duplicate enqueue)."""
        with self._lock:
            if self._conn is None:
                return False
            cur = self._conn.execute(
                "SELECT 1 FROM sync_queue WHERE table_name=? AND row_id=? AND operation=? LIMIT 1",
                (table, row_id, operation),
            )
            return cur.fetchone() is not None

    def requeue_unsynced_outbound(self, profile_id: str) -> None:
        """Enqueue upserts for rows with ``synced=0`` (retry after failed upload or app restart)."""
        if not profile_id:
            return
        with self._lock:
            if self._conn is None:
                return
            cur = self._conn.execute("SELECT id, payload FROM foods WHERE synced=0")
            food_rows = list(cur.fetchall())
            cur = self._conn.execute(
                "SELECT id, payload FROM recipes WHERE profile_id=? AND synced=0",
                (profile_id,),
            )
            recipe_rows = list(cur.fetchall())
            cur = self._conn.execute(
                """
                SELECT recipe_foods.id, recipe_foods.payload
                FROM recipe_foods
                JOIN recipes ON recipes.id = recipe_foods.recipe_id
                WHERE recipes.profile_id = ? AND recipe_foods.synced = 0
                """,
                (profile_id,),
            )
            ing_rows = list(cur.fetchall())
            cur = self._conn.execute(
                "SELECT id, payload FROM meals WHERE profile_id=? AND synced=0",
                (profile_id,),
            )
            meal_rows = list(cur.fetchall())
            cur = self._conn.execute(
                """
                SELECT meal_items.id, meal_items.payload
                FROM meal_items
                JOIN meals ON meals.id = meal_items.meal_id
                WHERE meals.profile_id = ? AND meal_items.synced = 0
                """,
                (profile_id,),
            )
            item_rows = list(cur.fetchall())

        batches = (
            ("foods", food_rows),
            ("recipes", recipe_rows),
            ("recipe_foods", ing_rows),
            ("meals", meal_rows),
            ("meal_items", item_rows),
        )
        for table, rows in batches:
            for row_id, payload in rows:
                if self.sync_queue_has_pending(table, row_id, "upsert"):
                    continue
                try:
                    pl = json.loads(payload)
                except (json.JSONDecodeError, TypeError):
                    continue
                self.enqueue_sync(table, "upsert", row_id, pl)


def _pk_column_for(table: str) -> Optional[str]:
    if table in (
        "profiles",
        "goals",
        "foods",
        "meals",
        "meal_items",
        "recipes",
        "recipe_foods",
    ):
        return "id"
    return None
