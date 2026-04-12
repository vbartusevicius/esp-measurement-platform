document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    loadPlugins();
    loadConfig();
    
    document.getElementById('config-form').addEventListener('submit', (e) => {
        e.preventDefault();
        saveConfig();
    });
    
    document.getElementById('restart-btn').addEventListener('click', restartDevice);
    document.getElementById('reset-btn').addEventListener('click', resetDevice);
    
    // Reload plugin params when plugin selection changes
    document.getElementById('active-plugin').addEventListener('change', () => {
        addLogMessage('Plugin changed - save and restart to apply');
    });
    
    setupConfigToggle();
});

function setupConfigToggle() {
    const toggleBtn = document.getElementById('config-toggle');
    const configPanel = document.querySelector('.config-panel');
    const toggleIcon = document.querySelector('.toggle-icon');
    
    if (toggleBtn && configPanel) {
        toggleBtn.addEventListener('click', () => {
            configPanel.classList.toggle('expanded');
            toggleIcon.textContent = configPanel.classList.contains('expanded') ? '-' : '+';
        });
    }
}

function updateUI(data) {
    // Network info
    setTextContent('wifi-network', data.wifi_network || 'Unknown');
    setTextContent('wifi-signal', data.wifi_signal ? data.wifi_signal + ' dBm' : 'N/A');
    setTextContent('ip-address', data.ip_address || 'Unknown');
    setTextContent('uptime', data.uptime || 'N/A');
    setTextContent('free-heap', data.free_heap ? Math.round(data.free_heap / 1024) + ' KB' : 'N/A');
    
    // Sensor connected
    const sensorEl = document.getElementById('sensor-status');
    if (sensorEl && data.sensor_connected !== undefined) {
        sensorEl.textContent = data.sensor_connected ? 'Connected' : 'Disconnected';
        sensorEl.className = 'stat-value ' + (data.sensor_connected ? 'connected' : 'disconnected');
    }
    
    // Plugin-specific stats
    const statsContainer = document.getElementById('plugin-stats');
    statsContainer.innerHTML = '';
    
    // Distance meters
    if (data.measured_distance !== undefined) {
        addStatItem(statsContainer, 'Distance', formatNumber(data.measured_distance, 3) + ' m', true);
    }
    if (data.relative_distance !== undefined) {
        const percent = (data.relative_distance * 100).toFixed(1) + '%';
        addStatItem(statsContainer, 'Level', percent, true);
        
        // Water indicator
        const indicator = document.createElement('div');
        indicator.className = 'water-indicator';
        const fill = document.createElement('div');
        fill.className = 'water-fill';
        fill.style.height = (data.relative_distance * 100) + '%';
        
        const val = data.relative_distance;
        fill.classList.add(val < 0.25 ? 'low' : val < 0.75 ? 'medium' : 'high');
        
        indicator.appendChild(fill);
        statsContainer.appendChild(indicator);
    }
    if (data.absolute_distance !== undefined) {
        addStatItem(statsContainer, 'Depth', formatNumber(data.absolute_distance, 2) + ' m', false);
    }
    
    // Radiation counter
    if (data.cpm !== undefined) {
        addStatItem(statsContainer, 'CPM', String(data.cpm), true);
    }
    if (data.dose !== undefined) {
        addStatItem(statsContainer, 'Dose', formatNumber(data.dose, 2) + ' µSv/h', true);
    }
}

function addStatItem(container, label, value, primary) {
    const div = document.createElement('div');
    div.className = 'stat-item' + (primary ? ' primary' : ' small');
    div.innerHTML = `<span class="stat-label">${label}:</span><span class="stat-value">${value}</span>`;
    container.appendChild(div);
}

function formatNumber(val, decimals) {
    if (val === undefined || val === null || isNaN(val)) return 'N/A';
    return Number(val).toFixed(decimals);
}

function setTextContent(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function addLogMessage(message, autoScroll = false) {
    const logContainer = document.getElementById('log-container');
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    
    if (!message.includes('[') || message.startsWith('[')) {
        entry.textContent = message;
    } else {
        const timestamp = new Date().toLocaleTimeString();
        entry.textContent = `[${timestamp}] ${message}`;
    }
    
    logContainer.appendChild(entry);
    
    if (autoScroll) {
        logContainer.scrollTop = logContainer.scrollHeight;
    }
    
    while (logContainer.children.length > 200) {
        logContainer.removeChild(logContainer.children[0]);
    }
}
