"""FastAPI application for StillPoint API."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..persistence.database import Database

app = FastAPI(title="StillPoint API", description="API for StillPoint follower detection system.")

# Dependency to get a database connection
def get_db():
    # Use the database path from environment or default to ./data/stillpoint.db
    db_path = os.getenv(
        "STILLPOINT_DB_PATH",
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "stillpoint.db"),
    )
    # Ensure the directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with Database(db_path) as db:
        yield db

# Serve static files (the web UI) from the core/web directory
web_dir = os.path.join(os.path.dirname(__file__), "..", "web")
app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")


@app.get("/api/detections")
async def get_detections(
    limit: int = Query(100, gt=0, le=1000),
    hours: int = Query(24, gt=0, le=168),  # up to 1 week
    db: Database = Depends(get_db),
):
    """
    Get recent detections.
    Returns a list of detections with signal info, limited to the last `hours` hours.
    """
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")
    query = """
        SELECT
            d.id,
            d.seen_at,
            d.lat,
            d.lon,
            d.rssi,
            d.source,
            d.raw,
            s.signal_type,
            s.identifier_hash,
            s.is_follower
        FROM detections d
        JOIN signals s ON d.signal_id = s.id
        WHERE d.seen_at >= ?
        ORDER BY d.seen_at DESC
        LIMIT ?
    """
    rows = db.fetchall(query, (cutoff, limit))
    # Convert rows to list of dicts
    result = []
    for row in rows:
        d = dict(row)
        # Ensure lat/lon are floats
        if d["lat"] is not None:
            d["lat"] = float(d["lat"])
        if d["lon"] is not None:
            d["lon"] = float(d["lon"])
        result.append(d)
    return result


@app.get("/api/followers")
async def get_followers(db: Database = Depends(get_db)):
    """
    Get signals marked as followers (is_follower=1) with their latest geo-cluster.
    """
    query = """
        SELECT
            s.id,
            s.identifier_hash,
            s.signal_type,
            s.first_seen,
            s.last_seen,
            s.is_follower,
            s.label,
            s.notes,
            g.id as cluster_id,
            g.centroid_lat,
            g.centroid_lon,
            g.detection_count,
            g.first_hit,
            g.last_hit
        FROM signals s
        LEFT JOIN geo_clusters g ON s.id = g.signal_id
        WHERE s.is_follower = 1
        ORDER BY s.last_seen DESC
    """
    rows = db.fetchall(query)
    result = []
    for row in rows:
        d = dict(row)
        # Convert bytes/strings as needed
        if d["centroid_lat"] is not None:
            d["centroid_lat"] = float(d["centroid_lat"])
        if d["centroid_lon"] is not None:
            d["centroid_lon"] = float(d["centroid_lon"])
        result.append(d)
    return result


@app.get("/api/map/geojson")
async def get_map_geojson(
    hours: int = Query(24, gt=0, le=168),
    followers_only: bool = Query(False),
    db: Database = Depends(get_db),
):
    """
    Get a GeoJSON FeatureCollection of detections for mapping.
    If followers_only is True, only include detections from follower signals.
    """
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")
    if followers_only:
        query = """
            SELECT
                d.lat,
                d.lon,
                d.seen_at,
                d.rssi,
                s.signal_type,
                s.identifier_hash
            FROM detections d
            JOIN signals s ON d.signal_id = s.id
            WHERE d.seen_at >= ?
              AND s.is_follower = 1
              AND d.lat IS NOT NULL
              AND d.lon IS NOT NULL
            ORDER BY d.seen_at
        """
    else:
        query = """
            SELECT
                d.lat,
                d.lon,
                d.seen_at,
                d.rssi,
                s.signal_type,
                s.identifier_hash
            FROM detections d
            JOIN signals s ON d.signal_id = s.id
            WHERE d.seen_at >= ?
              AND d.lat IS NOT NULL
              AND d.lon IS NOT NULL
            ORDER BY d.seen_at
        """
    rows = db.fetchall(query, (cutoff,))
    features = []
    for row in rows:
        lat, lon = row["lat"], row["lon"]
        if lat is None or lon is None:
            continue
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(lon), float(lat)],
            },
            "properties": {
                "seen_at": row["seen_at"],
                "rssi": row["rssi"],
                "signal_type": row["signal_type"],
                "identifier_hash": row["identifier_hash"],
            },
        }
        features.append(feature)
    feature_collection = {
        "type": "FeatureCollection",
        "features": features,
    }
    return feature_collection


# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}