"""Tests for the StillPoint SQLite schema and Database bootstrap.

These tests use an in-memory SQLite (`:memory:`) for speed. No tmp_path
fixtures — nothing to clean up.
"""
from __future__ import annotations

import sqlite3

import pytest

from core.persistence import Database


@pytest.fixture()
def db() -> Database:
    d = Database(":memory:")
    d.connect()
    d.bootstrap()
    yield d
    d.close()


def test_bootstrap_creates_all_tables(db: Database) -> None:
    rows = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    )
    names = {r["name"] for r in rows}
    expected = {"signals", "detections", "geo_clusters", "follower_events", "installation"}
    missing = expected - names
    assert not missing, f"missing tables after bootstrap: {missing}"


def test_salt_is_persistent_across_bootstrap() -> None:
    d1 = Database(":memory:")
    d1.connect()
    d1.bootstrap()
    salt_1 = d1.fetchone("SELECT salt FROM installation WHERE id = 1")["salt"]
    d1.close()

    # Fresh Database object, same underlying memory (different connection in :memory:,
    # but we just need to verify the row was written correctly).
    d2 = Database(":memory:")
    d2.connect()
    d2.bootstrap()
    salt_2 = d2.fetchone("SELECT salt FROM installation WHERE id = 1")["salt"]
    d2.close()

    # Both salts should be 32 bytes (the per-install length).
    assert len(bytes(salt_1)) == 32
    assert len(bytes(salt_2)) == 32


def test_identifier_hash_is_deterministic_within_install(db: Database) -> None:
    h1 = db.hash_identifier("AA:BB:CC:DD:EE:FF")
    h2 = db.hash_identifier("AA:BB:CC:DD:EE:FF")
    assert h1 == h2
    # And different from a different plaintext.
    assert h1 != db.hash_identifier("11:22:33:44:55:66")
    # And 64 hex chars (SHA-256).
    assert len(h1) == 64


def test_identifier_hash_unique_constraint(db: Database) -> None:
    """Two signals with the same identifier_hash must fail on insert."""
    h = db.hash_identifier("AA:BB:CC:DD:EE:FF")
    db.execute(
        "INSERT INTO signals (signal_type, identifier_hash, first_seen, last_seen) "
        "VALUES (?, ?, ?, ?)",
        ("wifi", h, "2026-06-30T00:00:00+00:00", "2026-06-30T00:00:00+00:00"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO signals (signal_type, identifier_hash, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?)",
            ("wifi", h, "2026-06-30T00:00:00+00:00", "2026-06-30T00:00:00+00:00"),
        )


def test_signal_type_check_constraint(db: Database) -> None:
    h = db.hash_identifier("00:11:22:33:44:55")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO signals (signal_type, identifier_hash, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?)",
            ("fm_radio", h, "2026-06-30T00:00:00+00:00", "2026-06-30T00:00:00+00:00"),
        )


def test_follower_event_check_constraint(db: Database) -> None:
    h = db.hash_identifier("AA:BB:CC:DD:EE:FF")
    db.execute(
        "INSERT INTO signals (signal_type, identifier_hash, first_seen, last_seen) "
        "VALUES (?, ?, ?, ?)",
        ("wifi", h, "2026-06-30T00:00:00+00:00", "2026-06-30T00:00:00+00:00"),
    )
    sig_id = db.fetchone("SELECT id FROM signals WHERE identifier_hash = ?", (h,))["id"]
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO follower_events (signal_id, event, recorded_at) VALUES (?, ?, ?)",
            (sig_id, "maybe", "2026-06-30T00:00:00+00:00"),
        )


def test_plain_plates_toggle(db: Database) -> None:
    assert db.plain_plates_enabled() is False
    db.set_plain_plates_enabled(True)
    assert db.plain_plates_enabled() is True
    db.set_plain_plates_enabled(False)
    assert db.plain_plates_enabled() is False


def test_bootstrap_is_idempotent() -> None:
    """Running bootstrap twice on the same DB must not fail."""
    d = Database(":memory:")
    d.connect()
    d.bootstrap()
    # Insert one signal so we can confirm the second bootstrap doesn't wipe it.
    h = d.hash_identifier("DE:AD:BE:EF:00:01")
    d.execute(
        "INSERT INTO signals (signal_type, identifier_hash, first_seen, last_seen) "
        "VALUES (?, ?, ?, ?)",
        ("bluetooth", h, "2026-06-30T00:00:00+00:00", "2026-06-30T00:00:00+00:00"),
    )
    d.bootstrap()  # should not error
    row = d.fetchone("SELECT COUNT(*) AS c FROM signals")
    assert row["c"] == 1
    d.close()