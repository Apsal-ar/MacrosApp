"""Operation queue that logs every local write for deferred push to Supabase.

Every Repository write calls SyncQueue.enqueue() before returning.
SyncManager drains the queue oldest-first when connectivity is available.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Dict, Any, List, Optional

from sync.cache_db import CacheDB
import config

logger = logging.getLogger(__name__)


class SyncQueueEntry:
    """Lightweight struct representing a single queued operation.

    Attributes:
        id: Auto-incremented SQLite row id.
        table_name: Target Supabase table.
        row_id: UUID of the affected row.
        operation: 'insert' | 'update' | 'delete'.
        payload: Full row data as a Python dict.
        retries: Number of failed push attempts so far.
        created_at: Unix timestamp of when the op was enqueued.
    """

    __slots__ = ("id", "table_name", "row_id", "operation", "payload", "retries", "created_at")

    def __init__(
        self,
        id: int,
        table_name: str,
        row_id: str,
        operation: str,
        payload: Dict[str, Any],
        retries: int,
        created_at: float,
    ) -> None:
        self.id = id
        self.table_name = table_name
        self.row_id = row_id
        self.operation = operation
        self.payload = payload
        self.retries = retries
        self.created_at = created_at


class SyncQueue:
    """Manages the persistent operation queue stored in the local SQLite cache.

    All methods are safe to call from any thread; they acquire a connection
    through the thread-local CacheDB mechanism.
    """

    def __init__(self) -> None:
        self._db = CacheDB.get_instance()

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def enqueue(
        self,
        table_name: str,
        row_id: str,
        operation: str,
        payload: Dict[str, Any],
    ) -> None:
        """Append a write operation to the queue.

        Args:
            table_name: Name of the Supabase/SQLite table being mutated.
            row_id: UUID primary key of the affected row.
            operation: One of 'insert', 'update', 'delete'.
            payload: Complete row data dict (used for upsert on Supabase side).
        """
        conn = self._db.connection()
        conn.execute(
            """
            INSERT INTO sync_queue (table_name, row_id, operation, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (table_name, row_id, operation, json.dumps(payload), time.time()),
        )
        conn.commit()
        logger.debug("Enqueued %s on %s/%s", operation, table_name, row_id)

    # ------------------------------------------------------------------
    # Read path (used by SyncManager)
    # ------------------------------------------------------------------

    def peek(self, limit: int = 50) -> List[SyncQueueEntry]:
        """Return up to `limit` oldest entries without removing them.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            Ordered list of SyncQueueEntry from oldest to newest.
        """
        conn = self._db.connection()
        rows = conn.execute(
            """
            SELECT id, table_name, row_id, operation, payload, retries, created_at
            FROM sync_queue
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            SyncQueueEntry(
                id=r["id"],
                table_name=r["table_name"],
                row_id=r["row_id"],
                operation=r["operation"],
                payload=json.loads(r["payload"]),
                retries=r["retries"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def pending_count(self) -> int:
        """Return the total number of operations waiting to be synced.

        Returns:
            Integer count of rows in sync_queue.
        """
        conn = self._db.connection()
        row = conn.execute("SELECT COUNT(*) FROM sync_queue").fetchone()
        return row[0]

    # ------------------------------------------------------------------
    # Drain path (used by SyncManager after successful push)
    # ------------------------------------------------------------------

    def mark_success(self, entry_id: int) -> None:
        """Delete a successfully synced entry from the queue.

        Args:
            entry_id: The auto-incremented id of the SyncQueueEntry.
        """
        conn = self._db.connection()
        conn.execute("DELETE FROM sync_queue WHERE id = ?", (entry_id,))
        conn.commit()

    def increment_retries(self, entry_id: int) -> None:
        """Increment the retry counter for a failed entry.

        Entries that exceed SYNC_QUEUE_MAX_RETRIES are removed to prevent
        the queue from growing unboundedly on permanently bad payloads.

        Args:
            entry_id: The auto-incremented id of the SyncQueueEntry.
        """
        conn = self._db.connection()
        conn.execute(
            "UPDATE sync_queue SET retries = retries + 1 WHERE id = ?",
            (entry_id,),
        )
        conn.execute(
            "DELETE FROM sync_queue WHERE id = ? AND retries > ?",
            (entry_id, config.SYNC_QUEUE_MAX_RETRIES),
        )
        conn.commit()

    def clear(self) -> None:
        """Remove all pending operations — intended for testing and reset flows."""
        conn = self._db.connection()
        conn.execute("DELETE FROM sync_queue")
        conn.commit()
