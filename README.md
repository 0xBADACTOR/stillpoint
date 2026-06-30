# StillPoint

A passive, defensive personal-safety tool that detects radio signals and
license plates following you across multiple locations.

*The still point is you. Anything moving with you across multiple locations
is the anomaly.*

## What it does

A Raspberry Pi in your car (or bag) passively listens to **WiFi, Bluetooth, Zigbee, NRF (2.4GHz), and other radio bands** using [Kismet](https://www.kismetwireless.net/).
With optional SDR hardware, it can also detect GSM/Cellular signals including
IMEI identifiers. Each detection is tagged with GPS coordinates and timestamped. Signals that
appear at **three or more distinct geo-clusters** are flagged as
"followers" and plotted on a map so you can review their movement.

A separate camera module runs **automatic number-plate recognition (ANPR)**
and feeds the same persistence engine, so a plate seen across multiple
locations is also flagged.

## Design principles

- **Local-only.** All data lives on your device. There is no cloud
  component, no remote server, no telemetry, no update channel. The map
  UI binds to `127.0.0.1` by default. This repository is intended to be
  run locally — do not deploy the backend to a public server.
- **Passive only.** This tool never deauthenticates, spoofs, or transmits.
  It only listens.
- **Defensive framing.** This is a personal-safety tool for detecting
  stalkers, persistent trackers (AirTags, Tiles), and suspicious vehicles.
  It is not a surveillance platform.
- **Operator accountability.** YOU are responsible for complying with the
  laws of your jurisdiction. Recording license plates and MAC addresses
  carries legal obligations in many places.

## Repository layout

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

Early scaffolding. See [`docs/roadmap.md`](docs/roadmap.md) for the
milestone plan.

## Quickstart (planned)

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

Passive radio monitoring is legal in most jurisdictions for personal
protection on your own property. **Recording license plates in a database
may be restricted** depending on where you live — review
[`docs/legal.md`](docs/legal.md) before deploying.

## Hardware Guide

See [`docs/hardware-guide.md`](docs/hardware-guide.md) for detailed
instructions on building and deploying StillPoint in a vehicle,
including parts list, assembly instructions, power wiring, and software
setup. The guide includes both a base configuration for WiFi/Bluetooth/Zigbee/NRF
detection and an optional upgrade path for GSM/IMEI reception using SDR hardware.