#!/usr/bin/env bash
# Provisions a fresh Raspberry Pi OS install for StillPoint.
#
# What it does (v0.1 placeholder — fleshed out as modules land):
#   1. apt installs: kismet, gpsd, gpsd-clients, python3-pip, git
#   2. Configures gpsd for the USB GPS dongle
#   3. Creates /opt/stillpoint, checks out this repo
#   4. Installs systemd units for kismet, ingest, api
#   5. Enables and starts services
#
# Usage:
#   curl -sSL <this-repo>/hardware/install.sh | sudo bash
#
# NOT YET IMPLEMENTED. See docs/roadmap.md.
set -euo pipefail
echo "install.sh placeholder — see docs/roadmap.md"