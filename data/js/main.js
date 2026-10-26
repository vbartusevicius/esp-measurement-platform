// App state, tabs, Overview/Device rendering and the settings form.
const STALE_AFTER_MS = 10000;      // status is broadcast every 2 s
// Applied without a restart: alert limits (any sensor prefix) and the relay rule
const LIVE_SETTING = /(^|\.)(limit_low|limit_high|limit_low_on|limit_high_on|limit_hysteresis)$|^relay_(mode|source)$/;

const state = {
    status: null,
    config: null,
    history: null,
    chartRange: null,   // null = default per sensor: tanks 24 h, the rest live
    lastUpdate: 0,
    formSnapshot: '',
    view: 'all',   // Overview sub-tab: 'all' (summary of every sensor) or a sensor id (its detail)
    logs: [],      // system-log lines from the WebSocket ("00d 01:02:03 [WARN] text")
    filter: { cats: new Set(['alert', 'relay', 'sensor', 'network', 'system']), sensor: '', search: '', warnOnly: false },
    seenAlarmT: -1,   // newest alert/fault event (device uptime) seen on the Events tab
};

// ---------------------------------------------------------------- sensors

function sensors(s) {
    return (s && s.sensors) || [];
}

// The sensor whose detail is shown: the only one, or the one picked in the sub-tabs.
function selectedSensor(s) {
    const list = sensors(s);
    return list.length === 1 ? list[0] : list.find(x => x.id === state.view) || null;
}

function multiSensor(s) {
    return sensors(s).length > 1;
}

// One sensor's data with the device fields, the shape every sensor view uses.
function sensorView(s, sensor) {
    return Object.assign({}, s, sensor || {}, { active_plugin: sensor ? sensor.id : '' });
}

// Overview sub-tab ('all' or a sensor id); kept in the URL (#overview/<id>) so back/refresh keep it.
function selectView(view) {
    view = view || 'all';
    if (view !== state.view) {
        state.view = view;
        state.history = null;
        state.chartRange = null;
        if (view !== 'all') loadHistory();
    }
    const hash = view === 'all' ? '#overview' : `#overview/${view}`;
    if (location.hash !== hash) history.replaceState(null, '', hash);
    renderAll();
}

// ---------------------------------------------------------------- helpers

function $(id) { return document.getElementById(id); }

function showToast(message) {
    const toast = $('toast');
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => { toast.hidden = true; }, 4000);
}

function addLogLine(message) {
    if (!message || state.logs.includes(message)) return;   // reconnects resend the recent lines
    state.logs.push(message);
    if (state.logs.length > 300) state.logs.shift();
    if (!$('tab-events').hidden) renderEventsTab();
}

// ---------------------------------------------------------------- tabs

function selectTab(hash) {
    let [name, view] = (hash || '').split('/');
    if (!$(`tab-${name}`)) name = 'overview';
    if (name === 'overview' && (view || 'all') !== state.view) {
        state.view = view || 'all';
        state.history = null;
        state.chartRange = null;
        if (state.view !== 'all') loadHistory();
    }
    document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
    document.querySelectorAll('.tab-panel').forEach(p => { p.hidden = p.id !== `tab-${name}`; });
    if (name === 'overview') renderAll();
    if (name === 'events') renderEventsTab();
}

// ---------------------------------------------------------------- status

function onStatus(data) {
    state.status = data;
    state.lastUpdate = Date.now();
    renderAll();
}

function isStale() {
    return !state.lastUpdate || Date.now() - state.lastUpdate > STALE_AFTER_MS;
}

function renderConnection() {
    const box = $('connection');
    const text = $('connection-text');
    if (!state.lastUpdate) {
        box.className = 'connection';
        text.textContent = 'Connecting…';
        return;
    }
    const age = Math.round((Date.now() - state.lastUpdate) / 1000);
    if (isStale()) {
        box.className = 'connection stale';
        text.textContent = `Offline · data ${formatDuration(age)} old`;
    } else {
        box.className = 'connection live';
        text.textContent = age < 3 ? 'Live' : `Live · ${age} s ago`;
    }
}

function renderHeader() {
    const s = state.status;
    const names = sensors(s).map(x => x.name);
    const name = (state.config && state.config.device_name) || names[0] || 'ESP Measurement Platform';
    $('device-title').textContent = name;
    document.title = name;
    if (s) $('device-subtitle').textContent = [names.join(', '), s.chip_id ? `ID ${s.chip_id}` : ''].filter(Boolean).join(' · ');
}

function renderAll() {
    renderConnection();
    renderHeader();
    const s = state.status;
    if (!s) return;
    document.body.classList.toggle('stale', isStale());
    if (!$('tab-overview').hidden) renderOverview(s);
    if (!$('tab-device').hidden) renderDevice(s);
    if (!$('tab-events').hidden) renderEventsTab();
    else renderEventsBadge(s);
    sensors(s).forEach(x => document.querySelectorAll(`[data-unit-of="${x.id}"]`)
        .forEach(n => { n.textContent = (x.screen && x.screen.unit) || ''; }));
    if (!$('tab-settings').hidden && state.config) {
        document.querySelectorAll('.sensor-block').forEach(updateBlockSummary);
        updateRelaySourceView();
    }
}

// ---------------------------------------------------------------- overview

function alertCard(cls, iconName, title, detail, meta, action) {
    const card = el('div', `alert ${cls}`);
    const body = el('div', 'alert-body');
    body.appendChild(el('div', 'alert-title', title));
    if (detail) body.appendChild(el('div', 'alert-detail', detail));
    if (meta) body.appendChild(el('div', 'alert-meta', meta));
    const actions = el('div', 'alert-actions');
    if (action) actions.appendChild(action);
    card.append(icon(iconName), body, actions);
    return card;
}

function lastEventAge(s, titles) {
    const e = (s.events || []).find(ev => titles.includes(ev.title));
    return e && num(s.uptime_s) ? s.uptime_s - e.t : null;
}

// `only`: in a sensor's tab, just that sensor's alerts (device alerts always show).
function renderAlerts(s, only) {
    const slot = $('alert-slot');
    slot.innerHTML = '';
    if (isStale()) {
        slot.appendChild(alertCard('warn', 'warn', 'Connection to the device lost',
            `The values below are from ${formatDuration((Date.now() - state.lastUpdate) / 1000)} ago. This page keeps retrying.`));
    }
    if (s.configured === false) {
        const link = el('a', 'btn', 'Open Settings');
        link.href = '#settings';
        const any = sensors(s).length > 0;
        slot.appendChild(alertCard('warn', 'info', any ? 'Setup not finished' : 'No sensor switched on',
            any ? 'Some required sensor or MQTT settings are missing.' : 'Switch on the sensors you have wired up in Settings.',
            '', link));
    }
    // On the summary each alert is compact (title, acknowledge, a link to the sensor's
    // tab); the advice text is in that tab.
    const named = multiSensor(s) && !only;
    slot.classList.toggle('compact', named);
    sensors(s).filter(x => !only || x.id === only).forEach(sensor => {
        const before = slot.children.length;
        renderSensorAlerts(slot, sensorView(s, sensor), named ? `${sensorTitle(sensor)}: ` : '');
        if (!named) return;
        [...slot.children].slice(before).forEach(card => {
            const link = el('button', 'btn btn-quiet', 'Details');
            link.type = 'button';
            link.addEventListener('click', () => selectView(sensor.id));
            (card.querySelector('.alert-actions') || card).appendChild(link);
        });
    });
}

// Fault, limit and sensor-specific alerts of one sensor; `who` names it when several run.
function renderSensorAlerts(slot, s, who) {
    const screen = s.screen;
    if (!screen) return;
    if (!screen.sensor_ok) {
        const age = lastEventAge(s, ['SENSOR FAULT']);
        slot.appendChild(alertCard('alarm', 'plug', who + 'Sensor fault', FAULT_HINTS[s.active_plugin] || 'Check the sensor wiring.',
            age !== null ? `Since ${formatClock(new Date(Date.now() - age * 1000))}` : ''));
    }
    const limits = s.limits || {};
    if (limits.state && limits.state !== 'normal') {
        const view = viewFor(screen);
        const below = limits.state === 'low';
        const limit = below ? limits.low : limits.high;
        let detail = `${fmt(screen.value, screen.decimals)} ${screen.unit} — alert ${below ? 'below' : 'above'} ${fmt(limit, screen.decimals)} ${screen.unit}.`;
        if (s.relay && s.relay.available && s.relay.mode !== 'manual' && s.relay.source === s.active_plugin) detail += ` Relay switched ${s.relay.on ? 'ON' : 'OFF'} automatically.`;
        const advice = view.advice[below ? 'low' : 'high'];
        if (advice) detail += ` ${advice}`;
        const age = lastEventAge(s, ['MIN LIMIT!', 'MAX LIMIT!']);
        const since = age !== null ? `Since ${formatClock(new Date(Date.now() - age * 1000))}` : '';
        let action = null;
        if (limits.alert) {
            action = el('button', 'btn', 'Acknowledge');
            action.type = 'button';
            action.addEventListener('click', () => acknowledgeAlert(s.active_plugin));
        }
        slot.appendChild(alertCard('alarm', 'alarm', `${who}${view.noun} ${below ? 'below' : 'above'} the alert limit`, detail,
            [since, limits.alert ? '' : 'Acknowledged'].filter(Boolean).join(' · '), action));
    } else if (screen.kind === 'meter' && hasStat(s, 'leak')) {
        slot.appendChild(alertCard('alarm', 'alarm', who + medium(s).noun + ' has not stopped for ' + fmt(stat(s, 'continuous_h')) + ' hours',
            'Something has flowed in every hour since then. Check toilets, taps and the heating refill; read the meter dial with everything closed.'));
    } else if (screen.kind === 'radiation' && screen.valid) {
        const avg = stat(s, 'dose_avg_5m');
        if (num(avg) && avg >= 0.2) {
            slot.appendChild(alertCard(avg >= 10 ? 'alarm' : 'warn', 'warn', who + doseBand(avg).label,
                `5-minute average ${fmt(avg, 2)} µSv/h. Typical background is 0.05–0.20 µSv/h. ${VIEWS.radiation.advice.high}`));
        }
    }
}

function renderTiles(s) {
    const box = $('tiles');
    box.innerHTML = '';
    if (!s.screen) return;
    viewFor(s.screen).tiles(s).forEach(t => {
        const tile = el('div', `tile ${t.cls || ''}`);
        const value = el('div', 'tile-value', t.value);
        if (t.unit) value.appendChild(el('span', 'unit', t.unit));
        tile.append(el('div', 'tile-label', t.label), value);
        if (t.note) tile.appendChild(el('div', 'tile-note', t.note));
        box.appendChild(tile);
    });
}

// The relay as one device-level bar: state, the rule in plain words, the last
// change, and either a switch (manual) or a link to the rule (automatic).
function renderRelay(s) {
    const bar = $('relay-bar');
    const relay = s.relay;
    bar.hidden = !(relay && relay.available);
    if (bar.hidden) return;
    const auto = relay.mode !== 'manual';
    const pill = $('relay-pill');
    pill.textContent = relay.on ? 'ON' : 'OFF';
    pill.classList.toggle('on', !!relay.on);
    bar.classList.toggle('stale', isStale());
    $('relay-mode').textContent = auto ? 'Automatic ›' : 'Manual ›';
    $('relay-mode').className = `relay-mode${auto ? ' auto' : ''}`;
    $('relay-mode').title = 'Relay rule in Settings';
    $('relay-rule').textContent = relayRule(s);

    const last = (s.events || []).find(e => e.title === 'RELAY ON' || e.title === 'RELAY OFF');
    const meta = [];
    if (last && num(s.uptime_s)) {
        const by = humanDetail(last.detail).replace(/^./, c => c.toLowerCase());
        meta.push(`Switched ${last.title === 'RELAY ON' ? 'on' : 'off'} ${formatClock(new Date(Date.now() - (s.uptime_s - last.t) * 1000))} ${by}`);
    }
    meta.push(`on ${relay.activations}× since start`);
    $('relay-meta').textContent = meta.join(' · ');

    $('relay-switch').hidden = auto;
    $('relay-settings-link').hidden = !auto;
    const toggle = $('relay-toggle');
    toggle.checked = !!relay.on;
    toggle.disabled = isStale();
    $('relay-switch-label').textContent = relay.on ? 'On' : 'Off';
}

function relayRule(s) {
    const relay = s.relay;
    if (relay.mode === 'manual') return 'You switch it here or from Home Assistant.';
    const sensor = sensors(s).find(x => x.id === relay.source);
    if (!sensor) return 'Follows the alerts of a sensor that is not running.';
    const name = multiSensor(s) ? sensorTitle(sensor) : 'the reading';
    const unit = (sensor.screen && sensor.screen.unit) || '';
    const lim = sensor.limits || {};
    const d = sensor.screen ? sensor.screen.decimals : undefined;
    const v = x => `${fmt(x, d)}${unit ? ' ' + unit : ''}`;
    const low = num(lim.low), high = num(lim.high);
    const action = relay.mode === 'on_alarm' ? 'on' : 'off';
    if (!low && !high) return `Follows ${name}, but it has no alert switched on, so the relay never switches.`;
    const cond = low && high ? `outside ${fmt(lim.low, d)}–${v(lim.high)}` : low ? `below ${v(lim.low)}` : `above ${v(lim.high)}`;
    let text = `Turns ${action} while ${name} is ${cond}.`;
    if (sensor.screen && sensor.screen.sensor_ok === false) text += ' Holding its state: sensor fault.';
    else if (lim.state && lim.state !== 'normal') text += ` Now: ${lim.state === 'low' ? 'below' : 'above'} the limit.`;
    return text;
}

// ---------------------------------------------------------------- overview
//
// One sensor: its detail view directly. Several: in-page sub-tabs "All sensors"
// + one per sensor. "All sensors" is the summary: one equal card per sensor
// (value, state in words, freshness, trend against its limits), the relay and
// the events; a card opens that sensor's tab, which shows only its detail.

const STATE_TEXT = { low: 'Below limit', high: 'Above limit' };

function sensorState(sensor) {
    const screen = sensor.screen || {};
    const lim = sensor.limits || {};
    if (screen.sensor_ok === false) return { cls: 'alarm', icon: 'plug', text: 'Sensor fault' };
    if (lim.state && lim.state !== 'normal') return { cls: 'alarm', icon: 'alarm', text: STATE_TEXT[lim.state] || 'Alert' };
    const leak = (sensor.stats || []).some(x => x.key === 'leak');
    if (leak) return { cls: 'alarm', icon: 'alarm', text: 'Continuous flow' };
    if (sensor.configured === false) return { cls: 'warn', icon: 'info', text: 'Setup unfinished' };
    return { cls: 'ok', icon: '', text: 'Normal' };
}

function sensorTitle(sensor) {
    return (sensor.screen && sensor.screen.title) || sensor.name;
}

function renderSubtabs(s) {
    const nav = $('sensor-tabs');
    nav.hidden = !multiSensor(s);
    nav.innerHTML = '';
    if (nav.hidden) return;
    const tab = (view, label, st) => {
        const b = el('button', `subtab${st ? ` ${st.cls}` : ''}`);
        b.type = 'button';
        b.setAttribute('role', 'tab');
        b.setAttribute('aria-selected', String(state.view === view));
        if (st && st.cls !== 'ok') b.appendChild(el('span', `subtab-mark ${st.cls}`, st.cls === 'alarm' ? '!' : '•'));
        b.appendChild(document.createTextNode(label));
        if (st && st.cls !== 'ok') b.setAttribute('aria-label', `${label}: ${st.text}`);
        b.addEventListener('click', () => selectView(view));
        nav.appendChild(b);
    };
    tab('all', 'All sensors');
    sensors(s).forEach(sensor => tab(sensor.id, sensorTitle(sensor), sensorState(sensor)));
}

// Up to two supporting values for a summary card, skipping the headline itself.
const CARD_SKIP = new Set(['sensor', 'medium', 'raw', 'capacity', 'liters_per_pulse', 'pulses', 'alert_threshold',
    'counts_total', 'leak', 'level', 'value', 'dose', 'flow_rate', 'distance', 'voltage']);

function summaryCard(s, sensor) {
    const screen = sensor.screen || {};
    const st = sensorState(sensor);
    const card = el('button', `card sensor-card ${st.cls}`);
    card.type = 'button';
    card.setAttribute('aria-label', `${sensor.name}: ${st.text}. Open details`);

    const head = el('div', 'sensor-card-head');
    const title = el('div', 'sensor-card-title');
    title.append(el('span', 'sensor-card-name', sensorTitle(sensor)), el('span', 'muted small', sensor.name));
    const chip = el('span', `state-chip ${st.cls}`);
    if (st.icon) chip.appendChild(icon(st.icon));
    chip.appendChild(document.createTextNode(st.text));
    head.append(title, chip);
    card.appendChild(head);

    const value = el('div', 'sensor-card-value');
    value.appendChild(el('span', 'num', screen.sensor_ok === false || !screen.valid ? '—' : fmt(screen.value, screen.decimals)));
    value.appendChild(el('span', 'unit', screen.unit || ''));
    card.appendChild(value);

    const extra = (sensor.stats || []).filter(x => !CARD_SKIP.has(x.key)).slice(0, 2);
    if (extra.length) {
        const dl = el('dl', 'sensor-card-facts');
        extra.forEach(x => { const d = el('div'); d.append(el('dt', '', x.label), el('dd', '', x.value)); dl.appendChild(d); });
        card.appendChild(dl);
    }

    const spark = sparkline(screen.trend, sensor.limits);
    if (spark) card.appendChild(spark);
    const foot = el('div', 'sensor-card-foot muted small');
    foot.append(el('span', '', isStale() ? 'No fresh data' : `Updated ${ago(state.lastUpdate)}`), el('span', 'open', 'Details ›'));
    card.appendChild(foot);
    card.addEventListener('click', () => selectView(sensor.id));
    return card;
}

function ago(ms) {
    const sec = Math.max(0, Math.round((Date.now() - ms) / 1000));
    return sec < 5 ? 'just now' : sec < 60 ? `${sec} s ago` : `${Math.round(sec / 60)} min ago`;
}

// Mini trend with the alert limits as dashed lines, so "near the limit" is visible at a glance.
function sparkline(values, limits) {
    const pts = (values || []).filter(v => v !== null && Number.isFinite(v));
    if (pts.length < 2) return null;
    const lim = [limits && limits.low, limits && limits.high].filter(v => num(v));
    let lo = Math.min(...pts, ...lim), hi = Math.max(...pts, ...lim);
    const pad = (hi - lo || 1) * 0.08;
    lo -= pad; hi += pad;
    const y = v => (40 - (v - lo) / (hi - lo) * 40).toFixed(1);
    const d = pts.map((v, i) => `${(i / (pts.length - 1) * 100).toFixed(1)},${y(v)}`).join(' ');
    const lines = lim.map(v => `<line x1="0" x2="100" y1="${y(v)}" y2="${y(v)}" class="limit"/>`).join('');
    const wrap = el('div', 'sensor-card-trend');
    wrap.innerHTML = `<svg viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true">${lines}<polyline points="${d}"/></svg>`;
    return wrap;
}

function renderOverview(status) {
    const multi = multiSensor(status);
    if (multi && state.view !== 'all' && !sensors(status).some(x => x.id === state.view)) state.view = 'all';
    const summary = multi && state.view === 'all';
    renderSubtabs(status);
    renderAlerts(status, summary || !multi ? null : state.view);
    $('summary-view').hidden = !summary;
    $('detail-view').hidden = summary;
    renderRelay(status);

    if (summary) {
        const grid = $('sensor-grid');
        grid.innerHTML = '';
        sensors(status).forEach(sensor => grid.appendChild(summaryCard(status, sensor)));
        renderLatestEvent(status);
        return;
    }
    const sensor = selectedSensor(status);
    const s = sensorView(status, sensor);
    const hero = $('hero-card');
    hero.innerHTML = '';
    hero.classList.toggle('stale', isStale());
    if (s.screen) hero.appendChild(viewFor(s.screen).hero(s, state.history));
    else hero.appendChild(el('div', 'skeleton', 'No sensor switched on yet.'));
    renderTiles(s);
    if (s.screen) renderTrend(s);
}

function renderLatestEvent(s) {
    const link = $('latest-event');
    const latest = (s.events || [])[0];
    link.textContent = '';
    if (!latest) return;
    const [title] = EVENT_TEXT[latest.title] || [latest.title];
    const when = num(s.uptime_s) ? formatClock(new Date(Date.now() - (s.uptime_s - latest.t) * 1000)) : '';
    link.append(`Latest event: ${title}${latest.detail ? ` (${latest.detail})` : ''} · ${when}`, el('b', '', ' All events ›'));
}

function chartRange(screen) {
    return state.chartRange || (screen.kind === 'level' || screen.kind === 'meter' ? '24h' : 'live');
}

function renderTrend(s) {
    const screen = s.screen;
    // Tank levels move over hours, so they default to 24 h; pressure and
    // radiation change within minutes, so they default to the live trend.
    let range = chartRange(screen);
    const hasHistory = state.history && state.history.values.length >= 2;
    if (range === '24h' && !hasHistory && !state.chartRange) range = 'live';
    document.querySelectorAll('.segmented button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.range === range)));

    const history = range === '24h';
    const values = history ? (hasHistory ? state.history.values : []) : (screen.trend || []);
    const step = history ? (hasHistory ? state.history.stepSec : 900) : (screen.trend_bucket_s || 60);
    const span = Math.max(1, values.length - 1) * step;
    $('trend-title').textContent = history ? `Last ${formatDuration(span)}` : 'Live trend';
    $('trend-caption').textContent = values.length > 1 ? `${formatDuration(step)} per point` : '';
    renderChart($('trend-chart'), {
        values, stepSec: step, unit: history && state.history.unit ? state.history.unit : screen.unit, decimals: screen.decimals,
        limits: history && screen.kind === 'meter' ? {} : (s.limits || {}),   // meter history is litres per bar, limits are L/min
        bars: history && (screen.kind === 'radiation' || screen.kind === 'meter'),
        yMin: screen.scale_min, yMax: screen.kind === 'level' ? screen.scale_max : undefined,
        emptyText: !screen.sensor_ok ? 'No data while the sensor is faulty'
            : history ? 'No history stored yet: it builds up over the first hours after a restart' : 'Collecting the first readings…',
    });

    const summary = $('trend-summary');
    summary.innerHTML = '';
    const vals = values.filter(num);
    if (history && screen.kind === 'meter' && vals.length) {
        const sum = vals.reduce((a, b) => a + b, 0);
        [['Used', `${fmt(sum)} L`], ['Busiest 15 min', `${fmt(Math.max(...vals))} L`]].forEach(([label, text]) => {
            const item = el('div', 'muted', label);
            item.appendChild(el('b', '', text));
            summary.appendChild(item);
        });
    } else if (vals.length > 1) {
        const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
        [['Lowest', Math.min(...vals)], ['Average', avg], ['Highest', Math.max(...vals)]].forEach(([label, v]) => {
            const item = el('div', 'muted', label);
            item.appendChild(el('b', '', `${fmt(v, screen.decimals)} ${screen.unit}`));
            summary.appendChild(item);
        });
    }
}

async function acknowledgeAlert(sensorId) {
    try {
        await apiPost('/alert/ack' + (sensorId ? `?sensor=${encodeURIComponent(sensorId)}` : ''));
        showToast('Alert acknowledged. It stays listed until the reading is back within limits.');
        setTimeout(requestStatus, 300);
    } catch (error) {
        showToast(`Could not acknowledge: ${error.message}`);
    }
}

async function toggleRelay() {
    const toggle = $('relay-toggle');
    const target = toggle.checked ? 'on' : 'off';
    // the switch only moves for real once the device reports the new state
    toggle.checked = !toggle.checked;
    if (!confirm(`Switch the relay ${target.toUpperCase()}?`)) return;
    try {
        await apiPost(`/relay?state=${target}`);
        setTimeout(requestStatus, 300);
    } catch (error) {
        showToast(`Relay not switched: ${error.message}`);
    }
}

// ---------------------------------------------------------------- events tab
//
// Device events and the system log on one timeline, newest first, grouped by
// day, with category chips, a sensor filter and a search; copy / download as text.

const EVENT_CAT = {
    'MIN LIMIT!': 'alert', 'MAX LIMIT!': 'alert', 'LIMIT CLEAR': 'alert',
    'RELAY ON': 'relay', 'RELAY OFF': 'relay',
    'SENSOR FAULT': 'sensor', 'SENSOR OK': 'sensor',
    'WIFI LOST': 'network', 'WIFI ONLINE': 'network', 'MQTT OFFLINE': 'network', 'MQTT ONLINE': 'network',
    'SYSTEM BOOT': 'system',
};
const LOG_LINE = /^(\d+)d (\d\d):(\d\d):(\d\d) \[(\w+)\] (.*)$/;

function deviceUptimeNow(s) {
    return num(s && s.uptime_s) ? s.uptime_s + (Date.now() - state.lastUpdate) / 1000 : null;
}

// All entries as {t (device uptime s), kind: 'event'|'log', cat, ...}
function timelineEntries(s) {
    const entries = (s.events || []).map(e => {
        const sensor = multiSensor(s) && sensors(s).find(x => e.detail.startsWith(`${sensorTitle(x)} `));
        return { t: e.t, kind: 'event', cat: EVENT_CAT[e.title] || 'system', raw: e,
                 sensor: sensor ? sensor.id : '', detail: sensor ? e.detail.slice(sensorTitle(sensor).length + 1) : e.detail };
    });
    state.logs.forEach((line, i) => {
        const m = LOG_LINE.exec(line);
        const t = m ? +m[1] * 86400 + +m[2] * 3600 + +m[3] * 60 + +m[4] : null;
        const text = m ? m[6] : line;
        const sensor = sensors(s).find(x => text.includes(x.name) || text.includes(`${sensorTitle(x)} `));
        entries.push({ t, order: i, kind: 'log', cat: 'log', level: m ? m[5] : 'INFO', text, sensor: sensor ? sensor.id : '' });
    });
    // newest first; log lines without a time keep their order at the end
    // (an event before the log line written with it)
    return entries.sort((a, b) => (b.t ?? -1) - (a.t ?? -1) || (a.kind === 'event' ? -1 : 0) - (b.kind === 'event' ? -1 : 0)
        || (b.order ?? 0) - (a.order ?? 0));
}

function visibleEntries(s) {
    const f = state.filter;
    const q = f.search.trim().toLowerCase();
    return timelineEntries(s).filter(e => {
        if (!f.cats.has(e.cat)) return false;
        if (e.kind === 'log' && f.warnOnly && e.level === 'INFO') return false;
        if (f.sensor && e.sensor !== f.sensor) return false;
        if (q && !entryText(e).toLowerCase().includes(q)) return false;
        return true;
    });
}

// Device shorthand in event details, in words: "AUTO LIMIT" -> "by the alert rule", "12%<20" -> "12 %, limit 20"
function humanDetail(detail) {
    const who = { 'AUTO LIMIT': 'By the alert rule', 'WEB UI': 'From the web page', MQTT: 'From Home Assistant / MQTT' };
    if (who[detail]) return who[detail];
    const m = /^([-\d.]+)([^<>\d]*)([<>])([-\d.]+)$/.exec(detail);
    return m ? `${m[1]}${m[2] ? ' ' + m[2] : ''} — limit ${m[4]}${m[2] ? ' ' + m[2] : ''}` : detail;
}

function entryTitle(e) {
    return e.kind === 'log' ? e.level : (EVENT_TEXT[e.raw.title] || [e.raw.title])[0];
}

function entryText(e) {
    const sensor = e.sensor && sensors(state.status).find(x => x.id === e.sensor);
    return [entryTitle(e), sensor ? sensorTitle(sensor) : '', e.kind === 'log' ? e.text : e.detail].filter(Boolean).join(' ');
}

function entryDate(e, now) {
    return e.t === null || now === null ? null : new Date(Date.now() - (now - e.t) * 1000);
}

function renderEventsTab() {
    const s = state.status;
    if (!s) return;
    const select = $('events-sensor');
    select.hidden = !multiSensor(s);
    if (!select.hidden && select.options.length !== sensors(s).length + 1) {
        select.innerHTML = '';
        select.appendChild(new Option('All sensors', ''));
        sensors(s).forEach(x => select.appendChild(new Option(sensorTitle(x), x.id)));
        select.value = state.filter.sensor;
    }
    $('log-level-wrap').hidden = !state.filter.cats.has('log');
    document.querySelectorAll('.events-filters .chip').forEach(c => c.setAttribute('aria-pressed', String(state.filter.cats.has(c.dataset.cat))));

    const now = deviceUptimeNow(s);
    const entries = visibleEntries(s);
    const all = timelineEntries(s).length;
    $('events-count').textContent = entries.length === all ? `${all} entries` : `${entries.length} of ${all} entries`;
    const box = $('events-timeline');
    box.innerHTML = '';
    if (!entries.length) {
        box.appendChild(el('p', 'empty muted', 'Nothing matches these filters.'));
        markEventsSeen(s);
        return;
    }
    let day = null;
    let list = null;
    entries.forEach(e => {
        const date = entryDate(e, now);
        const label = date ? dayLabel(date) : 'Earlier';
        if (label !== day) {
            day = label;
            box.appendChild(el('h3', 'timeline-day', label));
            list = el('ul', 'timeline-list');
            box.appendChild(list);
        }
        list.appendChild(timelineRow(e, date));
    });
    markEventsSeen(s);
}

function dayLabel(date) {
    const today = new Date();
    const yesterday = new Date(Date.now() - 86400000);
    if (date.toDateString() === today.toDateString()) return 'Today';
    if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
    return date.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' });
}

function timelineRow(e, date) {
    const sensor = e.sensor && sensors(state.status).find(x => x.id === e.sensor);
    const time = el('time', 'tl-time', date ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '');
    if (e.kind === 'log') {
        const li = el('li', `tl-row log ${e.level.toLowerCase()}`);
        const body = el('div', 'tl-body');
        body.append(el('span', `tl-level ${e.level.toLowerCase()}`, e.level), el('span', 'tl-log', e.text));
        li.append(el('span', 'tl-icon'), body, time);
        return li;
    }
    const [title, cls, iconName] = EVENT_TEXT[e.raw.title] || [e.raw.title, '', 'info'];
    const li = el('li', `tl-row ${cls}`);
    const body = el('div', 'tl-body');
    const head = el('div', 'tl-title');
    if (sensor) head.appendChild(el('span', 'tl-sensor', sensorTitle(sensor)));
    head.appendChild(document.createTextNode(title));
    body.append(head);
    if (e.detail) body.appendChild(el('div', 'tl-detail', humanDetail(e.detail)));
    const ic = el('span', 'tl-icon');
    ic.appendChild(icon(iconName));
    li.append(ic, body, time);
    return li;
}

// The Events tab badge counts alert / fault events you have not looked at yet.
function markEventsSeen(s) {
    const newest = (s.events || []).filter(e => ['alert', 'sensor'].includes(EVENT_CAT[e.title]) && e.title !== 'LIMIT CLEAR' && e.title !== 'SENSOR OK');
    if (newest.length) state.seenAlarmT = Math.max(state.seenAlarmT, ...newest.map(e => e.t));
    renderEventsBadge(s);
}

function renderEventsBadge(s) {
    const unseen = (s.events || []).filter(e => ['MIN LIMIT!', 'MAX LIMIT!', 'SENSOR FAULT'].includes(e.title) && e.t > state.seenAlarmT).length;
    const badge = $('events-badge');
    badge.hidden = !unseen || !$('tab-events').hidden;
    badge.textContent = unseen;
    badge.setAttribute('aria-label', `${unseen} new alert events`);
}

function eventsAsText() {
    const s = state.status;
    const now = deviceUptimeNow(s);
    return visibleEntries(s).map(e => {
        const date = entryDate(e, now);
        const when = date ? `${date.toLocaleDateString()} ${date.toLocaleTimeString()}` : '';
        return `${when}\t${entryText(e)}`;
    }).join('\n');
}

function setupEventsTab() {
    document.querySelectorAll('.events-filters .chip').forEach(chip => chip.addEventListener('click', () => {
        const cats = state.filter.cats;
        if (cats.has(chip.dataset.cat)) cats.delete(chip.dataset.cat); else cats.add(chip.dataset.cat);
        renderEventsTab();
    }));
    $('events-sensor').addEventListener('change', (e) => { state.filter.sensor = e.target.value; renderEventsTab(); });
    $('events-search').addEventListener('input', (e) => { state.filter.search = e.target.value; renderEventsTab(); });
    $('log-warn-only').addEventListener('change', (e) => { state.filter.warnOnly = e.target.checked; renderEventsTab(); });
    $('events-copy').addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(eventsAsText());
            showToast('Copied.');
        } catch (error) {
            showToast('Copying is blocked by the browser here; use Download.');
        }
    });
    $('events-download').addEventListener('click', () => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([eventsAsText()], { type: 'text/plain' }));
        a.download = `events-${(state.status && state.status.chip_id) || 'device'}.txt`;
        a.click();
        URL.revokeObjectURL(a.href);
    });
}

// ---------------------------------------------------------------- history

async function loadHistory() {
    // the sensor in view: the picked tab, or the only sensor (the device's default) on a single-sensor device
    const sensor = selectedSensor(state.status);
    const id = sensor ? sensor.id : (state.view !== 'all' ? state.view : '');
    if (!id && multiSensor(state.status)) return;   // the summary has no 24 h chart
    try {
        const data = await apiGet('/chart' + (id ? `?sensor=${encodeURIComponent(id)}` : ''));
        if (id && data.sensor && data.sensor !== (selectedSensor(state.status) || { id }).id) return;   // tab changed meanwhile
        if (data.points && data.points.length) {
            state.history = { values: data.points, stepSec: data.span_seconds || 60, unit: data.unit || '' };
        }
    } catch (error) {
        // keep the previous history
    }
    renderAll();
}

// ---------------------------------------------------------------- device

function signalQuality(rssi) {
    if (!num(rssi) || rssi === 0) return 'no signal';
    if (rssi >= -60) return 'excellent';
    if (rssi >= -70) return 'good';
    if (rssi >= -80) return 'fair';
    return 'weak';
}

function renderDevice(s) {
    const rssi = parseInt(s.wifi_signal, 10);
    const rows = [
        ['Sensors', sensors(s).map(x => x.name).join(', ') || '—'],
        ['WiFi network', s.wifi_network || '—'],
        ['Signal', num(rssi) ? `${rssi} dBm (${signalQuality(rssi)})` : '—'],
        ['IP address', s.ip_address || '—'],
        ['MQTT broker', s.mqtt_connected ? 'Connected' : 'Not connected'],
        ['Uptime', s.uptime || '—'],
        ['Free memory', num(s.free_heap) ? `${Math.round(s.free_heap / 1024)} KB` : '—'],
        ['Firmware', s.firmware_version || '—'],
        ['Device ID', s.chip_id || '—'],
        ['Errors / warnings', `${fmt(s.errors)} / ${fmt(s.warnings)} since start`],
    ];
    const dl = $('device-info');
    dl.innerHTML = '';
    rows.forEach(([k, v]) => {
        const item = el('div');
        item.append(el('dt', '', k), el('dd', '', v));
        dl.appendChild(item);
    });
}

// ---------------------------------------------------------------- settings

// One block per sensor type: on/off (with the poles it uses), then its own
// parameters and alert limits. Field names carry the sensor's settings prefix
// ("ad.distance_empty"), the same keys the firmware stores.
function renderSensorList(config) {
    const box = $('sensor-list');
    box.innerHTML = '';
    (config.sensors || []).forEach(sensor => box.appendChild(sensorBlock(sensor)));
    renderRelaySource();
}

function sensorBlock(sensor) {
    const block = el('section', 'sensor-block');
    block.dataset.sensor = sensor.id;
    block.dataset.inputs = (sensor.inputs || []).map(i => i.name).join(',');
    // Header: a disclosure button (name, poles, summary) and, beside it, the on/off switch
    const head = el('div', 'sensor-block-head');
    const expand = el('button', 'sensor-expand');
    expand.type = 'button';
    expand.id = `sensor-head-${sensor.id}`;
    expand.setAttribute('aria-controls', `sensor-body-${sensor.id}`);
    const poles = (sensor.inputs || []).map(i => `${i.pole} ${i.name}`).join(' + ');
    const text = el('span', 'sensor-expand-text');
    text.append(el('span', 'sensor-name', sensor.name), el('span', 'sensor-summary muted small'));
    const relayBadge = el('span', 'relay-badge', 'Drives the relay');
    relayBadge.hidden = true;
    expand.append(el('span', 'chevron'), text, relayBadge, el('span', 'sensor-poles muted small', poles ? `Poles ${poles}` : ''));
    const sw = el('label', 'switch');
    const toggle = document.createElement('input');
    toggle.type = 'checkbox';
    toggle.className = 'sensor-toggle';
    toggle.checked = !!sensor.enabled;
    toggle.setAttribute('aria-label', `${sensor.name} on`);
    const slider = el('span', 'slider');
    slider.setAttribute('aria-hidden', 'true');
    sw.append(toggle, slider, el('b', 'switch-state'));
    head.append(expand, sw);
    block.appendChild(head);

    const body = el('div', 'sensor-block-body');
    body.id = `sensor-body-${sensor.id}`;
    body.setAttribute('role', 'region');
    body.setAttribute('aria-labelledby', expand.id);
    const params = el('div', 'field-grid');
    (sensor.params || []).forEach(p => params.appendChild(paramField(sensor.prefix, p)));
    if (!(sensor.params || []).length) params.appendChild(el('p', 'muted small', 'This sensor has no extra settings.'));
    body.appendChild(params);
    body.appendChild(alertRows(sensor));
    const topic = el('small', 'hint');
    topic.append('MQTT state topic: ', el('code', 'sensor-topic', sensor.topic));
    body.appendChild(topic);
    block.appendChild(body);
    // Switching a sensor on opens it (it needs settings); switching it off closes it
    toggle.addEventListener('change', () => {
        setExpanded(block, toggle.checked);
        syncSensorBlock(block);
        renderRelaySource();
        onFormInput();
    });
    expand.addEventListener('click', () => setExpanded(block, expand.getAttribute('aria-expanded') !== 'true'));
    // Open from the start only when an enabled sensor still misses a required value
    const missing = sensor.enabled && (sensor.params || []).some(p => p.required && (p.value === undefined || p.value === ''));
    setExpanded(block, missing);
    syncSensorBlock(block);
    return block;
}

function setExpanded(block, open) {
    block.querySelector('.sensor-expand').setAttribute('aria-expanded', String(open));
    block.querySelector('.sensor-block-body').hidden = !open;
    block.classList.toggle('open', open);
}

// A switched-off sensor keeps its values but they are neither required nor sent.
function syncSensorBlock(block) {
    const on = block.querySelector('.sensor-toggle').checked;
    block.classList.toggle('off', !on);
    block.querySelector('.switch-state').textContent = on ? 'ON' : 'OFF';
    block.querySelectorAll('.sensor-block-body input, .sensor-block-body select').forEach(i => { i.disabled = !on; });
    updateBlockSummary(block);
}

// One line in the closed header: what the sensor does and its alerts, e.g. "Alerts: low 20, high 95"
function updateBlockSummary(block) {
    const out = block.querySelector('.sensor-summary');
    if (!block.querySelector('.sensor-toggle').checked) {
        out.textContent = 'Off';
        return;
    }
    const wrap = block.querySelector('.alert-rows');
    const p = wrap.dataset.prefix;
    const unit = (wrap.querySelector('.limit-unit') || {}).textContent || '';
    const parts = ['low', 'high'].filter(n => wrap.querySelector(`[data-switch="${p}limit_${n}_on"]`).checked)
        .map(n => `${n} ${wrap.querySelector(`[name="${p}limit_${n}"]`).value || '?'}${unit ? ' ' + unit : ''}`);
    const error = block.querySelector('.limit-error:not([hidden])') || block.querySelector(':invalid');
    out.textContent = error ? 'Needs attention' : parts.length ? `Alerts: ${parts.join(', ')}` : 'No alerts';
    out.classList.toggle('needs', !!error);
}

function paramField(prefix, p) {
    const key = prefix + p.key;
    const field = el('div', 'field');
    const label = el('label', '', p.label + (p.required ? ' *' : ''));
    label.htmlFor = `param-${key}`;
    const current = p.value !== undefined && p.value !== '' ? p.value : (p.default || '');
    let input;
    if (p.type === 'select') {
        input = document.createElement('select');
        (p.options || []).forEach(o => input.appendChild(new Option(o.label, o.value, false, o.value === current)));
        if (p.presets) {
            input.dataset.presets = JSON.stringify(p.presets);
            input.dataset.prefix = prefix;
            input.addEventListener('change', () => applyPreset(input));
        }
    } else {
        input = document.createElement('input');
        input.type = p.type || 'text';
        input.value = current;
        if (input.type === 'number') input.step = 'any';
    }
    input.id = `param-${key}`;
    input.name = key;
    if (p.required) input.required = true;
    field.append(label, input);
    const hint = el('small', 'hint', [PARAM_HINTS[p.key], p.default && p.type !== 'select' ? `Default: ${p.default}` : '']
        .filter(Boolean).join(' '));
    hint.dataset.defaultText = hint.textContent;
    field.appendChild(hint);
    return field;
}

function alertRows(sensor) {
    const lim = sensor.limits || {};
    const k = (name) => sensor.prefix + name;
    const wrap = el('div', 'alert-rows');
    wrap.dataset.prefix = sensor.prefix;
    const unit = () => {
        const u = el('span', 'limit-unit');
        u.dataset.unitOf = sensor.id;
        return u;
    };
    const row = (name, label, hint, value, on) => {
        const r = el('div', 'alert-row');
        const sw = el('label', 'switch');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.dataset.switch = k(`${name}_on`);
        cb.checked = on === '1';
        const state = el('b', 'switch-state');
        const text = el('span', 'switch-label', `${label} `);
        text.appendChild(state);
        sw.append(cb, el('span', 'slider'), text);
        const iu = el('div', 'input-unit');
        const input = document.createElement('input');
        input.type = 'number';
        input.step = 'any';
        input.name = k(name);
        input.value = value || '';
        input.setAttribute('aria-label', `${sensor.name} ${label}`);
        iu.append(input, unit());
        r.append(sw, iu, el('small', 'hint', hint));
        return r;
    };
    wrap.appendChild(el('span', 'row-label', 'Alerts (apply without a restart)'));
    wrap.appendChild(row('limit_low', 'Low alert', 'Alert when the reading drops below this value.', lim.low, lim.low_on));
    wrap.appendChild(row('limit_high', 'High alert', 'Alert when the reading rises above this value.', lim.high, lim.high_on));
    const r = el('div', 'alert-row');
    r.appendChild(el('span', 'row-label', 'Clear margin'));
    const iu = el('div', 'input-unit');
    const h = document.createElement('input');
    h.type = 'number';
    h.step = 'any';
    h.min = '0';
    h.placeholder = '0';
    h.name = k('limit_hysteresis');
    h.value = lim.hysteresis || '';
    h.setAttribute('aria-label', `${sensor.name} clear margin`);
    iu.append(h, unit());
    r.append(iu, el('small', 'hint', 'How far back inside the limit the reading must return before an alert clears.'));
    wrap.appendChild(r);
    wrap.appendChild(el('div', 'field-error limit-error'));
    wrap.querySelector('.limit-error').hidden = true;
    return wrap;
}

function enabledBlocks() {
    return [...document.querySelectorAll('.sensor-block')].filter(b => b.querySelector('.sensor-toggle').checked);
}

// "Follows the alerts of": one radio per switched-on sensor, so exactly one can
// drive the relay (the firmware also keeps a single relay_source). Shown only for
// the automatic modes; the chosen sensor's Settings block gets a badge.
function renderRelaySource() {
    const list = $('relay-source-list');
    const checked = list.querySelector('input:checked');
    const current = checked ? checked.value : (state.config && state.config.relay_source) || '';
    const blocks = enabledBlocks();
    const chosen = blocks.some(b => b.dataset.sensor === current) ? current : (blocks[0] && blocks[0].dataset.sensor);
    list.innerHTML = '';
    blocks.forEach(b => {
        const sensor = state.config.sensors.find(x => x.id === b.dataset.sensor);
        const label = el('label', 'choice');
        const radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'relay_source';
        radio.value = sensor.id;
        radio.checked = sensor.id === chosen;
        const text = el('span');
        text.append(el('b', '', sensor.name), el('small', 'relay-source-alerts', b.querySelector('.sensor-summary').textContent));
        label.append(radio, text);
        list.appendChild(label);
    });
    if (!blocks.length) list.appendChild(el('p', 'muted small', 'Switch on a sensor first.'));
    updateRelaySourceView();
}

function relaySourceId() {
    const r = document.querySelector('input[name="relay_source"]:checked');
    return r ? r.value : '';
}

function updateRelaySourceView() {
    const mode = document.querySelector('input[name="relay_mode"]:checked');
    const auto = !!mode && mode.value !== 'manual';
    $('relay-source-field').hidden = !auto;
    document.querySelectorAll('.sensor-block').forEach(b => {
        b.querySelector('.relay-badge').hidden = !auto || b.dataset.sensor !== relaySourceId();
    });
    document.querySelectorAll('#relay-source-list label').forEach(l => {
        const block = document.querySelector(`.sensor-block[data-sensor="${l.querySelector('input').value}"]`);
        l.querySelector('.relay-source-alerts').textContent = block.querySelector('.sensor-summary').textContent;
    });
}

function presetOf(select) {
    const presets = JSON.parse(select.dataset.presets || '{}');
    const option = select.options[select.selectedIndex];
    return { values: presets[select.value] || null, label: option ? option.text : '' };
}

// Choosing e.g. a tube fills in its known values; the fields stay editable.
function applyPreset(select) {
    const { values } = presetOf(select);
    if (!values) return;
    Object.entries(values).forEach(([key, value]) => {
        const input = $(`param-${select.dataset.prefix || ''}${key}`);
        if (input) input.value = value;
    });
    onFormInput();
}

function updatePresetHints() {
    document.querySelectorAll('#sensor-list select[data-presets]').forEach(select => {
        const { values, label } = presetOf(select);
        const all = JSON.parse(select.dataset.presets || '{}');
        const keys = new Set(Object.values(all).flatMap(v => Object.keys(v)));
        keys.forEach(key => {
            const input = $(`param-${select.dataset.prefix || ''}${key}`);
            if (!input) return;
            const hint = input.parentElement.querySelector('.hint');
            hint.innerHTML = '';
            if (!values || values[key] === undefined) {
                hint.textContent = hint.dataset.defaultText || '';
                return;
            }
            const same = parseFloat(input.value) === parseFloat(values[key]) || input.value === values[key];
            if (same) {
                hint.textContent = values[key] === '0' ? `No published ${label} value: off` : `${label} value`;
                return;
            }
            hint.append(`Changed from the ${label} value ${values[key]}. `);
            const reset = el('a', '', 'Use preset');
            reset.href = '#';
            reset.addEventListener('click', (e) => {
                e.preventDefault();
                input.value = values[key];
                onFormInput();
            });
            hint.appendChild(reset);
        });
    });
}

function formValues() {
    const values = {};
    for (const [k, v] of new FormData($('config-form')).entries()) values[k] = v;
    document.querySelectorAll('[data-switch]').forEach(sw => { if (!sw.disabled) values[sw.dataset.switch] = sw.checked ? '1' : '0'; });
    values.sensors = enabledBlocks().map(b => b.dataset.sensor).join(',');
    return values;
}

function renderAlertSwitches() {
    document.querySelectorAll('[data-switch]').forEach(sw => {
        const row = sw.closest('.alert-row');
        row.classList.toggle('off', !sw.checked);
        row.querySelector('.switch-state').textContent = sw.checked ? 'ON' : 'OFF';
        row.querySelector('input[type="number"]').required = sw.checked && !sw.disabled;
    });
    const mode = document.querySelector('input[name="relay_mode"]:checked');
    const source = document.querySelector(`.sensor-block[data-sensor="${relaySourceId()}"]`);
    const anyOn = source && [...source.querySelectorAll('[data-switch]')].some(sw => sw.checked);
    $('relay-mode-warning').hidden = !!anyOn || !source || !mode || mode.value === 'manual' || $('relay-settings').hidden;
}

function markClean() {
    state.formSnapshot = JSON.stringify(formValues());
    $('save-bar').hidden = true;
}

function onFormInput() {
    const dirty = JSON.stringify(formValues()) !== state.formSnapshot;
    $('save-bar').hidden = !dirty;
    renderAlertSwitches();
    updatePresetHints();
    validateSensors();
    document.querySelectorAll('.sensor-block').forEach(updateBlockSummary);
    updateRelaySourceView();
}

// Per sensor: limits make sense. Across sensors: no two need the same pole.
function validateSensors() {
    let ok = true;
    const used = {};
    enabledBlocks().forEach(block => {
        const wrap = block.querySelector('.alert-rows');
        const p = wrap.dataset.prefix;
        const on = (n) => wrap.querySelector(`[data-switch="${p}${n}_on"]`).checked;
        const val = (n) => parseFloat(wrap.querySelector(`[name="${p}${n}"]`).value);
        let message = '';
        if (on('limit_low') && !num(val('limit_low'))) message = 'Enter a value for the low alert, or switch it off.';
        else if (on('limit_high') && !num(val('limit_high'))) message = 'Enter a value for the high alert, or switch it off.';
        else if (on('limit_low') && on('limit_high') && val('limit_low') >= val('limit_high')) message = 'The low alert must be below the high alert.';
        (block.dataset.inputs || '').split(',').filter(Boolean).forEach(input => {
            if (used[input]) message = `Uses ${input}, which ${used[input]} already uses. Switch one of them off.`;
            else used[input] = block.querySelector('.switch-label').textContent;
        });
        const error = wrap.querySelector('.limit-error');
        error.hidden = !message;
        error.textContent = message;
        ok = ok && !message;
    });
    return ok;
}

async function loadConfig() {
    const config = await apiGet('/config');
    state.config = config;
    const set = (id, v) => { $(id).value = v || ''; };
    set('device-name', config.device_name);
    set('mqtt-host', config.mqtt_host);
    set('mqtt-port', config.mqtt_port || '1883');
    set('mqtt-user', config.mqtt_user);
    $('mqtt-pass').value = '';   // the device never sends the stored password
    $('mqtt-pass').placeholder = config.mqtt_pass_set ? 'Unchanged (leave empty to keep)' : 'No password';
    set('mqtt-device', config.mqtt_device);
    const mode = document.querySelector(`input[name="relay_mode"][value="${config.relay_mode || 'manual'}"]`);
    if (mode) mode.checked = true;
    $('relay-settings').hidden = !config.relay_available;
    $('relay-source-list').innerHTML = '';
    renderSensorList(config);
    renderTopics();
    markClean();
    renderAlertSwitches();
    validateSensors();
    renderHeader();
    if (state.status) renderAll();
}

function renderTopics() {
    const device = $('mqtt-device').value.trim() || (state.config && state.config.chip_id ? `esp_${state.config.chip_id}` : '<device>');
    const ids = enabledBlocks().map(b => b.dataset.sensor);
    $('mqtt-topics').textContent = ids.length ? ids.map(id => `${device}/stat/${id}`).join(', ') : 'Switch on a sensor first.';
    document.querySelectorAll('.sensor-block').forEach(b => { b.querySelector('.sensor-topic').textContent = `${device}/stat/${b.dataset.sensor}`; });
}

async function saveConfig(event) {
    event.preventDefault();
    const form = $('config-form');
    // open every block that has a problem, so the browser can point at the field
    const ok = validateSensors();
    enabledBlocks().forEach(b => {
        if (b.querySelector(':invalid') || b.querySelector('.limit-error:not([hidden])')) setExpanded(b, true);
    });
    if (!ok || !form.reportValidity()) return;
    const values = formValues();
    const before = JSON.parse(state.formSnapshot || '{}');
    const needsRestart = Object.keys(values).some(k => !LIVE_SETTING.test(k) && values[k] !== before[k]);
    try {
        await apiPost('/config', values);
        markClean();
        if (needsRestart) {
            if (confirm('Saved. Sensor and MQTT changes take effect after a restart. Restart now?')) {
                await apiPost('/restart');
                showToast('Restarting… this page reconnects by itself.');
            }
        } else {
            showToast('Saved and applied.');
        }
        await loadConfig();
        setTimeout(requestStatus, 300);
    } catch (error) {
        showToast(`Not saved: ${error.message}`);
    }
}

// ---------------------------------------------------------------- start

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tabs button').forEach(b => b.addEventListener('click', () => {
        history.replaceState(null, '', `#${b.dataset.tab}`);
        selectTab(b.dataset.tab);
    }));
    window.addEventListener('hashchange', () => selectTab(location.hash.slice(1)));
    document.addEventListener('change', (e) => { if (e.target.matches('[data-switch], input[name="relay_mode"], input[name="relay_source"]')) onFormInput(); });
    selectTab(location.hash.slice(1) || 'overview');

    $('relay-toggle').addEventListener('change', toggleRelay);
    setupEventsTab();
    $('config-form').addEventListener('submit', saveConfig);
    $('config-form').addEventListener('input', onFormInput);
    $('discard-btn').addEventListener('click', () => loadConfig().catch(() => {}));
    $('mqtt-device').addEventListener('input', renderTopics);
    $('sensor-list').addEventListener('change', renderTopics);
    $('upload-btn').addEventListener('click', uploadBinary);
    $('upload-file').addEventListener('change', (e) => {
        const file = e.target.files[0];
        $('upload-name').textContent = file ? `${file.name} (${Math.round(file.size / 1024)} KB)` : 'No file chosen';
        $('upload-btn').disabled = !file;
    });
    document.querySelectorAll('.segmented button').forEach(b => b.addEventListener('click', () => {
        state.chartRange = b.dataset.range;
        if (b.dataset.range === '24h') loadHistory();
        else renderAll();
    }));
    $('restart-btn').addEventListener('click', restartDevice);
    $('reset-btn').addEventListener('click', resetDevice);

    let resizeTimer;
    window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderAll, 150); });
    setInterval(renderConnection, 1000);
    setInterval(() => { if (isStale()) renderAll(); }, 5000);
    setInterval(loadHistory, 60000);

    connect();
    pollStatus();
    loadHistory();
    loadConfig().catch(error => showToast(`Could not load settings: ${error.message}`));
});
