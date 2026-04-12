let socket;
let reconnectInterval;

function initWebSocket() {
    connect();
}

function connect() {
    if (socket) {
        socket.close();
    }
    
    socket = new WebSocket(`ws://${window.location.host}/ws`);
    
    socket.onopen = () => {
        addLogMessage('WebSocket connected');
        clearInterval(reconnectInterval);
        requestStatus();
        requestLogHistory();
    };
    
    socket.onclose = () => {
        addLogMessage('WebSocket disconnected');
        reconnectInterval = setInterval(() => connect(), 5000);
    };
    
    socket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        } catch (error) {
            console.error('Error parsing message:', error);
        }
    };
}

function handleWebSocketMessage(data) {
    switch (data.event) {
        case 'log_update':
            addLogMessage(data.message);
            break;
        case 'log_batch':
            if (data.messages && Array.isArray(data.messages)) {
                const logContainer = document.getElementById('log-container');
                data.messages.forEach(message => {
                    if (message) addLogMessage(message, false);
                });
                logContainer.scrollTop = logContainer.scrollHeight;
            }
            break;
        case 'stats_update':
            updateUI(data);
            break;
    }
}

function requestStatus() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ event: 'request_status' }));
    }
}

function requestLogHistory() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ event: 'request_logs' }));
    }
}
