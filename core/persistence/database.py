"""SQLite database wrapper for StillPoint.

Owns:
    - connection lifecycle (connect, close, context manager)
    - schema bootstrap (idempotent; safe to run on every open)
    - per-install salt (generated on first run, persisted in `installation`)
    - identifier hashing (SHA-256 over plaintext + salt)

Pure stdlib. No ORM. Single-process; one connection per Database instance.
"""
from __future__ import annotations

import hashlib
import math
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, List, Optional

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_SALT_BYTES = 32


def _utcnow_iso() -> str:
    """ISO 8601 UTC, second precision. SQLite stores this as TEXT."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    """Thin wrapper around a single sqlite3 connection."""

    CLUSTER_DISTANCE_THRESHOLD_METERS = 100.0

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path) if str(path) != ":memory:" else Path(":memory:")
        self._conn: sqlite3.Connection | None = None
        self._salt: bytes | None = None

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> Database:
        self.connect()
        self.bootstrap()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def connect(self) -> None:
        if self._conn is not None:
            return
        # isolation_level=None puts sqlite3 in autocommit for DDL,
        # which we want for the PRAGMAs; we'll explicitly commit on writes.
        self._conn = sqlite3.connect(self._path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._salt = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() or use as context manager.")
        return self._conn

    # -- schema bootstrap ---------------------------------------------------

    def bootstrap(self) -> None:
        """Apply schema.sql and ensure the installation row exists.

        Idempotent: every CREATE uses IF NOT EXISTS. Safe to call on
        every open.
        """
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        self.conn.executescript(schema_sql)

        cur = self.conn.execute("SELECT salt FROM installation WHERE id = 1")
        row = cur.fetchone()
        if row is None:
            self._salt = secrets.token_bytes(_SALT_BYTES)
            self.conn.execute(
                "INSERT INTO installation (id, salt, created_at, plain_plates_enabled) "
                "VALUES (?, ?, ?, 0)",
                (1, self._salt, _utcnow_iso()),
            )
        else:
            self._salt = bytes(row["salt"])

    # -- identifier hashing -------------------------------------------------

    def hash_identifier(self, plaintext: str) -> str:
        """SHA-256(plaintext + per-install salt), hex-encoded.

        Used to canonicalise MAC addresses and plates into the unique key
        that joins signals ↔ detections.
        """
        if self._salt is None:
            raise RuntimeError("Database not bootstrapped. Call bootstrap() first.")
        digest = hashlib.sha256(plaintext.encode("utf-8") + self._salt).hexdigest()
        return digest

    # -- thin cursor helpers -----------------------------------------------

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, seq: list[tuple[Any, ...]]) -> sqlite3.Cursor:
        return self.conn.executemany(sql, seq)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self.conn.execute(sql, params).fetchone()
        return row

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    # -- geo-clustering ---------------------------------------------------

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return the great-circle distance between two points on Earth in meters."""
        # convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        # haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        # Radius of Earth in kilometers: 6371 km
        km = 6371 * c
        return km * 1000  # convert to meters

    def update_geo_clusters(self, signal_id: int | None = None) -> None:
        """Compute and store geo-clusters for signals.

        If signal_id is provided, only update that signal; otherwise update all signals.
        """
        # We'll delete existing clusters for the affected signal(s) and then insert new ones.
        if signal_id is not None:
            self.execute("DELETE FROM geo_clusters WHERE signal_id = ?", (signal_id,))
            signal_ids = [signal_id]
        else:
            self.execute("DELETE FROM geo_clusters")
            # Get all signal IDs that have at least one detection with lat/lon
            rows = self.fetchall(
                """
                SELECT DISTINCT signal_id FROM detections
                WHERE lat IS NOT NULL AND lon IS NOT NULL
                """
            )
            signal_ids = [row["signal_id"] for row in rows]

        for sid in signal_ids:
            # Get detections for this signal, ordered by seen_at
            rows = self.fetchall(
                """
                SELECT lat, lon, seen_at FROM detections
                WHERE signal_id = ? AND lat IS NOT NULL AND lon IS NOT NULL
                ORDER BY seen_at
                """,
                (sid,),
            )
            if not rows:
                continue

            clusters = []  # each cluster will be a dict with keys: lat_sum, lon_sum, count, first_seen, last_seen
            for lat, lon, seen_at in rows:
                if not clusters:
                    clusters.append({
                        'lat_sum': lat,
                        'lon_sum': lon,
                        'count': 1,
                        'first_seen': seen_at,
                        'last_seen': seen_at,
                    })
                else:
                    last_cluster = clusters[-1]
                    # compute centroid of last cluster
                    centroid_lat = last_cluster['lat_sum'] / last_cluster['count']
                    centroid_lon = last_cluster['lon_sum'] / last_cluster['count']
                    distance = self._haversine(centroid_lat, centroid_lon, float(lat), float(lon))
                    if distance <= self.CLUSTER_DISTANCE_THRESHOLD_METERS:
                        # add to current cluster
                        last_cluster['lat_sum'] += lat
                        last_cluster['lon_sum'] += lon
                        last_cluster['count'] += 1
                        last_cluster['last_seen'] = seen_at
                    else:
                        # start a new cluster
                        clusters.append({
                            'lat_sum': lat,
                            'lon_sum': lon,
                            'count': 1,
                            'first_seen': seen_at,
                            'last_seen': seen_at,
                        })

            # Now insert each cluster into geo_clusters
            for cluster in clusters:
                centroid_lat = cluster['lat_sum'] / cluster['count']
                centroid_lon = cluster['lon_sum'] / cluster['count']
                self.execute(
                    """
                    INSERT INTO geo_clusters (
                        signal_id, centroid_lat, centroid_lon, detection_count,
                        first_hit, last_hit
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sid,
                        centroid_lat,
                        centroid_lon,
                        cluster['count'],
                        cluster['first_seen'],
                        cluster['last_seen'],
                    ),
                )

    # -- installation-row accessors -----------------------------------------

    def plain_plates_enabled(self) -> bool:
        row = self.fetchone("SELECT plain_plates_enabled FROM installation WHERE id = 1")
        return bool(row and row["plain_plates_enabled"])

    def set_plain_plates_enabled(self, enabled: bool) -> None:
        self.execute(
            "UPDATE installation SET plain_plates_enabled = ? WHERE id = 1",
            (1 if enabled else 0,),
        )

    # -- ignored signals ----------------------------------------------------

    def is_signal_ignored(self, identifier_hash: str) -> bool:
        """Return True if the given identifier_hash is in the ignored_signals table."""
        row = self.fetchone(
            "SELECT 1 FROM ignored_signals WHERE identifier_hash = ?",
            (identifier_hash,),
        )
        return bool(row)

    def add_ignored_signal(self, identifier_hash: str, reason: Optional[str] = None) -> None:
        """Add an identifier_hash to the ignored_signals table."""
        self.execute(
            """
            INSERT INTO ignored_signals (identifier_hash, ignored_at, reason)
            VALUES (?, ?, ?)
            ON CONFLICT(identifier_hash) DO UPDATE SET
                ignored_at = excluded.ignored_at,
                reason = COALESCE(excluded.reason, ignored_signals.reason)
            """,
            (identifier_hash, _utcnow_iso(), reason),
        )

    def remove_ignored_signal(self, identifier_hash: str) -> None:
        """Remove an identifier_hash from the ignored_signals table."""
        self.execute(
            "DELETE FROM ignored_signals WHERE identifier_hash = ?",
            (identifier_hash,),
        )

    def list_ignored_signals(self) -> List[dict]:
        """Return a list of ignored signals as dictionaries."""
        rows = self.fetchall(
            "SELECT identifier_hash, ignored_at, reason FROM ignored_signals ORDER BY ignored_at DESC"
        )
        return [dict(row) for row in rows]

    def update_follower_status(self) -> None:
        """Update follower status for all signals based on geo-cluster count.

        A signal is considered a follower if it has 3 or more distinct geo-clusters.
        Updates the is_follower flag in the signals table and logs changes to
        follower_events table.
        """
        # Get all signals with their geo-cluster count
        rows = self.fetchall(
            """
            SELECT
                s.id,
                s.identifier_hash,
                s.signal_type,
                s.is_follower,
                COUNT(gc.id) as cluster_count
            FROM signals s
            LEFT JOIN geo_clusters gc ON s.id = gc.signal_id
            GROUP BY s.id, s.identifier_hash, s.signal_type, s.is_follower
            """
        )

        for row in rows:
            signal_id = row["id"]
            identifier_hash = row["identifier_hash"]
            signal_type = row["signal_type"]
            is_currently_follower = bool(row["is_follower"])
            cluster_count = row["cluster_count"]

            # Determine if it should be a follower (3+ clusters)
            should_be_follower = cluster_count >= 3

            # If status needs to change
            if should_be_follower and not is_currently_follower:
                # Mark as follower
                self.execute(
                    "UPDATE signals SET is_follower = 1 WHERE id = ?",
                    (signal_id,),
                )
                # Log the event
                self.execute(
                    """
                    INSERT INTO follower_events
                    (signal_id, event, reason, cluster_count, detection_count, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal_id,
                        "flagged",
                        f"Identified as follower with {cluster_count} geo-clusters",
                        cluster_count,
                        self._get_detection_count_for_signal(signal_id),
                        _utcnow_iso(),
                    ),
                )
            elif not should_be_follower and is_currently_follower:
                # Unmark as follower
                self.execute(
                    "UPDATE signals SET is_follower = 0 WHERE id = ?",
                    (signal_id,),
                )
                # Log the event
                self.execute(
                    """
                    INSERT INTO follower_events
                    (signal_id, event, reason, cluster_count, detection_count, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal_id,
                        "unflagged",
                        f"No longer meets follower criteria ({cluster_count} < 3 clusters)",
                        cluster_count,
                        self._get_detection_count_for_signal(signal_id),
                        _utcnow_iso(),
                    ),
                )

    def _get_detection_count_for_signal(self, signal_id: int) -> int:
        """Get the total detection count for a signal."""
        row = self.fetchone(
            "SELECT COUNT(*) as count FROM detections WHERE signal_id = ?",
            (signal_id,),
        )
        return row["count"] if row else 0