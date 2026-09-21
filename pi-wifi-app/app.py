from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import subprocess
import os
import re
import json
import glob
import socket
import datetime
import urllib.request
from urllib.error import URLError
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(days=365)

# ==============================================================================
# FILE PATH & REPOSITORY CONFIGURATIONS
# ==============================================================================
script_dir = os.path.dirname(os.path.abspath(__file__))
user_file = os.path.join(script_dir, 'user')
reset_file = os.path.join(script_dir, 'reset')
port_file_path = os.path.join(script_dir, 'webport')
hotspot_policy_file = os.path.join(script_dir, 'hotspot_policy')
local_wifi_version_file = os.path.join(script_dir, 'version.json')

REPO_BASE = "https://raw.githubusercontent.com/Chrisb003/pi-wifi-and-hotspot-configurator/main"

# Core application files required for the SPA to function correctly
CORE_FILES = [
    'app.py',
    'version.json',
    'templates/index.html',
    'static/style.css',
    'static/script.js'
]

# Legacy files from older versions that should be deleted to prevent clutter
OBSOLETE_FILES = [
    'templates/settings.html',
    'templates/hotspot.html',
    'templates/oled.html',
    'templates/login.html' # Now obsolete!
]

def download_file(url, dest_path):
    """
    Securely downloads a file from a URL to a local destination using urllib.
    Automatically creates any missing target directories (e.g., /static/).
    Returns True on success, False if a network or writing error occurs.
    """
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response, open(dest_path, 'wb') as out_file:
            out_file.write(response.read())
        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False

def verify_and_download_core_files():
    """
    Verifies all core application files exist locally. If any are missing,
    or if the terminal installer created the '.update_triggered' flag,
    it dynamically downloads the fresh files from the GitHub repository.
    """
    update_flag = os.path.join(script_dir, '.update_triggered')
    force_update = os.path.exists(update_flag)
    
    for file_path in CORE_FILES:
        full_path = os.path.join(script_dir, file_path)
        
        # Trigger download if the file is missing OR if the installer flagged an update
        if force_update or not os.path.exists(full_path):
            # Do NOT overwrite app.py because the install.sh script JUST downloaded the latest one!
            if file_path != 'app.py':
                print(f"Startup: Fetching '{file_path}'...")
                url = f"{REPO_BASE}/pi-wifi-app/{file_path}"
                download_file(url, full_path)
                
    # Clean up the flag so it boots normally (offline) next time
    if force_update:
        try:
            os.remove(update_flag)
            print("Startup: Terminal update synchronization complete.")
        except Exception: pass

def cleanup_obsolete_files():
    """
    Scans for and safely deletes legacy files from older versions of the app 
    (e.g., obsolete HTML templates from before the SPA migration).
    """
    for file_path in OBSOLETE_FILES:
        full_path = os.path.join(script_dir, file_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                print(f"Startup: Cleaned up obsolete file '{file_path}'.")
            except Exception as e:
                print(f"Startup: Failed to remove obsolete file '{file_path}': {e}")

# Run the self-healing and cleanup routines immediately before the server fully binds
verify_and_download_core_files()
cleanup_obsolete_files()

def get_oled_dir():
    """
    Detects if the OLED Monitor script is installed on the system.
    Scans the home directories and root for the 'oled_monitor' folder.
    Returns the absolute path if found, otherwise None.
    """
    for d in glob.glob('/home/*/oled_monitor'):
        if os.path.isdir(d): return d
    if os.path.isdir('/root/oled_monitor'): return '/root/oled_monitor'
    return None

# ==============================================================================
# STARTUP RESET LOGIC
# ==============================================================================
# If a physical file named 'reset' is found in the app directory on startup,
# delete the user credentials file to restore open access, then remove the trigger file.
if os.path.exists(reset_file):
    try:
        if os.path.exists(user_file): os.remove(user_file)
        os.remove(reset_file)
        print("Startup: Reset file detected. Authentication has been removed.")
    except Exception as e:
        print(f"Startup: Error resetting user: {e}")

# ==============================================================================
# UPDATE & VERSIONING FUNCTIONS
# ==============================================================================
def get_local_versions():
    """
    Reads the local version.json files for both the WiFi App and the OLED Monitor.
    Returns a tuple: (wifi_version, oled_version). Missing components return 'Not Installed'.
    """
    wifi_ver = "Unknown"
    oled_ver = "Not Installed"
    
    # Check WiFi App Version
    if os.path.exists(local_wifi_version_file):
        try:
            with open(local_wifi_version_file, 'r') as f:
                data = json.load(f)
                wifi_ver = data.get("version", "Unknown")
        except Exception: pass
        
    # Check OLED Monitor Version
    oled_dir = get_oled_dir()
    if oled_dir:
        oled_ver_file = os.path.join(oled_dir, 'version.json')
        if os.path.exists(oled_ver_file):
            try:
                with open(oled_ver_file, 'r') as f:
                    data = json.load(f)
                    oled_ver = data.get("version", "Unknown")
            except Exception:
                oled_ver = "Unknown"
        else:
            oled_ver = "Unknown"
            
    return wifi_ver, oled_ver

def parse_changelog(raw_markdown):
    """
    Parses the custom changelog Markdown format into a structured Python dictionary.
    Safely handles releases that have bullet points but no subtitles.
    """
    releases = []
    current_release = None
    current_section = None
    
    for line in raw_markdown.splitlines():
        line = line.strip()
        if not line: continue
        
        # Parse Release Header
        if line.startswith('## '):
            match = re.match(r'##\s*\[(.*?)\]\s*-\s*(.*)', line)
            version = match.group(1) if match else "Unknown"
            title = match.group(2) if match else line.replace('## ', '')
            current_release = {"version": version, "title": title, "sections": []}
            releases.append(current_release)
            current_section = None
            
        # Parse Subtitle Header
        elif line.startswith('** '):
            if current_release is not None:
                subtitle = line.replace('** ', '').strip()
                current_section = {"subtitle": subtitle, "bullets": []}
                current_release["sections"].append(current_section)
                
        # Parse Bullet Points
        elif line.startswith('*'):
            if current_release is not None:
                # If there are bullets but no subtitle, create a blank general section
                if current_section is None:
                    current_section = {"subtitle": "", "bullets": []}
                    current_release["sections"].append(current_section)
                    
                bullet_content = line[1:].strip()
                if bullet_content == "":
                    current_section["bullets"].append({"type": "space"})
                else:
                    current_section["bullets"].append({"type": "text", "content": bullet_content})
                    
    return releases

# ==============================================================================
# RAM CACHE (Minimizes SD Card I/O)
# ==============================================================================
RAM_CACHE = {
    'auth_enabled': None,
    'current_port': None
}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def get_credentials():
    """Retrieves the currently saved username and hashed password from the user file."""
    if os.path.exists(user_file):
        with open(user_file, 'r') as f:
            content = f.read().strip()
            if ':' in content: return content.split(':', 1)
    return None, None

def get_file_port(glob_pattern, default=""):
    """Searches the system to locate 'webport' files and caches the result in RAM."""
    cache_key = f"port_{glob_pattern}"
    if RAM_CACHE.get(cache_key) is not None: 
        return RAM_CACHE[cache_key]
        
    try:
        files = glob.glob(glob_pattern)
        if files:
            with open(files[0], 'r') as f:
                val = f.read().strip()
                if val: 
                    RAM_CACHE[cache_key] = val
                    return val
    except Exception: pass
    return default

def get_current_port():
    """Reads the active webport file for this specific app and caches it in RAM."""
    if RAM_CACHE['current_port'] is not None: 
        return RAM_CACHE['current_port']
        
    try:
        if os.path.exists(port_file_path):
            with open(port_file_path, 'r') as f:
                p = f.read().strip()
                if p.isdigit(): 
                    RAM_CACHE['current_port'] = int(p)
                    return RAM_CACHE['current_port']
    except: pass
    return 8080

# ==============================================================================
# NETWORKMANAGER ALIAS HELPERS
# ==============================================================================
def get_nm_prop(con_name, *props):
    """Safely fetches NetworkManager properties by testing known OS aliases."""
    for p in props:
        val = subprocess.run(['nmcli', '-g', p, 'con', 'show', con_name], capture_output=True, text=True).stdout.strip()
        if val: return val
    return ""

def get_nm_sec_prop(con_name, *props):
    """Safely fetches NetworkManager secrets by testing known OS aliases with sudo."""
    for p in props:
        val = subprocess.run(['sudo', 'nmcli', '-s', '-g', p, 'con', 'show', con_name], capture_output=True, text=True).stdout.strip()
        if val: return val
    return ""

# ==============================================================================
# NETWORK FUNCTIONS
# ==============================================================================
def get_interfaces_info():
    """
    Uses nmcli to detect all active network interfaces and identifies if any are broadcasting an AP.
    Handles both legacy ('802-11-wireless') and modern ('wifi') NetworkManager interface types.
    """
    try:
        res = subprocess.run(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'dev'], capture_output=True, text=True)
        interfaces = []
        default_iface = None
        
        for line in res.stdout.splitlines():
            parts = line.split(':')
            # Look for both legacy '802-11-wireless' and modern 'wifi' types
            if len(parts) >= 4 and parts[1] in ['802-11-wireless', 'wifi']:
                dev, state, conn = parts[0], parts[2], parts[3]
                is_hotspot = False
                
                if state == 'connected' and conn:
                    # Check mode using inline fallbacks for different OS versions
                    mode = subprocess.run(['nmcli', '-g', '802-11-wireless.mode', 'con', 'show', conn], capture_output=True, text=True).stdout.strip()
                    if not mode: 
                        mode = subprocess.run(['nmcli', '-g', 'wifi.mode', 'con', 'show', conn], capture_output=True, text=True).stdout.strip()
                    
                    if mode == 'ap': 
                        is_hotspot = True
                        
                interfaces.append({'name': dev, 'is_hotspot': is_hotspot})
        
        # Determine default interface (first one not running a hotspot)
        for iface in interfaces:
            if not iface['is_hotspot']:
                default_iface = iface['name']
                break
        
        if not default_iface and interfaces: 
            default_iface = interfaces[0]['name']
            
        return {'interfaces': interfaces, 'default': default_iface}
    except Exception: 
        return {'interfaces': [], 'default': ''}

def get_hotspot_policy():
    """
    Reads the user's saved policy on whether the Hotspot should automatically persist on boot.
    If no policy file exists, it checks if a hotspot is currently running and saves that as the baseline.
    """
    if os.path.exists(hotspot_policy_file):
        with open(hotspot_policy_file, 'r') as f: 
            return f.read().strip() == 'true'
            
    # Fallback: create the policy file based on current live state
    info = get_interfaces_info()
    for iface in info['interfaces']:
        if iface['is_hotspot']:
            with open(hotspot_policy_file, 'w') as f: 
                f.write('true')
            return True
            
    return False

def set_hotspot_priority(priority):
    """
    Modifies NetworkManager profiles to apply the chosen hotspot autoconnect priority.
    Iterates over all connections, identifies the 'ap' (hotspot) profile via alias fallbacks, 
    and enforces the autoconnect priority rule.
    """
    res = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show'], capture_output=True, text=True)
    for line in res.stdout.splitlines():
        parts = line.rsplit(':', 1)
        if len(parts) == 2 and parts[1] in ['802-11-wireless', 'wifi']:
            name = parts[0]
            
            # Check mode using inline fallbacks for different OS versions
            mode = subprocess.run(['nmcli', '-g', '802-11-wireless.mode', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
            if not mode: 
                mode = subprocess.run(['nmcli', '-g', 'wifi.mode', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
            
            if mode == 'ap':
                subprocess.run(['nmcli', 'con', 'modify', name, 'connection.autoconnect', 'yes', 'connection.autoconnect-priority', str(priority)])

def get_hotspot_config():
    """
    Detects existing NetworkManager Hotspot profiles and safely extracts credentials.
    Uses inline alias fallbacks (e.g., 'wifi.ssid' vs '802-11-wireless.ssid') to ensure 
    bulletproof UI population across different Linux distributions and NetworkManager versions.
    """
    hs_name, hs_ssid, hs_psk, hs_active, hs_iface = "Hotspot", "", "", False, ""
    try:
        res = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show'], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            parts = line.rsplit(':', 1)
            if len(parts) == 2 and parts[1] in ['802-11-wireless', 'wifi']:
                name = parts[0]
                
                # Determine if this connection is an Access Point (Hotspot)
                mode = subprocess.run(['nmcli', '-g', '802-11-wireless.mode', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
                if not mode: 
                    mode = subprocess.run(['nmcli', '-g', 'wifi.mode', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
                
                if mode == 'ap':
                    hs_name = name
                    
                    # Extract SSID using alias fallbacks
                    hs_ssid = subprocess.run(['nmcli', '-g', '802-11-wireless.ssid', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
                    if not hs_ssid: 
                        hs_ssid = subprocess.run(['nmcli', '-g', 'wifi.ssid', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
                    
                    # Extract Password (PSK) using sudo and alias fallbacks
                    hs_psk = subprocess.run(['sudo', 'nmcli', '-s', '-g', 'wifi-sec.psk', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
                    if not hs_psk: 
                        hs_psk = subprocess.run(['sudo', 'nmcli', '-s', '-g', '802-11-wireless-security.psk', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
                    
                    # Extract bound interface using alias fallbacks
                    hs_iface = subprocess.run(['nmcli', '-g', 'connection.interface-name', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
                    if not hs_iface: 
                        hs_iface = subprocess.run(['nmcli', '-g', 'GENERAL.DEVICES', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
                    
                    # Check if the connection is currently active
                    active_res = subprocess.run(['nmcli', '-t', '-f', 'NAME', 'con', 'show', '--active'], capture_output=True, text=True)
                    hs_active = any(n == name for n in active_res.stdout.splitlines())
                    
                    break # Found the AP, stop looping
    except Exception: 
        pass
        
    return {'name': hs_name, 'ssid': hs_ssid, 'password': hs_psk, 'active': hs_active, 'iface': hs_iface}

# ==============================================================================
# FLASK MIDDLEWARE & CONTEXT
# ==============================================================================
@app.before_request
def check_auth():
    """Security Middleware: Blocks access to routes without a valid session."""
    if RAM_CACHE.get('auth_enabled') is None:
        RAM_CACHE['auth_enabled'] = os.path.exists(user_file)
        
    if RAM_CACHE['auth_enabled']:
        # Allow the 'index' route to pass through because it renders the login screen natively!
        if request.endpoint not in ['index', 'login', 'static'] and not session.get('logged_in'):
            # If an unauthenticated user tries to hit an API endpoint directly, redirect them to the index/login
            return redirect(url_for('index'))

@app.context_processor
def inject_global_vars():
    """Injects globally accessible state and version variables into all Jinja2 HTML templates."""
    local_wifi, local_oled = get_local_versions()
    return {
        'auth_enabled': os.path.exists(user_file),
        'oled_installed': get_oled_dir() is not None,
        'current_port': get_current_port(),
        'local_wifi_version': local_wifi,
        'local_oled_version': local_oled
    }

# ==============================================================================
# WEB APPLICATION ROUTES
# ==============================================================================
@app.route('/')
def index():
    """Renders the single page application. Serves the login screen if authentication is required."""
    # FIXED: Check the RAM cache instead of hitting the SD card
    needs_login = RAM_CACHE.get('auth_enabled') and not session.get('logged_in')
    
    # If the user needs to log in, render the page immediately to hide backend data
    if needs_login:
        return render_template('index.html', needs_login=True, login_error=session.pop('login_error', None))

    # User is fully authenticated, fetch the system data securely
    hs_config = get_hotspot_config()
    hs_policy = get_hotspot_policy()
    
    oled_dir = get_oled_dir()
    current_data = "{}"
    if oled_dir:
        settings_file = os.path.join(oled_dir, 'settings.json')
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r') as f:
                    content = f.read()
                    content = re.sub(r'^\s*//.*$', '', content, flags=re.MULTILINE)
                    current_data = json.dumps(json.loads(content))
            except Exception: pass
            
    return render_template('index.html', 
                           needs_login=False,
                           hotspot=hs_config, 
                           force_hotspot=hs_policy,
                           current_settings=current_data)

@app.route('/login', methods=['POST'])
def login():
    """Handles the actual form submission from the index page's login form."""
    user = request.form.get('username')
    pw = request.form.get('password')
    saved_user, saved_hash = get_credentials()
    
    if saved_user == user and saved_hash and check_password_hash(saved_hash, pw):
        session.permanent = True
        session['logged_in'] = True
    else:
        session['login_error'] = "Invalid credentials"
        
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    """Destroys the current user session and redirects back to the SPA index."""
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/settings', methods=['POST'])
def settings():
    """Handles Web Application settings (Auth credentials and Port bindings) via form submission."""
    new_user = request.form.get('username')
    new_pw = request.form.get('password')
    if new_user and new_pw:
        hashed = generate_password_hash(new_pw)
        with open(user_file, 'w') as f: f.write(f"{new_user}:{hashed}")
        
        RAM_CACHE['auth_enabled'] = True # Update RAM immediately
        session.permanent = True
        session['logged_in'] = True
        
    new_port_str = request.form.get('port')
    port_changed_to = None
    if new_port_str and new_port_str.isdigit():
        new_port = int(new_port_str)
        current_port = get_current_port()
        if new_port != current_port:
            with open(port_file_path + '.bak', 'w') as f: f.write(str(current_port))
            with open(port_file_path, 'w') as f: f.write(str(new_port))
            subprocess.Popen(['/bin/sh', '-c', 'sleep 1.5 && systemctl restart pi-wifi-app.service'])
            port_changed_to = new_port
            
    if port_changed_to:
        return f"""
        <html>
        <body style='font-family:sans-serif; text-align:center; margin-top:50px; background:#121212; color:white;'>
            <h2>Changing Port to {port_changed_to}...</h2>
            <p>Please wait while the service restarts. You will be redirected automatically.</p>
            <script>setTimeout(() => {{ window.location.href = window.location.protocol + '//' + window.location.hostname + ':{port_changed_to}/'; }}, 3500);</script>
        </body>
        </html>
        """
        
    return redirect(url_for('index'))

@app.route('/hotspot', methods=['POST'])
def hotspot_page():
    """Handles configuring, enabling/disabling, and prioritizing the Wi-Fi Hotspot via form submission."""
    action = request.form.get('action')
    force_hs = request.form.get('force_hotspot') == 'on'
    device = request.form.get('device')
    
    with open(hotspot_policy_file, 'w') as f: f.write('true' if force_hs else 'false')
    set_hotspot_priority(100 if force_hs else 0)
    
    hs_info = get_hotspot_config()
    profile_name = hs_info['name']
    new_ssid = request.form.get('ssid')
    
    if action == 'save_and_toggle':
        new_pass = request.form.get('password')
        enable_hs = request.form.get('enable_hotspot') == 'on'
        
        # 1. MIRROR BASH SCRIPT: Delete existing profile to ensure a perfectly clean slate
        subprocess.run(['sudo', 'nmcli', 'connection', 'delete', profile_name], capture_output=True)
        
        # 2. MIRROR BASH SCRIPT: Add new connection
        if not device: device = 'wlan0'
        subprocess.run(['sudo', 'nmcli', 'con', 'add', 'type', 'wifi', 'ifname', device, 'con-name', profile_name, 'autoconnect', 'yes' if force_hs else 'no', 'ssid', new_ssid])
        
        # 3. MIRROR BASH SCRIPT: Enforce AP mode, band, and DHCP shared method
        subprocess.run(['sudo', 'nmcli', 'con', 'modify', profile_name, '802-11-wireless.mode', 'ap', '802-11-wireless.band', 'bg', 'ipv4.method', 'shared'])
        
        # 4. MIRROR BASH SCRIPT: Enforce Security
        if new_pass and len(new_pass) >= 8: 
            subprocess.run(['sudo', 'nmcli', 'con', 'modify', profile_name, 'wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.psk', new_pass])
        
        # Use Popen with a 1.5 second sleep so Flask can instantly return the JSON 
        # success message to Javascript BEFORE the radio restarts and drops the connection!
        if enable_hs: 
            subprocess.Popen(['/bin/sh', '-c', f'sleep 1.5 && sudo nmcli con up "{profile_name}"'])
        else: 
            subprocess.Popen(['/bin/sh', '-c', f'sleep 1.5 && sudo nmcli con down "{profile_name}"'])
                    
    # Return a clean JSON response instead of a separate HTML page redirect
    return jsonify({"status": "success", "message": "Hotspot settings saved. Adapter is restarting momentarily."})

@app.route('/oled')
def oled_page():
    """Safely redirects legacy OLED UI requests back to the SPA index."""
    return redirect(url_for('index'))

@app.route('/api/update/check', methods=['GET'])
def update_check():
    """
    API Endpoint: Gathers local versioning info, requests the latest target versions 
    from GitHub, downloads the changelog markdown files, parses them, and returns 
    a comprehensive JSON payload for the frontend UI to display.
    """
    local_wifi, local_oled = get_local_versions()
    target_wifi, target_oled = "Unknown", "Unknown"
    wifi_changelog, oled_changelog = [], []
    
    # 1. Fetch Target Versions from individual version.json files
    try:
        req = urllib.request.Request(f"{REPO_BASE}/pi-wifi-app/version.json", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            target_wifi = json.loads(response.read().decode('utf-8')).get("version", "Unknown")
    except Exception: pass

    try:
        req = urllib.request.Request(f"{REPO_BASE}/oled_monitor/version.json", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            target_oled = json.loads(response.read().decode('utf-8')).get("version", "Unknown")
    except Exception: pass

    # If both fail, we likely have no internet connection
    if target_wifi == "Unknown" and target_oled == "Unknown":
        return jsonify({"status": "error", "message": "Unable to connect to GitHub. Please verify your internet connection."})

    # 2. Fetch & Parse WiFi Changelog
    try:
        req = urllib.request.Request(f"{REPO_BASE}/pi-wifi-app/changelog.md", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            wifi_changelog = parse_changelog(response.read().decode('utf-8'))
    except Exception as e:
        # Gracefully handle missing/404 changelog file by injecting an error structure
        wifi_changelog = [{
            "version": "Error",
            "title": "Changelog Unavailable",
            "sections": [{
                "subtitle": "Could not load data",
                "bullets": [{"type": "text", "content": "The changelog file could not be retrieved from GitHub."}]
            }]
        }]

    # 3. Fetch & Parse OLED Changelog
    try:
        req = urllib.request.Request(f"{REPO_BASE}/oled_monitor/changelog.md", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            oled_changelog = parse_changelog(response.read().decode('utf-8'))
    except Exception as e:
        # Gracefully handle missing/404 changelog file by injecting an error structure
        oled_changelog = [{
            "version": "Error",
            "title": "Changelog Unavailable",
            "sections": [{
                "subtitle": "Could not load data",
                "bullets": [{"type": "text", "content": "The changelog file could not be retrieved from GitHub."}]
            }]
        }]

    # Compare versions to determine update availability
    wifi_update_avail = (local_wifi != target_wifi and target_wifi != "Unknown")
    oled_update_avail = (local_oled != "Not Installed" and local_oled != target_oled and target_oled != "Unknown")

    return jsonify({
        "status": "success",
        "wifi": {
            "local_version": local_wifi,
            "target_version": target_wifi,
            "update_available": wifi_update_avail,
            "changelog": wifi_changelog
        },
        "oled": {
            "installed": local_oled != "Not Installed",
            "local_version": local_oled,
            "target_version": target_oled,
            "update_available": oled_update_avail,
            "changelog": oled_changelog
        }
    })

@app.route('/api/update/run', methods=['POST'])
def update_run():
    """
    API Endpoint: Executes the over-the-air update by downloading fresh files 
    directly from GitHub and replacing the local installations.
    Accounts for the new Single Page Application structure by leveraging CORE_FILES.
    """
    data = request.json
    components = data.get('components', [])
    
    if not components:
        return jsonify({"status": "error", "message": "No components selected for update."})
        
    # --- Update OLED Monitor ---
    if "oled" in components:
        oled_dir = get_oled_dir()
        if oled_dir:
            files = [('monitor.py', 'monitor.py'), ('version.json', 'version.json')]
            for src, dest in files:
                success = download_file(f"{REPO_BASE}/oled_monitor/{src}", os.path.join(oled_dir, dest))
                if not success:
                    return jsonify({"status": "error", "message": f"Failed to download OLED file: {src}"})
            # Restart OLED immediately (it runs in background, won't break web server)
            subprocess.run(['systemctl', 'restart', 'oled_monitor.service'])
            
    # --- Update WiFi Configurator ---
    if "wifi" in components:
        # Dynamically map the CORE_FILES array to prevent missing components
        for file_path in CORE_FILES:
            success = download_file(f"{REPO_BASE}/pi-wifi-app/{file_path}", os.path.join(script_dir, file_path))
            if not success:
                return jsonify({"status": "error", "message": f"Failed to download WiFi file: {file_path}"})
                
        # Schedule the web app service to restart after 2 seconds, 
        # allowing Flask to safely return the success response below first.
        subprocess.Popen(['/bin/sh', '-c', 'sleep 2 && systemctl restart pi-wifi-app.service'])

    return jsonify({"status": "success", "message": "Update completed successfully. Services are restarting."})


# ==============================================================================
# SYSTEM & OLED API ROUTES
# ==============================================================================
@app.route('/api/system/status', methods=['GET'])
def system_status():
    """
    Returns a full JSON payload of current system variables for the OLED preview.
    Fetches real-time temperature, hotspot data, network interfaces, and ports.
    """
    now = datetime.datetime.now()
    
    temp = 0.0
    try:
        out = subprocess.check_output(['vcgencmd', 'measure_temp'], stderr=subprocess.DEVNULL).decode('utf-8')
        temp = float(out.replace('temp=', '').replace('\'C\n', ''))
    except Exception: pass

    hs_active = False
    ap_ssid, ap_psk, ap_iface, wifi_ssid = "", "", None, ""
    try:
        active_conns = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show', '--active'], capture_output=True, text=True).stdout.splitlines()
        for conn in active_conns:
            parts = conn.rsplit(':', 1)
            if len(parts) == 2 and parts[1] in ['802-11-wireless', 'wifi']:
                name = parts[0]
                mode = subprocess.run(['nmcli', '-g', '802-11-wireless.mode', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
                if not mode: mode = subprocess.run(['nmcli', '-g', 'wifi.mode', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
                
                if mode == 'ap':
                    hs_active = True
                    ap_ssid = subprocess.run(['nmcli', '-g', '802-11-wireless.ssid', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
                    if not ap_ssid: ap_ssid = subprocess.run(['nmcli', '-g', 'wifi.ssid', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
                    
                    ap_psk = subprocess.run(['sudo', 'nmcli', '-s', '-g', 'wifi-sec.psk', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
                    if not ap_psk: ap_psk = subprocess.run(['sudo', 'nmcli', '-s', '-g', '802-11-wireless-security.psk', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
                    
                    ap_iface = subprocess.run(['nmcli', '-g', 'GENERAL.DEVICES', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
                    if not ap_iface: ap_iface = subprocess.run(['nmcli', '-g', 'connection.interface-name', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
                elif mode == 'infrastructure':
                    wifi_ssid = subprocess.run(['nmcli', '-g', '802-11-wireless.ssid', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
                    if not wifi_ssid: wifi_ssid = subprocess.run(['nmcli', '-g', 'wifi.ssid', 'connection', 'show', name], capture_output=True, text=True).stdout.strip()
    except Exception: pass

    networks = []
    ap_ip = "10.42.0.1"
    try:
        out = subprocess.check_output(['ip', '-o', '-4', 'addr', 'show'], stderr=subprocess.DEVNULL).decode('utf-8')
        for line in out.split('\n'):
            if line.strip():
                parts = line.split()
                iface = parts[1]
                ip = parts[3].split('/')[0]
                if iface != "lo" and not iface.startswith("docker") and not iface.startswith("veth"):
                    networks.append({'iface': iface, 'ip': ip})
                    if iface == ap_iface: ap_ip = ip
    except Exception: pass

    wifi_port = str(get_current_port())
    diag_port = str(get_file_port('/home/*/Network-Testing-Tools/webport', default=""))

    return jsonify({
        'time': now.strftime("%H:%M:%S"), 'hour': now.strftime("%H"),
        'minute': now.strftime("%M"), 'second': now.strftime("%S"),
        'date': now.strftime("%Y-%m-%d"), 'day': now.strftime("%d"),
        'month': now.strftime("%m"), 'year': now.strftime("%Y"),
        'temp': temp, 'ap_ssid': ap_ssid if hs_active else "",
        'ap_pw': ap_psk if hs_active else "", 'ap_ip': ap_ip,
        'networks': networks,
        'wifi_ssid': wifi_ssid if wifi_ssid else "Not Connected",
        'wifi_port': wifi_port, 'diag_port': diag_port,
        'web_port': wifi_port, 'hotspot_active': hs_active
    })

@app.route('/api/oled/save', methods=['POST'])
def oled_save():
    """
    API Endpoint: Receives JSON data from the UI, validates the format, 
    overwrites settings.json, and restarts the backend OLED service.
    """
    oled_dir = get_oled_dir()
    if not oled_dir: return jsonify({"status":"error", "message":"OLED not installed"})
    
    data = request.json
    if not isinstance(data, dict) or 'pages' not in data:
        return jsonify({"status":"error", "message":"Invalid format"})
        
    settings_file = os.path.join(oled_dir, 'settings.json')
    try:
        with open(settings_file, 'w') as f: json.dump(data, f, indent=4)
        subprocess.run(['systemctl', 'restart', 'oled_monitor.service'])
        return jsonify({"status":"success", "message":"Settings Saved & Service Restarted"})
    except Exception as e: return jsonify({"status":"error", "message":str(e)})

@app.route('/api/oled/reset', methods=['POST'])
def oled_reset():
    """
    API Endpoint: Triggers a factory reset of the OLED settings by creating 
    a physical 'reset' file which the OLED script detects on restart.
    """
    oled_dir = get_oled_dir()
    if not oled_dir: return jsonify({"status":"error", "message":"OLED not installed"})
    try:
        open(os.path.join(oled_dir, 'reset'), 'w').close()
        subprocess.run(['systemctl', 'restart', 'oled_monitor.service'])
        return jsonify({"status":"success", "message":"Settings Reset to Defaults"})
    except Exception as e: return jsonify({"status":"error", "message":str(e)})

# ==============================================================================
# WIFI API ROUTES
# ==============================================================================
@app.route('/interfaces', methods=['GET'])
def interfaces():
    """API Endpoint: Returns JSON metadata about available network interfaces."""
    return jsonify(get_interfaces_info())

@app.route('/scan', methods=['GET'])
def scan():
    """
    API Endpoint: Executes an nmcli WiFi scan on the requested network adapter.
    Filters out the active Hotspot SSID to prevent self-connection loops.
    """
    try:
        device = request.args.get('device')
        
        # 1. Fetch current hotspot config to find the SSID we need to hide
        hs_config = get_hotspot_config()
        ignore_ssid = hs_config.get('ssid') if hs_config.get('active') else None
        
        # 2. Execute the scan (We must explicitly use 'list' before 'ifname' for nmcli)
        cmd = ['nmcli', '-t', '-f', 'SSID,SIGNAL', 'dev', 'wifi', 'list']
        if device: cmd.extend(['ifname', device])
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        networks = []
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            seen = set()
            for line in lines:
                if ':' in line:
                    ssid, signal = line.split(':', 1)
                    
                    # 3. Filter out empty SSIDs, duplicates, AND the active hotspot itself!
                    if ssid and ssid not in seen and ssid != ignore_ssid:
                        seen.add(ssid)
                        networks.append({'ssid': ssid, 'signal': signal})
                        
            return jsonify({'networks': networks, 'status': 'success'})
        else:
            error_msg = result.stderr.strip()
            if not error_msg: error_msg = "Scan failed. Hardware may be busy."
            return jsonify({'status': 'error', 'message': error_msg})
            
    except Exception as e: 
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/connect', methods=['POST'])
def connect():
    """
    API Endpoint: Executes nmcli to connect to a specific SSID. 
    Applies user-selected autoconnect policies after a successful connection.
    If the connection fails, gracefully restores the Hotspot if it was previously active.
    """
    data = request.json
    ssid = data.get('ssid')
    password = data.get('password', '')
    autoconnect = data.get('autoconnect', True)
    device = data.get('device')

    if not ssid: return jsonify({'status': 'error', 'message': 'SSID is required'})
    try:
        # 1. Capture current hotspot state before attempting the new connection
        hs_config = get_hotspot_config()
        hs_was_active = hs_config.get('active', False)
        hs_name = hs_config.get('name', 'Hotspot')

        # 2. Attempt the Wi-Fi connection
        cmd = ['nmcli', 'dev', 'wifi', 'connect', ssid]
        if password: cmd.extend(['password', password])
        if device: cmd.extend(['ifname', device])
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 3. Handle Success
        if result.returncode == 0:
            ac_val = 'yes' if autoconnect else 'no'
            subprocess.run(['nmcli', 'con', 'modify', ssid, 'connection.autoconnect', ac_val, 'connection.autoconnect-priority', '0'])
            if get_hotspot_policy(): set_hotspot_priority(100)
            return jsonify({'status': 'success', 'message': f'Successfully connected to {ssid}.'})
            
        # 4. Handle Failure & Restore Hotspot
        else:
            error_msg = result.stderr.strip()
            
            if hs_was_active and hs_name:
                # Bring the hotspot back online since the new Wi-Fi failed
                subprocess.run(['sudo', 'nmcli', 'con', 'up', hs_name], capture_output=True)
                error_msg += " (Restored previous Hotspot connection)."
                
            return jsonify({'status': 'error', 'message': error_msg})
            
    except Exception as e: 
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/disconnect', methods=['POST'])
def disconnect():
    """API Endpoint: Gracefully disconnects the specified network adapter from its current connection."""
    try:
        device = request.json.get('device', 'wlan0')
        result = subprocess.run(['nmcli', 'dev', 'disconnect', device], capture_output=True, text=True)
        if result.returncode == 0: return jsonify({'status': 'success', 'message': f'Disconnected from {device}.'})
        else: return jsonify({'status': 'error', 'message': result.stderr.strip()})
    except Exception as e: return jsonify({'status': 'error', 'message': str(e)})

def can_bind_port(check_port):
    """Safely checks if a requested network port is available for binding by the Flask application."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('0.0.0.0', check_port))
        s.close()
        return True
    except: return False

# ==============================================================================
# MAIN EXECUTION & PORT BINDING
# ==============================================================================
if __name__ == '__main__':
    port = get_current_port()
    bak_port = 8080
    
    # Read Backup port in case of binding conflicts
    try:
        if os.path.exists(port_file_path + '.bak'):
            with open(port_file_path + '.bak', 'r') as f:
                p = f.read().strip()
                if p.isdigit(): bak_port = int(p)
    except: pass

    # Smart Port Fallback Mechanism
    # Prevents the web server from crashing and locking out the user if they assign an invalid port.
    if not can_bind_port(port):
        print(f"Port {port} is in use or unavailable. Falling back to {bak_port}...")
        port = bak_port
        if not can_bind_port(port):
            print(f"Fallback port {port} is ALSO unavailable. Falling back to 8080...")
            port = 8080
            
        try:
            with open(port_file_path, 'w') as f: f.write(str(port))
        except: pass

    print(f"Starting web server on port {port}...")
    app.run(host='0.0.0.0', port=port)