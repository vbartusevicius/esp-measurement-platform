const API_BASE = '/api/v1';

async function loadPlugins() {
    try {
        const response = await fetch(`${API_BASE}/plugins`);
        if (!response.ok) throw new Error('Failed to fetch plugins');
        
        const data = await response.json();
        const select = document.getElementById('active-plugin');
        select.innerHTML = '';
        
        data.plugins.forEach(p => {
            const option = document.createElement('option');
            option.value = p.id;
            option.textContent = p.name;
            if (p.active) option.selected = true;
            select.appendChild(option);
        });
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
        
        document.getElementById('mqtt-host').value = config.mqtt_host || '';
        document.getElementById('mqtt-port').value = config.mqtt_port || '1883';
        document.getElementById('mqtt-user').value = config.mqtt_user || '';
        document.getElementById('mqtt-pass').value = config.mqtt_pass || '';
        document.getElementById('mqtt-device').value = config.mqtt_device || '';
        document.getElementById('mqtt-topic').value = config.mqtt_topic || '';
        
        // Build dynamic plugin parameter fields
        const container = document.getElementById('plugin-params');
        container.innerHTML = '';
        
        if (config.plugin_params && config.plugin_params.length > 0) {
            config.plugin_params.forEach(param => {
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
        
        addLogMessage('Configuration loaded');
    } catch (error) {
        addLogMessage(`Error loading configuration: ${error.message}`);
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
