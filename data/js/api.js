const API_BASE = '/api/v1';

async function loadPlugins() {
    try {
        const response = await fetch(`${API_BASE}/plugins`);
        if (!response.ok) throw new Error('Failed to fetch plugins');
        
        const data = await response.json();
        const select = document.getElementById('active-plugin');
        select.innerHTML = '<option value="" disabled>Select a plugin...</option>';
        
        let hasActive = false;
        data.plugins.forEach(p => {
            const option = document.createElement('option');
            option.value = p.id;
            option.textContent = p.name;
            if (p.active) {
                option.selected = true;
                hasActive = true;
            }
            select.appendChild(option);
        });
        
        if (!hasActive) {
            select.selectedIndex = 0;
        }
    } catch (error) {
        addLogMessage(`Error loading plugins: ${error.message}`);
    }
}

async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE}/config`);
        if (!response.ok) throw new Error('Failed to fetch configuration');
        
        const config = await response.json();
        
        document.getElementById('chip-id').textContent = 'ID: ' + (config.chip_id || '');
        document.getElementById('plugin-name').textContent = config.active_plugin || '';
        
        document.getElementById('device-name').value = config.device_name || '';
        document.getElementById('mqtt-host').value = config.mqtt_host || '';
        document.getElementById('mqtt-port').value = config.mqtt_port || '1883';
        document.getElementById('mqtt-user').value = config.mqtt_user || '';
        document.getElementById('mqtt-pass').value = config.mqtt_pass || '';
        document.getElementById('mqtt-device').value = config.mqtt_device || '';
        document.getElementById('mqtt-topic').value = config.mqtt_topic || '';
        
        // Build dynamic plugin parameter fields
        renderPluginParams(config.plugin_params);
        
        addLogMessage('Configuration loaded');
    } catch (error) {
        addLogMessage(`Error loading configuration: ${error.message}`);
    }
}

async function loadPluginParams(pluginId) {
    const container = document.getElementById('plugin-params');
    
    if (!pluginId) {
        container.innerHTML = '<p class="form-text">No plugin selected</p>';
        return;
    }
    
    // Show spinner while loading
    container.innerHTML = '<div class="loading-container"><div class="spinner"></div><span>Loading...</span></div>';
    
    try {
        const response = await fetch(`${API_BASE}/config?plugin=${pluginId}`);
        if (!response.ok) throw new Error('Failed to fetch plugin configuration');
        
        const config = await response.json();
        renderPluginParams(config.plugin_params);
    } catch (error) {
        container.innerHTML = '<p class="form-text">Error loading plugin parameters</p>';
        addLogMessage(`Error loading plugin parameters: ${error.message}`);
    }
}

function renderPluginParams(plugin_params) {
    const container = document.getElementById('plugin-params');
    container.innerHTML = '';
    
    if (plugin_params && plugin_params.length > 0) {
        plugin_params.forEach(param => {
            const group = document.createElement('div');
            group.className = 'form-group';
            
            const label = document.createElement('label');
            label.setAttribute('for', 'plugin-' + param.key);
            label.textContent = param.label + (param.required ? ' *' : '') + ':';
            
            const input = document.createElement('input');
            input.type = param.type || 'text';
            input.id = 'plugin-' + param.key;
            input.name = param.key;
            input.value = param.value || param.default || '';
            if (param.required) input.required = true;
            
            group.appendChild(label);
            group.appendChild(input);
            container.appendChild(group);
        });
    } else {
        container.innerHTML = '<p class="form-text">No additional parameters for this plugin</p>';
    }
}

async function saveConfig() {
    try {
        const form = document.getElementById('config-form');
        const formData = new FormData(form);
        const config = {};
        
        for (const [key, value] of formData.entries()) {
            config[key] = value;
        }
        
        const response = await fetch(`${API_BASE}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        if (!response.ok) throw new Error('Failed to save configuration');
        
        addLogMessage('Configuration saved');
        
        if (confirm('Configuration saved. Restart device to apply changes?')) {
            restartDevice();
        }
    } catch (error) {
        addLogMessage(`Error saving configuration: ${error.message}`);
    }
}

function uploadBinary() {
    const fileInput = document.getElementById('upload-file');
    const target = document.getElementById('upload-target').value;
    const status = document.getElementById('upload-status');

    if (!fileInput.files.length) {
        status.textContent = 'Select a .bin file first';
        return;
    }

    const file = fileInput.files[0];
    const form = new FormData();
    form.append('update', file, file.name);

    // XMLHttpRequest instead of fetch: it reports upload progress
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/upload?target=${encodeURIComponent(target)}`);

    xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) return;
        const percent = Math.round((event.loaded / event.total) * 100);
        status.textContent = `Uploading ${target}: ${percent}%`;
    };

    xhr.onload = () => {
        if (xhr.status === 200) {
            status.textContent = `${target} flashed - device is restarting`;
            addLogMessage(`${target} uploaded, device restarting`);
        } else {
            status.textContent = `Upload failed (HTTP ${xhr.status})`;
        }
    };

    xhr.onerror = () => {
        status.textContent = 'Upload failed - connection lost';
    };

    status.textContent = `Uploading ${target}...`;
    xhr.send(form);
}

async function restartDevice() {
    if (confirm('Are you sure you want to restart?')) {
        try {
            await fetch(`${API_BASE}/restart`, { method: 'POST' });
            addLogMessage('Device is restarting...');
            setTimeout(() => window.location.reload(), 10000);
        } catch (error) {
            addLogMessage(`Error: ${error.message}`);
        }
    }
}

async function resetDevice() {
    if (confirm('WARNING: This will reset ALL settings. Continue?')) {
        try {
            await fetch(`${API_BASE}/reset`, { method: 'POST' });
            addLogMessage('Device resetting...');
            setTimeout(() => { window.location.href = "http://192.168.4.1"; }, 5000);
        } catch (error) {
            addLogMessage(`Error: ${error.message}`);
        }
    }
}
