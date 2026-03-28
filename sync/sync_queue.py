"""Operation queue on top of CacheDB.sync_queue."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from sync.cache_db import CacheDB

logger = logging.getLogger(__name__)


class SyncQueue:
    """Thin facade over CacheDB durable queue."""

    def __init__(self, cache: CacheDB) -> None:
        self._db = cache

    def enqueue(self, table: str, op: str, row_id: str, payload: Dict[str, Any]) -> None:
        self._db.enqueue_sync(table, op, row_id, payload)

    def peek_batch(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._db.peek_sync_batch(limit)
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "table_name": r["table_name"],
                    "operation": r["operation"],
                    "row_id": r["row_id"],
                    "payload": json.loads(r["payload"]),
                    "created_at": r["created_at"],
                    "retries": r["retries"],
                    "last_error": r["last_error"],
                }
            )
        return out

    def dequeue(self, op_id: int) -> None:
        self._db.dequeue_sync(op_id)

    def record_failure(self, op_id: int, error: str) -> None:
        self._db.record_sync_failure(op_id, error)
