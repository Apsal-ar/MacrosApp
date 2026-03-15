"""Last-write-wins conflict resolver for offline-first sync.

When SyncManager detects that a remote row has a newer updated_at than the
local cached version, ConflictResolver decides which version wins and
archives the loser to conflict_log for audit purposes.

The strategy is designed to be swappable: subclass ConflictResolver and
override resolve() to implement field-level merge or user-prompted resolution.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Tuple

from sync.cache_db import CacheDB

logger = logging.getLogger(__name__)


class ConflictResolver:
    """Implements last-write-wins conflict resolution based on updated_at.

    The resolver is stateless and thread-safe; all state lives in the DB.
    """

    def __init__(self) -> None:
        self._db = CacheDB.get_instance()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        table_name: str,
        local_row: Dict[str, Any],
        remote_row: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        """Choose the winning row between a local and remote version.

        Uses updated_at (Unix timestamp float) as the tiebreaker.
        The losing row is archived to conflict_log.

        Args:
            table_name: Name of the table the conflict belongs to.
            local_row: The row as it exists in the local SQLite cache.
            remote_row: The row as pulled from Supabase.

        Returns:
            A tuple of (winning_row_dict, source) where source is
            'local' or 'remote'.
        """
        local_ts = float(local_row.get("updated_at", 0))
        remote_ts = float(remote_row.get("updated_at", 0))

        if remote_ts >= local_ts:
            winner, loser, source = remote_row, local_row, "remote"
        else:
            winner, loser, source = local_row, remote_row, "local"

        row_id = local_row.get("id", "unknown")
        logger.info(
            "Conflict on %s/%s — winner: %s (local=%.0f remote=%.0f)",
            table_name, row_id, source, local_ts, remote_ts,
        )
        self._archive_loser(table_name, row_id, loser, winner)
        return winner, source

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _archive_loser(
        self,
        table_name: str,
        row_id: str,
        loser: Dict[str, Any],
        winner: Dict[str, Any],
    ) -> None:
        """Persist the losing row to conflict_log for audit.

        Args:
            table_name: Affected table name.
            row_id: UUID of the conflicting row.
            loser: The row that was overwritten.
            winner: The row that won the conflict.
        """
        conn = self._db.connection()
        conn.execute(
            """
            INSERT INTO conflict_log (table_name, row_id, local_payload, remote_payload, resolved_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                table_name,
                row_id,
                json.dumps(loser),
                json.dumps(winner),
                time.time(),
            ),
        )
        conn.commit()

    def get_conflict_log(self, limit: int = 100) -> list:
        """Return recent conflict log entries for debugging.

        Args:
            limit: Maximum number of rows to return, newest first.

        Returns:
            List of sqlite3.Row objects.
        """
        conn = self._db.connection()
        return conn.execute(
            """
            SELECT * FROM conflict_log
            ORDER BY resolved_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
