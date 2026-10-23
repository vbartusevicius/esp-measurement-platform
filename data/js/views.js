// Sensor-specific views. Each view turns the status payload into one headline
// answer (hero), supporting tiles and, for tanks, a forecast.

const ICONS = {
    ok: 'M20 6 9 17l-5-5',
    alarm: 'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
    warn: 'M12 8v5m0 3h.01M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z',
    info: 'M12 16v-4m0-4h.01M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z',
    down: 'M12 5v14m-6-6 6 6 6-6',
    up: 'M12 19V5m-6 6 6-6 6 6',
    steady: 'M5 12h14',
    plug: 'M9 2v6m6-6v6M6 8h12v4a6 6 0 0 1-12 0zm6 10v4',
    clock: 'M12 6v6l4 2M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z',
};

function icon(name) {
    const svg = svgEl('svg', { viewBox: '0 0 24 24', class: 'icon', fill: 'none', stroke: 'currentColor',
        'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' });
    svg.appendChild(svgEl('path', { d: ICONS[name] || ICONS.info }));
    return svg;
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function num(v) { return isNum(v); }

function fmt(v, decimals = 0) {
    if (!num(v)) return '—';
    return Number(v).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function stat(data, key) {
    const entry = (data.stats || []).find(s => s.key === key);
    return entry ? entry.numeric : undefined;
}

function hasStat(data, key) {
    return (data.stats || []).some(s => s.key === key);
}

function formatEta(hours) {
    if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
    if (hours < 48) return `${Math.floor(hours)} h ${Math.round((hours % 1) * 60)} min`;
    return `${Math.floor(hours / 24)} d ${Math.round(hours % 24)} h`;
}

function formatClock(date) {
    const sameDay = date.toDateString() === new Date().toDateString();
    const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return sameDay ? time : `${date.toLocaleDateString([], { weekday: 'short' })} ${time}`;
}

function stateLine(cls, iconName, text) {
    const line = el('div', `state-line ${cls}`);
    line.append(icon(iconName), el('span', '', text));
    return line;
}

function heroValue(screen, text) {
    const value = el('div', 'hero-value', text);
    if (screen.unit) value.appendChild(el('span', 'unit', screen.unit));
    return value;
}

// Fault advice per plugin (v1 board terminals)
const FAULT_HINTS = {
    analog_distance: 'No 4–20 mA loop current. Check the probe wiring on J2.3 (+24 V) and J2.4; if it was shorted, the resettable fuse needs a minute to cool down.',
    ultrasonic_distance: 'No echo received. Check TRIG on J2.7 (IO2), ECHO on J2.6 (IO1), and that nothing covers the sensor face.',
    analog_voltage: 'Input outside the sensor\'s range. Check the sensor on J2.5 (0–10 V) and its supply.',
    radiation_counter: 'No pulses for 5 minutes. Check the detector\'s high-voltage supply and the pulse wire on J2.6 (IO1).',
};

function limitState(data) {
    const limits = data.limits || {};
    if (limits.state === 'low') return { cls: 'alarm', text: `Below the alert limit (${fmt(limits.low, data.screen.decimals)} ${data.screen.unit})` };
    if (limits.state === 'high') return { cls: 'alarm', text: `Above the alert limit (${fmt(limits.high, data.screen.decimals)} ${data.screen.unit})` };
    if (num(limits.low) || num(limits.high)) {
        const range = num(limits.low) && num(limits.high)
            ? `${fmt(limits.low, data.screen.decimals)}–${fmt(limits.high, data.screen.decimals)} ${data.screen.unit}`
            : num(limits.low) ? `above ${fmt(limits.low, data.screen.decimals)} ${data.screen.unit}` : `below ${fmt(limits.high, data.screen.decimals)} ${data.screen.unit}`;
        return { cls: 'ok', text: `Within limits (${range})` };
    }
    return { cls: 'ok', text: 'Normal' };
}

function sensorStateLine(data) {
    const screen = data.screen;
    if (!screen.sensor_ok) return stateLine('alarm', 'plug', 'Sensor fault — reading unavailable');
    if (!screen.valid) return stateLine('warn', 'clock', 'Warming up — first valid reading soon');
    const s = limitState(data);
    return stateLine(s.cls, s.cls === 'ok' ? 'ok' : 'alarm', s.text);
}

// ---------------------------------------------------------------- tank

function tankRate(data, history) {
    // %/h, negative = draining. Prefer 24 h consumption (stable, ignores refills),
    // then the recent history trend.
    const capacity = stat(data, 'capacity');
    const usage = stat(data, 'usage_24h');
    const flow = stat(data, 'flow_rate');
    if (num(flow) && flow > 0.05 && num(capacity) && capacity > 0) {
        return { rate: (flow * 60 / capacity) * 100, basis: 'current inflow' };
    }
    if (num(usage) && usage > 0 && num(capacity) && capacity > 0) {
        return { rate: -(usage / capacity) * 100 / 24, basis: 'your use over the last 24 h' };
    }
    if (history && history.values.length >= 4) {
        const pts = history.values.slice(-Math.min(history.values.length, Math.round(6 * 3600 / history.stepSec)));
        const n = pts.length;
        const mx = (n - 1) / 2;
        const my = pts.reduce((a, b) => a + b, 0) / n;
        let sxy = 0, sxx = 0;
        pts.forEach((v, i) => { sxy += (i - mx) * (v - my); sxx += (i - mx) * (i - mx); });
        const perStep = sxx ? sxy / sxx : 0;
        return { rate: perStep * 3600 / history.stepSec, basis: `the level trend over the last ${formatDuration((n - 1) * history.stepSec)}` };
    }
    return null;
}

function tankForecast(data, history) {
    const screen = data.screen;
    const limits = data.limits || {};
    const level = screen.value;
    const est = tankRate(data, history);
    const box = el('div', 'forecast');
    if (!screen.valid || !est || Math.abs(est.rate) < 0.05) {
        box.append(el('span', 'muted small', 'Forecast'),
            el('b', '', est ? 'Level steady' : 'Not enough history yet'),
            el('span', 'muted small', est ? `Based on ${est.basis}.` : 'Needs a few hours of readings.'));
        return box;
    }
    if (est.rate > 0) {
        const target = num(limits.high) ? limits.high : 100;
        const label = num(limits.high) ? `MAX ${fmt(target)} %` : 'full';
        if (level >= target) {
            box.append(el('span', 'muted small', 'Forecast'), el('b', '', `Filling, already at ${label}`));
        } else {
            const hours = (target - level) / est.rate;
            box.append(el('span', 'muted small', `Reaches ${label} in`),
                el('b', '', `~${formatEta(hours)}`),
                el('span', 'muted small', `Around ${formatClock(new Date(Date.now() + hours * 3600e3))}, based on ${est.basis}.`));
        }
        return box;
    }
    const target = num(limits.low) ? limits.low : 0;
    const label = num(limits.low) ? `the alert level (${fmt(target)} %)` : 'empty';
    if (level <= target) {
        box.classList.add('alarm');
        box.append(el('span', 'muted small', 'Forecast'), el('b', '', `Already at ${label}`));
        return box;
    }
    const hours = (level - target) / -est.rate;
    if (hours < 24) box.classList.add('warn');
    box.append(el('span', 'muted small', `Reaches ${label} in`),
        el('b', '', `~${formatEta(hours)}`),
        el('span', 'muted small', `Around ${formatClock(new Date(Date.now() + hours * 3600e3))}, based on ${est.basis}.`));
    return box;
}

function tankGraphic(data) {
    const screen = data.screen;
    const limits = data.limits || {};
    const W = 112, H = 200, top = 8, bottom = 192, inner = bottom - top;
    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Tank ${fmt(screen.value)} percent full` });
    const level = num(screen.value) && screen.sensor_ok ? Math.max(0, Math.min(100, screen.value)) : 0;
    const fillTop = bottom - inner * level / 100;
    const alarm = (data.limits || {}).state && data.limits.state !== 'normal';
    svg.appendChild(svgEl('rect', { x: 8, y: top, width: 76, height: inner, rx: 10, fill: 'var(--band)', stroke: 'var(--muted)', 'stroke-width': 1.5 }));
    svg.appendChild(svgEl('clipPath', { id: 'tank-clip' })).appendChild(svgEl('rect', { x: 8, y: top, width: 76, height: inner, rx: 10 }));
    svg.appendChild(svgEl('rect', { x: 8, y: fillTop, width: 76, height: bottom - fillTop, fill: alarm ? 'var(--alarm)' : 'var(--fill)', opacity: alarm ? 0.55 : 1, 'clip-path': 'url(#tank-clip)' }));
    [25, 50, 75].forEach(p => svg.appendChild(svgEl('line', { x1: 8, x2: 16, y1: bottom - inner * p / 100, y2: bottom - inner * p / 100, stroke: 'var(--muted)' })));
    [['low', 'MIN'], ['high', 'MAX']].forEach(([key, label]) => {
        if (!num(limits[key])) return;
        const ly = bottom - inner * Math.max(0, Math.min(100, limits[key])) / 100;
        svg.appendChild(svgEl('line', { x1: 4, x2: 88, y1: ly, y2: ly, stroke: 'var(--alarm)', 'stroke-width': 1.5, 'stroke-dasharray': '5 3' }));
        svg.appendChild(svgEl('text', { x: 90, y: ly + 4, 'font-size': 10, fill: 'var(--alarm)', 'font-weight': 600 }, label));
    });
    const wrap = el('div', 'tank');
    wrap.appendChild(svg);
    return wrap;
}

function levelHero(data, history) {
    const screen = data.screen;
    const capacity = stat(data, 'capacity');
    const volume = stat(data, 'volume');
    const main = el('div', 'hero-main');
    main.append(el('div', 'hero-label', 'Tank level'),
        heroValue(screen, screen.sensor_ok ? fmt(screen.value) : '—'));
    if (screen.sensor_ok) {
        main.appendChild(el('div', 'hero-sub', num(capacity)
            ? `${fmt(volume)} L of ${fmt(capacity)} L`
            : `Depth ${fmt(stat(data, 'depth'), 2)} m`));
    }
    main.appendChild(sensorStateLine(data));
    if (screen.sensor_ok) {
        const flow = stat(data, 'flow_rate');
        if (num(flow) && Math.abs(flow) >= 0.05) {
            main.appendChild(stateLine('ok', flow > 0 ? 'up' : 'down', `${flow > 0 ? 'Filling' : 'Draining'} at ${fmt(Math.abs(flow), 1)} L/min`));
        }
        main.appendChild(tankForecast(data, history));
    } else {
        main.appendChild(el('p', 'small', FAULT_HINTS[data.active_plugin] || 'Check the sensor wiring.'));
    }
    const hero = el('div', 'hero');
    hero.append(tankGraphic(data), main);
    return hero;
}

function levelTiles(data) {
    const screen = data.screen;
    const tiles = [];
    if (hasStat(data, 'capacity')) {
        const flow = stat(data, 'flow_rate');
        tiles.push({ label: 'Volume', value: fmt(stat(data, 'volume')), unit: 'L', note: `of ${fmt(stat(data, 'capacity'))} L` });
        tiles.push({ label: 'Flow now', value: (flow > 0 ? '+' : '') + fmt(flow, 1), unit: 'L/min', note: flow > 0.05 ? 'filling' : flow < -0.05 ? 'draining' : 'steady' });
        tiles.push({ label: 'Used, last 24 h', value: fmt(stat(data, 'usage_24h')), unit: 'L' });
    } else {
        tiles.push({ label: 'Depth', value: fmt(stat(data, 'depth'), 2), unit: 'm' });
        tiles.push({ label: 'Sensor to surface', value: fmt(stat(data, 'distance'), 2), unit: 'm' });
    }
    tiles.push({ label: '24 h range', value: `${fmt(screen.low_24h)}–${fmt(screen.high_24h)}`, unit: '%' });
    return tiles;
}

// ---------------------------------------------------------------- pressure / generic voltage

function analogScale(data) {
    const screen = data.screen;
    const limits = data.limits || {};
    const candidates = [screen.value, screen.low_24h, screen.high_24h, limits.low, limits.high].filter(num);
    let lo = num(screen.scale_min) ? screen.scale_min : Math.min(...candidates);
    let hi = num(screen.scale_max) ? screen.scale_max : Math.max(...candidates) * 1.2;
    if (!(hi > lo)) hi = lo + 1;
    const W = 320, L = 8, R = 312, barY = 26, barH = 12;
    const x = v => L + (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo) * (R - L);
    const svg = svgEl('svg', { viewBox: `0 0 ${W} 78`, role: 'img' });
    const defs = svg.appendChild(svgEl('defs'));
    const pattern = defs.appendChild(svgEl('pattern', { id: 'hatch', width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }));
    pattern.appendChild(svgEl('line', { x1: 0, y1: 0, x2: 0, y2: 6, stroke: 'var(--muted)', 'stroke-width': 1.5, opacity: 0.5 }));

    svg.appendChild(svgEl('rect', { x: L, y: barY, width: R - L, height: barH, fill: 'var(--band)', rx: 3 }));
    if (num(limits.low)) svg.appendChild(svgEl('rect', { x: L, y: barY, width: x(limits.low) - L, height: barH, fill: 'url(#hatch)' }));
    if (num(limits.high)) svg.appendChild(svgEl('rect', { x: x(limits.high), y: barY, width: R - x(limits.high), height: barH, fill: 'url(#hatch)' }));
    [limits.low, limits.high].forEach(v => {
        if (num(v)) svg.appendChild(svgEl('line', { x1: x(v), x2: x(v), y1: barY - 4, y2: barY + barH + 4, stroke: 'var(--alarm)', 'stroke-width': 2 }));
    });
    if (num(screen.low_24h) && num(screen.high_24h)) {
        svg.appendChild(svgEl('rect', { x: x(screen.low_24h), y: barY + barH + 6, width: Math.max(2, x(screen.high_24h) - x(screen.low_24h)), height: 4, fill: 'var(--muted)', rx: 2 }));
    }
    for (let i = 0; i <= 4; i++) {
        const v = lo + (hi - lo) * i / 4;
        const decimals = Math.abs(v - Math.round(v)) < 1e-6 ? 0 : (Math.abs(v * 10 - Math.round(v * 10)) < 1e-6 ? 1 : 2);
        svg.appendChild(svgEl('text', { x: x(v), y: 72, 'text-anchor': i === 0 ? 'start' : i === 4 ? 'end' : 'middle' }, fmt(v, decimals)));
    }
    if (screen.sensor_ok && num(screen.value)) {
        const px = x(screen.value);
        const alarm = limits.state && limits.state !== 'normal';
        svg.appendChild(svgEl('path', { d: `M${px - 7} 8 L${px + 7} 8 L${px} 22 Z`, fill: alarm ? 'var(--alarm)' : 'var(--text)' }));
        svg.appendChild(svgEl('line', { x1: px, x2: px, y1: barY, y2: barY + barH, stroke: alarm ? 'var(--alarm)' : 'var(--text)', 'stroke-width': 2 }));
    }
    const wrap = el('div', 'scale');
    wrap.appendChild(svg);
    const note = el('div', 'ref-note', 'Pointer: now · grey bar: last 24 h · hatched: outside the alert limits');
    wrap.appendChild(note);
    return wrap;
}

function pressureHero(data) {
    const screen = data.screen;
    const main = el('div', 'hero-main');
    main.append(el('div', 'hero-label', screen.kind === 'pressure' ? 'Pressure' : (screen.title || 'Reading')),
        heroValue(screen, screen.sensor_ok ? fmt(screen.value, screen.decimals) : '—'),
        sensorStateLine(data));
    if (screen.sensor_ok) main.appendChild(analogScale(data));
    else main.appendChild(el('p', 'small', FAULT_HINTS[data.active_plugin] || 'Check the sensor wiring.'));
    const hero = el('div', 'hero');
    hero.appendChild(main);
    return hero;
}

function pressureTiles(data) {
    const screen = data.screen;
    const limits = data.limits || {};
    const d = screen.decimals || 0;
    const tiles = [
        { label: '24 h low', value: fmt(screen.low_24h, d), unit: screen.unit },
        { label: '24 h high', value: fmt(screen.high_24h, d), unit: screen.unit },
        { label: 'Sensor signal', value: screen.signal || '—', note: 'at terminal J2.5' },
    ];
    tiles.push({ label: 'Alert limits', value: num(limits.low) || num(limits.high)
        ? `${num(limits.low) ? fmt(limits.low, d) : '—'} / ${num(limits.high) ? fmt(limits.high, d) : '—'}` : 'off', unit: num(limits.low) || num(limits.high) ? screen.unit : '', note: 'min / max' });
    return tiles;
}

// ---------------------------------------------------------------- radiation

// Dose-rate bands as used by Aranet (EURDEP / CDC / BfS references):
// < 0.20 µSv/h normal background, 0.20–10 above background, > 10 linked to health effects.
const DOSE_BANDS = [
    { max: 0.2, label: 'Normal background', cls: 'ok' },
    { max: 10, label: 'Above typical background', cls: 'warn' },
    { max: Infinity, label: 'High: prolonged exposure is a health risk', cls: 'alarm' },
];

function doseBand(v) {
    return DOSE_BANDS.find(b => v < b.max);
}

function doseScale(data) {
    const screen = data.screen;
    const avg = stat(data, 'dose_avg_5m');
    const threshold = num((data.limits || {}).high) ? data.limits.high : stat(data, 'alert_threshold');
    const W = 320, L = 8, R = 312, barY = 26, barH = 12;
    const x = v => L + (Math.log10(Math.max(0.01, Math.min(100, v))) + 2) / 4 * (R - L);
    const svg = svgEl('svg', { viewBox: `0 0 ${W} 80`, role: 'img' });
    [[0.01, 0.2, 'var(--band)'], [0.2, 10, 'color-mix(in srgb, var(--warn) 22%, var(--band))'], [10, 100, 'color-mix(in srgb, var(--alarm) 30%, var(--band))']]
        .forEach(([a, b, fill]) => svg.appendChild(svgEl('rect', { x: x(a), y: barY, width: x(b) - x(a), height: barH, fill })));
    [0.01, 0.1, 1, 10, 100].forEach((v, i) => svg.appendChild(svgEl('text',
        { x: x(v), y: 72, 'text-anchor': i === 0 ? 'start' : i === 4 ? 'end' : 'middle' }, String(v))));
    svg.appendChild(svgEl('text', { x: x(0.045), y: 18, 'text-anchor': 'middle' }, 'background'));
    svg.appendChild(svgEl('text', { x: x(1.4), y: 18, 'text-anchor': 'middle' }, 'elevated'));
    svg.appendChild(svgEl('text', { x: x(32), y: 18, 'text-anchor': 'middle' }, 'high'));
    if (num(threshold)) {
        svg.appendChild(svgEl('line', { x1: x(threshold), x2: x(threshold), y1: barY - 4, y2: barY + barH + 4, stroke: 'var(--alarm)', 'stroke-width': 2 }));
        svg.appendChild(svgEl('text', { x: x(threshold), y: barY + barH + 16, 'text-anchor': 'middle', fill: 'var(--alarm)' }, `alert ${threshold}`));
    }
    if (num(avg)) svg.appendChild(svgEl('circle', { cx: x(avg), cy: barY + barH / 2, r: 5, fill: 'none', stroke: 'var(--text)', 'stroke-width': 2 }));
    if (screen.sensor_ok && num(screen.value)) {
        const px = x(screen.value);
        svg.appendChild(svgEl('path', { d: `M${px - 6} ${barY - 2} L${px + 6} ${barY - 2} L${px} ${barY + 8} Z`, fill: 'var(--text)' }));
    }
    const wrap = el('div', 'scale');
    wrap.append(svg, el('div', 'ref-note', 'µSv/h, log scale · ▼ last minute · ○ 5-min average · typical background 0.05–0.20 µSv/h'));
    return wrap;
}

function radiationHero(data) {
    const screen = data.screen;
    const avg = stat(data, 'dose_avg_5m');
    const main = el('div', 'hero-main');
    main.append(el('div', 'hero-label', 'Gamma dose rate'),
        heroValue(screen, screen.sensor_ok ? fmt(screen.value, 2) : '—'));
    if (!screen.sensor_ok) {
        main.append(sensorStateLine(data), el('p', 'small', FAULT_HINTS.radiation_counter));
    } else if (!screen.valid) {
        main.append(stateLine('warn', 'clock', 'Warming up: counting for the first minute'));
    } else {
        // Classify on the 5-minute average: single one-minute readings are noisy.
        const basis = num(avg) ? avg : screen.value;
        const band = doseBand(basis);
        const limits = data.limits || {};
        if (limits.state === 'high') main.appendChild(stateLine('alarm', 'alarm', `Above your alert limit (${fmt(limits.high, 2)} µSv/h)`));
        else main.appendChild(stateLine(band.cls, band.cls === 'ok' ? 'ok' : 'alarm', band.label));
        main.appendChild(el('div', 'hero-sub small', `5-min average ${fmt(avg, 2)} µSv/h${num(avg) ? ` · ≈ ${fmt(avg * 8.76, 1)} mSv/year at this rate (gamma only)` : ''}`));
    }
    if (screen.sensor_ok) main.appendChild(doseScale(data));
    const hero = el('div', 'hero');
    hero.appendChild(main);
    return hero;
}

function radiationTiles(data) {
    const cpm = stat(data, 'cpm');
    const precision = num(cpm) && cpm > 0 ? 196 / Math.sqrt(cpm) : null;
    return [
        { label: 'Counts per minute', value: fmt(cpm), unit: 'CPM' },
        { label: '5-min average', value: fmt(stat(data, 'dose_avg_5m'), 2), unit: 'µSv/h' },
        { label: 'Precision (1 min)', value: precision ? `±${fmt(precision)}` : '—', unit: precision ? '%' : '', note: 'counting statistics, 95 %', cls: precision > 50 ? 'warn' : '' },
        { label: 'Counts since boot', value: fmt(stat(data, 'counts_total')) },
    ];
}

// ---------------------------------------------------------------- registry

const VIEWS = {
    level: { hero: levelHero, tiles: levelTiles, noun: 'Tank level',
        advice: { low: 'Refill the tank or check the supply.', high: 'Check the inlet valve and the overflow.' } },
    pressure: { hero: pressureHero, tiles: pressureTiles, noun: 'Pressure',
        advice: { low: 'Check for leaks, an empty supply or a stopped pump.', high: 'Check the pump control and the pressure relief valve.' } },
    voltage: { hero: pressureHero, tiles: pressureTiles, noun: 'Reading', advice: { low: '', high: '' } },
    radiation: { hero: radiationHero, tiles: radiationTiles, noun: 'Dose rate',
        advice: { low: '', high: 'Confirm it on the 5-minute average. Radon in still indoor air is the most common cause; ventilate and compare with your local background.' } },
};

function viewFor(screen) {
    return VIEWS[screen && screen.kind] || VIEWS.voltage;
}

// ---------------------------------------------------------------- events

const EVENT_TEXT = {
    'MIN LIMIT!': ['Below the alert limit', 'alarm', 'alarm'],
    'MAX LIMIT!': ['Above the alert limit', 'alarm', 'alarm'],
    'LIMIT CLEAR': ['Back within limits', '', 'ok'],
    'SENSOR FAULT': ['Sensor fault', 'alarm', 'plug'],
    'SENSOR OK': ['Sensor working again', '', 'ok'],
    'WIFI LOST': ['WiFi connection lost', 'warn', 'warn'],
    'WIFI ONLINE': ['WiFi connected', '', 'info'],
    'MQTT OFFLINE': ['MQTT broker disconnected', 'warn', 'warn'],
    'MQTT ONLINE': ['MQTT broker connected', '', 'info'],
    'RELAY ON': ['Relay switched on', '', 'info'],
    'RELAY OFF': ['Relay switched off', '', 'info'],
    'SYSTEM BOOT': ['Device started', '', 'info'],
};

function renderEvents(list, events, uptime, limit) {
    list.innerHTML = '';
    const items = (events || []).slice(0, limit || undefined);
    if (!items.length) {
        list.appendChild(el('li', 'empty', 'No events since the device started.'));
        return;
    }
    items.forEach(e => {
        const [title, cls, iconName] = EVENT_TEXT[e.title] || [e.title, '', 'info'];
        const li = el('li', cls);
        const text = el('div');
        text.append(el('div', 'ev-title', title), el('div', 'ev-detail', e.detail));
        const ago = num(uptime) ? uptime - e.t : null;
        const when = el('div', 'ev-time', ago === null ? '' : formatClock(new Date(Date.now() - ago * 1000)));
        if (ago !== null) when.title = `${formatDuration(ago)} ago`;
        li.append(icon(iconName), text, when);
        list.appendChild(li);
    });
}
