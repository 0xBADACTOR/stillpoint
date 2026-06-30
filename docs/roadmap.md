# Roadmap

## v0.1 — Skeleton (current)
- [x] Repo layout
- [x] `core/persistence` schema (SQLite tables for `detections`, `signals`, `geo_clusters`, `followers`)
- [x] `core/persistence` geo-clustering algorithm
- [x] Kismet log ingest script (`scripts/ingest_kismet.py`)
- [x] FastAPI server with `/detections`, `/followers`, `/map` endpoints
- [x] Leaflet map UI (`core/web`)
- [ ] `hardware/install.sh` — provisions a fresh Pi 4/5
- [x] Systemd units for Kismet, GPS, ingest, API, and ANPR
- [x] `docs/threat-model.md`, `docs/legal.md`

## v0.2 — Bluetooth enhancements
- [ ] BT-specific parser (BLE advertisements, manufacturer data)
- [ ] Known-tracker signatures (AirTag, Tile, SmartTag) — for identification, not blocking. Just labelling in the UI.
- [ ] Improved MAC randomization handling

## v0.3 — ANPR module improvements
- [ ] Plate normalization (state-aware, fuzzy match for OCR errors)
- [ ] Improved OCR accuracy (e.g., using confidence weighting, multiple OCR passes)
- [ ] Integration with GPS for geotagging (correlating ANPR detections with GPS timestamps)
- [ ] Performance optimizations (e.g., threading, batch processing)

## v1.0 — Public release
- [ ] Docker compose for the backend (runs anywhere, not just Pi)
- [ ] Installer image for Pi (`stillpoint-pi.img`)
- [ ] Threat model + legal docs reviewed
- [ ] README quickstart tested on clean Pi