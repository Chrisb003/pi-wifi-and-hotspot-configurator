// ==============================================================================
// SPA NAVIGATION & TIMEOUT LOGIC
// ==============================================================================
let inactivityTimer;

/**
 * Resets the 30-minute inactivity timer.
 * Triggered by mouse movements, clicks, and key presses.
 * If the user is idle for 30 minutes, it displays a blur overlay.
 */
function resetInactivityTimer() {
    clearTimeout(inactivityTimer);
    const overlay = document.getElementById('timeoutOverlay');
    
    // Only execute the timer logic if the overlay actually exists (user is logged in)
    if (overlay) {
        overlay.style.display = 'none';
        
        // 30 minutes = 30 * 60 * 1000 = 1,800,000 ms
        inactivityTimer = setTimeout(() => {
            overlay.style.display = 'flex';
        }, 1800000); 
    }
}

/**
 * Handles the Single Page Application (SPA) navigation.
 * Hides all sections, removes active classes from the menu, and then
 * displays the requested section, saving the state to local storage.
 * 
 * @param {string} sectionId - The ID suffix of the section to show (e.g., 'wifi', 'oled')
 */
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

/**
 * Toggles the web interface between Dark and Light mode.
 * Saves the user's preference in the browser's localStorage so it persists across reloads.
 */
function toggleTheme() {
    const isLight = document.body.classList.toggle('light-mode');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    document.getElementById('themeToggle').innerText = isLight ? '🌙 Dark' : '☀️ Light';
}

// ==============================================================================
// UPDATE MANAGER LOGIC
// ==============================================================================

/**
 * Fetches the latest version data and changelogs from the backend API.
 * Displays the Update Modal and builds side-by-side columns comparing
 * the local installed versions to the remote GitHub versions.
 */
async function checkForUpdates() {
    const modal = document.getElementById('updateModal');
    const content = document.getElementById('updateBody');
    const updateBtn = document.getElementById('runUpdateBtn');
    
    // Show modal in a loading state
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
        
        // --- WiFi App Column ---
        html += `<div class="update-col">
                    <h3 style="margin-top:0;">WiFi App</h3>
                    <div style="font-size: 13px; margin-bottom: 15px;">
                        Installed: <b>v${data.wifi.local_version}</b> <br>
                        Latest: <b>v${data.wifi.target_version}</b>
                    </div>`;
        if (data.wifi.update_available) updatesAvailable.push('wifi');
        html += buildChangelogHtml(data.wifi.changelog);
        html += `</div>`;

        // --- OLED Monitor Column (Only show if installed) ---
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

        // If updates are found, show the install button and attach the target components
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

/**
 * Transforms the parsed JSON changelog data into formatted HTML.
 * 
 * @param {Array} changelogData - The structured array of releases and bullet points.
 * @returns {string} - Formatted HTML string ready to be injected into the DOM.
 */
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

/**
 * Triggers the backend OTA update process for the selected components.
 * Displays a loading screen during the download and reloads the page upon success.
 * 
 * @param {Array} components - List of components to update (e.g., ['wifi', 'oled'])
 */
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

/**
 * Closes the update modal.
 */
function closeModal() {
    document.getElementById('updateModal').style.display = 'none';
}

// ==============================================================================
// WIFI & HOTSPOT LOGIC
// ==============================================================================
let interfacesData = [];

/**
 * Fetches available network interfaces from the backend.
 * Populates the dropdown menus for both the WiFi scanner and the Hotspot configurator.
 */
async function loadInterfaces() {
    try {
        const res = await fetch('/interfaces');
        const data = await res.json();
        interfacesData = data.interfaces;
        
        const wifiSelect = document.getElementById('wifiInterfaceSelect');
        const hotspotSelect = document.getElementById('hotspotInterfaceSelect');
        
        wifiSelect.innerHTML = '';
        if(hotspotSelect) hotspotSelect.innerHTML = '';
        
        // Hide the dropdowns entirely if no network interfaces are found
        if (data.interfaces.length === 0) { 
            wifiSelect.style.display = 'none'; 
            if(hotspotSelect) { 
                hotspotSelect.style.display = 'none'; 
                document.getElementById('ifaceLabel').style.display = 'none'; 
            }
            return; 
        }
        
        // Populate dropdown options
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
        
        // Set defaults based on active system states
        if (data.default) wifiSelect.value = data.default;
        
        if (hotspotSelect && window.HOTSPOT_IFACE) {
            if (Array.from(hotspotSelect.options).some(o => o.value === window.HOTSPOT_IFACE)) {
                hotspotSelect.value = window.HOTSPOT_IFACE;
            } else if (data.default) {
                hotspotSelect.value = data.default;
            }
        }
        
        checkWarning();
        
        // Hide dropdowns if there is only 1 interface available (no choice to be made)
        if (data.interfaces.length <= 1) {
            wifiSelect.style.display = 'none';
            if(hotspotSelect) { 
                hotspotSelect.style.display = 'none'; 
                document.getElementById('ifaceLabel').style.display = 'none'; 
            }
        }
    } catch (err) {}
}

/**
 * Checks if the user is trying to scan on an interface that is currently broadcasting a Hotspot.
 * If so, displays a warning block.
 */
function checkWarning() {
    const selected = document.getElementById('wifiInterfaceSelect').value;
    const iface = interfacesData.find(i => i.name === selected);
    const warning = document.getElementById('hotspotWarning');
    if (iface && iface.is_hotspot) warning.classList.remove('hidden');
    else warning.classList.add('hidden');
}

/**
 * Requests the backend to perform an nmcli WiFi scan on the chosen interface.
 * Updates the network dropdown list upon success.
 */
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
                option.value = net.ssid; 
                option.innerText = `${net.ssid} (Signal: ${net.signal}%)`;
                ssidSelect.appendChild(option);
            });
            connectForm.classList.remove('hidden');
            scanBtn.innerText = "Refresh Networks";
        } else {
            showMessage('wifiMsg', 'error', data.message); 
            scanBtn.innerText = "Search for WiFi Networks";
        }
    } catch (err) { 
        showMessage('wifiMsg', 'error', 'Network error.'); 
        scanBtn.innerText = "Search for WiFi Networks"; 
    }
    
    scanBtn.disabled = false;
}

/**
 * Sends a connection request to the backend with the selected SSID and Password.
 */
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
        
        if (data.status === 'success') { 
            showMessage('wifiMsg', 'success', data.message); 
            document.getElementById('password').value = ''; 
            loadInterfaces(); 
        } else { 
            showMessage('wifiMsg', 'error', 'Failed: ' + data.message); 
        }
    } catch (err) { 
        showMessage('wifiMsg', 'error', 'Network error.'); 
    }
    
    connectBtn.innerText = "Connect"; connectBtn.disabled = false;
}

/**
 * Disconnects the selected network interface.
 */
async function disconnectNetwork() {
    const btn = document.getElementById('disconnectBtn');
    const device = document.getElementById('wifiInterfaceSelect').value;
    
    btn.innerText = "Disconnecting..."; btn.disabled = true; showMessage('wifiMsg', '', '');
    
    try {
        const response = await fetch('/disconnect', { 
            method: 'POST', headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify({ device }) 
        });
        const data = await response.json();
        
        if (data.status === 'success') { 
            showMessage('wifiMsg', 'success', data.message); 
            loadInterfaces(); 
        } else { 
            showMessage('wifiMsg', 'error', 'Failed: ' + data.message); 
        }
    } catch (err) { 
        showMessage('wifiMsg', 'error', 'Network error.'); 
    }
    
    btn.innerText = "Disconnect Current WiFi"; btn.disabled = false;
}

/**
 * Helper function to inject success/error alert boxes into specific areas of the DOM.
 * Automatically clears success messages after 4 seconds.
 * 
 * @param {string} targetId - The HTML ID of the message container to inject into.
 * @param {string} type - 'success' or 'error' class names.
 * @param {string} text - The message body to display.
 */
function showMessage(targetId, type, text) {
    const msgDiv = document.getElementById(targetId);
    if (!text) { msgDiv.className = 'hidden'; return; }
    
    msgDiv.innerText = text; 
    msgDiv.className = type;
    msgDiv.style.display = 'block';
    
    if(type === 'success') {
        setTimeout(() => msgDiv.style.display = 'none', 4000);
    }
}

// ==============================================================================
// OLED LOGIC (Only runs if the OLED physical screen is installed)
// ==============================================================================
let oledSettings = {};
let systemStatus = {};

/**
 * Continuously polls the backend to retrieve live system stats (temperature, ports, IPs).
 * Updates the Configuration Guide visual variables and calls renderPreview() to simulate the screen.
 */
async function fetchSystemStatus() {
    try {
        const res = await fetch('/api/system/status');
        systemStatus = await res.json();
        
        // Update live header badge
        if(systemStatus.temp !== undefined) {
            document.getElementById('liveTemp').innerText = `Pi: ${systemStatus.temp.toFixed(1)}°C`;
        }
        
        // Update documentation variable cheat-sheet
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

/**
 * Initializes the OLED Web form logic. 
 * Parses the raw settings.json payload injected into window.OLED_SETTINGS_JSON 
 * and applies all values to the global settings form inputs.
 */
function initOLEDForm() {
    if(!window.OLED_INSTALLED) return;
    
    oledSettings = window.OLED_SETTINGS_JSON || {};
    
    // Safety fallback defaults
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

    // Map JSON to hardware inputs
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
    
    // Attach live listeners for preview manipulation
    const inputs = document.querySelectorAll('#section-oled input');
    inputs.forEach(i => {
        i.addEventListener('input', () => {
            if(i.id === 'brightness') document.getElementById('brightness_val').innerText = i.value;
            renderPreview();
        });
    });
    document.getElementById('pagesContainer').addEventListener('input', renderPreview);
    
    // Start system status polling
    fetchSystemStatus();
    setInterval(fetchSystemStatus, 5000);
}

/**
 * Dynamically builds the HTML cards for every page defined in the OLED's 'pages' array.
 * Rebuilds the preview selector dropdown simultaneously.
 */
function renderPages() {
    const container = document.getElementById('pagesContainer');
    container.innerHTML = '';
    
    if(!oledSettings.pages || oledSettings.pages.length === 0) {
        container.innerHTML = '<div style="text-align:center; color:#888; font-size:14px; padding:20px;">No pages configured. Click Add Page.</div>';
    }

    // Populate preview dropdown
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

    // Build UI blocks per page
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

        // Port appending toggles
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

/**
 * Changes a page's layout type, applies standard defaults to custom lines if needed, and re-renders.
 */
function updatePageType(index, newType) {
    syncStateFromUI();
    oledSettings.pages[index].type = newType;
    if(newType === 'custom' && !oledSettings.pages[index].lines) oledSettings.pages[index].lines = ['Time: {time}', 'Temp: {temp}C'];
    renderPages();
}

/**
 * Adds a new default custom text page to the end of the OLED configuration array.
 */
function addPage() {
    syncStateFromUI();
    if(!oledSettings.pages) oledSettings.pages = [];
    oledSettings.pages.push({ type: 'custom', duration: 20, align: 'left', lines: ['New Custom Page'] });
    renderPages();
}

/**
 * Deletes an existing OLED page by index.
 */
function deletePage(index) {
    syncStateFromUI();
    oledSettings.pages.splice(index, 1);
    renderPages();
}

/**
 * Scrapes every active form input on the UI to build the exact JavaScript object 
 * representation of what will be written to 'settings.json'.
 */
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

/**
 * Helper function to dynamically construct the ":80/8080/9000" port string 
 * based on the active toggles for the specific page being processed.
 * 
 * @param {Object} page - The specific page configuration mapping object
 * @returns {string} - The built suffix string, or empty.
 */
function buildPortSuffix(page) {
    let ports = [];
    if(page.show_diagnostic_port && systemStatus.diag_port) ports.push(systemStatus.diag_port);
    if(page.show_wifi_port && systemStatus.wifi_port) ports.push(systemStatus.wifi_port);
    if(page.custom_port && page.custom_port.trim() !== '') ports.push(page.custom_port.trim());
    
    if(ports.length > 0) return ":" + ports.join("/");
    return "";
}

/**
 * Paints the 128x32 OLED preview box in the UI.
 * Applies visual overrides (rotation, inversion, opacity) and simulates text parsing.
 * Analyzes the layout for logical warnings (like attempting to render a hotspot page when the hotspot is down).
 */
function renderPreview() {
    if(!window.OLED_INSTALLED) return;
    syncStateFromUI();
    
    const box = document.getElementById('oledPreviewText');
    const oledBox = document.getElementById('oledBoxElem');
    const warnDiv = document.getElementById('previewWarnings');
    
    let previewWarnings = [];
    
    // Apply user color themes to the preview
    if (oledSettings.invert_colors) {
        oledBox.style.background = '#fff'; oledBox.style.color = '#000';
        box.style.color = '#000';
    } else {
        oledBox.style.background = '#000'; oledBox.style.color = '#fff';
        box.style.color = '#fff';
    }
    
    // Rotate canvas entirely if standard preview exact rotation is checked
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

    // Logical constraint warnings calculation
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

    // Render text output
    let lines = [];
    let portSuffix = buildPortSuffix(p);
    
    if(p.type === 'network_list') {
        lines = [`wlan0: 192.168.1.10${portSuffix}`, `eth0: 10.0.0.5${portSuffix}`];
    } else if(p.type === 'hotspot_details') {
        lines = [`Pi: ${systemStatus.ap_ssid || "My_Hotspot"}`, `PW: ${systemStatus.ap_pw || "Pass123"}`, `IP: ${systemStatus.ap_ip || "10.42.0.1"}${portSuffix}`];
    } else if(p.type === 'custom') {
        // Fallback port string without leading colon if the user relies purely on {web_port} inline
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

/**
 * Validates system states, calculates warnings, and issues the JSON POST request 
 * to save changes to the physical OLED monitor file.
 */
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

/**
 * Issues a POST command to wipe the OLED configuration back to factory settings.
 * Refreshes the page upon success.
 */
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

/**
 * Toggles the visibility of a password input field between 'password' and 'text'.
 * 
 * @param {string} inputId - The ID of the target password input element.
 * @param {HTMLElement} btn - The toggle button element itself.
 */
function togglePasswordVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    if (input.type === 'password') {
        input.type = 'text';
        btn.innerText = '🙈'; // Switch to closed eye symbol when visible
    } else {
        input.type = 'password';
        btn.innerText = '👁️'; // Switch back to open eye symbol
    }
}

// ==============================================================================
// INITIALIZATION BOOTSTRAPPER
// ==============================================================================
/**
 * Main application bootstrapper. Runs immediately when the DOM completes loading.
 * Configures event listeners, determines the active tab, and kicks off async data requests.
 */
window.onload = () => {
    // Sync the dark/light mode toggle text immediately upon loading
    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) themeBtn.innerText = document.body.classList.contains('light-mode') ? '🌙 Dark' : '☀️ Light';
    
    // Set up inactivity timers to monitor user engagement across the document
    document.addEventListener('mousemove', resetInactivityTimer);
    document.addEventListener('keypress', resetInactivityTimer);
    document.addEventListener('click', resetInactivityTimer);
    resetInactivityTimer();
    
    // Check if the user is fully logged in by looking for an SPA navigation wrapper
    if (document.getElementById('section-wifi')) {
        let active = localStorage.getItem('activeSection') || 'wifi';
        if(active === 'oled' && !window.OLED_INSTALLED) active = 'wifi';
        showSection(active);
        
        loadInterfaces();
        initOLEDForm();
    }
};