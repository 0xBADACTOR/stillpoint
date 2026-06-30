# Threat model

## What this tool protects against
- **Physical stalkers** carrying a phone with WiFi/BT enabled that gets
  detected repeatedly as you move between locations.
- **Planting of tracking devices** (AirTags, Tiles, custom BLE beacons)
  on your person or vehicle.
- **Suspicious vehicles** following you whose plates get logged at
  multiple waypoints.

## What this tool does NOT protect against
- **Dedicated RF-silent operators** who turn off radios when not in use.
- **Plate-swapping stalkers** who rotate plates per encounter.
- **High-altitude or directed surveillance** — the Pi has the sensitivity
  of a consumer-grade chipset.
- **Stalkers who never follow the same route twice** — the 3-cluster
  heuristic assumes some path overlap.

## Adversarial considerations for the software itself
- **Database poisoning**: if an attacker can write to the SQLite file,
  they can mark arbitrary signals as followers. Mitigation: filesystem
  permissions + signed updates + optional append-only mode.
- **Data exfiltration**: the web UI exposes detection history. The
  default config binds only to `127.0.0.1`. The intended deployment is
  local — do not expose the backend to a network.
- **DoS via RF flooding**: a hostile environment can saturate the radio
  with millions of unique MACs. Mitigation: rate-limit ingestion, cap
  database size, alert on sudden spikes.