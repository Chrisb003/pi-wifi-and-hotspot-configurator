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

DEFAULT_JSON = """{
    "enable_screen": true,
    "enable_fan": true,
    "brightness": 255,
    "fan_on_temp": 55.0,
    "fan_off_temp": 45.0,
    "show_warnings": true,
    "warning_temp": 75.0,
    "rotate_180": false,
    "invert_colors": false,
    "pixel_shift_screensaver": true,
    "minimum_fan_run_time_seconds": 60,
    "quiet_hours_enabled": false,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "page_duration_seconds": 20,
    "hardware_update_interval_seconds": 5,
    "network_update_interval_seconds": 20,
    "pages": [
        {
            "type": "network_list",
            "show_ap_ip_when_connected": true,
            "duration": 20,
            "align": "left",
            "scroll_vertical": true,
            "scroll_horizontal": true
        },
        {
            "type": "hotspot_details",
            "hide_when_connected": true,
            "duration": 20,
            "align": "left",
            "scroll_vertical": true,
            "scroll_horizontal": true
        }
    ]
}"""

def load_settings():
    settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')
    reset_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reset')
    
    if os.path.exists(reset_file) or not os.path.exists(settings_file):
        try:
            with open(settings_file, 'w') as f:
                f.write(DEFAULT_JSON)
            if os.path.exists(reset_file):
                os.remove(reset_file)
        except Exception: pass
            
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
            content = re.sub(r'^\s*//.*$', '', content, flags=re.MULTILINE)
            loaded = json.loads(content)
            for k, v in loaded.items():
                default_dict[k] = v
    except json.JSONDecodeError:
        default_dict["_error"] = True
    except Exception: pass
    return default_dict

settings = load_settings()
ENABLE_SCREEN = settings.get("enable_screen", True)
ENABLE_FAN = settings.get("enable_fan", True)

if not ENABLE_SCREEN and not ENABLE_FAN:
    print("Screen and Fan are both disabled in settings.json. Exiting cleanly.")
    sys.exit(0)

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

FAN_I2C_ADDR = 0x20
fan_present = False
if ENABLE_FAN:
    try:
        bus = smbus.SMBus(1)
        fan_present = True
    except Exception:
        pass

def get_text_width(text, font):
    try: return int(draw.textlength(text, font=font))
    except AttributeError:
        try: return font.getsize(text)[0]
        except Exception: return len(text) * 6

def format_custom_line(text, temp, ap_ssid, ap_ip, ap_psk, wifi_ssid, web_port):
    now = datetime.datetime.now()
    replacements = {
        "{time}": now.strftime("%H:%M:%S"), "{hour}": now.strftime("%H"),
        "{minute}": now.strftime("%M"), "{second}": now.strftime("%S"),
        "{date}": now.strftime("%Y-%m-%d"), "{day}": now.strftime("%d"),
        "{month}": now.strftime("%m"), "{year}": now.strftime("%Y"),
        "{temp}": str(temp), "{ap_ssid}": ap_ssid or "N/A",
        "{ap_pw}": ap_psk or "N/A", "{ap_ip}": ap_ip or "N/A",
        "{wifi_ssid}": wifi_ssid or "Not Connected", "{web_port}": web_port or "80"
    }
    for k, v in replacements.items(): text = text.replace(k, v)
    return text

def get_webport():
    ports = []
    for p in ['/home/*/Network-Testing-Tools/webport', '/home/*/pi-wifi-app/webport']:
        try:
            files = glob.glob(p)
            if files:
                with open(files[0], 'r') as f:
                    v = f.read().strip()
                    if v and v not in ports: ports.append(v)
        except Exception: pass
    return "/".join(ports) if ports else "80"

def get_networks():
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
                            stations = subprocess.check_output(['sudo', 'iw', 'dev', ap_iface, 'station', 'dump'], stderr=subprocess.DEVNULL).decode('utf-8')
                            if "Station" in stations: ap_has_clients = True
                        except Exception: pass
                elif mode == 'infrastructure':
                    wifi_ssid = subprocess.check_output(['nmcli', '-g', '802-11-wireless.ssid', 'connection', 'show', name], stderr=subprocess.DEVNULL).decode('utf-8').strip()
    except Exception: pass
    return ap_ssid, ap_psk, ap_has_clients, ap_iface, wifi_ssid

def get_temp():
    try:
        out = subprocess.check_output(['vcgencmd', 'measure_temp'], stderr=subprocess.DEVNULL).decode('utf-8')
        return float(out.replace('temp=', '').replace('\'C\n', ''))
    except Exception: return 0.0

def get_undervoltage():
    try:
        out = subprocess.check_output(['vcgencmd', 'get_throttled'], stderr=subprocess.DEVNULL).decode('utf-8')
        val = int(out.replace('throttled=', '').strip(), 16)
        return (val & 1) == 1
    except Exception: return False

def is_quiet_hours(start_str, end_str):
    try:
        now = datetime.datetime.now().time()
        st = datetime.datetime.strptime(start_str, "%H:%M").time()
        ed = datetime.datetime.strptime(end_str, "%H:%M").time()
        if st < ed: return st <= now <= ed
        else: return now >= st or now <= ed
    except Exception: return False

last_hw_fetch, last_net_fetch = 0, 0
networks = []
ap_ssid, ap_psk, ap_has_clients, ap_iface, wifi_ssid = None, None, False, None, None
web_port = "80"
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

try:
    while True:
        current_time = time.time()
        q_enabled = settings.get("quiet_hours_enabled", False)
        in_quiet = q_enabled and is_quiet_hours(settings.get("quiet_hours_start", "22:00"), settings.get("quiet_hours_end", "07:00"))
        
        hw_interval = settings.get("hardware_update_interval_seconds", 5)
        if current_time - last_hw_fetch > hw_interval:
            temp = get_temp()
            uv = get_undervoltage()
            
            if ENABLE_FAN and fan_present:
                try:
                    turn_on_temp = settings.get("warning_temp", 75.0) if in_quiet else settings.get("fan_on_temp", 55.0)
                    if temp >= turn_on_temp:
                        if not fan_currently_on:
                            bus.write_byte(FAN_I2C_ADDR, 0xFE)
                            fan_currently_on = True
                            fan_last_on_time = current_time
                    elif temp <= settings.get("fan_off_temp", 45.0):
                        if fan_currently_on:
                            if (current_time - fan_last_on_time) >= settings.get("minimum_fan_run_time_seconds", 60):
                                bus.write_byte(FAN_I2C_ADDR, 0xFF)
                                fan_currently_on = False
                except Exception: pass
            last_hw_fetch = current_time

        if ENABLE_SCREEN:
            SHOW_WARN = settings.get("show_warnings", True)
            WARN_TEMP = settings.get("warning_temp", 75.0)
            is_warning_state = SHOW_WARN and (uv or temp > WARN_TEMP)
            
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

            px_shift = settings.get("pixel_shift_screensaver", True)
            ox = int(current_time / 3600) % 2 if px_shift else 0
            oy = int((current_time / 3600) + 1) % 2 if px_shift else 0

            net_interval = settings.get("network_update_interval_seconds", 20)
            if current_time - last_net_fetch > net_interval:
                networks = get_networks()
                ap_ssid, ap_psk, ap_has_clients, ap_iface, wifi_ssid = get_hotspot_details()
                web_port = get_webport()
                last_net_fetch = current_time

            draw.rectangle((0, 0, width, height), outline=bg_col, fill=bg_col)
            
            if settings.get("_error"):
                draw.text((ox, oy), "Settings Invalid!", font=font, fill=txt_col)
                draw.text((ox, oy + 11), "Check settings.json", font=font, fill=txt_col)
                disp_image = image.rotate(180) if rotate_180 else image
                disp.image(disp_image)
                disp.show()
                time.sleep(FPS_DELAY)
                continue
                
            if is_warning_state:
                if int(current_time * 2) % 2 == 0:
                    if uv: draw.text((ox, oy), "WARNING: VOLT DROP!", font=font, fill=txt_col)
                    if temp > WARN_TEMP: draw.text((ox, oy + 16), f"WARNING: HOT! {temp}C", font=font, fill=txt_col)
                disp_image = image.rotate(180) if rotate_180 else image
                disp.image(disp_image)
                disp.show()
                time.sleep(FPS_DELAY)
                continue
                
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
                    
                if ptype == "network_list":
                    nlines = []
                    show_ap_ip = page_config.get("show_ap_ip_when_connected", True)
                    for iface, ip in networks:
                        if iface == ap_iface:
                            if show_ap_ip and ap_has_clients: nlines.append(f"Pi: {ip}:{web_port}")
                        else:
                            nlines.append(f"{iface}: {ip}:{web_port}")
                    if nlines:
                        pages_to_render.append({"type": "custom", "lines": nlines, "duration": dur, "s_v": s_v, "s_h": s_h, "align": align})
                        
                elif ptype == "hotspot_details":
                    if ap_ssid and ap_psk:
                        hide = page_config.get("hide_when_connected", True)
                        if not (hide and ap_has_clients):
                            ip_str = ap_ip_current if ap_ip_current else "10.42.0.1"
                            pages_to_render.append({
                                "type": "custom", "duration": dur,
                                "lines": [f"Pi: {ap_ssid}", f"PW: {ap_psk}", f"IP: {ip_str}:{web_port}"],
                                "s_v": s_v, "s_h": s_h, "align": align
                            })
                            
                elif ptype == "custom":
                    clines = []
                    for line in page_config.get("lines", []):
                        clines.append(format_custom_line(str(line), temp, ap_ssid, ap_ip_current, ap_psk, wifi_ssid, web_port))
                    pages_to_render.append({"type": "custom", "lines": clines, "duration": dur, "s_v": s_v, "s_h": s_h, "align": align})
                    
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
                
                if s_v and total_height > height:
                    max_y = total_height - height
                    sdur = active_dur - 2.0 
                    if sdur <= 0.1: sdur = 0.1
                    if elapsed < 1.0: y_base = 0
                    elif elapsed > active_dur - 1.0: y_base = -max_y
                    else: y_base = -int(((elapsed - 1.0)/sdur) * max_y)
                    
                for i, line in enumerate(current_page["lines"]):
                    dy = y_base + (i * line_height)
                    if -line_height < dy < height:
                        lw = get_text_width(line, font)
                        xb = 0
                        if lw > width and s_h:
                            mx = lw - width + 10
                            cyc = mx * 0.05 + 2.0
                            ph = (elapsed % (cyc * 2))
                            if ph < cyc: xp = max(0, ph - 1.0) / (cyc - 1.0) if cyc > 1 else 0
                            else: xp = max(0, (cyc * 2 - ph) - 1.0) / (cyc - 1.0) if cyc > 1 else 0
                            xb = max(min(-int(xp * mx), 0), -mx)
                        else:
                            if align == "center": xb = (width - lw) // 2
                            elif align == "right": xb = width - lw
                        draw.text((xb + ox, dy + oy), line, font=font, fill=txt_col)
                        
            disp_image = image.rotate(180) if rotate_180 else image
            disp.image(disp_image)
            disp.show()
            time.sleep(FPS_DELAY)
            
        else:
            time.sleep(hw_interval if hw_interval > 0 else 1)
        
except KeyboardInterrupt:
    if ENABLE_FAN and fan_present:
        try: bus.write_byte(FAN_I2C_ADDR, 0xFF)
        except Exception: pass