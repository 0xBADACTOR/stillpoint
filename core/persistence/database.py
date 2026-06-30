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
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_SALT_BYTES = 32


def _utcnow_iso() -> str:
    """ISO 8601 UTC, second precision. SQLite stores this as TEXT."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    """Thin wrapper around a single sqlite3 connection."""

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

    # -- installation-row accessors -----------------------------------------

    def plain_plates_enabled(self) -> bool:
        row = self.fetchone("SELECT plain_plates_enabled FROM installation WHERE id = 1")
        return bool(row and row["plain_plates_enabled"])

    def set_plain_plates_enabled(self, enabled: bool) -> None:
        self.execute(
            "UPDATE installation SET plain_plates_enabled = ? WHERE id = 1",
            (1 if enabled else 0,),
        )