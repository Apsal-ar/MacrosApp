"""Local SQLite cache for Macro Tracker — fast reads, write-through to Supabase.

Stores JSON payloads mirroring Supabase row shapes. Used by repositories for
local-first reads and immediate persistence; remote sync runs in background
threads where applicable.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LocalStore:
    """Thread-safe SQLite backing store keyed by entity type."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    def open(self) -> None:
        """Open the database and create schema if needed."""
        with self._lock:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._init_schema()

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
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_goals_profile ON goals(profile_id);

            CREATE TABLE IF NOT EXISTS foods (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS meals (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                date TEXT NOT NULL,
                meal_number INTEGER NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_meals_profile_date
                ON meals(profile_id, date);

            CREATE TABLE IF NOT EXISTS meal_items (
                id TEXT PRIMARY KEY,
                meal_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
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
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recipes_profile ON recipes(profile_id);

            CREATE TABLE IF NOT EXISTS recipe_ingredients (
                id TEXT PRIMARY KEY,
                recipe_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recipe_ing_recipe ON recipe_ingredients(recipe_id);

            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                op TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        c.commit()

    # ------------------------------------------------------------------
    # Meta / user switch
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
        """Clear cached rows when the logged-in user changes."""
        prev = self.get_meta("active_user_id")
        if prev is not None and prev != user_id:
            self._clear_user_data()
        self.set_meta("active_user_id", user_id)

    def _clear_user_data(self) -> None:
        logger.info("LocalStore: clearing cache (user switch)")
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
                "recipe_ingredients",
                "foods",
            ):
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.commit()

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def upsert_profile(self, row: Dict[str, Any]) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        pid = row["id"]
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "INSERT OR REPLACE INTO profiles(id, payload, updated_at) VALUES(?,?,?)",
                (pid, payload, ts),
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
    # Goals (one cached row per profile — latest wins)
    # ------------------------------------------------------------------

    def upsert_goals(self, row: Dict[str, Any]) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        gid = row["id"]
        profile_id = row["profile_id"]
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM goals WHERE profile_id=?", (profile_id,))
            self._conn.execute(
                "INSERT INTO goals(id, profile_id, payload, updated_at) VALUES(?,?,?,?)",
                (gid, profile_id, payload, ts),
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

    def upsert_food(self, row: Dict[str, Any]) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        fid = row["id"]
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "INSERT OR REPLACE INTO foods(id, payload, updated_at) VALUES(?,?,?)",
                (fid, payload, ts),
            )
            self._conn.commit()

    def get_food(self, food_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._conn is None:
                return None
            cur = self._conn.execute(
                "SELECT payload FROM foods WHERE id=?", (food_id,)
            )
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
        out: List[Dict[str, Any]] = []
        with self._lock:
            if self._conn is None:
                return out
            cur = self._conn.execute("SELECT payload FROM foods")
            for (payload,) in cur.fetchall():
                try:
                    d = json.loads(payload)
                    if d.get("source") == "manual" and d.get("created_by") == profile_id:
                        out.append(d)
                except (json.JSONDecodeError, TypeError):
                    continue
        out.sort(key=lambda x: (x.get("name") or "").lower())
        return out

    # ------------------------------------------------------------------
    # Meals / meal date cache
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

    def upsert_meal(self, row: Dict[str, Any]) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        mid = row["id"]
        profile_id = row["profile_id"]
        date = row["date"]
        meal_number = int(row.get("meal_number") or 0)
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO meals
                (id, profile_id, date, meal_number, payload, updated_at)
                VALUES(?,?,?,?,?,?)""",
                (mid, profile_id, date, meal_number, payload, ts),
            )
            self._conn.commit()

    def delete_meal(self, meal_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute("DELETE FROM meals WHERE id=?", (meal_id,))
            self._conn.execute("DELETE FROM meal_items WHERE meal_id=?", (meal_id,))
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

    def upsert_meal_item(self, row: Dict[str, Any]) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        iid = row["id"]
        meal_id = row["meal_id"]
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO meal_items(id, meal_id, payload, updated_at)
                   VALUES(?,?,?,?)""",
                (iid, meal_id, payload, ts),
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

    def clear_meals_for_date(self, profile_id: str, date: str) -> None:
        """Remove cached meals and items for a date (before remote refresh)."""
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
                    "DELETE FROM recipe_ingredients WHERE recipe_id=?", (rid,)
                )
            self._conn.execute("DELETE FROM recipes WHERE profile_id=?", (profile_id,))
            self._conn.commit()
        self.set_meta(f"recipes_loaded:{profile_id}", "")

    def upsert_recipe(self, row: Dict[str, Any]) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        rid = row["id"]
        profile_id = row["profile_id"]
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO recipes(id, profile_id, payload, updated_at)
                   VALUES(?,?,?,?)""",
                (rid, profile_id, payload, ts),
            )
            self._conn.commit()

    def upsert_recipe_ingredient(self, row: Dict[str, Any]) -> None:
        payload = json.dumps(row, default=str)
        ts = float(row.get("updated_at") or time.time())
        iid = row["id"]
        recipe_id = row["recipe_id"]
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                """INSERT OR REPLACE INTO recipe_ingredients(id, recipe_id, payload, updated_at)
                   VALUES(?,?,?,?)""",
                (iid, recipe_id, payload, ts),
            )
            self._conn.commit()

    def delete_recipe_ingredient(self, ingredient_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "DELETE FROM recipe_ingredients WHERE id=?", (ingredient_id,)
            )
            self._conn.commit()

    def delete_recipe(self, recipe_id: str) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "DELETE FROM recipe_ingredients WHERE recipe_id=?", (recipe_id,)
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

    def get_recipe_ingredient_rows(self, recipe_id: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self._lock:
            if self._conn is None:
                return rows
            cur = self._conn.execute(
                "SELECT payload FROM recipe_ingredients WHERE recipe_id=?",
                (recipe_id,),
            )
            for (payload,) in cur.fetchall():
                try:
                    rows.append(json.loads(payload))
                except json.JSONDecodeError:
                    continue
        return rows

    # ------------------------------------------------------------------
    # Sync queue (failed remote writes)
    # ------------------------------------------------------------------

    def enqueue_sync(
        self, table_name: str, op: str, payload: Dict[str, Any]
    ) -> None:
        with self._lock:
            if self._conn is None:
                return
            self._conn.execute(
                "INSERT INTO sync_queue(table_name, op, payload, created_at) VALUES(?,?,?,?)",
                (table_name, op, json.dumps(payload, default=str), time.time()),
            )
            self._conn.commit()
