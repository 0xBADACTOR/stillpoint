# Roadmap

## v0.1 — Skeleton (current)
- [x] Repo layout
- [ ] `core/persistence` schema (SQLite tables for `detections`,
      `signals`, `geo_clusters`, `followers`)
- [ ] `core/persistence` geo-clustering algorithm
- [ ] Kismet log ingest script (`scripts/ingest_kismet.py`)
- [ ] FastAPI server with `/detections`, `/followers`, `/map` endpoints
- [ ] Leaflet map UI (`core/web`)
- [ ] `hardware/install.sh` — provisions a fresh Pi 4/5
- [ ] Systemd units for Kismet + GPS + ingest
- [ ] `docs/threat-model.md`, `docs/legal.md`

## v0.2 — Bluetooth priority
- [ ] BT-specific parser (BLE advertisements, manufacturer data)
- [ ] Known-tracker signatures (AirTag, Tile, SmartTag) — for *identification*,
      not blocking. Just labelling in the UI.

## v0.3 — ANPR module
- [ ] Camera module: OpenALPR or PaddleOCR backend
- [ ] Plate normalization (state-aware, fuzzy match for OCR errors)
- [ ] Same persistence engine — plates get the same follower detection

## v1.0 — Public release
- [ ] Docker compose for the backend (runs anywhere, not just Pi)
- [ ] Installer image for Pi (`stillpoint-pi.img`)
- [ ] Threat model + legal docs reviewed
- [ ] README quickstart tested on clean Pi