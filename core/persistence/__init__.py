"""Persistence layer: SQLite schema + geo-clustering + follower detection.

Public entry points:
    from core.persistence import Database
"""
from __future__ import annotations

from core.persistence.database import Database

__all__ = ["Database"]