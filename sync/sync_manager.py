"""Connectivity-aware sync manager.

Runs on Kivy's Clock scheduler every SYNC_INTERVAL_SECONDS seconds.
When connectivity is detected:
1. Flushes the SyncQueue (local → Supabase).
2. Pulls remote changes (Supabase → local), applying ConflictResolver where needed.

Exposes SyncStatus as a simple observable object so UI components can bind
to pending_count and last_synced_at without coupling to internals.
"""

from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from sync.cache_db import CacheDB
from sync.sync_queue import SyncQueue
from sync.conflict_resolver import ConflictResolver
import config

logger = logging.getLogger(__name__)

# Tables that SyncManager pulls from remote, in dependency order
_PULL_TABLES: List[str] = [
    "profiles",
    "goals",
    "foods",
    "meals",
    "meal_items",
    "recipes",
    "recipe_ingredients",
]


@dataclass
class SyncStatus:
    """Observable snapshot of sync engine state.

    Attributes:
        pending_count: Operations waiting in the queue.
        last_synced_at: Unix timestamp of the most recent successful flush, or None.
        is_online: Whether connectivity was detected on the last poll.
        error_message: Last error string, or None if no errors.
    """

    pending_count: int = 0
    last_synced_at: Optional[float] = None
    is_online: bool = False
    error_message: Optional[str] = None


class SyncManager:
    """Orchestrates offline-first sync between the local SQLite cache and Supabase.

    Designed as a singleton; obtain via SyncManager.get_instance().
    The Kivy App should call start() once on app launch, passing a reference
    to the initialised Supabase client.
    """

    _instance: Optional["SyncManager"] = None

    def __init__(self) -> None:
        self._db = CacheDB.get_instance()
        self._queue = SyncQueue()
        self._resolver = ConflictResolver()
        self._supabase: Optional[Any] = None
        self._profile_id: Optional[str] = None
        self._status = SyncStatus()
        self._listeners: List[Callable[[SyncStatus], None]] = []
        self._clock_event: Optional[Any] = None

    @classmethod
    def get_instance(cls) -> "SyncManager":
        """Return the process-wide SyncManager singleton.

        Returns:
            The shared SyncManager instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, supabase_client: Any, profile_id: str) -> None:
        """Attach the Supabase client and begin the polling loop.

        Should be called once after successful authentication.

        Args:
            supabase_client: An initialised supabase-py Client instance.
            profile_id: The authenticated user's profile UUID.
        """
        self._supabase = supabase_client
        self._profile_id = profile_id
        self._schedule_next()
        logger.info("SyncManager started for profile %s", profile_id)

    def stop(self) -> None:
        """Cancel the polling loop and detach the Supabase client."""
        if self._clock_event is not None:
            self._clock_event.cancel()
            self._clock_event = None
        self._supabase = None
        self._profile_id = None

    # ------------------------------------------------------------------
    # Status observation
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable[[SyncStatus], None]) -> None:
        """Register a callback to be invoked whenever SyncStatus changes.

        Args:
            callback: Function accepting a SyncStatus instance.
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[SyncStatus], None]) -> None:
        """Deregister a previously added callback.

        Args:
            callback: The same callable passed to add_listener.
        """
        self._listeners.discard(callback) if hasattr(self._listeners, "discard") else None
        if callback in self._listeners:
            self._listeners.remove(callback)

    @property
    def status(self) -> SyncStatus:
        """Current SyncStatus snapshot."""
        self._status.pending_count = self._queue.pending_count()
        return self._status

    # ------------------------------------------------------------------
    # Manual trigger
    # ------------------------------------------------------------------

    def sync_now(self) -> None:
        """Trigger an immediate sync cycle outside the regular schedule.

        Safe to call from the UI thread; the actual network work is done
        inline (consider running on a background thread for large queues).
        """
        self._run_sync_cycle(dt=0)

    # ------------------------------------------------------------------
    # Core sync cycle
    # ------------------------------------------------------------------

    def _run_sync_cycle(self, dt: float) -> None:  # noqa: ARG002
        """Execute one push + pull cycle.

        Args:
            dt: Kivy Clock delta (ignored).
        """
        if not config.ENABLE_SYNC or self._supabase is None:
            return

        self._status.is_online = self._check_connectivity()
        if not self._status.is_online:
            self._notify_listeners()
            self._schedule_next()
            return

        try:
            self._flush_queue()
            self._pull_remote()
            self._status.last_synced_at = time.time()
            self._status.error_message = None
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Sync cycle failed: %s", exc, exc_info=True)
            self._status.error_message = str(exc)

        self._status.pending_count = self._queue.pending_count()
        self._notify_listeners()
        self._schedule_next()

    # ------------------------------------------------------------------
    # Push (local → remote)
    # ------------------------------------------------------------------

    def _flush_queue(self) -> None:
        """Push all pending queue entries to Supabase, oldest first."""
        entries = self._queue.peek(limit=100)
        if not entries:
            return

        logger.info("Flushing %d queued operations", len(entries))
        for entry in entries:
            try:
                self._push_entry(entry)
                self._queue.mark_success(entry.id)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Push failed for %s/%s: %s", entry.table_name, entry.row_id, exc)
                self._queue.increment_retries(entry.id)

    def _push_entry(self, entry: Any) -> None:
        """Push a single queue entry to the appropriate Supabase table.

        Args:
            entry: A SyncQueueEntry to be applied.
        """
        table = self._supabase.table(entry.table_name)
        if entry.operation in ("insert", "update"):
            table.upsert(entry.payload).execute()
        elif entry.operation == "delete":
            table.delete().eq("id", entry.row_id).execute()

    # ------------------------------------------------------------------
    # Pull (remote → local)
    # ------------------------------------------------------------------

    def _pull_remote(self) -> None:
        """Fetch remote rows updated since last_synced_at and merge locally."""
        since = self._status.last_synced_at or 0.0
        for table_name in _PULL_TABLES:
            try:
                self._pull_table(table_name, since)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Pull failed for %s: %s", table_name, exc)

    def _pull_table(self, table_name: str, since: float) -> None:
        """Pull and merge all rows in a table updated after `since`.

        Args:
            table_name: Supabase table to pull from.
            since: Unix timestamp; only rows with updated_at > since are fetched.
        """
        response = (
            self._supabase.table(table_name)
            .select("*")
            .gt("updated_at", since)
            .execute()
        )
        remote_rows: List[Dict[str, Any]] = response.data or []
        if not remote_rows:
            return

        conn = self._db.connection()
        for remote_row in remote_rows:
            row_id = remote_row.get("id")
            local_row = conn.execute(
                f"SELECT * FROM {table_name} WHERE id = ?", (row_id,)  # noqa: S608
            ).fetchone()

            if local_row is None:
                self._upsert_local(conn, table_name, remote_row, sync_status="synced")
            else:
                local_dict = dict(local_row)
                if local_dict.get("sync_status") == "pending":
                    winner, _ = self._resolver.resolve(table_name, local_dict, remote_row)
                    self._upsert_local(conn, table_name, winner, sync_status="synced")
                else:
                    self._upsert_local(conn, table_name, remote_row, sync_status="synced")
        conn.commit()

    def _upsert_local(
        self,
        conn: Any,
        table_name: str,
        row: Dict[str, Any],
        sync_status: str = "synced",
    ) -> None:
        """Insert or replace a row in the local SQLite cache.

        Args:
            conn: Open sqlite3.Connection.
            table_name: Target table.
            row: Row data dict (must include 'id').
            sync_status: Value to set on the sync_status column.
        """
        row = {**row, "sync_status": sync_status}
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" * len(row))
        conn.execute(
            f"INSERT OR REPLACE INTO {table_name} ({cols}) VALUES ({placeholders})",  # noqa: S608
            list(row.values()),
        )

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    @staticmethod
    def _check_connectivity() -> bool:
        """Probe connectivity with a quick TCP connection attempt.

        Returns:
            True if the host is reachable, False otherwise.
        """
        try:
            socket.setdefaulttimeout(2)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _schedule_next(self) -> None:
        """Schedule the next sync cycle via Kivy Clock."""
        try:
            from kivy.clock import Clock  # pylint: disable=import-outside-toplevel
            self._clock_event = Clock.schedule_once(
                self._run_sync_cycle, config.SYNC_INTERVAL_SECONDS
            )
        except ImportError:
            pass

    def _notify_listeners(self) -> None:
        """Invoke all registered SyncStatus listeners with a fresh snapshot."""
        status = self.status
        for callback in self._listeners:
            try:
                callback(status)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Listener raised: %s", exc)
