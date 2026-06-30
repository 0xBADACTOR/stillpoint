#!/usr/bin/env python3
"""Kismet log ingester.

Reads Kismet's JSON-per-line alert/devices log and writes normalized
detections into the persistence layer.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Add the project root to the sys.path so we can import core.persistence
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.persistence.database import Database


def parse_kismet_line(line: str) -> dict | None:
    """Parse a single line of Kismet JSON log and return a dict of relevant fields.

    Returns None if the line is not valid JSON or missing required fields.
    """
    try:
        data = json.loads(line.strip())
    except json.JSONDecodeError:
        return None

    # We expect at least a device MAC address and a timestamp.
    # Adjust the keys based on the actual Kismet log format.
    # Common MAC address fields in Kismet JSON: device.macaddr, mac, addr2
    mac = None
    if isinstance(data.get("device"), dict):
        mac = data["device"].get("macaddr")
    if not mac:
        mac = data.get("mac") or data.get("addr2") or data.get("bssid")
    if not mac:
        return None

    # Timestamp: try common fields
    ts = data.get("time") or data.get("timestamp") or data.get("UTC_time")
    if not ts:
        return None
    # We'll assume the timestamp is in ISO format or a Unix timestamp.
    # If it's a Unix timestamp, we'll convert to ISO string.
    if isinstance(ts, (int, float)):
        from datetime import datetime, timezone
        ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    # Latitude and longitude
    lat = data.get("lat") or data.get("latitude")
    lon = data.get("lon") or data.get("longitude")
    # Convert to float if present, else None
    if lat is not None:
        try:
            lat = float(lat)
        except (ValueError, TypeError):
            lat = None
    if lon is not None:
        try:
            lon = float(lon)
        except (ValueError, TypeError):
            lon = None

    # Signal strength (RSSI in dBm)
    signal = data.get("signal") or data.get("rssi") or data.get("signal_strength")
    if signal is not None:
        try:
            signal = int(signal)
        except (ValueError, TypeError):
            signal = None

    # Determine signal type based on the datasource or type field.
    # This is a heuristic; adjust as needed.
    # Kismet datasources: wifi, bluetooth, zigbee, gsm, etc.
    # We'll map to our signal_type: 'wifi', 'bluetooth', 'zigbee', 'nrf', 'gsm', 'other'
    datasource = data.get("kismet.datasource", data.get("datasource", ""))
    if not isinstance(datasource, str):
        datasource = str(datasource)
    datasource_lower = datasource.lower()

    if "zigbee" in datasource_lower:
        signal_type = "zigbee"
    elif "nrf" in datasource_lower or "nrf24" in datasource_lower or "nrf5" in datasource_lower:
        signal_type = "nrf"
    elif "bt" in datasource_lower or "bluetooth" in datasource_lower:
        signal_type = "bluetooth"
    elif "wifi" in datasource_lower or "802.11" in datasource_lower:
        signal_type = "wifi"
    elif "gsm" in datasource_lower or "grgsm" in datasource_lower:
        signal_type = "gsm"
    else:
        # If we can't determine, default to 'other'
        signal_type = "other"

    # Extract identifier based on signal type
    identifier = None
    if signal_type in ("wifi", "bluetooth"):
        # Use MAC address
        identifier = mac
    elif signal_type == "anpr":
        # For ANPR, we expect a license plate
        # Common plate fields in Kismet JSON (if available via ANPR plugin)
        plate = None
        if isinstance(data.get("device"), dict):
            device = data["device"]
            if isinstance(device.get("anpr"), dict):
                anpr = device["anpr"]
                if isinstance(anpr.get("plate"), str):
                    plate = anpr["plate"]
            elif isinstance(device.get("plate"), str):
                plate = device["plate"]
        if not plate:
            plate = data.get("plate")
        identifier = plate
    elif signal_type == "gsm":
        # For GSM, we want the IMEI
        imei = None
        # Try common paths for IMEI in Kismet JSON
        if isinstance(data.get("device"), dict):
            device = data["device"]
            if isinstance(device.get("device"), dict):
                inner_device = device["device"]
                if isinstance(inner_device.get("imei"), str):
                    imei = inner_device["imei"]
            if not imei and isinstance(device.get("imei"), str):
                imei = device["imei"]
        if not imei and isinstance(data.get("imei"), str):
            imei = data["imei"]
        # If still not found, try to look in layers (if present)
        if not imei and isinstance(data.get("Layers"), dict):
            layers = data["Layers"]
            for layer_name, layer_data in layers.items():
                if isinstance(layer_data, dict) and "imei" in layer_data:
                    imei = layer_data["imei"]
                    break
        identifier = imei
    else:
        # For 'other' and any other types, we don't have a standard identifier
        # We'll skip these for tracking purposes
        return None

    # If we don't have an identifier, skip
    if not identifier:
        return None

    # Keywords to alert on (case-insensitive) - only for SSID/device name fields
    alert_keywords = ["police", "drone", "surveillance", "monitor", "qps", "government", "federal", "law", "enforcement"]
    alert_triggered = False
    # We check for keywords in the SSID (for wifi) or device name if available
    ssid = None
    device_name = None
    if isinstance(data.get("device"), dict):
        device = data["device"]
        if isinstance(device.get("dot11.device"), dict):
            dot11_device = device["dot11.device"]
            if isinstance(dot11_device.get("dot11_ssid"), dict):
                ssid = dot11_device["dot11_ssid"].get("ssid")
            elif isinstance(dot11_device.get("dot11_ssid"), str):
                ssid = dot11_device["dot11_ssid"]
        # Also try: device.dot11.device.dot11_ssid (if the structure is different)
        if not ssid and isinstance(device.get("dot11_device"), dict):
            dot11_device = device["dot11_device"]
            if isinstance(dot11_device.get("dot11_ssid"), dict):
                ssid = dot11_device["dot11_ssid"].get("ssid")
            elif isinstance(dot11_device.get("dot11_ssid"), str):
                ssid = dot11_device["dot11_ssid"]
        # Device name (for any type)
        if isinstance(device.get("device"), dict):
            inner_device = device["device"]
            if isinstance(inner_device.get("device"), dict):
                device_name = inner_device["device"].get("device")
            elif isinstance(inner_device.get("device"), str):
                device_name = inner_device["device"]
        if not device_name and isinstance(device.get("device"), str):
            device_name = device["device"]
    # If still not found, try top-level
    if not ssid:
        ssid = data.get("dot11.device.dot11_ssid") or data.get("ssid")
    if not device_name:
        device_name = data.get("device")

    # Check for keywords in SSID or device name
    text_to_check = ""
    if ssid and isinstance(ssid, str):
        text_to_check += ssid.lower()
    if device_name and isinstance(device_name, str):
        text_to_check += " " + device_name.lower()
    for keyword in alert_keywords:
        if keyword in text_to_check:
            alert_triggered = True
            break

    return {
        "mac": mac,
        "timestamp": ts,
        "lat": lat,
        "lon": lon,
        "signal": signal,
        "signal_type": signal_type,
        "source": datasource or "kismet",
        "ssid": ssid,
        "device_name": device_name,
        "raw": line.strip(),  # store the original line
        "alert_triggered": alert_triggered,
        "identifier": identifier,  # the raw identifier (MAC, plate, IMEI) for hashing
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest Kismet JSON logs into StillPoint database."
    )
    parser.add_argument(
        "logfile",
        nargs="?",
        default=os.path.expanduser("~/kismet/kismet.log"),
        help="Path to the Kismet log file (default: ~/kismet/kismet.log)",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        default=os.path.join(PROJECT_ROOT, "data", "stillpoint.db"),
        help="Path to the SQLite database file (default: ./data/stillpoint.db)",
    )
    # Optional: allow user to specify a MAC to ignore at runtime
    parser.add_argument(
        "--ignore",
        dest="ignore_mac",
        action="append",
        default=[],
        help="MAC address to ignore (can be repeated)",
    )
    args = parser.parse_args()

    # Ensure the data directory exists
    os.makedirs(os.path.dirname(args.db_path), exist_ok=True)

    # Process the log file
    with Database(args.db_path) as db:
        # If any --ignore MACs were provided, add them to the ignore list
        for mac in args.ignore_mac:
            try:
                # Hash the MAC using the database's salt to get identifier_hash
                identifier_hash = db.hash_identifier(mac)
                db.add_ignored_signal(identifier_hash, reason="Added via --ignore flag")
                print(f"Ignoring MAC {mac} (hash: {identifier_hash})", file=sys.stderr)
            except Exception as e:
                print(f"Failed to ignore MAC {mac}: {e}", file=sys.stderr)

        # We'll process line by line
        with open(args.logfile, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                parsed = parse_kismet_line(line)
                if parsed is None:
                    # Skip lines that can't be parsed
                    continue

                # If alert triggered and not ignored, print a warning to stderr
                if parsed["alert_triggered"]:
                    # Check if this signal is ignored
                    try:
                        identifier_hash = db.hash_identifier(parsed["identifier"])
                        if not db.is_signal_ignored(identifier_hash):
                            print(
                                f"ALERT: {parsed['ssid'] or 'Unknown SSID'} (MAC: {parsed['mac']}) matched keyword at {parsed['timestamp']}",
                                file=sys.stderr,
                            )
                    except Exception as e:
                        # If we can't hash, we still alert? But we shouldn't get here if we have an identifier.
                        print(
                            f"ALERT: {parsed['ssid'] or 'Unknown SSID'} (MAC: {parsed['mac']}) matched keyword at {parsed['timestamp']} (hashing error: {e})",
                            file=sys.stderr,
                        )

                # Hash the identifier using the database's per-install salt
                try:
                    identifier_hash = db.hash_identifier(parsed["identifier"])
                except RuntimeError:
                    # Database not bootstrapped? Should not happen if we just opened it.
                    raise

                # Check if this signal is ignored
                if db.is_signal_ignored(identifier_hash):
                    # Silently ignore: do not alert, but still store data? We'll store but skip alert.
                    # We'll still insert the detection below.
                    pass

                # Determine if we should store the plaintext identifier
                plain_plates_enabled = db.plain_plates_enabled()
                identifier_plain = parsed["identifier"] if plain_plates_enabled else None

                # Insert or update the signal
                # We use INSERT OR IGNORE because of the UNIQUE constraint on identifier_hash.
                # If the signal already exists, we update the last_seen and other fields?
                # For simplicity, we'll do an UPSERT: insert if not exists, else update last_seen.
                # We also update the identifier_plain if it's NULL and we now have a value?
                # But note: the plain_plates_enabled flag is set at install and rarely changes.
                # We'll update the identifier_plain only if it's currently NULL and we have a value to store?
                # However, to keep it simple, we'll do:
                #   INSERT ... ON CONFLICT(identifier_hash) DO UPDATE SET
                #       last_seen = excluded.last_seen,
                #       identifier_plane = COALESCE(excluded.identifier_plain, identifier_plain)
                # But note: we don't want to overwrite a non-NULL identifier_plain with NULL if the flag changes to False.
                # So we only update identifier_plain if the existing value is NULL and the new value is not NULL?
                # However, the flag is set at install and we assume it doesn't change often.
                # For simplicity, we'll only update last_seen on conflict and leave identifier_plain as is.
                # This means if the flag changes from False to True, existing records won't get the plaintext filled in.
                # That's acceptable because we don't have the plaintext for past events.
                cursor = db.execute(
                    """
                    INSERT INTO signals (signal_type, identifier_hash, identifier_plain, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(identifier_hash) DO UPDATE SET
                        last_seen = excluded.last_seen
                    """,
                    (
                        parsed["signal_type"],
                        identifier_hash,
                        identifier_plain,
                        parsed["timestamp"],
                        parsed["timestamp"],
                    ),
                )
                # Get the signal_id (either the newly inserted or the existing one)
                signal_id = db.fetchone(
                    "SELECT id FROM signals WHERE identifier_hash = ?",
                    (identifier_hash,),
                )["id"]

                # Insert the detection
                db.execute(
                    """
                    INSERT INTO detections (signal_id, seen_at, lat, lon, rssi, source, raw)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal_id,
                        parsed["timestamp"],
                        parsed["lat"],
                        parsed["lon"],
                        parsed["signal"],
                        parsed["source"],
                        parsed["raw"],
                    ),
                )

                # Optional: provide progress every 1000 lines
                if line_num % 1000 == 0:
                    print(f"Processed {line_num} lines...", file=sys.stderr)

    print(f"Finished processing {args.logfile}", file=sys.stderr)


if __name__ == "__main__":
    main()