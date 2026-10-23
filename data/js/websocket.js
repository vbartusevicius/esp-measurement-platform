// Live updates over the WebSocket; falls back to polling /status while it is down.
let socket = null;
let reconnectDelay = 1000;
let pollTimer = null;

function connect() {
    socket = new WebSocket(`ws://${window.location.host}/ws`);

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
        else if (data.event === 'log_update') addLogLine(data.message);
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
