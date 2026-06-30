# StillPoint Hardware Deployment Guide

This document provides detailed instructions for building and deploying the StillPoint system in a vehicle for passive radio frequency detection and follower tracking.

## Overview

StillPoint is designed to run on a Raspberry Pi 5 in a vehicle environment, passively collecting radio signals (WiFi, Bluetooth, GSM, etc.) via Kismet, processing them for geographic clustering, and identifying persistent followers (signals appearing in 3+ distinct locations).

## Recommended Hardware Configuration

The following build provides optimal balance of reliability, performance, and cost for daily vehicle use (~$350 total):

| Component | Specific Model | Purpose |
|-----------|----------------|---------|
| **Single Board Computer** | Raspberry Pi 5 (8GB RAM) | Main processing unit |
| **GPS Receiver** | u-blox ZED-F9P RTK GNSS Breakout | Precision timing/location |
| **GPS Antenna** | u-blox ANN-MB-00 (L1/L2 Band) | Required for ZED-F9P operation |
| **Storage** | Kingston NV2 NVMe SSD (500GB, M.2 2280) | High-endurance logging |
| **NVMe Adapter** | Pineberry Stone 2 (M.2 to USB 3.0) | Connects SSD to Pi5 USB 3.0 |
| **Power Supply** | RD-5V 5A DC-DC Buck Converter | Vehicle 12V → 5V isolation |
| **UPS HAT** | PiSaver LiFePO4 UPS HAT (10,000mAh) | Graceful shutdown on power loss |
| **Enclosure** | Polycase WB Series WB10-6-4B (IP66) | Dust/water protection |
| **Cooling** | Noctua NF-A4x10 5V PWM Fan | Prevents thermal throttling |

*Note: This base configuration supports WiFi, Bluetooth, Zigbee, and NRF signals. For GSM/IMEI reception, see the [GSM/SDR Upgrade](#gsm-sdr-upgrade) section below.*

*See [PARTS LIST DETAILS](#parts-list) for vendor links and alternatives.*

## Assembly Instructions

### Step 1: Prepare the Enclosure
1. Drill 4x 3mm ventilation holes in the enclosure lid (covered with waterproof Gore-Tex patch later)
2. Cut a 10mm hole for power input wires on the side
3. Attach 4x M3 standoffs inside the enclosure base for Pi5 mounting plate
4. Apply conformal coating to enclosure interior if in humid climates

### Step 2: Mount the Single Board Computer
1. Attach Raspberry Pi 5 to a 2mm acrylic mounting plate using 4x M2.5x6mm screws
2. Apply thermal pad (included with Pi5 case) to CPU/VPU
3. Mount plate inside enclosure using M3 standoffs
4. Connect Noctua fan:
   - Red wire → 5V pin (GPIO #2)
   - Black wire → Ground pin (GPIO #6)
   - Yellow wire → GPIO #12 (PWM control, optional)

### Step 3: Install Storage & Power
1. Insert Kingston NV2 SSD into Pineberry Stone 2 adapter
2. Connect Stone 2 to a **blue USB 3.0 port** on Pi5 (top row)
3. Wire RD-5V converter:
   - **INPUT**: 
     - Red (12V+) → Fuse holder → 16AWG red wire → Vehicle 12V (fuse tap)
     - Black (12V-) → 16AWG black wire → Vehicle chassis ground
   - **OUTPUT**:
     - Red (5V) → Micro-USB → Pi5 USB-C power port
     - Black (GND) → Micro-USB → Pi5 USB-C power port
4. Connect PiSaver UPS HAT:
   - Stack directly on Pi5 GPIO header (align pin 1!)
   - Connect LiFePO4 battery pack to HAT JST port
   - Set jumper to "5V Out" position

### Step 4: Install GPS System
1. Mount u-blox ANN-MB-00 antenna on vehicle dash (clear sky view)
   - Use 3M VHB tape + silicone sealant at base
   - Run coax cable through existing grommet (e.g., firewall)
2. Connect antenna coax to ZED-F9P breakout U.FL port
3. Connect ZED-F9P to Pi5 via USB:
   - Micro-USB (on breakout) → USB 2.0 port (black port, bottom row)
   - *Note: Use powered USB hub if experiencing instability*

### Step 5: Final Checks & Sealing
1. Apply Gore-Tex patches over ventilation holes (prevents water ingress while allowing airflow)
2. Label all cables with heat-shrink tags: "POWER", "GPS", "SSD", "FAN"
3. Apply dielectric grease to all USB/U.FL connections
4. Close enclosure and torque screws to 0.5 Nm (hand-tight + 1/4 turn)

## Power Wiring Diagram (Vehicle)

```
Vehicle Battery (+12V)
        │
        ├───[2A Fuse]───┬───[RD-5V Converter INPUT (+)]
        │               │
        │               └───[RD-5V Converter INPUT (-)]─── Chassis Ground (Black wire)
        │
        └─── [Optional: Cellular Modem Power]─── [Ignition-switched 12V] (for parked alerts)
```
*Converter OUTPUT → Pi5 USB-C power port (via Micro-USB cable)*  
*PiSaver UPS HAT provides battery backup during cranking/transients*

## Software Setup on Hardware

### 1. Install OS (64-bit Raspberry Pi OS Lite)
```bash
# Download latest Raspberry Pi OS Lite (64-bit)
wget https://downloads.raspberrypi.org/raspios_lite_arm64_latest
# Flash to NVMe via USB adapter on another computer
sudo dd if=raspios_lite_arm64_latest.img of=/dev/sdX bs=4M status=progress
```

### 2. Initial Configuration
```bash
sudo raspi-config
# → System Options → Wireless LAN (set country/SSID/password if using WiFi for setup)
# → Interface Options → SSH → Enable
# → Performance Options → GPU Memory → 64 (minimize for headless)
# → Advanced Options → Expand Filesystem
# Reboot
```

### 3. Install Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-pip python3-venv i2c-tools gpsd gpsd-clients
# Install StillPoint in a venv
git clone https://github.com/0xBADACTOR/stillpoint.git
cd stillpoint
python3 -m venv venv
source venv/bin/activate
pip install -e .[dev]  # Installs fastapi, uvicorn, etc.
deactivate
```

### 4. Configure Services (Critical for Auto-Start)
Create `/etc/systemd/system/kismet.service`:
```ini
[Unit]
Description=Kismet WiFi/Bluetooth Scanner
After=network-online.target gpsd.service
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/stillpoint
ExecStart=/usr/bin/kismet
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/gpsd.service`:
```ini
[Unit]
Description=GPS Daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
ExecStart=/usr/sbin/gpsd /dev/ttyACM0 -F /var/run/gpsd.sock
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/stillpoint-ingest.service`:
```ini
[Unit]
Description=StillPoint Kismet Log Ingestor
After=kismet.service gpsd.service
Wants=kismet.service gpsd.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/stillpoint
ExecStart=/home/pi/stillpoint/venv/bin/python scripts/ingest_kismet.py --db /home/pi/data/stillpoint.db
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/stillpoint-anpr.service`:
```ini
[Unit]
Description=StillPoint ANPR Processor
After=kismet.service gpsd.service
Wants=kismet.service gpsd.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/stillpoint
ExecStart=/home/pi/stillpoint/venv/bin/python scripts/anpr_processor.py --db /home/pi/data/stillpoint.db --save-detections
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/stillpoint-api.service`:
```ini
[Unit]
Description=StillPoint REST API Server
After=stillpoint-ingest.service
Wants=stillpoint-ingest.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/stillpoint
ExecStart=/home/pi/stillpoint/venv/bin/uvicorn core.api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable all services:
```bash
sudo systemctl enable kismet gpsd stillpoint-ingest stillpoint-anpr stillpoint-api
sudo systemctl start kismet gpsd stillpoint-ingest stillpoint-anpr stillpoint-api
```

### 5. Verify Operation
```bash
# Check service status
sudo systemctl status kismet gpsd stillpoint-ingest stillpoint-api

# View live logs
sudo journalctl -u stillpoint-ingest -f

# Test API from another device on same network
curl http://[PI_IP]:8000/health  # Should return {"status":"ok"}
curl http://[PI_IP]:8000/api/followers  # Should return [] initially
```

## Vehicle Installation Guide

### Mounting Locations (Ranked by Preference)
1. **Under Front Seat** (Best):
   - Pros: Stable temperature, easy access for maintenance, protected from direct sun
   - Cons: May suffer from RF shadowing (test with phone hotspot first)
2. **Trunk/Cargo Area** (Good):
   - Pros: Ample space, isolated from engine noise
   - Cons: Longer GPS antenna cable runs (use low-loss RG174 if >3m)
3. **Behind Glovebox** (Acceptable):
   - Pros: Hidden, factory-like appearance
   - Cons: Limited airflow, potential heat buildup

### Critical Installation Tips
- **Fusing ALWAYS**: Place fuse within 18" of battery tap (use ANL fuse holder for >10A systems)
- **Grounding**: Bolt black wire to clean, unpainted chassis point (scrape paint, use star washer)
- **Antenna Separation**: Keep GPS antenna >20cm from any transmitting antennas (phone, radio)
- **Vibration Isolation**: Place 1/4" closed-cell foam under enclosure if mounting on suspension points
- **Legal Check**: Verify local laws before deployment (see `docs/legal.md`)

### First-Time Verification
1. Power on vehicle → wait 2 minutes for GPS fix
2. Check GPS status: `cgps -s` (should show 2D/3D fix with >3 satellites)
3. Verify Kismet is running: `ps aux | grep kismet`
4. Check for new detections after 5 minutes:
   ```bash
   sqlite3 /home/pi/data/stillpoint.db "SELECT COUNT(*) FROM detections;"
   ```
5. Visit `http://[PI_IP]:8000` in browser → see Leaflet map (empty until detections accumulate)

## Maintenance Schedule

| Interval | Task |
|----------|------|
| **Weekly** | Check SSD health: `sudo smartctl -a /dev/nvme0n1` |
| **Monthly** | Replace desiccant packet in enclosure<br>Inspect antenna connections for corrosion |
| **Every 6 Months** | Update OS: `sudo apt update && sudo apt full-upgrade -y`<br>Reapply conformal coating if degraded |
| **Annually** | Test UPS battery runtime (simulate power loss)<br>Re-torque enclosure screws to 0.5 Nm |

## Safety & Legal Notes
1. **Never install where it interferes with driving, airbags, or vehicle controls**
2. **All power connections MUST be fused** (use add-a-circuit fuse taps for OEM wiring)
3. **StillPoint is PASSIVE ONLY** – it never transmits or interferes with signals
4. **Consult `docs/legal.md`** before deploying (covers RF monitoring laws by jurisdiction)
5. **In case of smoke/smell**: Disconnect power immediately – do not troubleshoot while powered

## Optional Upgrade Paths
As needs evolve, consider these additions:

### For GSM/Cellular Signal Reception
- **SDR Receiver**: RTL-SDR Blog V3 or NooElec NESDR SMArt ($25-35)
  - Frequency range: 24 MHz - 1.7 GHz (covers all GSM bands)
  - Requires external antenna
- **GSM Antenna**: Wideband whip antenna (800-960 MHz / 1710-1980 MHz) ($10-15)
  - Alternatively: Poynting XPOL-1-5G (covers cellular bands) if already using for other purposes
- **Software**: gr-gsm + Kismet plugin
  - Install via: `sudo apt install -y gr-gsm gnuradio`
  - Follow [gr-gsm installation guide](https://github.com/ptrkrysik/gr-gsm) for latest version
  - Configure Kismet to use the `grgsm_capture` interface
- **Power**: Draws from USB port (ensure adequate power supply)
- **Placement**: Keep >20cm from GPS antenna to avoid desensitization
- **Legal Note**: IMEI interception may have additional regulatory considerations - consult local laws

### For Remote Alerts
- Add Quectel EC25-AFX LTE modem (M.2) + SIM → enables SMS/email alerts

### For Extreme Environments
- Swap enclosure for Pelican 1010 + heating pad (cold climates)

### For Analytics
- Add Samsung 990 Pro 1TB NVMe → enables months of local storage

### For Stealth
- Use Flir Black Hornet Nano camera (hidden) for visual correlation (requires separate system)

## PARTS LIST DETAILS

### Core System (Required for Basic Operation)
| Item | Model/Specification | Quantity | Approx. Cost | Vendor/Link |
|------|---------------------|----------|--------------|-------------|
| **Single Board Computer** | Raspberry Pi 5 (8GB RAM) | 1 | $75 | [PiShop.us](https://pishop.us/collections/raspberry-pi-5) |
| **GPS Receiver** | u-blox ZED-F9P RTK GNSS Breakout | 1 | $199 | [SparkFun](https://www.sparkfun.com/products/18654) |
| **GPS Antenna** | u-blox ANN-MB-00 (L1/L2 Band) | 1 | $25 | [Digi-Key](https://www.digikey.com/en/products/detail/u-blox-ag/ANN-MB-00/15328193) |
| **Storage** | Kingston NV2 NVMe SSD (500GB, M.2 2280) | 1 | $45 | [Amazon](https://www.amazon.com/Kingston-NV2-NVMe-SNV2S500G/dp/B0B5V5YQ1F) |
| **NVMe Adapter** | Pineberry Stone 2 (M.2 to USB 3.0) | 1 | $25 | [Pine64](https://pine64.com/product/stone-2-nvme-to-usb-3-0-adapter/) |
| **Power Supply** | RD-5V 5A DC-DC Buck Converter | 1 | $12 | [Amazon](https://www.amazon.com/RD-5V-Converter-Regulator-Protector/dp/B08B5F5YQJ) |
| **UPS HAT** | PiSaver LiFePO4 UPS HAT (10,000mAh) | 1 | $65 | [PiSupply](https://pisupp.li/pisaver-lifepo4-ups-hat) |
| **Enclosure** | Polycase WB Series WB10-6-4B (IP66) | 1 | $30 | [Allied Electronics](https://www.alliedelec.com/polycase-wb10-6-4b/70214354/) |
| **Cooling** | Noctua NF-A4x10 5V PWM Fan | 1 | $15 | [Amazon](https://www.amazon.com/Noctua-NF-A4x10-PWM-Fan/dp/B07D7D1F9G) |
| **Cables/Connectors** | Various (USB, power, etc.) | 1 set | $15 | Multiple sources |
| **Mounting Hardware** | Screws, standoffs, tape, etc. | 1 set | $10 | Hardware store |
| ****Total (Base System)*** |  |  | **~$451** |  |

*Note: The base system cost is higher than the earlier estimate due to current market prices. Costs can be reduced by:*
- *Using Raspberry Pi 4B (8GB) instead of Pi 5: -$30*
- *Using Samsung PRO Endurance 256GB microSD instead of NVMe: -$30*
- *Using a more basic UPS solution: -$20*

### GSM/SDR Upgrade (Optional for Cellular/IMEI Reception)
| Item | Model/Specification | Quantity | Approx. Cost | Vendor/Link |
|------|---------------------|----------|--------------|-------------|
| **SDR Receiver** | RTL-SDR Blog V3 or NooElec NESDR SMArt | 1 | $30 | [Amazon](https://www.amazon.com/RTL-SDR-Blog-V3-Software-Defined/dp/B0756RS72Y) |
| **GSM Antenna** | Wideband whip (800-960 MHz / 1710-1980 MHz) | 1 | $12 | [Amazon](https://www.amazon.com/POYNTING-XPOL-1-5G-Omni-Directional/dp/B07Q6RZ9Z6) |
| **USB Extension Cable** (if needed) | USB 2.0 A Male to A Female | 1 | $8 | [Amazon](https://www.amazon.com/AmazonBasics-United-States-Extension/dp/B01EV70C78) |
| ****Total (GSM/SDR Add-on)*** |  |  | **~$50** |  |

### Optional Enhancements
| Item | Model/Specification | Quantity | Approx. Cost | Vendor/Link |
|------|---------------------|----------|--------------|-------------|
| **Cellular Modem** | Quectel EC25-AFX LTE-A Module (M.2) | 1 | $45 | [Amazon](https://www.amazon.com/Quectel-EC25-AFX-LTE-A-Module/dp/B08B5F5YQJ) |
| **External Antenna** | Poynting XPOL-1-5G (omni-directional) | 1 | $45 | [Amazon](https://www.amazon.com/POYNTING-XPOL-1-5G-Omni-Directional/dp/B07Q6RZ9Z6) |
| **CAN Bus Interface** | PiCAN2 Duo | 1 | $28 | [SK Pang](https://shop.skpang.co.uk/catalog/pican2-duo-can-bus-board-for-raspberry-pi-2-3-4-plus-2058) |
| **Environmental Sensors** | Sensirion SPS30 (PM) + BME688 (VOC) | 1 set | $65 | [Sensirion](https://sensirion.com/products/catalog/SPS30/) |

## Troubleshooting Common Issues

### No GPS Fix
- Verify antenna has clear sky view (no metal obstructions)
- Check `cgps -s` output for satellite count
- Ensure ZED-F9P is connected to USB 2.0 port (not USB 3.0 which can cause interference)
- Try different USB cable (some are power-only)

### High CPU Temperatures
- Verify fan is connected and spinning
- Check thermal paste application on CPU
- Ensure ventilation holes are not blocked
- Consider underclocking in `/boot/config.txt`: `arm_freq=1500`

### SSD Corruption Warnings
- Use only automotive-rated SSDs (Kingston NV2 is rated for 24/7 operation)
- Ensure proper shutdown via UPS HAT
- Run monthly SMART checks: `sudo smartctl -a /dev/nvme0n1`

### Kismet Not Seeing Packets
- Verify interface is up: `ip link show wlan0mon`
- Check Kismet logs: `journalctl -u kismet -f`
- Ensure user `pi` has access to `/dev/rfkill`

### GSM/SDR Not Receiving Signals
- Verify SDR is recognized: `lsusb | grep -i rtl`
- Check dump1090 or similar test tool to verify reception
- Ensure proper antenna connection and orientation
- Check gain settings in gr-gsm configuration
- Verify Kismet is configured to use grgsm source

## Integration with Existing Software

This hardware setup works with all previously implemented StillPoint features:
- **Geo-clustering**: `core/persistence/database.py::update_geo_clusters()`
- **Follower Detection**: `core/persistence/database.py::update_follower_status()`
- **Signal Type Detection**: Includes GSM/IMEI handling in `scripts/ingest_kismet.py`
- **ANPR Processing**: License plate recognition via `scripts/anpr_processor.py`
- **Ignore List**: Manage via `db.add_ignored_signal()` and `db.is_signal_ignored()`
- **API Endpoints**: 
  - `GET /api/followers` - view detected followers
  - `GET /api/map/geojson` - Leaflet-compatible geographic data
  - `GET /api/detections` - raw detection history
- **Alerting**: Keyword alerts (police, drone, surveillance, etc.) print to stderr during ingest

For software development details, see:
- [`README.md`](README.md) - project overview
- [`core/persistence/database.py`](core/persistence/database.py) - core logic
- [`scripts/ingest_kismet.py`](scripts/ingest_kismet.py) - data ingestion
- [`core/api/main.py`](core/api/main.py) - REST API implementation

## License & Disclaimer
Hardware assembly instructions are provided as-is. User assumes all risk associated with vehicle electrical modifications. StillPoint software is licensed under MIT - see [LICENSE](LICENSE).

*Last updated: 2026-06-30*