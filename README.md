# StillPoint

A passive, defensive personal-safety tool that detects radio signals and
license plates following you across multiple locations.

*The still point is you. Anything moving with you across multiple locations
is the anomaly.*

## Features

- **Multi-band radio detection**: Passively monitors WiFi, Bluetooth, Zigbee, NRF (2.4GHz), and other bands via Kismet
- **Optional GSM/IMEI detection**: With SDR hardware (e.g., RTL-SDR), captures cellular identifiers
- **Automatic License Plate Recognition (ANPR)**: Camera-based plate detection and OCR
- **Geographic clustering**: Groups detections by location using Haversine distance (100m threshold)
- **Follower identification**: Flags signals appearing in 3+ distinct geographic clusters
- **Ignore lists**: Suppress alerts for known devices while maintaining audit trail
- **Real-time web interface**: Leaflet.js map showing detections and followers
- **Privacy-first design**: All data stored locally; optional plaintext storage for operator accountability
- **Modular architecture**: Separate services for ingestion, API, and UI

## How It Works

1. **Data Collection**: Kismet logs radio signals; optional camera captures license plates
2. **Normalization**: Identifiers (MAC, IMEI, plate) are hashed with per-install salt for privacy
3. **Geotagging**: Each detection is timestamped and GPS-located (when available)
4. **Clustering**: Sequential time-ordered clustering groups detections by location
5. **Follower Detection**: Signals with 3+ unique clusters are flagged as potential followers
6. **Alerting**: Suspicious SSIDs/device names (e.g., "police", "surveillance") trigger stderr alerts
7. **Visualization**: Leaflet map displays detections by type with follower highlighting

## Design Principles

- **Local-only.** All data lives on your device. There is no cloud component, no remote server, no telemetry, no update channel. The map UI binds to `127.0.0.1` by default. This repository is intended to be run locally — do not deploy the backend to a public server.
- **Passive only.** This tool never deauthenticates, spoofs, or transmits. It only listens.
- **Defensive framing.** This is a personal-safety tool for detecting stalkers, persistent trackers (AirTags, Tiles), and suspicious vehicles. It is not a surveillance platform.
- **Operator accountability.** YOU are responsible for complying with the laws of your jurisdiction. Recording license plates and MAC addresses carries legal obligations in many places.

## Repository Layout

```
stillpoint/
├── core/           # Shared backend: persistence engine, API, web UI
│   ├── persistence # SQLite schema + follower-detection logic
│   ├── api         # FastAPI server
│   └── web         # Leaflet-based map UI
├── hardware/       # Pi provisioning scripts (Kismet, GPS, systemd)
├── scripts/        # Operator utilities
├── docs/           # Architecture, threat model, legal notes, hardware guide
└── .github/        # CI workflows
```

## Status

Early scaffolding. See [`docs/roadmap.md`](docs/roadmap.md) for the milestone plan.

## Quickstart (Planned)

```bash
git clone <this-repo>          # local clone, no remote push assumed
cd stillpoint
./hardware/install.sh          # provisions a fresh Pi
docker compose up core         # starts the backend + map UI
# browse to http://localhost:8000  (127.0.0.1 only — do not expose)
```

## License

MIT — see [`LICENSE`](LICENSE).

## Legal

Passive radio monitoring is legal in most jurisdictions for personal protection on your own property. **Recording license plates in a database may be restricted** depending on where you live — review [`docs/legal.md`](docs/legal.md) before deploying.

## Hardware Guide

See [`docs/hardware-guide.md`](docs/hardware-guide.md) for detailed instructions on building and deploying StillPoint in a vehicle, including parts list, assembly instructions, power wiring, and software setup. The guide includes both a base configuration for WiFi/Bluetooth/Zigbee/NRF detection and an optional upgrade path for GSM/IMEI reception using SDR hardware.