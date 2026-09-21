from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import subprocess
import os
import re
import json
import glob
import socket
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(days=365)

script_dir = os.path.dirname(os.path.abspath(__file__))
user_file = os.path.join(script_dir, 'user')
reset_file = os.path.join(script_dir, 'reset')
port_file_path = os.path.join(script_dir, 'webport')
hotspot_policy_file = os.path.join(script_dir, 'hotspot_policy')

def get_oled_dir():
    """Detects if the OLED Monitor script is installed by locating its directory."""
    for d in glob.glob('/home/*/oled_monitor'):
        if os.path.isdir(d): return d
    if os.path.isdir('/root/oled_monitor'): return '/root/oled_monitor'
    return None

# ==========================================
# STARTUP RESET LOGIC
# ==========================================
if os.path.exists(reset_file):
    try:
        if os.path.exists(user_file): os.remove(user_file)
        os.remove(reset_file)
        print("Startup: Reset file detected. Authentication has been removed.")
    except Exception as e:
        print(f"Startup: Error resetting user: {e}")

def get_credentials():
    """Retrieves the currently saved username and hashed password from the user file."""
    if os.path.exists(user_file):
        with open(user_file, 'r') as f:
            content = f.read().strip()
            if ':' in content: return content.split(':', 1)
    return None, None

def get_current_port():
    """Reads the active webport file to determine which port the app should bind to."""
    try:
        if os.path.exists(port_file_path):
            with open(port_file_path, 'r') as f:
                p = f.read().strip()
                if p.isdigit(): return int(p)
    except: pass
    return 8080

def get_interfaces_info():
    """
    Uses nmcli to detect all active network interfaces and identifies if any 
    of them are currently broadcasting a Hotspot (Access Point mode).
    Returns a list of interfaces and a safe default interface.
    """
    try:
        res = subprocess.run(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'dev'], capture_output=True, text=True)
        interfaces = []
        default_iface = None
        for line in res.stdout.splitlines():
            if ':wifi:' in line:
                parts = line.split(':')
                dev, state = parts[0], parts[2]
                conn = parts[3] if len(parts) > 3 else ''
                is_hotspot = False
                if state == 'connected' and conn:
                    mode_res = subprocess.run(['nmcli', '-g', '802-11-wireless.mode', 'con', 'show', conn], capture_output=True, text=True)
                    if mode_res.stdout.strip() == 'ap': is_hotspot = True
                interfaces.append({'name': dev, 'is_hotspot': is_hotspot})
        
        for iface in interfaces:
            if not iface['is_hotspot']:
                default_iface = iface['name']
                break
        
        if not default_iface and interfaces: default_iface = interfaces[0]['name']
        return {'interfaces': interfaces, 'default': default_iface}
    except Exception:
        return {'interfaces': [], 'default': ''}

def get_hotspot_policy():
    """Reads the user's saved policy on whether Hotspots should persist on boot with high priority."""
    if os.path.exists(hotspot_policy_file):
        with open(hotspot_policy_file, 'r') as f: return f.read().strip() == 'true'
    info = get_interfaces_info()
    for iface in info['interfaces']:
        if iface['is_hotspot']:
            with open(hotspot_policy_file, 'w') as f: f.write('true')
            return True
    return False

def set_hotspot_priority(priority):
    """Modifies NetworkManager profiles to apply the chosen hotspot autoconnect priority."""
    res = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show'], capture_output=True, text=True)
    for line in res.stdout.splitlines():
        if '802-11-wireless' in line:
            name = line.split(':')[0]
            mode_res = subprocess.run(['nmcli', '-g', '802-11-wireless.mode', 'con', 'show', name], capture_output=True, text=True)
            if mode_res.strip() == 'ap' or (mode_res.returncode == 0 and mode_res.stdout.strip() == 'ap'):
                subprocess.run(['nmcli', 'con', 'modify', name, 'connection.autoconnect', 'yes', 'connection.autoconnect-priority', str(priority)])

def get_hotspot_config():
    """Detects existing NetworkManager Hotspot connection profile name, SSID, and Password."""
    hs_name, hs_ssid, hs_psk, hs_active = "Hotspot", "", "", False
    try:
        res = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show'], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if '802-11-wireless' in line:
                name = line.split(':')[0]
                mode_res = subprocess.run(['nmcli', '-g', '802-11-wireless.mode', 'con', 'show', name], capture_output=True, text=True)
                if mode_res.stdout.strip() == 'ap':
                    hs_name = name
                    hs_ssid = subprocess.run(['nmcli', '-g', '802-11-wireless.ssid', 'con', 'show', name], capture_output=True, text=True).stdout.strip()
                    psk_res = subprocess.run(['sudo', 'nmcli', '--show-secrets', '-g', '802-11-wireless-security.psk', 'con', 'show', name], capture_output=True, text=True)
                    hs_psk = psk_res.stdout.strip()
                    active_res = subprocess.run(['nmcli', '-t', '-f', 'NAME', 'con', 'show', '--active'], capture_output=True, text=True)
                    if hs_name in active_res.stdout:
                        hs_active = True
                    break
    except Exception:
        pass
    return {'name': hs_name, 'ssid': hs_ssid, 'password': hs_psk, 'active': hs_active}

@app.before_request
def check_auth():
    """Middleware: Validates login status before allowing access to private application routes."""
    if os.path.exists(user_file):
        if request.endpoint not in ['login', 'static'] and not session.get('logged_in'):
            return redirect(url_for('login'))

@app.context_processor
def inject_global_vars():
    """Injects globally accessible state variables into all Jinja2 templates."""
    return {
        'auth_enabled': os.path.exists(user_file),
        'oled_installed': get_oled_dir() is not None,
        'current_port': get_current_port()
    }

@app.route('/')
def index():
    """Renders the main WiFi Configuration dashboard."""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user authentication. Validates credentials and sets the permanent secure session cookie."""
    if request.method == 'POST':
        user = request.form.get('username')
        pw = request.form.get('password')
        saved_user, saved_hash = get_credentials()
        if saved_user == user and saved_hash and check_password_hash(saved_hash, pw):
            session.permanent = True
            session['logged_in'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Destroys the current user session and redirects to the login screen."""
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Handles Web Application settings (Auth credentials and Port bindings)."""
    if request.method == 'POST':
        new_user = request.form.get('username')
        new_pw = request.form.get('password')
        if new_user and new_pw:
            hashed = generate_password_hash(new_pw)
            with open(user_file, 'w') as f: f.write(f"{new_user}:{hashed}")
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
                <script>
                    setTimeout(() => {{
                        window.location.href = window.location.protocol + '//' + window.location.hostname + ':{port_changed_to}/';
                    }}, 3500);
                </script>
            </body>
            </html>
            """
            
        return redirect(url_for('index'))
    return render_template('settings.html', current_user=get_credentials()[0])

@app.route('/hotspot', methods=['GET', 'POST'])
def hotspot_page():
    """Handles configuring, enabling/disabling, and prioritizing the Wi-Fi Hotspot."""
    if request.method == 'POST':
        action = request.form.get('action')
        force_hs = request.form.get('force_hotspot') == 'on'
        
        with open(hotspot_policy_file, 'w') as f:
            f.write('true' if force_hs else 'false')
        set_hotspot_priority(100 if force_hs else 0)
        
        hs_info = get_hotspot_config()
        profile_name = hs_info['name']
        
        if action == 'save_and_toggle':
            new_ssid = request.form.get('ssid')
            new_pass = request.form.get('password')
            enable_hs = request.form.get('enable_hotspot') == 'on'
            
            if new_ssid:
                subprocess.run(['sudo', 'nmcli', 'con', 'modify', profile_name, '802-11-wireless.ssid', new_ssid])
            if new_pass and len(new_pass) >= 8:
                subprocess.run(['sudo', 'nmcli', 'con', 'modify', profile_name, '802-11-wireless-security.key-mgmt', 'wpa-psk', '802-11-wireless-security.psk', new_pass])
                
            if enable_hs: subprocess.run(['sudo', 'nmcli', 'con', 'up', profile_name])
            else: subprocess.run(['sudo', 'nmcli', 'con', 'down', profile_name])
                
        return redirect(url_for('hotspot_page'))
        
    hs_data = get_hotspot_config()
    force_hotspot = get_hotspot_policy()
    return render_template('hotspot.html', hotspot=hs_data, force_hotspot=force_hotspot)

@app.route('/api/system/temp', methods=['GET'])
def system_temp():
    """Returns the current internal hardware CPU temperature of the Raspberry Pi."""
    try:
        out = subprocess.check_output(['vcgencmd', 'measure_temp'], stderr=subprocess.DEVNULL).decode('utf-8')
        temp = float(out.replace('temp=', '').replace('\'C\n', ''))
        return jsonify({'temp': temp})
    except Exception:
        return jsonify({'temp': 0.0})

@app.route('/oled')
def oled_page():
    """Renders the OLED Configuration UI, dynamically loading settings.json from the oled_monitor directory."""
    oled_dir = get_oled_dir()
    if not oled_dir: return "OLED Monitor is not installed on this system.", 404
    
    settings_file = os.path.join(oled_dir, 'settings.json')
    current_data = "{}"
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r') as f:
                content = f.read()
                content = re.sub(r'^\s*//.*$', '', content, flags=re.MULTILINE)
                loaded = json.loads(content)
                current_data = json.dumps(loaded)
        except Exception:
            current_data = "{}"
            
    return render_template('oled.html', current_settings=current_data)

@app.route('/api/oled/save', methods=['POST'])
def oled_save():
    """API Endpoint: Receives JSON data from the UI, validates it, overwrites settings.json, and restarts the OLED service."""
    oled_dir = get_oled_dir()
    if not oled_dir: return jsonify({"status":"error", "message":"OLED not installed"})
    
    data = request.json
    if not isinstance(data, dict) or 'pages' not in data:
        return jsonify({"status":"error", "message":"Invalid format"})
        
    settings_file = os.path.join(oled_dir, 'settings.json')
    try:
        with open(settings_file, 'w') as f:
            json.dump(data, f, indent=4)
        subprocess.run(['systemctl', 'restart', 'oled_monitor.service'])
        return jsonify({"status":"success", "message":"Settings Saved & Service Restarted"})
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)})

@app.route('/api/oled/reset', methods=['POST'])
def oled_reset():
    """API Endpoint: Triggers a factory reset of the OLED settings by creating a physical 'reset' file."""
    oled_dir = get_oled_dir()
    if not oled_dir: return jsonify({"status":"error", "message":"OLED not installed"})
    try:
        open(os.path.join(oled_dir, 'reset'), 'w').close()
        subprocess.run(['systemctl', 'restart', 'oled_monitor.service'])
        return jsonify({"status":"success", "message":"Settings Reset to Defaults"})
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)})

@app.route('/interfaces', methods=['GET'])
def interfaces():
    """API Endpoint: Returns JSON metadata about available network interfaces."""
    return jsonify(get_interfaces_info())

@app.route('/scan', methods=['GET'])
def scan():
    """API Endpoint: Executes an nmcli WiFi scan on the requested network adapter and returns a list of SSIDs."""
    try:
        device = request.args.get('device')
        cmd = ['nmcli', '-t', '-f', 'SSID,SIGNAL', 'dev', 'wifi']
        if device: cmd.extend(['ifname', device])
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        networks = []
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            seen = set()
            for line in lines:
                if ':' in line:
                    ssid, signal = line.split(':', 1)
                    if ssid and ssid not in seen:
                        seen.add(ssid)
                        networks.append({'ssid': ssid, 'signal': signal})
        return jsonify({'networks': networks, 'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/connect', methods=['POST'])
def connect():
    """API Endpoint: Executes nmcli to connect to a specific SSID. Applies autoconnect policies after success."""
    data = request.json
    ssid = data.get('ssid')
    password = data.get('password', '')
    autoconnect = data.get('autoconnect', True)
    device = data.get('device')

    if not ssid: return jsonify({'status': 'error', 'message': 'SSID is required'})
    try:
        cmd = ['nmcli', 'dev', 'wifi', 'connect', ssid]
        if password: cmd.extend(['password', password])
        if device: cmd.extend(['ifname', device])
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            ac_val = 'yes' if autoconnect else 'no'
            subprocess.run(['nmcli', 'con', 'modify', ssid, 'connection.autoconnect', ac_val, 'connection.autoconnect-priority', '0'])
            if get_hotspot_policy(): set_hotspot_priority(100)
            return jsonify({'status': 'success', 'message': f'Successfully connected to {ssid}.'})
        else:
            return jsonify({'status': 'error', 'message': result.stderr.strip()})
    except Exception as e: return jsonify({'status': 'error', 'message': str(e)})

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
    """Safely checks if a requested port is available for binding by the Flask application."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('0.0.0.0', check_port))
        s.close()
        return True
    except:
        return False

if __name__ == '__main__':
    port = get_current_port()
    bak_port = 8080
    
    try:
        if os.path.exists(port_file_path + '.bak'):
            with open(port_file_path + '.bak', 'r') as f:
                p = f.read().strip()
                if p.isdigit(): bak_port = int(p)
    except: pass

    if not can_bind_port(port):
        print(f"Port {port} is in use or unavailable. Falling back to {bak_port}...")
        port = bak_port
        if not can_bind_port(port):
            print(f"Fallback port {port} is ALSO unavailable. Falling back to 8080...")
            port = 8080
            
        try:
            with open(port_file_path, 'w') as f:
                f.write(str(port))
        except: pass

    print(f"Starting web server on port {port}...")
    app.run(host='0.0.0.0', port=port)