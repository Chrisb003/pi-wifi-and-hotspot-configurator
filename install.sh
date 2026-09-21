#!/bin/sh

# ==========================================
# Pi WiFi, Hotspot & OLED Manager Installer
# Version: 2.4.0 (Smart Refresh Logic Added)
# ==========================================
INSTALLER_VERSION="1.0.0"
REPO_BASE="https://raw.githubusercontent.com/Chrisb003/pi-wifi-and-hotspot-configurator/main"

# ---------------------------------------------------------
# Sudo Check
# ---------------------------------------------------------
# Ensure the user ran the script with sudo privileges, which is required
# for apt-get installations, systemd service creation, and network modifications.
sudo -v || { echo "This script requires sudo privileges. Exiting."; exit 1; }

# ---------------------------------------------------------
# User & Directory Resolution
# ---------------------------------------------------------
# When a script is run with sudo, $USER becomes root. We want to install the
# application files into the actual user's home directory (e.g., /home/pi),
# so we check $SUDO_USER first to find the real user who executed the script.
if [ "$(id -u)" -eq 0 ]; then
    if [ -n "$SUDO_USER" ]; then
        ACTUAL_USER="$SUDO_USER"
        USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
    else
        ACTUAL_USER="root"
        USER_HOME="/root"
    fi
else
    ACTUAL_USER=$(id -un)
    USER_HOME="$HOME"
fi

# Define core directories and file paths
WIFI_DIR="$USER_HOME/pi-wifi-app"
OLED_DIR="$USER_HOME/oled_monitor"
WIFI_SERVICE="/etc/systemd/system/pi-wifi-app.service"
OLED_SERVICE="/etc/systemd/system/oled_monitor.service"
PORT_FILE="$WIFI_DIR/webport"
DEFAULT_PORT="8080"

# Set default installation states
INSTALL_MODE="install"
INSTALL_WIFI="no"
INSTALL_OLED="no"

# ---------------------------------------------------------
# Local Version Detection
# ---------------------------------------------------------
# Parses the local version.json files to see what is currently installed.
# We use standard grep and cut to remain 100% POSIX compliant without needing jq.
INSTALLED_WIFI_VERSION="none"
INSTALLED_OLED_VERSION="none"

if [ -f "$WIFI_DIR/version.json" ]; then
    INSTALLED_WIFI_VERSION=$(grep '"version"' "$WIFI_DIR/version.json" | cut -d':' -f2 | tr -d ' ",\n\r')
fi
if [ -f "$OLED_DIR/version.json" ]; then
    INSTALLED_OLED_VERSION=$(grep '"version"' "$OLED_DIR/version.json" | cut -d':' -f2 | tr -d ' ",\n\r')
fi

# Fallback in case the file exists but was empty/corrupted
INSTALLED_WIFI_VERSION=${INSTALLED_WIFI_VERSION:-"unknown"}
INSTALLED_OLED_VERSION=${INSTALLED_OLED_VERSION:-"unknown"}

# ---------------------------------------------------------
# Fetch Remote Version Information
# ---------------------------------------------------------
# Attempts to securely download the master 'version' file from the GitHub 
# repository with a 5-second timeout (-m 5).
echo ">>> Fetching latest version information from GitHub..."
VERSION_FILE="/tmp/pi_manager_version_info"
curl -sSL -m 5 "$REPO_BASE/version" -o "$VERSION_FILE" >/dev/null 2>&1

if [ -f "$VERSION_FILE" ]; then
    # Extract version strings, stripping out any quotes
    TARGET_OLED_VERSION=$(grep -i '^OLED_VERSION=' "$VERSION_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    TARGET_WIFI_VERSION=$(grep -i '^WIFI_VERSION=' "$VERSION_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
fi

# Fallback to "unknown" if the variables are empty (e.g. file not found or no internet)
TARGET_OLED_VERSION=${TARGET_OLED_VERSION:-"unknown"}
TARGET_WIFI_VERSION=${TARGET_WIFI_VERSION:-"unknown"}

# Cleanup temp file
rm -f "$VERSION_FILE"

# ---------------------------------------------------------
# Detection & Menu Logic
# ---------------------------------------------------------
# Checks if the directories or systemd services already exist to determine
# if this is a fresh install or an update/reinstall.
HAS_WIFI="no"
HAS_OLED="no"
if [ -d "$WIFI_DIR" ] || [ -f "$WIFI_SERVICE" ]; then HAS_WIFI="yes"; fi
if [ -d "$OLED_DIR" ] || [ -f "$OLED_SERVICE" ]; then HAS_OLED="yes"; fi

# Determine if the installed components match the remote target versions
UP_TO_DATE="yes"
if [ "$HAS_WIFI" = "yes" ] && [ "$INSTALLED_WIFI_VERSION" != "$TARGET_WIFI_VERSION" ]; then UP_TO_DATE="no"; fi
if [ "$HAS_OLED" = "yes" ] && [ "$INSTALLED_OLED_VERSION" != "$TARGET_OLED_VERSION" ]; then UP_TO_DATE="no"; fi

SKIP_MENU="no"

if [ "$HAS_WIFI" = "yes" ] || [ "$HAS_OLED" = "yes" ]; then
    echo "=================================================="
    echo " Pi WiFi, Hotspot & OLED Manager (Installer v$INSTALLER_VERSION)"
    echo "=================================================="
    
    # ---------------------------------------------------------
    # Up-To-Date Fast Path
    # ---------------------------------------------------------
    if [ "$UP_TO_DATE" = "yes" ]; then
        echo "Status: Your installed components are completely up-to-date!"
        if [ "$HAS_WIFI" = "yes" ]; then echo " - WiFi UI : v$INSTALLED_WIFI_VERSION"; fi
        if [ "$HAS_OLED" = "yes" ]; then echo " - OLED    : v$INSTALLED_OLED_VERSION"; fi
        echo "--------------------------------------------------"
        printf "Would you like to force a reinstall/refresh of the code? (y/N): "
        read force_choice < /dev/tty
        case "$force_choice" in
            [Yy]* )
                INSTALL_MODE="update"
                INSTALL_WIFI="$HAS_WIFI"
                INSTALL_OLED="$HAS_OLED"
                SKIP_MENU="yes"
                echo "Proceeding to download and replace the code..."
                ;;
            * )
                SKIP_MENU="no"
                echo "--------------------------------------------------"
                ;;
        esac
    fi

    # ---------------------------------------------------------
    # Standard Existing Installation Menu
    # ---------------------------------------------------------
    if [ "$SKIP_MENU" = "no" ]; then
        echo "Status: Existing installation detected."
        if [ "$HAS_WIFI" = "yes" ]; then
            echo " - WiFi UI : Installed v$INSTALLED_WIFI_VERSION -> Target v$TARGET_WIFI_VERSION"
        else
            echo " - WiFi UI : Not Installed"
        fi
        if [ "$HAS_OLED" = "yes" ]; then
            echo " - OLED    : Installed v$INSTALLED_OLED_VERSION -> Target v$TARGET_OLED_VERSION"
        else
            echo " - OLED    : Not Installed"
        fi
        echo "--------------------------------------------------"
        echo "1) Update existing components"
        echo "2) Install missing components (Install BOTH)"
        echo "3) Full Reinstall (wipes existing components & rebuilds)"
        echo "4) Reset OLED Settings to Default"
        echo "5) Uninstall ALL completely"
        echo "6) Exit"
        printf "Select an option [1-6]: "
        read menu_choice < /dev/tty # Read directly from TTY to allow 'curl | sh' piping
        
        case "$menu_choice" in
            1)
                INSTALL_MODE="update"
                INSTALL_WIFI="$HAS_WIFI"
                INSTALL_OLED="$HAS_OLED"
                echo "Proceeding with update. Your settings will be preserved..."
                ;;
            2)
                INSTALL_MODE="install"
                INSTALL_WIFI="yes"
                INSTALL_OLED="yes"
                echo "Proceeding to install all missing components..."
                ;;
            3)
                INSTALL_MODE="reinstall"
                INSTALL_WIFI="$HAS_WIFI"
                INSTALL_OLED="$HAS_OLED"
                echo "Proceeding with full reinstall..."
                sudo systemctl stop pi-wifi-app oled_monitor.service >/dev/null 2>&1
                [ "$INSTALL_WIFI" = "yes" ] && sudo rm -rf "$WIFI_DIR"
                [ "$INSTALL_OLED" = "yes" ] && sudo rm -rf "$OLED_DIR"
                ;;
            4)
                if [ "$HAS_OLED" = "yes" ]; then
                    echo ">>> Resetting OLED settings.json to default..."
                    touch "$OLED_DIR/reset"
                    sudo systemctl restart oled_monitor.service 2>/dev/null
                    echo "Settings Reset Complete!"
                else
                    echo "OLED is not installed. Nothing to reset."
                fi
                exit 0
                ;;
            5)
                echo ">>> Starting complete uninstallation..."
                sudo systemctl stop pi-wifi-app oled_monitor.service 2>/dev/null
                sudo systemctl disable pi-wifi-app oled_monitor.service 2>/dev/null
                sudo rm -f "$WIFI_SERVICE" "$OLED_SERVICE"
                sudo rm -f /etc/NetworkManager/dnsmasq-shared.d/captive.conf
                sudo rm -f /var/www/html/index.sh
                sudo systemctl daemon-reload
                sudo systemctl restart NetworkManager lighttpd 2>/dev/null
                sudo rm -rf "$WIFI_DIR" "$OLED_DIR"
                echo "Uninstallation Complete!"
                exit 0
                ;;
            6|* )
                echo "Exiting without making changes."
                exit 0
                ;;
        esac
    fi
else
    # ---------------------------------------------------------
    # Fresh Installation Menu
    # ---------------------------------------------------------
    echo "=================================================="
    echo " Pi WiFi, Hotspot & OLED Manager (Installer v$INSTALLER_VERSION)"
    echo "=================================================="
    echo "Latest Versions -> WiFi UI: v$TARGET_WIFI_VERSION | OLED: v$TARGET_OLED_VERSION"
    echo "What would you like to install?"
    echo "1) WiFi & Hotspot Manager Only (Web UI)"
    echo "2) OLED Display & Fan Controller Only (Background Service)"
    echo "3) Install BOTH (Recommended)"
    echo "4) Cancel"
    printf "Select an option [1-4]: "
    read install_choice < /dev/tty
    
    case "$install_choice" in
        1) INSTALL_WIFI="yes"; INSTALL_OLED="no" ;;
        2) INSTALL_WIFI="no"; INSTALL_OLED="yes" ;;
        3) INSTALL_WIFI="yes"; INSTALL_OLED="yes" ;;
        * ) echo "Installation aborted."; exit 0 ;;
    esac
fi

# ---------------------------------------------------------
# Dynamic APT Dependencies
# ---------------------------------------------------------
# Selectively builds a list of Debian packages to install depending on which
# components the user chose. This prevents installing heavy graphics libraries
# if the user only wants the WiFi interface.
APT_PACKAGES=""
if [ "$INSTALL_WIFI" = "yes" ]; then
    APT_PACKAGES="$APT_PACKAGES python3-flask network-manager lighttpd"
fi
if [ "$INSTALL_OLED" = "yes" ]; then
    APT_PACKAGES="$APT_PACKAGES swig liblgpio-dev python3-lgpio python3-rpi.gpio python3-venv python3-pip python3-pil i2c-tools python3-smbus"
fi

if [ -n "$APT_PACKAGES" ]; then
    echo ">>> Installing required system packages..."
    sudo apt-get update
    sudo apt-get install -y $APT_PACKAGES
fi

# =========================================================
# OLED INSTALLATION ROUTINE
# =========================================================
if [ "$INSTALL_OLED" = "yes" ]; then
    echo ">>> Safely Enabling I2C Interface..."
    # Uses raspi-config to enable I2C at the hardware level, then probes the modules
    sudo raspi-config nonint do_i2c 0
    sudo modprobe i2c-dev 2>/dev/null || true
    sudo modprobe i2c-bcm2835 2>/dev/null || true

    # Create Python Virtual Environment
    # We use a venv to prevent breaking system-level Python packages in Debian 12 (Bookworm)
    if [ "$INSTALL_MODE" = "reinstall" ] || [ ! -d "$OLED_DIR/env" ]; then
        echo ">>> Setting up Python Virtual Environment for OLED..."
        mkdir -p "$OLED_DIR"
        python3 -m venv --system-site-packages "$OLED_DIR/env"
        "$OLED_DIR/env/bin/pip" install --upgrade adafruit-circuitpython-ssd1306 adafruit-blinka Pillow
    fi

    # Download OLED Script & Version Files from GitHub
    echo ">>> Downloading OLED Manager files..."
    mkdir -p "$OLED_DIR"
    curl -sSL "$REPO_BASE/oled_monitor/monitor.py" -o "$OLED_DIR/monitor.py"
    curl -sSL "$REPO_BASE/oled_monitor/version.json" -o "$OLED_DIR/version.json"

    # Create OLED Systemd Service
    # Ensures the OLED script runs automatically on boot as a background daemon
    echo ">>> Creating OLED Systemd Service..."
    cat << EOF | sudo tee "$OLED_SERVICE" > /dev/null
[Unit]
Description=OLED Network Monitor & Fan Controller
After=network.target

[Service]
Type=simple
ExecStart=$OLED_DIR/env/bin/python $OLED_DIR/monitor.py
WorkingDirectory=$OLED_DIR
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
EOF
    # Set proper ownership so the actual user can edit the files later
    sudo chown -R "$ACTUAL_USER:$ACTUAL_USER" "$OLED_DIR"
fi

# =========================================================
# WIFI APP INSTALLATION ROUTINE
# =========================================================
if [ "$INSTALL_WIFI" = "yes" ]; then
    echo ">>> Creating WiFi application directories..."
    mkdir -p "$WIFI_DIR/templates"

    # Create the default web port configuration file if it doesn't exist
    if [ ! -f "$PORT_FILE" ]; then
        echo "$DEFAULT_PORT" > "$PORT_FILE"
    fi

    # Download all necessary Python, HTML, and Version files from GitHub
    echo ">>> Downloading WiFi Manager files..."
    curl -sSL "$REPO_BASE/pi-wifi-app/app.py" -o "$WIFI_DIR/app.py"
    curl -sSL "$REPO_BASE/pi-wifi-app/version.json" -o "$WIFI_DIR/version.json"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/index.html" -o "$WIFI_DIR/templates/index.html"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/login.html" -o "$WIFI_DIR/templates/login.html"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/settings.html" -o "$WIFI_DIR/templates/settings.html"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/hotspot.html" -o "$WIFI_DIR/templates/hotspot.html"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/oled.html" -o "$WIFI_DIR/templates/oled.html"

    # Web Authentication Setup
    # Generates a secure werkzeug password hash natively through Python during installation
    if [ "$INSTALL_MODE" != "update" ] && [ ! -f "$WIFI_DIR/user" ]; then
        printf "Do you want to enable web authentication? (y/N): "
        read auth_choice < /dev/tty
        case "$auth_choice" in
            [Yy]* )
                printf "Enter username: "
                read WEB_USER < /dev/tty
                printf "Enter password: "
                stty -echo < /dev/tty # Hide password input
                read WEB_PASS < /dev/tty
                stty echo < /dev/tty # Restore terminal text
                echo ""
                WEB_HASH=$(python3 -c "import sys; from werkzeug.security import generate_password_hash; print(generate_password_hash(sys.argv[1]))" "$WEB_PASS")
                echo "$WEB_USER:$WEB_HASH" > "$WIFI_DIR/user"
                echo "Authentication configured."
                ;;
        esac
    fi

    # ---------------------------------------------------------
    # Lighttpd & Captive Portal Routing Configuration
    # ---------------------------------------------------------
    # Modifies lighttpd to enable Bash CGI scripts, allowing dynamic redirection
    # for the Captive Portal popup to work on iOS and Android devices.
    echo ">>> Configuring Lighttpd for Captive Portal..."
    grep -q 'mod_cgi' /etc/lighttpd/lighttpd.conf || echo 'server.modules += ( "mod_cgi" )' | sudo tee -a /etc/lighttpd/lighttpd.conf
    grep -q 'cgi.assign' /etc/lighttpd/lighttpd.conf || echo 'cgi.assign = ( ".sh" => "/bin/bash" )' | sudo tee -a /etc/lighttpd/lighttpd.conf
    grep -q 'index.sh' /etc/lighttpd/lighttpd.conf || echo 'index-file.names += ( "index.sh" )' | sudo tee -a /etc/lighttpd/lighttpd.conf

    # Create the dynamic index.sh file that reads the current port and redirects the user
    cat << 'EOF' | sudo tee /var/www/html/index.sh > /dev/null
#!/bin/bash
PORT=80
PORT_FILE=$(ls /home/*/Network-Testing-Tools/webport 2>/dev/null | head -n 1)
if [ -z "$PORT_FILE" ]; then
    PORT_FILE=$(ls /home/*/pi-wifi-app/webport 2>/dev/null | head -n 1)
fi
if [ -n "$PORT_FILE" ] && [ -r "$PORT_FILE" ]; then
    EXTRACTED_PORT=$(cat "$PORT_FILE" | tr -d '[:space:]')
    [ -n "$EXTRACTED_PORT" ] && PORT="$EXTRACTED_PORT"
fi
echo "Status: 302 Found"
echo "Location: http://10.42.0.1:${PORT}/"
echo ""
EOF

    sudo chmod +x /var/www/html/index.sh
    sudo rm -f /var/www/html/index.html

    # Tell NetworkManager to hijack all DNS requests (for the Hotspot) to point to the Pi
    sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
    echo "address=/#/10.42.0.1" | sudo tee /etc/NetworkManager/dnsmasq-shared.d/captive.conf > /dev/null

    # Create WiFi Systemd Service
    echo ">>> Creating WiFi Systemd Service..."
    cat << EOF | sudo tee "$WIFI_SERVICE" > /dev/null
[Unit]
Description=Pi WiFi Configurator Web App
After=network.target network-manager.service

[Service]
User=root
WorkingDirectory=$WIFI_DIR
ExecStart=/usr/bin/python3 $WIFI_DIR/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
    # Set proper ownership
    sudo chown -R "$ACTUAL_USER:$ACTUAL_USER" "$WIFI_DIR"
fi

# ---------------------------------------------------------
# Service Startups & Finalization
# ---------------------------------------------------------
echo ">>> Restarting Services..."
sudo systemctl daemon-reload

if [ "$INSTALL_WIFI" = "yes" ]; then
    sudo systemctl enable pi-wifi-app
    sudo systemctl restart pi-wifi-app lighttpd NetworkManager
fi

if [ "$INSTALL_OLED" = "yes" ]; then
    sudo systemctl enable oled_monitor.service
    sudo systemctl restart oled_monitor.service
fi

echo "==================================================="
echo " Installation complete!"
echo " The installed components are now running."
echo " Note: To reset web auth physically, run:"
echo " touch $WIFI_DIR/reset && sudo systemctl restart pi-wifi-app"
echo "==================================================="