// App state, tabs, Overview/History/Device rendering and the settings form.
const STALE_AFTER_MS = 10000;      // status is broadcast every 2 s
const LIVE_SETTINGS = ['limit_low', 'limit_high', 'limit_low_on', 'limit_high_on', 'limit_hysteresis', 'relay_mode'];

const state = {
    status: null,
    config: null,
    history: null,
    chartRange: null,   // null = default per sensor: tanks 24 h, the rest live
    lastUpdate: 0,
    formSnapshot: '',
};

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
    if (!message) return;
    const log = $('log-container');
    const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 4;
    log.appendChild(el('div', '', message));
    while (log.children.length > 300) log.removeChild(log.firstChild);
    if (atBottom) log.scrollTop = log.scrollHeight;
}

// ---------------------------------------------------------------- tabs

function selectTab(name) {
    if (!$(`tab-${name}`)) name = 'overview';
    document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
    document.querySelectorAll('.tab-panel').forEach(p => { p.hidden = p.id !== `tab-${name}`; });
    if (name === 'overview') renderAll();
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
    const name = (state.config && state.config.device_name) || (s && s.active_plugin_name) || 'ESP Measurement Platform';
    $('device-title').textContent = name;
    document.title = name;
    if (s) $('device-subtitle').textContent = [s.active_plugin_name, s.chip_id ? `ID ${s.chip_id}` : ''].filter(Boolean).join(' · ');
}

function renderAll() {
    renderConnection();
    renderHeader();
    const s = state.status;
    if (!s) return;
    document.body.classList.toggle('stale', isStale());
    if (!$('tab-overview').hidden) renderOverview(s);
    if (!$('tab-device').hidden) renderDevice(s);
    document.querySelectorAll('.limit-unit').forEach(n => { n.textContent = (s.screen && s.screen.unit) || ''; });
}

// ---------------------------------------------------------------- overview

function alertCard(cls, iconName, title, detail, meta, action) {
    const card = el('div', `alert ${cls}`);
    const body = el('div', 'alert-body');
    body.appendChild(el('div', 'alert-title', title));
    if (detail) body.appendChild(el('div', 'alert-detail', detail));
    if (meta) body.appendChild(el('div', 'alert-meta', meta));
    card.append(icon(iconName), body);
    if (action) card.appendChild(action);
    return card;
}

function lastEventAge(s, titles) {
    const e = (s.events || []).find(ev => titles.includes(ev.title));
    return e && num(s.uptime_s) ? s.uptime_s - e.t : null;
}

function renderAlerts(s) {
    const slot = $('alert-slot');
    slot.innerHTML = '';
    const screen = s.screen;
    if (isStale()) {
        slot.appendChild(alertCard('warn', 'warn', 'Connection to the device lost',
            `The values below are from ${formatDuration((Date.now() - state.lastUpdate) / 1000)} ago. This page keeps retrying.`));
    }
    if (!screen) {
        slot.appendChild(alertCard('warn', 'info', 'No sensor selected', 'Choose the sensor type in Settings to start measuring.'));
        return;
    }
    if (!screen.sensor_ok) {
        const age = lastEventAge(s, ['SENSOR FAULT']);
        slot.appendChild(alertCard('alarm', 'plug', 'Sensor fault', FAULT_HINTS[s.active_plugin] || 'Check the sensor wiring.',
            age !== null ? `Since ${formatClock(new Date(Date.now() - age * 1000))}` : ''));
    }
    const limits = s.limits || {};
    if (limits.state && limits.state !== 'normal') {
        const view = viewFor(screen);
        const below = limits.state === 'low';
        const limit = below ? limits.low : limits.high;
        let detail = `${fmt(screen.value, screen.decimals)} ${screen.unit} — alert ${below ? 'below' : 'above'} ${fmt(limit, screen.decimals)} ${screen.unit}.`;
        if (s.relay && s.relay.available && s.relay.mode !== 'manual') detail += ` Relay switched ${s.relay.on ? 'ON' : 'OFF'} automatically.`;
        const advice = view.advice[below ? 'low' : 'high'];
        if (advice) detail += ` ${advice}`;
        const age = lastEventAge(s, ['MIN LIMIT!', 'MAX LIMIT!']);
        const since = age !== null ? `Since ${formatClock(new Date(Date.now() - age * 1000))}` : '';
        let action = null;
        if (limits.alert) {
            action = el('button', 'btn', 'Acknowledge');
            action.type = 'button';
            action.addEventListener('click', acknowledgeAlert);
        }
        slot.appendChild(alertCard('alarm', 'alarm', `${view.noun} ${below ? 'below' : 'above'} the alert limit`, detail,
            [since, limits.alert ? '' : 'Acknowledged'].filter(Boolean).join(' · '), action));
    } else if (screen.kind === 'radiation' && screen.valid) {
        const avg = stat(s, 'dose_avg_5m');
        if (num(avg) && avg >= 0.2) {
            slot.appendChild(alertCard(avg >= 10 ? 'alarm' : 'warn', 'warn', doseBand(avg).label,
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

function renderRelay(s) {
    const card = $('relay-card');
    const relay = s.relay;
    card.hidden = !(relay && relay.available);
    if (card.hidden) return;
    const auto = relay.mode !== 'manual';
    const stateEl = $('relay-state');
    stateEl.textContent = relay.on ? 'ON' : 'OFF';
    stateEl.className = 'relay-state' + (relay.on ? ' on' : '');
    $('relay-mode').textContent = auto ? 'Automatic' : 'Manual';
    $('relay-info').textContent = (auto
        ? `Follows the alert: ${relay.mode === 'on_alarm' ? 'on' : 'off'} while a limit is exceeded. Change this in Settings.`
        : 'Switch it here or from Home Assistant.') + ` Switched on ${relay.activations}× since start.`;
    const toggle = $('relay-toggle');
    toggle.textContent = relay.on ? 'Turn off' : 'Turn on';
    toggle.disabled = auto || isStale();
    toggle.dataset.target = relay.on ? 'off' : 'on';
}

function renderOverview(s) {
    renderAlerts(s);
    const hero = $('hero-card');
    hero.innerHTML = '';
    hero.classList.toggle('stale', isStale());
    if (s.screen) hero.appendChild(viewFor(s.screen).hero(s, state.history));
    else hero.appendChild(el('div', 'skeleton', 'No sensor configured yet.'));
    renderTiles(s);

    if (s.screen) renderTrend(s);
    renderRelay(s);
    renderEventsCard(s);
}

function chartRange(screen) {
    return state.chartRange || (screen.kind === 'level' ? '24h' : 'live');
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
        values, stepSec: step, unit: screen.unit, decimals: screen.decimals,
        limits: s.limits || {}, bars: history && screen.kind === 'radiation',
        yMin: screen.scale_min, yMax: screen.kind === 'level' ? screen.scale_max : undefined,
        emptyText: !screen.sensor_ok ? 'No data while the sensor is faulty'
            : history ? 'No history stored yet: it builds up over the first hours after a restart' : 'Collecting the first readings…',
    });

    const summary = $('trend-summary');
    summary.innerHTML = '';
    const vals = values.filter(num);
    if (vals.length > 1) {
        const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
        [['Lowest', Math.min(...vals)], ['Average', avg], ['Highest', Math.max(...vals)]].forEach(([label, v]) => {
            const item = el('div', 'muted', label);
            item.appendChild(el('b', '', `${fmt(v, screen.decimals)} ${screen.unit}`));
            summary.appendChild(item);
        });
    }
}

function renderEventsCard(s) {
    const events = s.events || [];
    renderEvents($('events-list'), events, s.uptime_s);
    if (!events.length) {
        $('events-summary').textContent = 'none since the device started';
        return;
    }
    const latest = events[0];
    const [title] = EVENT_TEXT[latest.title] || [latest.title];
    const ago = num(s.uptime_s) ? s.uptime_s - latest.t : null;
    $('events-summary').textContent = `${events.length} since start · latest: ${title}` +
        (ago !== null ? `, ${formatClock(new Date(Date.now() - ago * 1000))}` : '');
}

async function acknowledgeAlert() {
    try {
        await apiPost('/display?action=dismiss');
        showToast('Alert acknowledged. It stays listed until the reading is back within limits.');
        setTimeout(requestStatus, 300);
    } catch (error) {
        showToast(`Could not acknowledge: ${error.message}`);
    }
}

async function toggleRelay() {
    const target = $('relay-toggle').dataset.target;
    if (!target) return;
    if (!confirm(`Switch the relay ${target.toUpperCase()}?`)) return;
    try {
        await apiPost(`/relay?state=${target}`);
        setTimeout(requestStatus, 300);
    } catch (error) {
        showToast(`Relay not switched: ${error.message}`);
    }
}

// ---------------------------------------------------------------- history

async function loadHistory() {
    try {
        const data = await apiGet('/chart');
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
        ['Sensor type', s.active_plugin_name || '—'],
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

function renderPluginParams(params) {
    const box = $('plugin-params');
    box.innerHTML = '';
    if (!params || !params.length) {
        box.appendChild(el('p', 'muted small', 'This sensor has no extra settings.'));
        return;
    }
    params.forEach(p => {
        const field = el('div', 'field');
        const label = el('label', '', p.label + (p.required ? ' *' : ''));
        label.htmlFor = `param-${p.key}`;
        const current = p.value !== undefined && p.value !== '' ? p.value : (p.default || '');
        let input;
        if (p.type === 'select') {
            input = document.createElement('select');
            (p.options || []).forEach(o => input.appendChild(new Option(o.label, o.value, false, o.value === current)));
            if (p.presets) {
                input.dataset.presets = JSON.stringify(p.presets);
                input.addEventListener('change', () => applyPreset(input));
            }
        } else {
            input = document.createElement('input');
            input.type = p.type || 'text';
            input.value = current;
            if (input.type === 'number') input.step = 'any';
        }
        input.id = `param-${p.key}`;
        input.name = p.key;
        if (p.required) input.required = true;
        field.append(label, input);
        const hint = el('small', 'hint', p.default && p.type !== 'select' ? `Default: ${p.default}` : '');
        hint.dataset.defaultText = hint.textContent;
        field.appendChild(hint);
        box.appendChild(field);
    });
    updatePresetHints();
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
        const input = $(`param-${key}`);
        if (input) input.value = value;
    });
    onFormInput();
}

function updatePresetHints() {
    document.querySelectorAll('#plugin-params select[data-presets]').forEach(select => {
        const { values, label } = presetOf(select);
        const all = JSON.parse(select.dataset.presets || '{}');
        const keys = new Set(Object.values(all).flatMap(v => Object.keys(v)));
        keys.forEach(key => {
            const input = $(`param-${key}`);
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
    document.querySelectorAll('[data-switch]').forEach(sw => { values[sw.dataset.switch] = sw.checked ? '1' : '0'; });
    return values;
}

function renderAlertSwitches() {
    document.querySelectorAll('[data-switch]').forEach(sw => {
        const row = sw.closest('.alert-row');
        row.classList.toggle('off', !sw.checked);
        row.querySelector('.switch-state').textContent = sw.checked ? 'ON' : 'OFF';
        row.querySelector('input[type="number"]').required = sw.checked;
    });
    const anyOn = $('limit-low-on').checked || $('limit-high-on').checked;
    const mode = document.querySelector('input[name="relay_mode"]:checked');
    $('relay-mode-warning').hidden = anyOn || !mode || mode.value === 'manual' || $('relay-mode-group').hidden;
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
    validateLimits();
}

function validateLimits() {
    const lowOn = $('limit-low-on').checked;
    const highOn = $('limit-high-on').checked;
    const low = parseFloat($('limit-low').value);
    const high = parseFloat($('limit-high').value);
    let message = '';
    if (lowOn && !num(low)) message = 'Enter a value for the low alert, or switch it off.';
    else if (highOn && !num(high)) message = 'Enter a value for the high alert, or switch it off.';
    else if (lowOn && highOn && low >= high) message = 'The low alert must be below the high alert.';
    const error = $('limit-error');
    error.hidden = !message;
    error.textContent = message;
    return !message;
}

async function loadConfig(pluginId) {
    const config = await apiGet('/config' + (pluginId ? `?plugin=${encodeURIComponent(pluginId)}` : ''));
    if (pluginId) {
        renderPluginParams(config.plugin_params);
        onFormInput();
        return;
    }
    state.config = config;
    const plugins = await apiGet('/plugins');
    const select = $('active-plugin');
    select.innerHTML = '';
    if (!plugins.plugins.some(p => p.active)) select.appendChild(new Option('Choose a sensor…', '', true, true));
    plugins.plugins.forEach(p => select.appendChild(new Option(p.name, p.id, false, p.active)));

    const set = (id, v) => { $(id).value = v || ''; };
    set('device-name', config.device_name);
    set('mqtt-host', config.mqtt_host);
    set('mqtt-port', config.mqtt_port || '1883');
    set('mqtt-user', config.mqtt_user);
    set('mqtt-pass', config.mqtt_pass);
    set('mqtt-device', config.mqtt_device);
    set('mqtt-topic', config.mqtt_topic);
    set('limit-low', config.limit_low);
    set('limit-high', config.limit_high);
    set('limit-hysteresis', config.limit_hysteresis);
    const switchOn = (flag, value) => flag !== undefined ? flag === '1' : !!value;
    $('limit-low-on').checked = switchOn(config.limit_low_on, config.limit_low);
    $('limit-high-on').checked = switchOn(config.limit_high_on, config.limit_high);
    const mode = document.querySelector(`input[name="relay_mode"][value="${config.relay_mode || 'manual'}"]`);
    if (mode) mode.checked = true;
    $('relay-mode-group').hidden = !config.relay_available;
    renderPluginParams(config.plugin_params);
    markClean();
    renderAlertSwitches();
    validateLimits();
    renderHeader();
}

async function saveConfig(event) {
    event.preventDefault();
    const form = $('config-form');
    if (!validateLimits() || !form.reportValidity()) return;
    const values = formValues();
    const before = JSON.parse(state.formSnapshot || '{}');
    const needsRestart = Object.keys(values).some(k => !LIVE_SETTINGS.includes(k) && values[k] !== before[k]);
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
    document.addEventListener('change', (e) => { if (e.target.matches('[data-switch], input[name="relay_mode"]')) onFormInput(); });
    selectTab(location.hash.slice(1) || 'overview');

    $('relay-toggle').addEventListener('click', toggleRelay);
    $('config-form').addEventListener('submit', saveConfig);
    $('config-form').addEventListener('input', onFormInput);
    $('discard-btn').addEventListener('click', () => loadConfig().catch(() => {}));
    $('active-plugin').addEventListener('change', (e) => loadConfig(e.target.value).catch(() => {}));
    $('mqtt-device').addEventListener('input', (e) => {
        const plugin = $('active-plugin').value;
        if (e.target.value.trim() && plugin) $('mqtt-topic').value = `${e.target.value.trim()}/stat/${plugin}`;
    });
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
