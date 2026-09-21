# Raspberry Pi WiFi, Hotspot & OLED Manager

A unified Raspberry Pi management stack for Wi‑Fi, hotspot control, OLED display monitoring, and automatic update handling. This project combines a Flask-based admin dashboard, NetworkManager integration, a background OLED/fan monitor, and a smart installer into one self-maintaining system.

This is something I created with the help of AI so I could easily configure the wifi, hotspot, oled screen and change the fan behavour for a pi I was using as a dedicated test device for my network testing dashboard. Both parts are seperate and there is the option to install them sperately. 
The pi hat is a waveshare poe hat with oled screen https://www.waveshare.com/wiki/PoE_HAT_(B) So this is what that part of the code was for.

## Overview

This project is designed for Raspberry Pi systems that need a simple, local-first way to:

- manage Wi‑Fi connections via `nmcli`
- create and control an Access Point / hotspot
- configure a dedicated OLED display and PoE fan controller
- monitor system temperature and connectivity in real time
- perform local update checks and OTA refreshes from the web UI
- run unattended with self-healing recovery behavior

It is built for Raspberry Pi OS, and it uses the existing system tools instead of requiring an external cloud service.

---

## Features

### Wi‑Fi and hotspot management

- Manage available wireless interfaces from a responsive single-page dashboard
- Scan for nearby Wi‑Fi networks and connect to them using `nmcli`
- Disconnect a current Wi‑Fi connection from the UI
- Configure a hotspot on a chosen adapter, including binding to a specific interface such as `wlan1`
- Force hotspot autoconnect priority at boot and persist the hotspot policy
- Prevent scanning on interfaces that are currently acting as an Access Point
- Support captive portal redirection via `lighttpd` and NetworkManager DNS rules

### Web dashboard and access control

- Unified Flask SPA with tabs for Wi‑Fi, Hotspot, Settings, and OLED
- Optional username/password protection for the web interface
- Configurable web port with safe fallback logic
- Automatic session timeout / inactivity overlay
- Self-healing startup checks for missing core app files
- Automatic cleanup of obsolete legacy files from older versions

### OLED display and fan control

- Supports SSD1306 OLED displays over I2C
- Monitors CPU temperature using `vcgencmd`
- Controls a PoE HAT fan with hysteresis and anti-flutter logic
- Displays configurable pages such as:
  - network list
  - hotspot details
  - custom text pages
- Supports vertical and horizontal scrolling
- Includes quiet hours / night mode
- Supports brightness control, rotate/invert modes, and screensaver behavior
- Stores configuration in a JSON settings file and reloads on service restart

### OTA and maintenance

- Detects installed app and OLED versions locally
- Compares local versions to GitHub versions
- Downloads and parses changelogs from the repository
- Lets the user check for updates from the UI and trigger selected component updates
- Installs, reinstalls, updates, and removes components through the terminal installer
- Gracefully handles missing or corrupted files by recovering them from GitHub
- Falls back to alternate web ports if the chosen port is already in use

---

## Project components

### 1. Installer

File: `install.sh`

Responsible for:

- fresh installs
- component updates
- reinstall flows
- optional OLED-only or Wi‑Fi-only install modes
- dependency installation (`apt`, `pip`, `venv`, `NetworkManager`, etc.)
- systemd service creation
- captive portal setup
- uninstall and reset flows

### 2. Wi‑Fi app backend and UI

Path: `pi-wifi-app/`

Includes:

- `app.py` – Flask web app and API routes
- `templates/index.html` – SPA layout and UI structure
- `static/style.css` – styling
- `static/script.js` – front-end logic for Wi‑Fi, OTA updates, and OLED preview
- `version.json` – local app version metadata

The web app exposes API endpoints for:

- scanning Wi‑Fi networks
- connecting/disconnecting Wi‑Fi
- hotspot configuration
- reading system status
- saving/resetting OLED settings
- update checks and update execution

### 3. OLED monitor daemon

Path: `oled_monitor/`

Includes:

- `monitor.py` – background service that reads hardware state, controls the display, and manages the fan
- `settings.json` – runtime OLED configuration
- `version.json` – local OLED component version metadata

This service keeps the display, fan, and system monitoring logic independent from the Flask app.

---

## Requirements

This project is intended for:

- Raspberry Pi hardware
- Raspberry Pi OS / Debian-based Linux
- `NetworkManager`
- `lighttpd`
- Python 3
- I2C-enabled hardware for OLED support

For OLED support, the system should have:

- an SSD1306-compatible OLED connected over I2C
- PoE HAT fan support or a compatible fan wiring setup
- the I2C interface enabled

---

## Quick installation

Run this from a terminal on your Raspberry Pi:

```bash
curl -sSL https://raw.githubusercontent.com/Chrisb003/pi-wifi-and-hotspot-configurator/main/install.sh | sh
```

The installer will detect whether the project is already installed and offer options such as:

- install Wi‑Fi app only
- install OLED manager only
- install both
- update existing components
- reinstall
- reset OLED settings
- uninstall completely

> The installer requires `sudo` privileges because it configures system services, NetworkManager, and package dependencies.

---

## Manual install behavior

The installer:

- creates the app directories under the active user’s home folder
- installs the required APT packages
- enables I2C when the OLED component is installed
- creates a Python virtual environment for the OLED service
- downloads the project files from GitHub
- creates `systemd` services for the web app and OLED daemon
- configures lighttpd and captive portal redirect behavior
- starts the services automatically

---

## How the app is used

### Web dashboard

Once running, open the web interface in a browser using the configured port, typically:

```text
http://<pi-ip>:8080/
```

The dashboard includes:

- Wi‑Fi network scanner and connector
- hotspot manager with interface binding and toggle controls
- web authentication settings
- OLED configuration panel and live preview
- update checker and OTA update trigger

### Web authentication

The app can protect the UI with a username and password. If the authentication file exists, access is gated until the user logs in.

### Resetting auth

If you are locked out of the dashboard, run:

```bash
touch ~/pi-wifi-app/reset && sudo systemctl restart pi-wifi-app
```

This removes the saved credentials and restarts the service.

### Resetting OLED settings

If the OLED configuration becomes broken or you want to restore the default layout, run:

```bash
touch ~/oled_monitor/reset && sudo systemctl restart oled_monitor.service
```

---

## Services and runtime behavior

The project uses systemd services for persistence:

- `pi-wifi-app.service` – Flask web app
- `oled_monitor.service` – OLED display + fan daemon

Manual restarts:

```bash
sudo systemctl restart pi-wifi-app.service
sudo systemctl restart oled_monitor.service
```

---

## OTA update system

The app includes a built-in update checker that:

- reads local version metadata
- fetches remote version metadata from GitHub
- downloads changelog files
- compares versions for the Wi‑Fi app and OLED component
- allows selective update of each component from the web interface

The backend update logic downloads the newest files from the repository and restarts the relevant service.

---

## Files and folder structure

```text
.
├── install.sh
├── README.md
├── pi-wifi-app/
│   ├── app.py
│   ├── version.json
│   ├── static/
│   │   ├── script.js
│   │   └── style.css
│   ├── templates/
│   │   └── index.html
│   └── ...
├── oled_monitor/
│   ├── monitor.py
│   ├── version.json
│   ├── settings.json
│   └── ...
└── ...
```

---

## Notes on design

This project tries to be:

- offline-first wherever possible
- local-only for configuration and system interactions
- resilient to partial failures
- easy to reinstall, refresh, or reset

It relies on local system commands such as:

- `nmcli`
- `vcgencmd`
- `ip`
- `i2c` utilities
- `systemctl`

This keeps the project functional even without internet access for day-to-day management.

---

## Troubleshooting

### Service not starting

Check logs:

```bash
sudo systemctl status pi-wifi-app.service
sudo systemctl status oled_monitor.service
```

### Auth is locked

```bash
touch ~/pi-wifi-app/reset && sudo systemctl restart pi-wifi-app
```

### OLED config is broken

```bash
touch ~/oled_monitor/reset && sudo systemctl restart oled_monitor.service
```

### Port conflict

The app includes fallback port logic so that if the selected port is unavailable, it attempts a backup and then defaults to `8080`.

---

## Summary

This project is a complete Raspberry Pi utility for managing Wi‑Fi, hotspots, OLED display hardware, and OTA maintenance from a single local dashboard. It is designed to be practical for real hardware use, resilient to errors, and easy to update or recover from broken states.

If you are deploying it on a Raspberry Pi, the recommended path is to run the installer and then use the built-in web dashboard to configure Wi‑Fi, the hotspot, and the OLED screen with minimal manual intervention.
