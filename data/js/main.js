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
    document.getElementById('active-plugin').addEventListener('change', (e) => {
        addLogMessage('Plugin changed - setting fields updated');
        loadPluginParams(e.target.value);
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
    // System info
    setTextContent('wifi-network', data.wifi_network || 'Unknown');
    setTextContent('wifi-signal', data.wifi_signal ? data.wifi_signal + ' dBm' : 'N/A');
    setTextContent('ip-address', data.ip_address || 'Unknown');
    setTextContent('uptime', data.uptime || 'N/A');
    setTextContent('free-heap', data.free_heap ? Math.round(data.free_heap / 1024) + ' KB' : 'N/A');
    
    const mqttEl = document.getElementById('mqtt-status');
    if (mqttEl && data.mqtt_connected !== undefined) {
        mqttEl.textContent = data.mqtt_connected ? 'Connected' : 'Disconnected';
        mqttEl.className = 'stat-value ' + (data.mqtt_connected ? 'connected' : 'disconnected');
    }
    
    // Plugin stats - rendered generically from stats array
    const statsContainer = document.getElementById('plugin-stats');
    if (!data.stats || !Array.isArray(data.stats)) return;
    statsContainer.innerHTML = '';
    
    data.stats.forEach(stat => {
        addStatItem(statsContainer, stat.label, stat.value, stat.primary);
        
        if (stat.render === 'progress') {
            const indicator = document.createElement('div');
            indicator.className = 'water-indicator';
            const fill = document.createElement('div');
            fill.className = 'water-fill';
            fill.style.height = (stat.numeric * 100) + '%';
            fill.classList.add(stat.numeric < 0.25 ? 'low' : stat.numeric < 0.75 ? 'medium' : 'high');
            indicator.appendChild(fill);
            statsContainer.appendChild(indicator);
        }
    });
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
