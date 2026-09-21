// ==========================================
// SPA NAVIGATION & TIMEOUT LOGIC
// ==========================================
let inactivityTimer;

function resetInactivityTimer() {
    clearTimeout(inactivityTimer);
    document.getElementById('timeoutOverlay').style.display = 'none';
    // 30 minutes = 30 * 60 * 1000 = 1800000 ms
    inactivityTimer = setTimeout(() => {
        document.getElementById('timeoutOverlay').style.display = 'flex';
    }, 1800000); 
}

function showSection(sectionId) {
    document.querySelectorAll('.nav-section').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.nav-links a').forEach(el => el.classList.remove('active'));
    
    const targetSection = document.getElementById('section-' + sectionId);
    if(targetSection) {
        targetSection.style.display = 'block';
        document.getElementById('nav-' + sectionId).classList.add('active');
        localStorage.setItem('activeSection', sectionId);
    }
}

function toggleTheme() {
    const isLight = document.body.classList.toggle('light-mode');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    document.getElementById('themeToggle').innerText = isLight ? '🌙 Dark' : '☀️ Light';
}

// ==========================================
// UPDATE MANAGER LOGIC
// ==========================================
async function checkForUpdates() {
    const modal = document.getElementById('updateModal');
    const content = document.getElementById('updateBody');
    const updateBtn = document.getElementById('runUpdateBtn');
    
    modal.style.display = 'flex';
    content.innerHTML = '<div style="text-align:center; padding: 40px;">Searching GitHub for latest versions...</div>';
    updateBtn.style.display = 'none';
    
    try {
        const res = await fetch('/api/update/check');
        const data = await res.json();
        
        if(data.status === 'error') {
            content.innerHTML = `<div class="error">${data.message}</div>`;
            return;
        }

        let html = '<div class="update-columns">';
        let updatesAvailable = [];
        
        // WiFi Column
        html += `<div class="update-col">
                    <h3 style="margin-top:0;">WiFi App</h3>
                    <div style="font-size: 13px; margin-bottom: 15px;">
                        Installed: <b>v${data.wifi.local_version}</b> <br>
                        Latest: <b>v${data.wifi.target_version}</b>
                    </div>`;
        if (data.wifi.update_available) updatesAvailable.push('wifi');
        html += buildChangelogHtml(data.wifi.changelog);
        html += `</div>`;

        // OLED Column
        if (data.oled.installed) {
            html += `<div class="update-col">
                        <h3 style="margin-top:0;">OLED Monitor</h3>
                        <div style="font-size: 13px; margin-bottom: 15px;">
                            Installed: <b>v${data.oled.local_version}</b> <br>
                            Latest: <b>v${data.oled.target_version}</b>
                        </div>`;
            if (data.oled.update_available) updatesAvailable.push('oled');
            html += buildChangelogHtml(data.oled.changelog);
            html += `</div>`;
        }
        
        html += '</div>';
        content.innerHTML = html;

        if (updatesAvailable.length > 0) {
            updateBtn.style.display = 'inline-block';
            updateBtn.onclick = () => executeUpdate(updatesAvailable);
        } else {
            content.innerHTML = '<div class="success" style="margin-bottom: 20px;">You are completely up to date!</div>' + html;
        }

    } catch (e) {
        content.innerHTML = '<div class="error">Network error occurred while checking for updates.</div>';
    }
}

function buildChangelogHtml(changelogData) {
    if (!changelogData || changelogData.length === 0) return '<p style="font-size:12px; color:var(--info-text);">No recent changelog data.</p>';
    
    let html = '';
    changelogData.forEach(release => {
        html += `<div class="changelog-release">`;
        html += `<h3 class="changelog-title">[${release.version}] - ${release.title}</h3>`;
        release.sections.forEach(sec => {
            html += `<h4 class="changelog-subtitle">${sec.subtitle}</h4>`;
            html += `<ul class="changelog-bullets">`;
            sec.bullets.forEach(b => {
                if (b.type === 'space') {
                    html += `<div class="changelog-space"></div>`;
                } else {
                    html += `<li>${b.content}</li>`;
                }
            });
            html += `</ul>`;
        });
        html += `</div>`;
    });
    return html;
}

async function executeUpdate(components) {
    const content = document.getElementById('updateBody');
    const updateBtn = document.getElementById('runUpdateBtn');
    
    updateBtn.style.display = 'none';
    content.innerHTML = '<div style="text-align:center; padding: 40px;"><h3 style="color:var(--link-color);">Downloading Updates...</h3><p>Please do not turn off the Raspberry Pi. This will take a few seconds.</p></div>';
    
    try {
        const res = await fetch('/api/update/run', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ components })
        });
        const data = await res.json();
        
        if (data.status === 'success') {
            content.innerHTML = `<div style="text-align:center; padding: 40px;"><h3 style="color:#a5d6a7;">Update Successful!</h3><p>Services are restarting. The page will reload momentarily.</p></div>`;
            setTimeout(() => window.location.reload(), 4000);
        } else {
            content.innerHTML = `<div class="error">Update Failed: ${data.message}</div>`;
        }
    } catch (e) {
        content.innerHTML = `<div class="error">Connection lost during update. The system may be restarting. Please refresh manually in a few seconds.</div>`;
    }
}

function closeModal() {
    document.getElementById('updateModal').style.display = 'none';
}

// ==========================================
// WIFI & HOTSPOT LOGIC
// ==========================================
let interfacesData = [];

async function loadInterfaces() {
    try {
        const res = await fetch('/interfaces');
        const data = await res.json();
        interfacesData = data.interfaces;
        
        const wifiSelect = document.getElementById('wifiInterfaceSelect');
        const hotspotSelect = document.getElementById('hotspotInterfaceSelect');
        
        wifiSelect.innerHTML = '';
        if(hotspotSelect) hotspotSelect.innerHTML = '';
        
        if (data.interfaces.length === 0) { 
            wifiSelect.style.display = 'none'; 
            if(hotspotSelect) { hotspotSelect.style.display = 'none'; document.getElementById('ifaceLabel').style.display = 'none'; }
            return; 
        }
        
        data.interfaces.forEach(iface => {
            const optW = document.createElement('option');
            optW.value = iface.name;
            optW.innerText = iface.name + (iface.is_hotspot ? ' (Running Hotspot)' : '');
            wifiSelect.appendChild(optW);
            
            if (hotspotSelect) {
                const optH = document.createElement('option');
                optH.value = iface.name;
                optH.innerText = iface.name + (iface.is_hotspot ? ' (Current Hotspot)' : '');
                hotspotSelect.appendChild(optH);
            }
        });
        
        if (data.default) wifiSelect.value = data.default;
        
        if (hotspotSelect && window.HOTSPOT_IFACE) {
            if (Array.from(hotspotSelect.options).some(o => o.value === window.HOTSPOT_IFACE)) {
                hotspotSelect.value = window.HOTSPOT_IFACE;
            } else if (data.default) {
                hotspotSelect.value = data.default;
            }
        }
        
        checkWarning();
        if (data.interfaces.length <= 1) {
            wifiSelect.style.display = 'none';
            if(hotspotSelect) { hotspotSelect.style.display = 'none'; document.getElementById('ifaceLabel').style.display = 'none'; }
        }
    } catch (err) {}
}

function checkWarning() {
    const selected = document.getElementById('wifiInterfaceSelect').value;
    const iface = interfacesData.find(i => i.name === selected);
    const warning = document.getElementById('hotspotWarning');
    if (iface && iface.is_hotspot) warning.classList.remove('hidden');
    else warning.classList.add('hidden');
}

async function scanNetworks() {
    const scanBtn = document.getElementById('scanBtn');
    const connectForm = document.getElementById('connectForm');
    const ssidSelect = document.getElementById('ssidSelect');
    const device = document.getElementById('wifiInterfaceSelect').value;
    
    scanBtn.innerText = "Searching..."; scanBtn.disabled = true; showMessage('wifiMsg', '', '');
    
    try {
        const response = await fetch('/scan?device=' + encodeURIComponent(device));
        const data = await response.json();
        if (data.status === 'success') {
            ssidSelect.innerHTML = '<option value="">Select a network...</option>';
            data.networks.forEach(net => {
                const option = document.createElement('option');
                option.value = net.ssid; option.innerText = `${net.ssid} (Signal: ${net.signal}%)`;
                ssidSelect.appendChild(option);
            });
            connectForm.classList.remove('hidden');
            scanBtn.innerText = "Refresh Networks";
        } else {
            showMessage('wifiMsg', 'error', data.message); scanBtn.innerText = "Search for WiFi Networks";
        }
    } catch (err) { showMessage('wifiMsg', 'error', 'Network error.'); scanBtn.innerText = "Search for WiFi Networks"; }
    scanBtn.disabled = false;
}

async function connectNetwork() {
    const connectBtn = document.getElementById('connectBtn');
    const ssid = document.getElementById('ssidSelect').value;
    const password = document.getElementById('password').value;
    const autoconnect = document.getElementById('autoconnect').checked;
    const device = document.getElementById('wifiInterfaceSelect').value;
    
    if (!ssid) return showMessage('wifiMsg', 'error', 'Select a network.');
    connectBtn.innerText = "Connecting..."; connectBtn.disabled = true; showMessage('wifiMsg', '', '');
    
    try {
        const response = await fetch('/connect', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ssid, password, autoconnect, device })
        });
        const data = await response.json();
        if (data.status === 'success') { showMessage('wifiMsg', 'success', data.message); document.getElementById('password').value = ''; loadInterfaces(); }
        else { showMessage('wifiMsg', 'error', 'Failed: ' + data.message); }
    } catch (err) { showMessage('wifiMsg', 'error', 'Network error.'); }
    connectBtn.innerText = "Connect"; connectBtn.disabled = false;
}

async function disconnectNetwork() {
    const btn = document.getElementById('disconnectBtn');
    const device = document.getElementById('wifiInterfaceSelect').value;
    btn.innerText = "Disconnecting..."; btn.disabled = true; showMessage('wifiMsg', '', '');
    try {
        const response = await fetch('/disconnect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device }) });
        const data = await response.json();
        if (data.status === 'success') { showMessage('wifiMsg', 'success', data.message); loadInterfaces(); }
        else { showMessage('wifiMsg', 'error', 'Failed: ' + data.message); }
    } catch (err) { showMessage('wifiMsg', 'error', 'Network error.'); }
    btn.innerText = "Disconnect Current WiFi"; btn.disabled = false;
}

function showMessage(targetId, type, text) {
    const msgDiv = document.getElementById(targetId);
    if (!text) { msgDiv.className = 'hidden'; return; }
    msgDiv.innerText = text; msgDiv.className = type;
    msgDiv.style.display = 'block';
    if(type === 'success') setTimeout(() => msgDiv.style.display = 'none', 4000);
}

// ==========================================
// OLED LOGIC (Only runs if installed)
// ==========================================
let oledSettings = {};
let systemStatus = {};

async function fetchSystemStatus() {
    try {
        const res = await fetch('/api/system/status');
        systemStatus = await res.json();
        
        if(systemStatus.temp !== undefined) document.getElementById('liveTemp').innerText = `Pi: ${systemStatus.temp.toFixed(1)}°C`;
        
        document.getElementById('doc_time').innerText = systemStatus.time;
        document.getElementById('doc_date').innerText = systemStatus.date;
        document.getElementById('doc_temp').innerText = systemStatus.temp;
        document.getElementById('doc_port').innerText = systemStatus.web_port;
        document.getElementById('doc_wifi').innerText = systemStatus.wifi_ssid;
        document.getElementById('doc_hs').innerText = systemStatus.ap_ssid || "N/A";
        document.getElementById('doc_pw').innerText = systemStatus.ap_pw || "N/A";
        document.getElementById('doc_ip').innerText = systemStatus.ap_ip;
        
        renderPreview();
    } catch(e) {}
}

function initOLEDForm() {
    if(!window.OLED_INSTALLED) return;
    
    oledSettings = window.OLED_SETTINGS_JSON || {};
    
    const DEFAULTS = { 
        enable_screen: true, enable_fan: true, brightness: 255, 
        fan_on_temp: 55.0, fan_off_temp: 45.0, minimum_fan_run_time_seconds: 60,
        show_warnings: true, warning_temp: 75.0,
        rotate_180: false, invert_colors: false, pixel_shift_screensaver: true,
        quiet_hours_enabled: false, quiet_hours_start: "22:00", quiet_hours_end: "07:00",
        page_duration_seconds: 20, network_update_interval_seconds: 20, hardware_update_interval_seconds: 5, 
        pages: [] 
    };
    for(let k in DEFAULTS) { if(oledSettings[k] === undefined) oledSettings[k] = DEFAULTS[k]; }

    document.getElementById('enable_screen').checked = oledSettings.enable_screen;
    document.getElementById('enable_fan').checked = oledSettings.enable_fan;
    document.getElementById('fan_on').value = oledSettings.fan_on_temp;
    document.getElementById('fan_off').value = oledSettings.fan_off_temp;
    document.getElementById('fan_min_run').value = oledSettings.minimum_fan_run_time_seconds;
    
    document.getElementById('brightness').value = oledSettings.brightness;
    document.getElementById('brightness_val').innerText = oledSettings.brightness;
    document.getElementById('rotate_180').checked = oledSettings.rotate_180;
    document.getElementById('invert_colors').checked = oledSettings.invert_colors;
    document.getElementById('pixel_shift').checked = oledSettings.pixel_shift_screensaver;
    
    document.getElementById('show_warnings').checked = oledSettings.show_warnings;
    document.getElementById('warn_temp').value = oledSettings.warning_temp;
    
    document.getElementById('quiet_enabled').checked = oledSettings.quiet_hours_enabled;
    document.getElementById('quiet_start').value = oledSettings.quiet_hours_start;
    document.getElementById('quiet_end').value = oledSettings.quiet_hours_end;
    
    document.getElementById('global_dur').value = oledSettings.page_duration_seconds;
    document.getElementById('net_interval').value = oledSettings.network_update_interval_seconds;
    document.getElementById('hw_interval').value = oledSettings.hardware_update_interval_seconds;
    
    renderPages();
    
    const inputs = document.querySelectorAll('#section-oled input');
    inputs.forEach(i => {
        i.addEventListener('input', () => {
            if(i.id === 'brightness') document.getElementById('brightness_val').innerText = i.value;
            renderPreview();
        });
    });
    document.getElementById('pagesContainer').addEventListener('input', renderPreview);
    
    fetchSystemStatus();
    setInterval(fetchSystemStatus, 5000);
}

function renderPages() {
    const container = document.getElementById('pagesContainer');
    container.innerHTML = '';
    
    if(!oledSettings.pages || oledSettings.pages.length === 0) {
        container.innerHTML = '<div style="text-align:center; color:#888; font-size:14px; padding:20px;">No pages configured. Click Add Page.</div>';
    }

    const previewSelect = document.getElementById('previewPageSelect');
    const currentPreview = previewSelect.value;
    previewSelect.innerHTML = '';
    (oledSettings.pages || []).forEach((p, i) => {
        let opt = document.createElement('option');
        opt.value = i;
        let typeLabel = p.type === 'network_list' ? 'Network IPs' : (p.type === 'hotspot_details' ? 'Hotspot Details' : 'Custom Text');
        opt.innerText = `Preview Page ${i + 1} (${typeLabel})`;
        previewSelect.appendChild(opt);
    });
    if (currentPreview && currentPreview < (oledSettings.pages || []).length) {
        previewSelect.value = currentPreview;
    } else if ((oledSettings.pages || []).length > 0) {
        previewSelect.value = "0";
    }

    (oledSettings.pages || []).forEach((page, index) => {
        const card = document.createElement('div');
        card.className = 'page-card';
        
        let specifics = '';
        if(page.type === 'custom') {
            const linesText = (page.lines || []).join('\n');
            specifics = `
                <label>Custom Lines (variables: {time}, {temp}, {wifi_ssid}, {ap_ip})</label>
                <textarea id="page_lines_${index}">${linesText}</textarea>
            `;
        } else if(page.type === 'network_list') {
            specifics = `
                <label class="checkbox-label">
                    <input type="checkbox" id="page_apip_${index}" ${page.show_ap_ip_when_connected !== false ? 'checked' : ''}> Show Hotspot IP when clients connect
                </label>
            `;
        } else if(page.type === 'hotspot_details') {
            specifics = `
                <label class="checkbox-label">
                    <input type="checkbox" id="page_hide_${index}" ${page.hide_when_connected !== false ? 'checked' : ''}> Auto-hide this screen when a device connects
                </label>
            `;
        }

        // Port UI injections for all types
        const portUI = `
            <div class="flex-row" style="margin-top: 10px;">
                <div>
                    <label class="checkbox-label" style="font-size:12px;">
                        <input type="checkbox" id="page_diagport_${index}" ${page.show_diagnostic_port !== false ? 'checked' : ''}> Add Diag Port
                    </label>
                </div>
                <div>
                    <label class="checkbox-label" style="font-size:12px;">
                        <input type="checkbox" id="page_wifiport_${index}" ${page.show_wifi_port !== false ? 'checked' : ''}> Add WiFi Port
                    </label>
                </div>
                <div>
                    <input type="text" id="page_customport_${index}" placeholder="Custom Port (e.g. 9000)" value="${page.custom_port || ''}" style="padding: 6px; margin-bottom: 0; font-size:12px;">
                </div>
            </div>
        `;

        card.innerHTML = `
            <div class="page-card-header">
                <strong>Page ${index + 1}</strong>
                <button class="btn-danger" onclick="deletePage(${index})">Remove</button>
            </div>
            
            <div class="flex-row">
                <div>
                    <label>Page Type</label>
                    <select id="page_type_${index}" onchange="updatePageType(${index}, this.value)">
                        <option value="network_list" ${page.type === 'network_list' ? 'selected' : ''}>Network IPs</option>
                        <option value="hotspot_details" ${page.type === 'hotspot_details' ? 'selected' : ''}>Hotspot Details</option>
                        <option value="custom" ${page.type === 'custom' ? 'selected' : ''}>Custom Text</option>
                    </select>
                </div>
                <div>
                    <label>Duration (0 to disable)</label>
                    <input type="number" id="page_dur_${index}" value="${page.duration !== undefined ? page.duration : 20}">
                </div>
            </div>
            
            <div class="flex-row">
                <div>
                    <label>Text Alignment</label>
                    <select id="page_align_${index}">
                        <option value="left" ${page.align === 'left' ? 'selected' : ''}>Left</option>
                        <option value="center" ${page.align === 'center' ? 'selected' : ''}>Center</option>
                        <option value="right" ${page.align === 'right' ? 'selected' : ''}>Right</option>
                    </select>
                </div>
            </div>
            ${specifics}
            ${portUI}
        `;
        container.appendChild(card);
    });
    renderPreview();
}

function updatePageType(index, newType) {
    syncStateFromUI();
    oledSettings.pages[index].type = newType;
    if(newType === 'custom' && !oledSettings.pages[index].lines) oledSettings.pages[index].lines = ['Time: {time}', 'Temp: {temp}C'];
    renderPages();
}

function addPage() {
    syncStateFromUI();
    if(!oledSettings.pages) oledSettings.pages = [];
    oledSettings.pages.push({ type: 'custom', duration: 20, align: 'left', lines: ['New Custom Page'] });
    renderPages();
}

function deletePage(index) {
    syncStateFromUI();
    oledSettings.pages.splice(index, 1);
    renderPages();
}

function syncStateFromUI() {
    oledSettings.enable_screen = document.getElementById('enable_screen').checked;
    oledSettings.enable_fan = document.getElementById('enable_fan').checked;
    oledSettings.fan_on_temp = parseFloat(document.getElementById('fan_on').value);
    oledSettings.fan_off_temp = parseFloat(document.getElementById('fan_off').value);
    oledSettings.minimum_fan_run_time_seconds = parseInt(document.getElementById('fan_min_run').value);
    
    oledSettings.brightness = parseInt(document.getElementById('brightness').value);
    oledSettings.rotate_180 = document.getElementById('rotate_180').checked;
    oledSettings.invert_colors = document.getElementById('invert_colors').checked;
    oledSettings.pixel_shift_screensaver = document.getElementById('pixel_shift').checked;
    
    oledSettings.show_warnings = document.getElementById('show_warnings').checked;
    oledSettings.warning_temp = parseFloat(document.getElementById('warn_temp').value);
    
    oledSettings.quiet_hours_enabled = document.getElementById('quiet_enabled').checked;
    oledSettings.quiet_hours_start = document.getElementById('quiet_start').value;
    oledSettings.quiet_hours_end = document.getElementById('quiet_end').value;
    
    oledSettings.page_duration_seconds = parseInt(document.getElementById('global_dur').value);
    oledSettings.network_update_interval_seconds = parseInt(document.getElementById('net_interval').value);
    oledSettings.hardware_update_interval_seconds = parseInt(document.getElementById('hw_interval').value);
    
    (oledSettings.pages || []).forEach((page, i) => {
        const typeSel = document.getElementById(`page_type_${i}`);
        if(!typeSel) return;
        page.type = typeSel.value;
        page.duration = parseInt(document.getElementById(`page_dur_${i}`).value);
        page.align = document.getElementById(`page_align_${i}`).value;
        
        page.show_diagnostic_port = document.getElementById(`page_diagport_${i}`).checked;
        page.show_wifi_port = document.getElementById(`page_wifiport_${i}`).checked;
        page.custom_port = document.getElementById(`page_customport_${i}`).value;
        
        if(page.type === 'custom') {
            page.lines = document.getElementById(`page_lines_${i}`).value.split('\n');
        } else if(page.type === 'network_list') {
            page.show_ap_ip_when_connected = document.getElementById(`page_apip_${i}`).checked;
        } else if(page.type === 'hotspot_details') {
            page.hide_when_connected = document.getElementById(`page_hide_${i}`).checked;
        }
    });
}

function buildPortSuffix(page) {
    let ports = [];
    if(page.show_diagnostic_port && systemStatus.diag_port) ports.push(systemStatus.diag_port);
    if(page.show_wifi_port && systemStatus.wifi_port) ports.push(systemStatus.wifi_port);
    if(page.custom_port && page.custom_port.trim() !== '') ports.push(page.custom_port.trim());
    if(ports.length > 0) return ":" + ports.join("/");
    return "";
}

function renderPreview() {
    if(!window.OLED_INSTALLED) return;
    syncStateFromUI();
    
    const box = document.getElementById('oledPreviewText');
    const oledBox = document.getElementById('oledBoxElem');
    const warnDiv = document.getElementById('previewWarnings');
    
    let previewWarnings = [];
    
    if (oledSettings.invert_colors) {
        oledBox.style.background = '#fff'; oledBox.style.color = '#000';
        box.style.color = '#000';
    } else {
        oledBox.style.background = '#000'; oledBox.style.color = '#fff';
        box.style.color = '#fff';
    }
    
    const exactPreview = document.getElementById('exact_preview_toggle').checked;
    oledBox.style.transform = (oledSettings.rotate_180 && exactPreview) ? 'rotate(180deg)' : 'none';

    if (!oledSettings.pages || oledSettings.pages.length === 0) {
        box.innerHTML = '<div style="text-align:center; padding-top:10px;">No Pages Configured</div>';
        warnDiv.style.display = 'none';
        return;
    }

    let selectedIdx = parseInt(document.getElementById('previewPageSelect').value);
    if (isNaN(selectedIdx) || selectedIdx >= oledSettings.pages.length) selectedIdx = 0;
    let p = oledSettings.pages[selectedIdx];
    
    if(!p) { box.innerHTML = ''; warnDiv.style.display = 'none'; return; }

    if (!oledSettings.enable_screen) previewWarnings.push("OLED Screen is currently globally DISABLED in hardware settings.");
    if (p.duration <= 0) previewWarnings.push("This page is disabled (Duration 0).");
    if (p.type === 'hotspot_details' && systemStatus.hotspot_active === false) {
        previewWarnings.push("Hotspot is currently OFF. This page will be skipped dynamically on the physical screen.");
    }

    if (previewWarnings.length > 0) {
        warnDiv.innerHTML = previewWarnings.map(w => `<div>⚠️ ${w}</div>`).join('');
        warnDiv.style.display = 'block';
    } else {
        warnDiv.style.display = 'none';
    }

    let lines = [];
    let portSuffix = buildPortSuffix(p);
    
    if(p.type === 'network_list') {
        lines = [`wlan0: 192.168.1.10${portSuffix}`, `eth0: 10.0.0.5${portSuffix}`];
    } else if(p.type === 'hotspot_details') {
        lines = [`Pi: ${systemStatus.ap_ssid || "My_Hotspot"}`, `PW: ${systemStatus.ap_pw || "Pass123"}`, `IP: ${systemStatus.ap_ip || "10.42.0.1"}${portSuffix}`];
    } else if(p.type === 'custom') {
        // Fallback port string without leading colon if purely replaced inline
        let inlinePort = portSuffix.startsWith(':') ? portSuffix.substring(1) : "80"; 
        
        lines = (p.lines || []).map(l => l
            .replace('{time}', systemStatus.time || "14:30:00")
            .replace('{temp}', systemStatus.temp !== undefined ? systemStatus.temp : "48.5")
            .replace('{wifi_ssid}', systemStatus.wifi_ssid || "Not Connected")
            .replace('{ap_ip}', systemStatus.ap_ip || "10.42.0.1")
            .replace('{ap_ssid}', systemStatus.ap_ssid || "N/A")
            .replace('{ap_pw}', systemStatus.ap_pw || "N/A")
            .replace('{date}', systemStatus.date || "2026-09-20")
            .replace('{hour}', systemStatus.hour || "14")
            .replace('{minute}', systemStatus.minute || "30")
            .replace('{second}', systemStatus.second || "00")
            .replace('{year}', systemStatus.year || "2026")
            .replace('{month}', systemStatus.month || "09")
            .replace('{day}', systemStatus.day || "20")
            .replace('{web_port}', inlinePort)
        );
    }

    box.style.textAlign = p.align === 'center' ? 'center' : (p.align === 'right' ? 'right' : 'left');
    box.style.width = '100%';
    box.innerHTML = lines.map(l => `<div>${l}</div>`).join('');
}

async function saveOLEDConfig() {
    syncStateFromUI();
    
    let warnings = [];
    if (!oledSettings.enable_screen) warnings.push("• The OLED screen display is disabled.");
    if (!oledSettings.enable_fan) warnings.push("• The PoE Fan automatic control is disabled.");
    if (oledSettings.quiet_hours_enabled) warnings.push(`• Quiet Hours are ON. Screen & Fan will be disabled between ${oledSettings.quiet_hours_start} and ${oledSettings.quiet_hours_end}.`);
    
    if (warnings.length > 0) {
        if (!confirm("WARNING / NOTICE:\n" + warnings.join("\n") + "\n\nAre you sure you want to save and apply these settings?")) return;
    }

    showMessage('oledMsg', 'success', 'Saving and restarting OLED...');
    try {
        const res = await fetch('/api/oled/save', {
            method: 'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify(oledSettings)
        });
        const data = await res.json();
        showMessage('oledMsg', data.status, data.message);
    } catch(e) {
        showMessage('oledMsg', 'error', 'Network error.');
    }
}

async function resetOLEDConfig() {
    if(!confirm("Are you sure you want to completely reset the OLED settings?")) return;
    showMessage('oledMsg', 'success', 'Sending reset command...');
    try {
        const res = await fetch('/api/oled/reset', { method: 'POST' });
        const data = await res.json();
        showMessage('oledMsg', data.status, data.message);
        if(data.status === 'success') setTimeout(() => window.location.reload(), 1500);
    } catch(e) {
        showMessage('oledMsg', 'error', 'Network error.');
    }
}

// Initialization Bootstrapper
window.onload = () => {
    document.getElementById('themeToggle').innerText = document.body.classList.contains('light-mode') ? '🌙 Dark' : '☀️ Light';
    
    // Set up inactivity timers
    document.addEventListener('mousemove', resetInactivityTimer);
    document.addEventListener('keypress', resetInactivityTimer);
    document.addEventListener('click', resetInactivityTimer);
    resetInactivityTimer();
    
    // Determine last open tab
    let active = localStorage.getItem('activeSection') || 'wifi';
    if(active === 'oled' && !window.OLED_INSTALLED) active = 'wifi';
    showSection(active);
    
    // Initialize components
    loadInterfaces();
    initOLEDForm();
};