-- StillPoint SQLite schema (v0.1)
--
-- Five tables:
--   signals         - one row per unique MAC or plate
--   detections      - time-series of observations
--   geo_clusters    - cached cluster centroids per signal
--   follower_events - audit trail of follower flag transitions
--   installation    - single-row config: salt, plaintext opt-in, created_at
--
-- Notes:
--   * identifier_hash is the canonical join key. Same MAC across sessions
--     maps to the same row.
--   * identifier_plain is NULL by default. Populated only when the operator
--     explicitly enables plain_plates_enabled in the installation table.
--   * Indexes are tuned for the query patterns we expect:
--       - "show me detections for signal X over time range T"
--       - "show me all followers"
--       - "show me detections near a lat/lon"

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------------------
-- installation: single-row config. The CHECK keeps it that way.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS installation (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    salt                  BLOB NOT NULL,
    created_at            TEXT NOT NULL,
    plain_plates_enabled  INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- signals: one row per unique MAC / plate / BT identifier
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signals (
    id                INTEGER PRIMARY KEY,
    signal_type       TEXT NOT NULL CHECK (signal_type IN ('wifi', 'bluetooth', 'anpr')),
    identifier_hash   TEXT NOT NULL UNIQUE,
    identifier_plain  TEXT,
    label             TEXT,
    first_seen        TEXT NOT NULL,
    last_seen         TEXT NOT NULL,
    is_follower       INTEGER NOT NULL DEFAULT 0,
    follower_since    TEXT,
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_type     ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_follower ON signals(is_follower) WHERE is_follower = 1;

-- ---------------------------------------------------------------------------
-- detections: time-series observations. Largest table by far.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS detections (
    id          INTEGER PRIMARY KEY,
    signal_id   INTEGER NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    seen_at     TEXT NOT NULL,
    lat         REAL,
    lon         REAL,
    rssi        INTEGER,
    source      TEXT NOT NULL,
    raw         TEXT
);

CREATE INDEX IF NOT EXISTS idx_detections_signal ON detections(signal_id, seen_at);
CREATE INDEX IF NOT EXISTS idx_detections_time   ON detections(seen_at);
CREATE INDEX IF NOT EXISTS idx_detections_geo
    ON detections(lat, lon) WHERE lat IS NOT NULL AND lon IS NOT NULL;

-- ---------------------------------------------------------------------------
-- geo_clusters: cached cluster centroids per signal.
-- Populated by the follower-detection worker. Speeds up the followers query.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo_clusters (
    id              INTEGER PRIMARY KEY,
    signal_id       INTEGER NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    centroid_lat    REAL NOT NULL,
    centroid_lon    REAL NOT NULL,
    detection_count INTEGER NOT NULL,
    first_hit       TEXT NOT NULL,
    last_hit        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clusters_signal ON geo_clusters(signal_id);

-- ---------------------------------------------------------------------------
-- follower_events: append-only audit trail of flag/unflag transitions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS follower_events (
    id              INTEGER PRIMARY KEY,
    signal_id       INTEGER NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    event           TEXT NOT NULL CHECK (event IN ('flagged', 'unflagged')),
    reason          TEXT,
    cluster_count   INTEGER,
    detection_count INTEGER,
    recorded_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_follower_events_signal ON follower_events(signal_id, recorded_at);