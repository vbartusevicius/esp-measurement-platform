// Dependency-free SVG time-series chart: line or bars, limit lines, hover readout.
const SVG_NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs, text) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    if (text !== undefined) node.textContent = text;
    return node;
}

// isFinite(null) is true in JS: disabled limits arrive as null, so check the type.
function isNum(v) { return typeof v === 'number' && Number.isFinite(v); }

function formatDuration(seconds) {
    seconds = Math.max(0, Math.round(seconds));
    if (seconds < 90) return `${seconds} s`;
    if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
    if (seconds < 172800) return `${Math.round(seconds / 3600)} h`;
    return `${Math.round(seconds / 86400)} d`;
}

function niceStep(range, count) {
    const raw = range / count;
    const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / magnitude;
    return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * magnitude;
}

// opts: values[], stepSec, unit, decimals, limits {low, high}, yMin, yMax, bars
function renderChart(container, opts) {
    container.innerHTML = '';
    const width = container.clientWidth || 600;
    const height = container.clientHeight || 170;
    const pad = { left: 44, right: 12, top: 12, bottom: 22 };
    const svg = svgEl('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img' });
    container.appendChild(svg);

    const values = opts.values || [];
    const finite = values.filter(isNum);
    if (finite.length < 2) {
        svg.appendChild(svgEl('text', { x: width / 2, y: height / 2, 'text-anchor': 'middle', class: 'empty' },
            opts.emptyText || 'Collecting data…'));
        return;
    }

    const limits = opts.limits || {};
    const extent = finite.slice();
    if (isNum(limits.low)) extent.push(limits.low);
    if (isNum(limits.high)) extent.push(limits.high);
    let lo = isNum(opts.yMin) ? opts.yMin : Math.min(...extent);
    let hi = isNum(opts.yMax) ? opts.yMax : Math.max(...extent);
    if (!isNum(opts.yMin) || !isNum(opts.yMax)) {
        const span = (hi - lo) || Math.abs(hi) || 1;
        if (!isNum(opts.yMin)) lo -= span * 0.1;
        if (!isNum(opts.yMax)) hi += span * 0.1;
        if (opts.bars && lo > 0 && !isNum(opts.yMin)) lo = 0;
    }
    if (hi - lo < 1e-9) hi = lo + 1;

    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;
    const n = values.length;
    const x = i => pad.left + (n === 1 ? plotW : (i / (n - 1)) * plotW);
    const y = v => pad.top + (1 - (v - lo) / (hi - lo)) * plotH;
    const decimals = opts.decimals || 0;

    // grid + y labels
    const step = niceStep(hi - lo, 4);
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
        svg.appendChild(svgEl('line', { x1: pad.left, x2: width - pad.right, y1: y(v), y2: y(v), class: 'grid' }));
        svg.appendChild(svgEl('text', { x: pad.left - 6, y: y(v) + 4, 'text-anchor': 'end', class: 'axis' },
            v.toFixed(step < 1 ? Math.min(3, Math.max(decimals, Math.ceil(-Math.log10(step)))) : 0)));
    }

    // x labels: relative time
    const total = (n - 1) * opts.stepSec;
    [[0, `−${formatDuration(total)}`, 'start'], [0.5, `−${formatDuration(total / 2)}`, 'middle'], [1, 'now', 'end']]
        .forEach(([f, label, anchor]) => svg.appendChild(svgEl('text',
            { x: pad.left + f * plotW, y: height - 4, 'text-anchor': anchor, class: 'axis' }, label)));

    if (opts.bars) {
        const bw = Math.max(1, plotW / n - 1);
        values.forEach((v, i) => {
            if (v === null || !isNum(v)) return;
            const top = y(Math.max(v, lo));
            svg.appendChild(svgEl('rect', { x: pad.left + i * (plotW / n), y: top, width: bw, height: Math.max(1, y(lo) - top), class: 'bar' }));
        });
    } else {
        let d = '';
        values.forEach((v, i) => {
            if (v === null || !isNum(v)) return;
            d += (d ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1);
        });
        const firstIdx = values.findIndex(v => v !== null && isNum(v));
        svg.appendChild(svgEl('path', { d: `${d}L${x(n - 1)} ${y(lo)}L${x(firstIdx)} ${y(lo)}Z`, class: 'area' }));
        svg.appendChild(svgEl('path', { d, class: 'series' }));
    }

    [['low', 'MIN'], ['high', 'MAX']].forEach(([key, label]) => {
        const v = limits[key];
        if (!isNum(v) || v < lo || v > hi) return;
        svg.appendChild(svgEl('line', { x1: pad.left, x2: width - pad.right, y1: y(v), y2: y(v), class: 'limit' }));
        svg.appendChild(svgEl('text', { x: width - pad.right, y: y(v) - 4, 'text-anchor': 'end', class: 'limit-label' },
            `${label} ${v.toFixed(decimals)}`));
    });

    // hover readout
    const guide = svgEl('line', { y1: pad.top, y2: pad.top + plotH, class: 'guide', visibility: 'hidden' });
    svg.appendChild(guide);
    const tip = document.createElement('div');
    tip.className = 'chart-tip';
    tip.hidden = true;
    container.appendChild(tip);
    const hit = svgEl('rect', { x: pad.left, y: pad.top, width: plotW, height: plotH, fill: 'transparent' });
    svg.appendChild(hit);
    const move = (event) => {
        const rect = svg.getBoundingClientRect();
        const px = (event.clientX - rect.left) * (width / rect.width);
        const i = Math.max(0, Math.min(n - 1, Math.round(((px - pad.left) / plotW) * (n - 1))));
        const v = values[i];
        if (v === null || !isNum(v)) return;
        guide.setAttribute('x1', x(i));
        guide.setAttribute('x2', x(i));
        guide.setAttribute('visibility', 'visible');
        const ago = (n - 1 - i) * opts.stepSec;
        tip.textContent = `${v.toFixed(decimals)} ${opts.unit || ''} · ${ago ? formatDuration(ago) + ' ago' : 'now'}`;
        tip.style.left = `${(x(i) / width) * 100}%`;
        tip.hidden = false;
    };
    hit.addEventListener('pointermove', move);
    hit.addEventListener('pointerdown', move);
    hit.addEventListener('pointerleave', () => { guide.setAttribute('visibility', 'hidden'); tip.hidden = true; });
}
