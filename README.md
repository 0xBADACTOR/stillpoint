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
- **Intended for defensive use only.** This tool is meant to enhance personal safety by detecting passive anomalies. It should not be used to facilitate or conceal illegal activities.
- **Operator accountability.** YOU are responsible for complying with the laws of your jurisdiction. Recording license plates and MAC addresses carries legal obligations in many places.

## Limitations

Understanding what StillPoint does **not** do is as important as what it does:
- **No active countermeasures**: Does not jam, deauthenticate, or interfere with signals
- **No facial recognition**: Focuses on signals and plates, not individuals
- **Limited indoor performance**: GPS accuracy degrades significantly indoors/underground
- **SDR optional**: GSM/IMEI detection requires additional hardware
- **ANPR limitations**: Plate recognition accuracy varies with lighting, angle, speed, and plate condition
- **Follower false positives**: Common devices (e.g., frequently seen delivery vehicles) may appear as followers

## Threat Model

StillPoint is designed to defend against specific threats while acknowledging its limitations:
- **Protects against**: Physical stalkers with active devices, planted trackers (AirTags/Tiles), suspicious vehicles with recurring plates
- **Does not protect against**: RF-silent operators, plate-swapping stalkers, high-altitude surveillance, or adversaries who never repeat routes
- **Software considerations**: Mitigates database poisoning via filesystem protections, prevents data exfiltration via localhost-only binding, and rate-limits ingestion to resist RF flooding

See [`docs/threat-model.md`](docs/threat-model.md) for the complete threat analysis.

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[HARDWARE GUIDE](docs/hardware-guide.md)**: Complete instructions for building and deploying StillPoint in a vehicle, including:
  - Recommended hardware specifications and parts list with vendor links
  - Step-by-step assembly instructions with diagrams
  - Power wiring and installation guidelines
  - Software setup (OS installation, dependencies, configuration)
  - Systemd service configuration for auto-start
  - Vehicle installation tips and maintenance schedule
  - Troubleshooting common issues
  - Optional upgrade paths (SDR for GSM/IMEI, cellular modem for alerts, etc.)

- **[LEGAL NOTES](docs/legal.md)**: Important legal considerations for using StillPoint:
  - Passive radio monitoring regulations by jurisdiction (US, EU, Australia)
  - License plate recording laws and GDPR considerations
  - Recommendations for compliant use (data retention, hashing, privacy precautions)
  - Licensing information and intended use (local, personal use only)

- **[THREAT MODEL](docs/threat-model.md)**: Analysis of threats StillPoint is designed to mitigate:
  - Protection against physical stalkers, planted trackers (AirTags/Tiles), and suspicious vehicles
  - Limitations (RF-silent operators, plate-swapping stalkers, etc.)
  - Software security considerations (database poisoning, data exfiltration, DoS resistance)

- **[ROADMAP](docs/roadmap.md)**: Development plan showing progress toward releases:
  - **v0.1 (Current)**: Core functionality (persistence, ingestion, geo-clustering, follower detection, API/UI)
  - **v0.2**: Bluetooth enhancements (BLE advertisements, tracker signatures)
  - **v0.3**: ANPR module improvements (plate normalization, OCR error correction)
  - **v1.0**: Public release (Docker support, Pi image, tested quickstart)

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

Currently implementing **v0.1 core functionality**:
- ✅ SQLite schema and persistence layer
- ✅ Kismet log ingestor with multi-band detection
- ✅ Geo-clustering algorithm (100m Haversine distance)
- ✅ Follower detection (3+ cluster threshold)
- ✅ REST API and Leaflet web interface
- ✅ ANPR module (camera + OCR)
- ✅ Systemd services for auto-start
- ⏳ Hardware provisioning script

See [`docs/roadmap.md`](docs/roadmap.md) for detailed milestone planning.

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

## Legal & Compliance

**Important**: This tool is for personal safety use only. Operators are responsible for complying with local laws regarding radio monitoring and license plate recording.

Key legal considerations:
- **Passive radio monitoring**: Generally legal in most jurisdictions for personal use, but restrictions may apply
- **License plate recording**: May be regulated as personal data in many regions (e.g., GDPR in EU/UK)
- **Data retention**: Recommend 30-day automatic purge to minimize privacy risks
- **Hashing**: Identifiers are stored as SHA-256 hashes by default; plaintext storage requires explicit opt-in

See [`docs/legal.md`](docs/legal.md) for detailed jurisdictional information.

## Hardware Guide

See [`docs/hardware-guide.md`](docs/hardware-guide.md) for detailed instructions on building and deploying StillPoint in a vehicle, including parts list, assembly instructions, power wiring, and software setup. The guide includes both a base configuration for WiFi/Bluetooth/Zigbee/NRF detection and an optional upgrade path for GSM/IMEI reception using SDR hardware.