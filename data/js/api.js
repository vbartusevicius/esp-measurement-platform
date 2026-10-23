const API_BASE = 'api/v1';   // relative, so the UI also works behind a reverse-proxy path

async function apiGet(path) {
    const response = await fetch(API_BASE + path, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
}

async function apiPost(path, body) {
    const options = { method: 'POST' };
    if (body !== undefined) {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify(body);
    }
    const response = await fetch(API_BASE + path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
    return data;
}

function uploadBinary() {
    const fileInput = document.getElementById('upload-file');
    const status = document.getElementById('upload-status');
    const progress = document.getElementById('upload-progress');

    if (!fileInput.files.length) {
        status.textContent = 'Choose a .bin file first.';
        return;
    }
    if (!confirm(`Install ${fileInput.files[0].name}? The device restarts afterwards.`)) return;

    const form = new FormData();
    form.append('update', fileInput.files[0], fileInput.files[0].name);

    // XMLHttpRequest instead of fetch: it reports upload progress
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/upload`);
    progress.hidden = false;
    progress.value = 0;
    xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) return;
        progress.value = Math.round((event.loaded / event.total) * 100);
        status.textContent = `Uploading… ${progress.value}%`;
    };
    xhr.onload = () => {
        progress.hidden = true;
        let reason = '';
        try { reason = JSON.parse(xhr.responseText).message || ''; } catch (e) { /* not JSON */ }
        status.textContent = xhr.status === 200
            ? 'Installed. The device is restarting, this page reconnects by itself.'
            : `Upload failed: ${reason || `HTTP ${xhr.status}`}.`;
    };
    xhr.onerror = () => {
        progress.hidden = true;
        status.textContent = 'Upload failed: connection lost.';
    };
    status.textContent = 'Uploading…';
    xhr.send(form);
}

async function restartDevice() {
    if (!confirm('Restart the device now?')) return;
    try {
        await apiPost('/restart');
        showToast('Restarting… this page reconnects by itself.');
    } catch (error) {
        showToast(`Restart failed: ${error.message}`);
    }
}

async function resetDevice() {
    const answer = prompt('Factory reset erases WiFi, MQTT and sensor settings.\nType RESET to confirm.');
    if (answer !== 'RESET') return;
    try {
        await apiPost('/reset');
        showToast('Resetting. Join the device\'s setup WiFi to configure it again.');
    } catch (error) {
        showToast(`Reset failed: ${error.message}`);
    }
}
