import time
import datetime
import subprocess
import board
import busio
import glob
import json
import os
import re
import sys
import smbus
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306

# ==============================================================================
# DEFAULT CONFIGURATION
# ==============================================================================
DEFAULT_JSON = """{
    // =====================================================================
    // OLED MONITOR SETTINGS
    // =====================================================================
    // Welcome to the configuration file! You can edit these values to change
    // how the OLED screen behaves. 
    // 
    // NOTE: This file is only read when the background service starts.
    // If you edit this file, you MUST restart the service for changes to apply:
    // sudo systemctl restart oled_monitor.service
    // 
    // IF YOU BREAK THIS FILE: Just run this command in your terminal to 
    // restore the default settings: touch ~/oled_monitor/reset
    // =====================================================================
    
    // --- Feature Toggles ---
    // Enable or disable the OLED screen (true/false)
    "enable_screen": true,
    // Enable or disable the PoE Fan automatic control (true/false)
    "enable_fan": true,
    
    // --- Hardware & Warning Settings ---
    // Brightness of the OLED screen (0 to 255, where 255 is maximum brightness)
    "brightness": 255,
    
    // Temperature (in Celsius) at which the PoE HAT fan turns ON
    "fan_on_temp": 55.0,
    // Temperature at which the fan turns OFF
    "fan_off_temp": 45.0,
    
    // Show flashing "HOT!" and "VOLT DROP!" screens if there is an issue?
    "show_warnings": true,
    // Temperature that triggers the HOT! warning screen
    "warning_temp": 75.0,
    
    // --- Extra Screen & Fan Features ---
    // Rotate the screen upside down (180 degrees)?
    "rotate_180": false,
    // Invert colors? (White background, black text)
    "invert_colors": false,
    
    // Shift the screen content 1 pixel every hour to prevent OLED burn-in?
    "pixel_shift_screensaver": true,
    
    // Minimum time (in seconds) the fan must stay on once triggered (Anti-Flutter)
    "minimum_fan_run_time_seconds": 60,
    
    // --- Quiet Hours / Night Mode ---
    // Turns off screen and relies on passive cooling during these hours
    "quiet_hours_enabled": false,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    
    // --- Global Display & Timing Settings ---
    // Default time each page is shown (in seconds) if not specified per-page
    "page_duration_seconds": 20,
    
    // How often to check for hardware changes like CPU Temp (in seconds)
    "hardware_update_interval_seconds": 5,
    // How often to scan for new IP addresses and Wifi changes (in seconds)
    "network_update_interval_seconds": 20,
    
    // =====================================================================
    // Pages Configuration
    // =====================================================================
    // This is the list of screens to show. 
    // Set "duration": 0 on any page to completely hide/disable it.
    "pages": [
        {
            "type": "network_list",
            // Set to true to append the Hotspot IP to the bottom of the list 
            // ONLY when a device is actively connected to the hotspot.
            "show_ap_ip_when_connected": true,
            
            // --- Port Display Settings ---
            "show_diagnostic_port": true,
            "show_wifi_port": true,
            "custom_port": "", // E.g., "9000", or leave blank for none
            
            "duration": 20,
            "align": "left",
            "scroll_vertical": true,
            "scroll_horizontal": true
        },
        {
            "type": "hotspot_details",
            // Set to true to automatically hide the Hotspot SSID/Password 
            // page when a device successfully connects.
            "hide_when_connected": true,
            
            // --- Port Display Settings ---
            "show_diagnostic_port": true,
            "show_wifi_port": true,
            "custom_port": "",
            
            "duration": 20,
            "align": "left",
            "scroll_vertical": true,
            "scroll_horizontal": true
        },
        {
            // ==========================================
            // EXAMPLE CUSTOM PAGE (Disabled by default)
            // ==========================================
            // Change "duration" to 20 to enable this page!
            "type": "custom",
            "duration": 0, 
            
            "show_diagnostic_port": true,
            "show_wifi_port": true,
            "custom_port": "",
            
            // Text alignment: "left" (default), "center", or "right"
            "align": "center",
            // Scrolling: set to false to lock text in place
            "scroll_vertical": true,
            "scroll_horizontal": true,
            
            // DYNAMIC VARIABLES FOR CUSTOM PAGES:
            // {time}      - 14:30:00        {hour}       - 14
            // {minute}    - 30              {second}     - 00
            // {date}      - 2026-09-20      {day}        - 20
            // {month}     - 09              {year}       - 2026
            // {temp}      - 48.5            {ap_ip}      - 10.42.0.1
            // {ap_ssid}   - Your_Hotspot    {ap_pw}      - Password123
            // {wifi_ssid} - Connected_Wifi  {web_port}   - 80/8080
            "lines": [
                "Time: {time}",
                "Date: {date}",
                "WiFi: {wifi_ssid}",
                "CPU Temp: {temp}C"
            ]
        }
    ]
}"""

# ==============================================================================
# CORE FUNCTIONS
# ==============================================================================

def load_settings():
    """
    Loads configuration from 'settings.json'. 
    If the file is missing, or a 'reset' file is found in the directory, 
    it automatically generates a fresh settings.json using DEFAULT_JSON.
    It strips Javascript-style comments (//) before parsing so the user can easily read the file.
    """
    settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')
    reset_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reset')
    
    # Check for reset trigger or missing config
    if os.path.exists(reset_file) or not os.path.exists(settings_file):
        try:
            with open(settings_file, 'w') as f:
                f.write(DEFAULT_JSON)
            if os.path.exists(reset_file):
                os.remove(reset_file)
        except Exception: pass
            
    # Baseline fallback dict to prevent crashes if JSON is incomplete
    default_dict = {
        "enable_screen": True, "enable_fan": True,
        "brightness": 255, "rotate_180": False, "invert_colors": False,
        "pixel_shift_screensaver": True, "minimum_fan_run_time_seconds": 60,
        "quiet_hours_enabled": False, "quiet_hours_start": "22:00", "quiet_hours_end": "07:00",
        "fan_on_temp": 55.0, "fan_off_temp": 45.0,
        "show_warnings": True, "warning_temp": 75.0,
        "page_duration_seconds": 20, 
        "hardware_update_interval_seconds": 5,
        "network_update_interval_seconds": 20,
        "pages": [{"type": "network_list", "show_ap_ip_when_connected": True, "duration": 20}]
    }
    
    try:
        with open(settings_file, 'r') as f:
            content = f.read()
            # Regex to remove '// comment' lines before parsing JSON
            content = re.sub(r'^\s*//.*$', '', content, flags=re.MULTILINE)
            loaded = json.loads(content)
            # Merge loaded settings over the default dictionary
            for k, v in loaded.items():
                default_dict[k] = v
    except json.JSONDecodeError:
        # Flag if JSON is corrupted so we can warn the user on the physical screen
        default_dict["_error"] = True
    except Exception: pass
    
    return default_dict


def get_text_width(text, font):
    """
    Calculates the exact pixel width of a given text string. 
    Crucial for determining if a line is too long for the 128px screen, 
    which triggers the horizontal bounce-scrolling logic.
    """
    try: 
        return int(draw.textlength(text, font=font))
    except AttributeError:
        # Fallback for older Pillow versions
        try: return font.getsize(text)[0]
        except Exception: return len(text) * 6


def format_custom_line(text, temp, ap_ssid, ap_ip, ap_psk, wifi_ssid, web_port_str):
    """
    Takes a custom string from settings.json and injects live variables into it.
    E.g. "Temp is {temp}C" becomes "Temp is 55.0C".
    """
    now = datetime.datetime.now()
    replacements = {
        "{time}": now.strftime("%H:%M:%S"), "{hour}": now.strftime("%H"),
        "{minute}": now.strftime("%M"), "{second}": now.strftime("%S"),
        "{date}": now.strftime("%Y-%m-%d"), "{day}": now.strftime("%d"),
        "{month}": now.strftime("%m"), "{year}": now.strftime("%Y"),
        "{temp}": str(temp), "{ap_ssid}": ap_ssid or "N/A",
        "{ap_pw}": ap_psk or "N/A", "{ap_ip}": ap_ip or "N/A",
        "{wifi_ssid}": wifi_ssid or "Not Connected", "{web_port}": web_port_str or "80"
    }
    for k, v in replacements.items(): 
        text = text.replace(k, v)
    return text


def get_file_port(glob_pattern, default=""):
    """
    Searches the system using a glob pattern to locate specific 'webport' configuration files.
    Used to dynamically detect which port the WiFi App and Diagnostic Dashboard are running on.
    """
    try:
        files = glob.glob(glob_pattern)
        if files:
            with open(files[0], 'r') as f:
                val = f.read().strip()
                if val: return val
    except Exception: pass
    return default


def build_port_string(page_config, diag_port, wifi_port, include_colon=True):
    """
    Evaluates the page configuration toggles and builds a cleanly formatted 
    port suffix string for IP addresses. E.g., returns ":80/8080/9000".
    Handles the Network Diagnostic port, WiFi port, and an optional Custom port.
    """
    ports = []
    
    # 1. Diagnostic Port
    if page_config.get("show_diagnostic_port", True) and diag_port:
        if diag_port not in ports: ports.append(diag_port)
            
    # 2. WiFi Config Port
    if page_config.get("show_wifi_port", True) and wifi_port:
        if wifi_port not in ports: ports.append(wifi_port)
            
    # 3. Custom Port (e.g., a node server or API running on a specific port)
    custom_port = str(page_config.get("custom_port", "")).strip()
    if custom_port:
        if custom_port not in ports: ports.append(custom_port)
        
    if ports:
        joined = "/".join(ports)
        return f":{joined}" if include_colon else joined
        
    return ""


def get_networks():
    """
    Uses the system `ip` command to fetch a list of all active IPv4 interfaces
    and their corresponding IP addresses. Safely ignores loopback (lo) and Docker networks.
    """
    networks = []
    try:
        out = subprocess.check_output(['ip', '-o', '-4', 'addr', 'show'], stderr=subprocess.DEVNULL).decode('utf-8')
        for line in out.split('\n'):
            if line.strip():
                parts = line.split()
                iface = parts[1]
                ip = parts[3].split('/')[0]
                if iface != "lo" and not iface.startswith("docker") and not iface.startswith("veth"):
                    networks.append((iface, ip))
    except Exception: pass
    return networks


def get_hotspot_details():
    """
    Interrogates NetworkManager to see if an Access Point (Hotspot) is currently active.
    Extracts the Hotspot SSID, Passkey (PSK), Interface binding, and detects if clients are connected.
    Also grabs the standard Infrastructure WiFi SSID if connected to an external network.
    """
    ap_ssid, ap_psk, ap_has_clients, ap_iface, wifi_ssid = None, None, False, None, None
    try:
        active_conns = subprocess.check_output(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show', '--active'], stderr=subprocess.DEVNULL).decode('utf-8').split('\n')
        for conn in active_conns:
            if 'wireless' in conn or '802-11-wireless' in conn:
                name = conn.split(':')[0]
                mode = subprocess.check_output(['nmcli', '-g', '802-11-wireless.mode', 'connection', 'show', name], stderr=subprocess.DEVNULL).decode('utf-8').strip()
                
                if mode == 'ap':
                    ap_ssid = subprocess.check_output(['nmcli', '-g', '802-11-wireless.ssid', 'connection', 'show', name], stderr=subprocess.DEVNULL).decode('utf-8').strip()
                    ap_psk = subprocess.check_output(['sudo', 'nmcli', '--show-secrets', '-g', '802-11-wireless-security.psk', 'connection', 'show', name], stderr=subprocess.DEVNULL).decode('utf-8').strip()
                    ap_iface = subprocess.check_output(['nmcli', '-g', 'GENERAL.DEVICES', 'connection', 'show', name], stderr=subprocess.DEVNULL).decode('utf-8').strip()
                    
                    if ap_iface:
                        try:
                            # Use iw dump to physically count associated stations (clients)
                            stations = subprocess.check_output(['sudo', 'iw', 'dev', ap_iface, 'station', 'dump'], stderr=subprocess.DEVNULL).decode('utf-8')
                            if "Station" in stations: ap_has_clients = True
                        except Exception: pass
                        
                elif mode == 'infrastructure':
                    wifi_ssid = subprocess.check_output(['nmcli', '-g', '802-11-wireless.ssid', 'connection', 'show', name], stderr=subprocess.DEVNULL).decode('utf-8').strip()
    except Exception: pass
    
    return ap_ssid, ap_psk, ap_has_clients, ap_iface, wifi_ssid


def get_temp():
    """
    Queries the hardware directly to retrieve the current CPU temperature in Celsius.
    """
    try:
        out = subprocess.check_output(['vcgencmd', 'measure_temp'], stderr=subprocess.DEVNULL).decode('utf-8')
        return float(out.replace('temp=', '').replace('\'C\n', ''))
    except Exception: return 0.0


def get_undervoltage():
    """
    Reads the system throttled flags. If bit 0 is flipped (1), the Pi is currently 
    experiencing an active power undervoltage.
    """
    try:
        out = subprocess.check_output(['vcgencmd', 'get_throttled'], stderr=subprocess.DEVNULL).decode('utf-8')
        val = int(out.replace('throttled=', '').strip(), 16)
        return (val & 1) == 1
    except Exception: return False


def is_quiet_hours(start_str, end_str):
    """
    Compares the current system time against the user-configured Quiet Hours window.
    Safely handles time windows that cross midnight (e.g., 22:00 to 07:00).
    """
    try:
        now = datetime.datetime.now().time()
        st = datetime.datetime.strptime(start_str, "%H:%M").time()
        ed = datetime.datetime.strptime(end_str, "%H:%M").time()
        if st < ed: return st <= now <= ed
        else: return now >= st or now <= ed
    except Exception: return False


# ==============================================================================
# INITIALIZATION & SETUP
# ==============================================================================
settings = load_settings()
ENABLE_SCREEN = settings.get("enable_screen", True)
ENABLE_FAN = settings.get("enable_fan", True)

if not ENABLE_SCREEN and not ENABLE_FAN:
    print("Screen and Fan are both disabled in settings.json. Exiting cleanly.")
    sys.exit(0)

# Initialize OLED Display over I2C
if ENABLE_SCREEN:
    i2c = busio.I2C(board.SCL, board.SDA)
    disp = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
    brightness_level = max(0, min(255, int(settings.get("brightness", 255))))
    disp.contrast(brightness_level)
    
    width = disp.width
    height = disp.height
    image = Image.new("1", (width, height))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

# Initialize Fan Controller over I2C
FAN_I2C_ADDR = 0x20
fan_present = False
if ENABLE_FAN:
    try:
        bus = smbus.SMBus(1)
        fan_present = True
    except Exception: pass

# Global State Variables
last_hw_fetch, last_net_fetch = 0, 0
networks = []
ap_ssid, ap_psk, ap_has_clients, ap_iface, wifi_ssid = None, None, False, None, None
diag_port, wifi_port = "", ""
temp, uv = 0.0, False

current_page_idx = 0
page_start_time = time.time()
FPS_DELAY = 0.05    

fan_currently_on = False
fan_last_on_time = 0
screen_sleeping = False

bg_col = 255 if settings.get("invert_colors", False) else 0
txt_col = 0 if settings.get("invert_colors", False) else 255
rotate_180 = settings.get("rotate_180", False)


# ==============================================================================
# MAIN EVENT LOOP
# ==============================================================================
try:
    while True:
        current_time = time.time()
        
        # 1. Quiet Hours Validation
        q_enabled = settings.get("quiet_hours_enabled", False)
        in_quiet = q_enabled and is_quiet_hours(settings.get("quiet_hours_start", "22:00"), settings.get("quiet_hours_end", "07:00"))
        
        # 2. Hardware Polling & Fan Control
        hw_interval = settings.get("hardware_update_interval_seconds", 5)
        if current_time - last_hw_fetch > hw_interval:
            temp = get_temp()
            uv = get_undervoltage()
            
            if ENABLE_FAN and fan_present:
                try:
                    # In quiet hours, only trigger the fan if we hit the extreme emergency temp
                    turn_on_temp = settings.get("warning_temp", 75.0) if in_quiet else settings.get("fan_on_temp", 55.0)
                    
                    if temp >= turn_on_temp:
                        if not fan_currently_on:
                            bus.write_byte(FAN_I2C_ADDR, 0xFE) # Turn Fan On
                            fan_currently_on = True
                            fan_last_on_time = current_time
                    elif temp <= settings.get("fan_off_temp", 45.0):
                        if fan_currently_on:
                            # Anti-Flutter: Don't turn off until minimum run time is met
                            if (current_time - fan_last_on_time) >= settings.get("minimum_fan_run_time_seconds", 60):
                                bus.write_byte(FAN_I2C_ADDR, 0xFF) # Turn Fan Off
                                fan_currently_on = False
                except Exception: pass
            last_hw_fetch = current_time

        # 3. Screen Rendering Sequence
        if ENABLE_SCREEN:
            SHOW_WARN = settings.get("show_warnings", True)
            WARN_TEMP = settings.get("warning_temp", 75.0)
            is_warning_state = SHOW_WARN and (uv or temp > WARN_TEMP)
            
            # 3A. Night Mode (Screen Sleep)
            if in_quiet and not is_warning_state:
                if not screen_sleeping:
                    try: disp.poweroff()
                    except Exception: 
                        draw.rectangle((0, 0, width, height), outline=bg_col, fill=bg_col)
                        disp.image(image)
                        disp.show()
                    screen_sleeping = True
                time.sleep(hw_interval if hw_interval > 0 else 1)
                continue
            else:
                if screen_sleeping:
                    try: disp.poweron()
                    except Exception: pass
                    screen_sleeping = False

            # 3B. Screensaver Pixel Shifting
            px_shift = settings.get("pixel_shift_screensaver", True)
            ox = int(current_time / 3600) % 2 if px_shift else 0
            oy = int((current_time / 3600) + 1) % 2 if px_shift else 0

            # 3C. Network Polling
            net_interval = settings.get("network_update_interval_seconds", 20)
            if current_time - last_net_fetch > net_interval:
                networks = get_networks()
                ap_ssid, ap_psk, ap_has_clients, ap_iface, wifi_ssid = get_hotspot_details()
                
                # Retrieve the active ports for the diagnostic and wifi dashboards
                diag_port = get_file_port('/home/*/Network-Testing-Tools/webport')
                wifi_port = get_file_port('/home/*/pi-wifi-app/webport')
                
                last_net_fetch = current_time

            # Clear Screen Background
            draw.rectangle((0, 0, width, height), outline=bg_col, fill=bg_col)
            
            # 3D. Error Overlay (JSON Corruption)
            if settings.get("_error"):
                draw.text((ox, oy), "Settings Invalid!", font=font, fill=txt_col)
                draw.text((ox, oy + 11), "Check settings.json", font=font, fill=txt_col)
                disp_image = image.rotate(180) if rotate_180 else image
                disp.image(disp_image)
                disp.show()
                time.sleep(FPS_DELAY)
                continue
                
            # 3E. Hardware Warning Overlay
            if is_warning_state:
                # Flash the text on and off every half second
                if int(current_time * 2) % 2 == 0:
                    if uv: draw.text((ox, oy), "WARNING: VOLT DROP!", font=font, fill=txt_col)
                    if temp > WARN_TEMP: draw.text((ox, oy + 16), f"WARNING: HOT! {temp}C", font=font, fill=txt_col)
                disp_image = image.rotate(180) if rotate_180 else image
                disp.image(disp_image)
                disp.show()
                time.sleep(FPS_DELAY)
                continue
                
            # 3F. Compile Active Page Content
            pages_to_render = []
            ap_ip_current = ""
            for iface, ip in networks:
                if iface == ap_iface: ap_ip_current = ip
                    
            global_dur = settings.get("page_duration_seconds", 20)
            for page_config in settings.get("pages", []):
                ptype = page_config.get("type")
                dur = page_config.get("duration", global_dur)
                s_v = page_config.get("scroll_vertical", True)
                s_h = page_config.get("scroll_horizontal", True)
                align = page_config.get("align", "left")
                
                if dur <= 0: continue
                    
                # Compile: Network Interfaces List
                if ptype == "network_list":
                    nlines = []
                    show_ap_ip = page_config.get("show_ap_ip_when_connected", True)
                    port_suffix = build_port_string(page_config, diag_port, wifi_port, include_colon=True)
                    
                    for iface, ip in networks:
                        if iface == ap_iface:
                            if show_ap_ip and ap_has_clients: 
                                nlines.append(f"Pi: {ip}{port_suffix}")
                        else:
                            nlines.append(f"{iface}: {ip}{port_suffix}")
                            
                    if nlines:
                        pages_to_render.append({"type": "custom", "lines": nlines, "duration": dur, "s_v": s_v, "s_h": s_h, "align": align})
                        
                # Compile: Hotspot Credentials
                elif ptype == "hotspot_details":
                    if ap_ssid and ap_psk:
                        hide = page_config.get("hide_when_connected", True)
                        if not (hide and ap_has_clients):
                            ip_str = ap_ip_current if ap_ip_current else "10.42.0.1"
                            port_suffix = build_port_string(page_config, diag_port, wifi_port, include_colon=True)
                            pages_to_render.append({
                                "type": "custom", "duration": dur,
                                "lines": [f"Pi: {ap_ssid}", f"PW: {ap_psk}", f"IP: {ip_str}{port_suffix}"],
                                "s_v": s_v, "s_h": s_h, "align": align
                            })
                            
                # Compile: User Custom Text
                elif ptype == "custom":
                    clines = []
                    custom_port_str = build_port_string(page_config, diag_port, wifi_port, include_colon=False)
                    if not custom_port_str: custom_port_str = "80" # Fallback if used purely via the {web_port} tag
                    
                    for line in page_config.get("lines", []):
                        clines.append(format_custom_line(str(line), temp, ap_ssid, ap_ip_current, ap_psk, wifi_ssid, custom_port_str))
                    pages_to_render.append({"type": "custom", "lines": clines, "duration": dur, "s_v": s_v, "s_h": s_h, "align": align})
                    
            # 3G. Execute Rendering & Scrolling Math
            if not pages_to_render:
                draw.text((ox, oy + 12), "No Active Pages", font=font, fill=txt_col)
            else:
                if current_page_idx >= len(pages_to_render):
                    current_page_idx = 0
                    page_start_time = current_time
                    
                current_page = pages_to_render[current_page_idx]
                active_dur = current_page["duration"]
                s_v = current_page["s_v"]
                s_h = current_page["s_h"]
                align = current_page["align"]
                elapsed = current_time - page_start_time
                
                # Check if it's time to transition to the next page
                if elapsed >= active_dur:
                    current_page_idx = (current_page_idx + 1) % len(pages_to_render)
                    current_page = pages_to_render[current_page_idx]
                    page_start_time = current_time
                    elapsed = 0
                    active_dur = current_page["duration"]
                    s_v = current_page["s_v"]
                    s_h = current_page["s_h"]
                    align = current_page["align"]
                    
                line_height = 11
                total_height = len(current_page["lines"]) * line_height
                y_base = 0
                
                # Calculate Vertical Scrolling Position (Pan Upwards smoothly)
                if s_v and total_height > height:
                    max_y = total_height - height
                    sdur = active_dur - 2.0 # Wait 1 second at top, 1 second at bottom
                    if sdur <= 0.1: sdur = 0.1
                    if elapsed < 1.0: y_base = 0
                    elif elapsed > active_dur - 1.0: y_base = -max_y
                    else: y_base = -int(((elapsed - 1.0)/sdur) * max_y)
                    
                # Calculate Horizontal Scrolling & Text Alignment
                for i, line in enumerate(current_page["lines"]):
                    dy = y_base + (i * line_height)
                    
                    # Only render the line if it is currently visible on the Y axis
                    if -line_height < dy < height:
                        lw = get_text_width(line, font)
                        xb = 0
                        
                        if lw > width and s_h:
                            # Bounce text back and forth if it exceeds the screen width
                            mx = lw - width + 10
                            cyc = mx * 0.05 + 2.0
                            ph = (elapsed % (cyc * 2))
                            if ph < cyc: xp = max(0, ph - 1.0) / (cyc - 1.0) if cyc > 1 else 0
                            else: xp = max(0, (cyc * 2 - ph) - 1.0) / (cyc - 1.0) if cyc > 1 else 0
                            xb = max(min(-int(xp * mx), 0), -mx)
                        else:
                            # Apply static text alignment
                            if align == "center": xb = (width - lw) // 2
                            elif align == "right": xb = width - lw
                            
                        # Draw the final calculated line to the buffer
                        draw.text((xb + ox, dy + oy), line, font=font, fill=txt_col)
                        
            # Apply hardware rotation, dump buffer to the physical OLED, and sleep to conserve CPU
            disp_image = image.rotate(180) if rotate_180 else image
            disp.image(disp_image)
            disp.show()
            time.sleep(FPS_DELAY)
            
        else:
            # If the screen is disabled entirely, just sleep to save CPU 
            # while the background fan controller continues to run.
            time.sleep(hw_interval if hw_interval > 0 else 1)
        
except KeyboardInterrupt:
    # Cleanup safely if the script is manually terminated
    if ENABLE_FAN and fan_present:
        try: bus.write_byte(FAN_I2C_ADDR, 0xFF)
        except Exception: pass