"""Background Supabase sync: flush queue, pull remote, periodic schedule."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from kivy.clock import Clock

from sync.cache_db import CacheDB
from sync.sync_queue import SyncQueue

logger = logging.getLogger(__name__)

# Push queue in FK-safe order (parents before children)
_TABLE_ORDER = {
    "profiles": 0,
    "goals": 1,
    "foods": 2,
    "recipes": 3,
    "recipe_foods": 4,
    "meals": 5,
    "meal_items": 6,
}

# Pull order: parents before children
_PULL_ORDER = [
    "profiles",
    "goals",
    "foods",
    "recipes",
    "recipe_foods",
    "meals",
    "meal_items",
]

_MEAL_ITEM_SELECT = (
    "id, meal_id, food_id, quantity_g, updated_at, "
    "foods(name, calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g, salt)"
)

_RECIPE_FOODS_SELECT = (
    "id, recipe_id, food_id, quantity_g, updated_at, "
    "foods(name, calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g, salt)"
)


def _strip_sync_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove cache-only keys before sending to Supabase."""
    out = {k: v for k, v in payload.items() if k not in ("sync_status",)}
    return out


def _foods_payload_for_remote(clean: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure food upsert matches Supabase ``foods`` columns (no cache-only keys)."""
    return dict(clean)


class SyncManager:
    """Singleton: flush outbound queue, pull inbound changes, schedule periodic sync."""

    _instance: Optional["SyncManager"] = None
    _lock = threading.Lock()

    def __init__(self, supabase: Any, cache: CacheDB) -> None:
        self._sb = supabase
        self._cache = cache
        self._queue = SyncQueue(cache)
        self._profile_id: str = ""
        self._scheduled = False

    @classmethod
    def get_instance(cls) -> Optional["SyncManager"]:
        return cls._instance

    @classmethod
    def init_instance(cls, supabase: Any, cache: CacheDB) -> "SyncManager":
        with cls._lock:
            cls._instance = cls(supabase, cache)
            return cls._instance

    def set_profile_id(self, profile_id: str) -> None:
        self._profile_id = profile_id

    def _sort_batch(
        self, batch: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        return sorted(
            batch,
            key=lambda x: (_TABLE_ORDER.get(x["table_name"], 99), x["created_at"]),
        )

    def flush(self) -> None:
        """Drain queue: push to Supabase, dequeue successes, retry failures."""
        if self._sb is None:
            return
        if self._profile_id:
            self._cache.requeue_unsynced_outbound(self._profile_id)
        batch = self._queue.peek_batch(100)
        if not batch:
            return
        for op in self._sort_batch(batch):
            op_id = op["id"]
            table = op["table_name"]
            operation = op["operation"]
            payload = op["payload"]
            try:
                tbl = self._sb.table(table)
                if operation == "delete":
                    rid = payload.get("id") or op["row_id"]
                    tbl.delete().eq("id", rid).execute()
                else:
                    clean = _strip_sync_fields(dict(payload))
                    self._upsert_with_profile_fallback(table, clean)
                self._queue.dequeue(op_id)
                rid_ok = payload.get("id") or op["row_id"]
                if rid_ok:
                    self._cache.mark_synced(table, rid_ok)
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("sync flush failed op=%s: %s", op_id, exc)
                self._queue.record_failure(op_id, str(exc))

    def _upsert_with_profile_fallback(self, table: str, clean: Dict[str, Any]) -> None:
        tbl = self._sb.table(table)
        if table == "foods":
            clean = _foods_payload_for_remote(clean)
        try:
            tbl.upsert(clean).execute()
        except Exception as exc:  # pylint: disable=broad-except
            message = str(exc)
            optional_cols = ("waist_cm", "neck_cm", "hips_cm", "body_fat_pct")
            if table == "profiles" and any(
                f"'{col}'" in message for col in optional_cols
            ):
                legacy = {k: v for k, v in clean.items() if k not in optional_cols}
                tbl.upsert(legacy).execute()
                return
            if table == "goals" and "meal_labels" in message:
                clean.pop("meal_labels", None)
                tbl.upsert(clean).execute()
                return
            raise

    def pull(self) -> None:
        """Fetch rows from Supabase newer than local cache (last-write-wins on tie → remote)."""
        if self._sb is None or not self._profile_id:
            return
        pid = self._profile_id
        try:
            self._pull_profiles(pid)
            self._pull_goals(pid)
            self._pull_foods(pid)
            self._pull_recipes(pid)
            self._pull_meals(pid)
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("sync pull: %s", exc)

    def _pull_profiles(self, profile_id: str) -> None:
        r = self._sb.table("profiles").select("*").eq("id", profile_id).execute()
        if r.data:
            row = r.data[0]
            local = self._cache.get_profile(profile_id)
            if self._should_take_remote(local, row):
                self._cache.upsert_profile(row, from_remote=True)

    def _pull_goals(self, profile_id: str) -> None:
        r = (
            self._sb.table("goals")
            .select("*")
            .eq("profile_id", profile_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if r.data:
            row = r.data[0]
            local = self._cache.get_goals_for_profile(profile_id)
            if self._should_take_remote(local, row):
                self._cache.upsert_goals(row, from_remote=True)

    def _pull_foods(self, profile_id: str) -> None:
        max_ts = self._cache.max_updated_at("foods")
        qry = self._sb.table("foods").select("*").eq("created_by", profile_id)
        if max_ts > 0:
            qry = qry.gte("updated_at", max_ts)
        q = qry.execute()
        for row in q.data or []:
            local = self._cache.get_food(row["id"])
            if self._should_take_remote(local, row):
                self._cache.upsert_food(row, from_remote=True)

    def _pull_recipes(self, profile_id: str) -> None:
        r = (
            self._sb.table("recipes")
            .select("*")
            .eq("profile_id", profile_id)
            .execute()
        )
        for row in r.data or []:
            local = self._cache.get_recipe_row(row["id"])
            if self._should_take_remote(local, row):
                self._cache.upsert_recipe(row, from_remote=True)
            rid = row["id"]
            ir = (
                self._sb.table("recipe_foods")
                .select(_RECIPE_FOODS_SELECT)
                .eq("recipe_id", rid)
                .execute()
            )
            for ing in ir.data or []:
                self._cache.upsert_recipe_food(ing, from_remote=True)
        self._cache.set_recipes_list_fetched(profile_id)

    def _pull_meals(self, profile_id: str) -> None:
        r = (
            self._sb.table("meals")
            .select("*")
            .eq("profile_id", profile_id)
            .execute()
        )
        for row in r.data or []:
            local_m = None
            for m in self._cache.get_all_meals_for_profile_rows(profile_id):
                if m.get("id") == row["id"]:
                    local_m = m
                    break
            if self._should_take_remote(local_m, row):
                self._cache.upsert_meal(row, from_remote=True)
            mid = row["id"]
            ir = (
                self._sb.table("meal_items")
                .select(_MEAL_ITEM_SELECT)
                .eq("meal_id", mid)
                .execute()
            )
            for item in ir.data or []:
                self._cache.upsert_meal_item(item, from_remote=True)

    @staticmethod
    def _should_take_remote(
        local: Optional[Dict[str, Any]], remote: Dict[str, Any]
    ) -> bool:
        if local is None:
            return True
        lu = float(local.get("updated_at") or 0)
        ru = float(remote.get("updated_at") or 0)
        if ru > lu:
            return True
        if ru < lu:
            return False
        return True  # tie → remote wins

    def full_sync(self) -> None:
        self.flush()
        self.pull()

    def schedule(self, interval: float = 30.0) -> None:
        if self._scheduled:
            return
        self._scheduled = True

        def tick(_dt: float) -> None:
            threading.Thread(target=self._safe_flush_pull, daemon=True).start()

        Clock.schedule_interval(tick, interval)

    def _safe_flush_pull(self) -> None:
        try:
            self.flush()
            self.pull()
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("scheduled sync: %s", exc)


def _spawn_bg(fn: Any) -> None:
    threading.Thread(target=fn, daemon=True).start()


def trigger_flush_async() -> None:
    """Fire-and-forget flush from repositories."""
    sm = SyncManager.get_instance()
    if sm is None:
        return
    _spawn_bg(sm.flush)
