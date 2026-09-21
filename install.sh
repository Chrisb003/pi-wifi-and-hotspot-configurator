#!/bin/sh

# ==========================================
# Pi WiFi, Hotspot & OLED Manager Installer
# Version: 2.1.0 (Modular Installation)
# ==========================================
VERSION="2.1.0"
REPO_BASE="https://raw.githubusercontent.com/Chrisb003/pi-wifi-and-hotspot-configurator/main"

sudo -v || { echo "This script requires sudo privileges. Exiting."; exit 1; }

# Determine the current user and home directory
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

WIFI_DIR="$USER_HOME/pi-wifi-app"
OLED_DIR="$USER_HOME/oled_monitor"
WIFI_SERVICE="/etc/systemd/system/pi-wifi-app.service"
OLED_SERVICE="/etc/systemd/system/oled_monitor.service"
PORT_FILE="$WIFI_DIR/webport"
DEFAULT_PORT="8080"

INSTALL_MODE="install"
INSTALL_WIFI="no"
INSTALL_OLED="no"

# ==========================================
# DETECTION & MENU LOGIC
# ==========================================
HAS_WIFI="no"
HAS_OLED="no"
if [ -d "$WIFI_DIR" ] || [ -f "$WIFI_SERVICE" ]; then HAS_WIFI="yes"; fi
if [ -d "$OLED_DIR" ] || [ -f "$OLED_SERVICE" ]; then HAS_OLED="yes"; fi

if [ "$HAS_WIFI" = "yes" ] || [ "$HAS_OLED" = "yes" ]; then
    echo "=================================================="
    echo " Pi WiFi, Hotspot & OLED Manager (v$VERSION)"
    echo "=================================================="
    echo "Status: Existing installation detected."
    echo " - WiFi & Hotspot Manager: $HAS_WIFI"
    echo " - OLED & Fan Controller:  $HAS_OLED"
    echo "--------------------------------------------------"
    echo "1) Update existing components"
    echo "2) Install missing components (Install BOTH)"
    echo "3) Full Reinstall (wipes existing components & rebuilds)"
    echo "4) Reset OLED Settings to Default"
    echo "5) Uninstall ALL completely"
    echo "6) Exit"
    printf "Select an option [1-6]: "
    read menu_choice < /dev/tty
    
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
else
    echo "=================================================="
    echo " Pi WiFi, Hotspot & OLED Manager (v$VERSION)"
    echo "=================================================="
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

# ==========================================
# DYNAMIC DEPENDENCIES
# ==========================================
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

# ==========================================
# OLED INSTALLATION ROUTINE
# ==========================================
if [ "$INSTALL_OLED" = "yes" ]; then
    echo ">>> Safely Enabling I2C Interface..."
    sudo raspi-config nonint do_i2c 0
    sudo modprobe i2c-dev 2>/dev/null || true
    sudo modprobe i2c-bcm2835 2>/dev/null || true

    if [ "$INSTALL_MODE" = "reinstall" ] || [ ! -d "$OLED_DIR/env" ]; then
        echo ">>> Setting up Python Virtual Environment for OLED..."
        mkdir -p "$OLED_DIR"
        python3 -m venv --system-site-packages "$OLED_DIR/env"
        "$OLED_DIR/env/bin/pip" install --upgrade adafruit-circuitpython-ssd1306 adafruit-blinka Pillow
    fi

    echo ">>> Downloading OLED Manager..."
    mkdir -p "$OLED_DIR"
    curl -sSL "$REPO_BASE/oled_monitor/monitor.py" -o "$OLED_DIR/monitor.py"

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
    sudo chown -R "$ACTUAL_USER:$ACTUAL_USER" "$OLED_DIR"
fi

# ==========================================
# WIFI APP INSTALLATION ROUTINE
# ==========================================
if [ "$INSTALL_WIFI" = "yes" ]; then
    echo ">>> Creating WiFi application directories..."
    mkdir -p "$WIFI_DIR/templates"

    if [ ! -f "$PORT_FILE" ]; then
        echo "$DEFAULT_PORT" > "$PORT_FILE"
    fi

    echo ">>> Downloading WiFi Manager files..."
    curl -sSL "$REPO_BASE/pi-wifi-app/app.py" -o "$WIFI_DIR/app.py"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/index.html" -o "$WIFI_DIR/templates/index.html"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/login.html" -o "$WIFI_DIR/templates/login.html"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/settings.html" -o "$WIFI_DIR/templates/settings.html"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/hotspot.html" -o "$WIFI_DIR/templates/hotspot.html"
    curl -sSL "$REPO_BASE/pi-wifi-app/templates/oled.html" -o "$WIFI_DIR/templates/oled.html"

    if [ "$INSTALL_MODE" != "update" ] && [ ! -f "$WIFI_DIR/user" ]; then
        printf "Do you want to enable web authentication? (y/N): "
        read auth_choice < /dev/tty
        case "$auth_choice" in
            [Yy]* )
                printf "Enter username: "
                read WEB_USER < /dev/tty
                printf "Enter password: "
                stty -echo < /dev/tty
                read WEB_PASS < /dev/tty
                stty echo < /dev/tty
                echo ""
                WEB_HASH=$(python3 -c "import sys; from werkzeug.security import generate_password_hash; print(generate_password_hash(sys.argv[1]))" "$WEB_PASS")
                echo "$WEB_USER:$WEB_HASH" > "$WIFI_DIR/user"
                echo "Authentication configured."
                ;;
        esac
    fi

    echo ">>> Configuring Lighttpd for Captive Portal..."
    grep -q 'mod_cgi' /etc/lighttpd/lighttpd.conf || echo 'server.modules += ( "mod_cgi" )' | sudo tee -a /etc/lighttpd/lighttpd.conf
    grep -q 'cgi.assign' /etc/lighttpd/lighttpd.conf || echo 'cgi.assign = ( ".sh" => "/bin/bash" )' | sudo tee -a /etc/lighttpd/lighttpd.conf
    grep -q 'index.sh' /etc/lighttpd/lighttpd.conf || echo 'index-file.names += ( "index.sh" )' | sudo tee -a /etc/lighttpd/lighttpd.conf

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

    sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
    echo "address=/#/10.42.0.1" | sudo tee /etc/NetworkManager/dnsmasq-shared.d/captive.conf > /dev/null

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
    sudo chown -R "$ACTUAL_USER:$ACTUAL_USER" "$WIFI_DIR"
fi

# ==========================================
# SERVICE RESTARTS
# ==========================================
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
echo " Note: To reset web auth physically, run:"
echo " touch $WIFI_DIR/reset && sudo systemctl restart pi-wifi-app"
echo "==================================================="