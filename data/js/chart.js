let chartTimer;

function initChart() {
    fetchChart();
    chartTimer = setInterval(fetchChart, 60000);
}

async function fetchChart() {
    const panel = document.getElementById('chart-panel');
    try {
        const response = await fetch('/api/v1/chart');
        if (!response.ok) return;

        const data = await response.json();
        if (!data.points || data.points.length < 2) return;

        panel.style.display = '';
        let title = 'History';
        if (data.unit) title += ` (${data.unit})`;
        if (data.span_seconds) title += ` · ${data.span_seconds}s per point`;
        document.getElementById('chart-title').textContent = title;

        drawChart(data.points);
    } catch (error) {
        panel.style.display = 'none';
    }
}

function drawChart(points) {
    const canvas = document.getElementById('history-chart');
    const ctx = canvas.getContext('2d');

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = 120;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    const primary = getComputedStyle(document.documentElement).getPropertyValue('--primary-color').trim() || '#2196F3';
    const text = getComputedStyle(document.documentElement).getPropertyValue('--text-color').trim() || '#333';

    const max = Math.max(...points, 0.001);
    const barWidth = Math.max(1, Math.floor(width / points.length) - 1);

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = primary;

    points.forEach((v, i) => {
        const h = (v / max) * (height - 18);
        ctx.fillRect(i * (barWidth + 1), height - h, barWidth, h);
    });

    ctx.fillStyle = text;
    ctx.font = '10px sans-serif';
    ctx.fillText(max.toFixed(2), 2, 10);
    ctx.fillText('0', 2, height - 2);
}
