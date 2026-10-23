// Live updates over the WebSocket; falls back to polling /status while it is down.
let socket = null;
let reconnectDelay = 1000;
let pollTimer = null;

function connect() {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';   // e.g. behind an HTTPS reverse proxy
    socket = new WebSocket(`${scheme}://${window.location.host}${window.location.pathname.replace(/[^/]*$/, '')}ws`);

    socket.onopen = () => {
        reconnectDelay = 1000;
        stopPolling();
        sendEvent('request_status');
        sendEvent('request_logs');
    };

    socket.onclose = () => {
        startPolling();
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 15000);
    };

    socket.onmessage = (event) => {
        if (typeof event.data !== 'string') return;
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (error) {
            return;
        }
        if (data.event === 'stats_update') onStatus(data);
        else if (data.event === 'log_batch') (data.messages || []).forEach(addLogLine);
    };
}

function sendEvent(name) {
    if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ event: name }));
}

function requestStatus() {
    if (socket && socket.readyState === WebSocket.OPEN) sendEvent('request_status');
    else pollStatus();
}

async function pollStatus() {
    try {
        onStatus(await apiGet('/status'));
    } catch (error) {
        // still offline: the connection indicator shows the data age
    }
}

function startPolling() {
    if (!pollTimer) pollTimer = setInterval(pollStatus, 5000);
}

function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
}
