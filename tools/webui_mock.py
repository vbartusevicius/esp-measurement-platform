"""Mock ESP Measurement Platform for developing and previewing the web UI
(data/) without hardware: serves the real UI plus the REST/WebSocket API with
simulated sensors.

    python3 tools/webui_mock.py [port]      then open http://127.0.0.1:8790/?sensor=tank

Scenarios: house, house-alarm (four sensors side by side), tank, tank-basic, tank-alarm, pressure, radiation,
radiation-high, water, water-leak, gas, fault.
Add &clean=1 to hide the scenario switcher (used for the README screenshots).
"""
import base64, hashlib, json, math, os, struct, sys, threading, time
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
START = time.time()
BOOT_UPTIME = 3 * 86400 + 5 * 3600   # pretend the device has been up 3 d 5 h

PLUGINS = {
    'analog_distance': 'Analog Distance Meter',
    'ultrasonic_distance': 'Ultrasonic Distance Meter',
    'radiation_counter': 'Radiation Counter Gateway',
    'analog_voltage': 'Pressure / 0-10 V Sensor',
    'pulse_meter': 'Pulse Meter (water, gas, oil)',
}

# firmware: ScopedSettings::prefixFor() and the sensor-bank poles each plugin needs (IPlugin::inputs)
PREFIX = {'analog_distance': 'ad.', 'ultrasonic_distance': 'ud.', 'radiation_counter': 'rc.', 'analog_voltage': 'av.',
          'pulse_meter': 'pm.'}
INPUTS = {'analog_distance': [(3, '4-20mA')], 'ultrasonic_distance': [(5, 'IO1'), (6, 'IO2')],
          'radiation_counter': [(7, 'IO3')], 'analog_voltage': [(4, '0-10V')], 'pulse_meter': [(8, 'IO4')]}
LIMIT_KEYS = ('limit_low', 'limit_high', 'limit_low_on', 'limit_high_on', 'limit_hysteresis')

COMMON_DISTANCE = [
    ('avg_sample_count', 'Median Window Samples', '10', 'number', False),
    ('sampling_interval', 'Sampling Interval (s)', '10', 'number', False),
    ('level_deadband_cm', 'Change Deadband (cm)', '10', 'number', False),
    ('step_confirm_samples', 'Step Confirm Samples', '5', 'number', False),
    ('max_change_cm_min', 'Max Change Rate (cm/min, 0=off)', '0', 'number', False),
    ('total_volume', 'Total Volume (L)', '', 'number', False),
]
PARAMS = {
    'analog_distance': [('sensor_range', 'Sensor Range (m)', '5', 'number', True),
                        ('distance_empty', 'Empty Reading (cm)', '10', 'number', True),
                        ('distance_full', 'Full Reading (cm)', '100', 'number', True)] + COMMON_DISTANCE,
    'ultrasonic_distance': [('distance_empty', 'Empty Distance (cm)', '200', 'number', True),
                            ('distance_full', 'Full Distance (cm)', '20', 'number', True)] + COMMON_DISTANCE,
    'radiation_counter': [('tube_model', 'Geiger tube', 'j305', 'select', False),
                          ('tube_conversion_factor', 'Tube Factor (CPM/uSv/h)', '123.1', 'number', False),
                          ('tube_dead_time_us', 'Tube Dead Time (us, 0=off)', '180', 'number', False),
                          ('alert_dose_usv_h', 'Alert Threshold (uSv/h avg)', '0.3', 'number', False),
                          ('display_graph_resolution', 'Graph Bar Seconds', '600', 'number', False)],
    'analog_voltage': [('voltage_min', 'Sensor Output at Min (V)', '0.5', 'number', True),
                       ('voltage_max', 'Sensor Output at Max (V)', '4.5', 'number', True),
                       ('value_min', 'Value at Min', '0', 'number', True),
                       ('value_max', 'Value at Max', '10', 'number', True),
                       ('value_unit', 'Unit (bar, psi, kPa, V...)', 'bar', 'text', False),
                       ('value_decimals', 'Decimals', '1', 'number', False),
                       ('display_title', 'Display Title (4 chars)', 'PRES', 'text', False),
                       ('sampling_interval', 'Sampling Interval (s)', '5', 'number', False)],
    'pulse_meter': [('meter_medium', 'Medium', 'water', 'select', False),
                    ('meter_liters_per_pulse', 'Litres per Pulse (K)', '1', 'number', True),
                    ('meter_reading_m3', 'Meter Reading (m3)', '', 'number', False),
                    ('meter_min_pulse_gap_ms', 'Min Pulse Gap (ms)', '50', 'number', False),
                    ('meter_leak_hours', 'Leak Alert after (h, 0=off)', '24', 'number', False)],
}

TUBES = [('j305', 'J305 (glass, 107 mm)', '123.1', '180'), ('m4011', 'M4011 (glass, 88 mm)', '153.8', '0'),
         ('sbm20', 'SBM-20 / СБМ-20', '175.4', '190'), ('sts5', 'STS-5 / СТС-5', '175.4', '190'),
         ('si29bg', 'SI-29BG / СИ-29БГ', '122', '0'), ('sbm19', 'SBM-19 / СБМ-19', '476.2', '0'),
         ('lnd712', 'LND 712 (end window)', '108', '90'), ('si3bg', 'SI-3BG / СИ-3БГ (high range)', '1.58', '0')]
SELECT_EXTRA = {'meter_medium': dict(options=[dict(value='water', label='Water'), dict(value='gas', label='Gas'),
                                               dict(value='oil', label='Oil / fuel'), dict(value='other', label='Other (volume)')],
                                      presets={}),
                'tube_model': dict(
    options=[dict(value=t[0], label=t[1]) for t in TUBES] + [dict(value='custom', label='Other / custom')],
    presets={t[0]: {'tube_conversion_factor': t[2], 'tube_dead_time_us': t[3]} for t in TUBES})}

SCENARIOS = {
    'house': dict(label='House: tank + pressure + radiation + water', name='Utility room', relay=True, mode='off_alarm',
                  source='analog_distance', parts=['tank', 'pressure', 'radiation', 'water']),
    'house-alarm': dict(label='House with alerts (tank low, radiation, leak)', name='Utility room', relay=True, mode='off_alarm',
                        source='analog_distance', parts=['tank-alarm', 'pressure', 'radiation-high', 'water-leak']),
    'tank': dict(label='Water tank (4–20 mA, with volume)', plugin='analog_distance', name='Rainwater tank',
                 relay=True, mode='manual', low='20', high='95', hyst='5', capacity=3000, base=64.0,
                 values={'total_volume': '3000', 'distance_empty': '250', 'distance_full': '30'}),
    'tank-basic': dict(label='Tank, ultrasonic (no volume, setup unfinished)', plugin='ultrasonic_distance', name='Well',
                       relay=True, mode='manual', low='', high='', hyst='', capacity=None, base=47.0, values={}),
    'tank-alarm': dict(label='Tank below MIN, relay automatic', plugin='analog_distance', name='Rainwater tank',
                       relay=True, mode='off_alarm', low='20', high='95', hyst='5', capacity=3000, base=12.4,
                       values={'total_volume': '3000'}),
    'pressure': dict(label='Water pressure 0.5–4.5 V (pump cycling)', plugin='analog_voltage', name='House water pressure',
                     relay=True, mode='off_alarm', low='1.5', high='5.5', hyst='0.3', values={}),
    'radiation': dict(label='Radiation, normal background', plugin='radiation_counter', name='Basement radiation',
                      relay=True, mode='manual', low='', high='0.3', hyst='0.05', dose=0.11,
                      values={'tube_model': 'j305', 'tube_conversion_factor': '123.1', 'tube_dead_time_us': '180'}),
    'radiation-high': dict(label='Radiation, elevated (alert)', plugin='radiation_counter', name='Basement radiation',
                           relay=True, mode='on_alarm', low='', high='0.3', hyst='0.05', dose=0.42,
                           values={'tube_model': 'm4011', 'tube_conversion_factor': '150', 'tube_dead_time_us': '0'}),
    'gas': dict(label='Gas meter (dial reader, 10 L per turn)', plugin='pulse_meter', name='House gas', relay=False,
                mode='manual', low='', high='', hyst='', leak=False, medium='gas',
                values={'meter_medium': 'gas', 'meter_liters_per_pulse': '10', 'meter_reading_m3': '4821.3'}),
    'water': dict(label='Water meter (dial reader)', plugin='pulse_meter', name='House water', relay=True,
                  mode='off_alarm', low='', high='30', hyst='2', leak=False,
                  values={'meter_liters_per_pulse': '1', 'meter_reading_m3': '1666.6'}),
    'water-leak': dict(label='Water meter, continuous flow (leak)', plugin='pulse_meter', name='House water', relay=True,
                       mode='manual', low='', high='30', hyst='2', leak=True,
                       values={'meter_liters_per_pulse': '1', 'meter_reading_m3': '1666.6'}),
    'fault': dict(label='Tank with a sensor fault', plugin='analog_distance', name='Rainwater tank',
                  relay=True, mode='manual', low='20', high='95', hyst='5', capacity=3000, base=0, fault=True,
                  values={'total_volume': '3000'}),
}

runtime = {}   # per scenario mutable state: relay, ack, config overrides
lock = threading.Lock()
clients = []   # (conn, scenario)


def rt(name):
    if name not in runtime:
        s = SCENARIOS[name]
        cfg = {'relay_mode': s['mode'], 'relay_source': s.get('source', ''), 'device_name': s['name']}
        if 'parts' not in s:
            cfg.update({'limit_low': s['low'], 'limit_high': s['high'], 'limit_hysteresis': s['hyst'],
                        'limit_low_on': '1' if s['low'] else '0', 'limit_high_on': '1' if s['high'] else '0'})
        runtime[name] = {'relay_on': False, 'activations': 2, 'ack': False, 'last_state': None, 'config': cfg}
    return runtime[name]


def parts(name):
    """The single-sensor scenarios that make up a scenario (itself for the classic ones)."""
    return SCENARIOS[name].get('parts', [name])


def part_for(name, plugin):
    return next((p for p in parts(name) if SCENARIOS[p]['plugin'] == plugin), None)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def uptime():
    return int(BOOT_UPTIME + time.time() - START)


def noise(seed, amp):
    return amp * (math.sin(seed * 12.9898) * 43758.5453 % 1 - 0.5) * 2


def simulate(name):
    """Returns (screen, stats, history, history_step, chart_unit)."""
    s = SCENARIOS[name]
    t = time.time() - START
    if s['plugin'] in ('analog_distance', 'ultrasonic_distance'):
        if s.get('fault'):
            screen = dict(kind='level', title='TANK', value=0, text='0', unit='%', decimals=0, valid=False,
                          scale_min=0, scale_max=100, trend_bucket_s=60, trend=[], lines=[], sensor_label='SENS',
                          sensor_ok=False, raw='0.0cm', signal='0.0mA', low_24h=58, high_24h=71)
            hist = [71 - i * 0.12 for i in range(60)]
            # the same stats the firmware sends while the loop is open (DistancePluginBase::getStats)
            stats = [dict(key='level', label='Level', value='0.0%', numeric=0),
                     dict(key='depth', label='Depth', value='0.00 m', numeric=0),
                     dict(key='volume', label='Volume', value='0 L', numeric=0),
                     dict(key='capacity', label='Capacity', value=f"{s['capacity']} L", numeric=s['capacity']),
                     dict(key='distance', label='Distance', value='0.000 m', numeric=0),
                     dict(key='raw', label='Raw', value='0.000 m', numeric=0),
                     dict(key='sensor', label='Sensor', value='Disconnected', numeric=0),
                     dict(key='flow_rate', label='Flow Rate', value='+0.00 L/min', numeric=0),
                     dict(key='usage_24h', label='Usage 24h', value='0.0 L', numeric=0)]
            return screen, stats, hist, 900, '%'
        drain = 0.014 if s['capacity'] else 0.006            # %/min
        level = s['base'] - drain * t / 60 + 0.25 * math.sin(t / 40)
        trend = [s['base'] - drain * (t / 60 - (55 - i)) + 0.25 * math.sin((t - (55 - i) * 60) / 40) for i in range(56)]
        # 24 h: refill 14 h ago from 30 % to 92 %, then daily-use drawdown to now
        hist = []
        for i in range(96):
            hours_ago = (95 - i) * 0.25
            if hours_ago > 14:
                v = 30 + (hours_ago - 14) * 0.6
            else:
                v = level + (92 - level) * (hours_ago / 14) ** 1.1
            hist.append(round(v + noise(i, 0.3), 2))
        stats = [dict(key='level', label='Level', value=f'{level:.1f}%', numeric=level / 100, render='progress', primary=True),
                 dict(key='depth', label='Depth', value=f'{level / 100 * 2.2:.2f} m', numeric=level / 100 * 2.2, render='text', primary=True)]
        lines = [dict(label='DEP', value=f'{level / 100 * 2.2:.2f}m'), dict(label='DST', value=f'{2.5 - level / 100 * 2.2:.2f}m')]
        if s['capacity']:
            vol = level / 100 * s['capacity']
            flow = -drain / 100 * s['capacity'] + noise(int(t / 2), 0.05)
            stats += [dict(key='volume', label='Volume', value=f'{vol:.0f} L', numeric=vol, render='text', primary=True),
                      dict(key='capacity', label='Capacity', value=f"{s['capacity']} L", numeric=s['capacity'], render='text', primary=False),
                      dict(key='flow_rate', label='Flow Rate', value=f'{flow:+.2f} L/min', numeric=round(flow, 2), render='text', primary=True),
                      dict(key='usage_24h', label='Usage 24h', value='612.0 L', numeric=612.0, render='text', primary=False)]
            lines = [dict(label='VOL', value=f'{vol:.0f}L'), dict(label='FLW', value=f'{flow:+.1f}Lm')]
        stats += [dict(key='distance', label='Distance', value=f'{2.5 - level / 100 * 2.2:.3f} m', numeric=2.5 - level / 100 * 2.2, render='text', primary=False),
                  dict(key='sensor', label='Sensor', value='Connected', numeric=1, render='text', primary=False)]
        screen = dict(kind='level', title='TANK', value=round(level, 1), text=f'{level:.0f}', unit='%', decimals=0, valid=True,
                      scale_min=0, scale_max=100, trend_bucket_s=60, trend=[round(v, 2) for v in trend], lines=lines,
                      sensor_label='SENS', sensor_ok=True, raw=f'{(2.5 - level / 100 * 2.2) * 100:.1f}cm',
                      signal='16.5mA' if s['plugin'] == 'analog_distance' else '14120us',
                      low_24h=round(min(hist), 1), high_24h=round(max(hist), 1))
        return screen, stats, hist, 900, '%'

    if s['plugin'] == 'analog_voltage':
        def pressure(sec):
            phase = (sec % 180) / 180          # pump cycle: drawdown 2.8 -> 4.2 bar recovery
            return 4.2 - 1.4 * phase if phase < 0.85 else 2.8 + 1.4 * (phase - 0.85) / 0.15
        p = pressure(t) + noise(int(t), 0.03)
        trend = [round(pressure(t - (55 - i) * 5), 2) for i in range(56)]
        hist = [round(3.5 + 0.25 * math.sin(i / 7) + noise(i, 0.1) - (0.9 if 30 < i < 34 else 0), 2) for i in range(96)]
        volts = 0.5 + p * 0.4
        stats = [dict(key='value', label='Value', value=f'{p:.1f} bar', numeric=p, render='text', primary=True),
                 dict(key='voltage', label='Input', value=f'{volts:.3f} V', numeric=volts, render='text', primary=False),
                 dict(key='sensor', label='Sensor', value='Connected', numeric=1, render='text', primary=False)]
        screen = dict(kind='pressure', title='PRES', value=round(p, 2), text=f'{p:.1f}', unit='bar', decimals=1, valid=True,
                      scale_min=0, scale_max=10, trend_bucket_s=5, trend=trend,
                      lines=[dict(label='IN', value=f'{volts:.2f}V'), dict(label='RNG', value='10bar')],
                      sensor_label='SENS', sensor_ok=True, raw=f'{p:.2f}bar', signal=f'{volts:.2f}V',
                      low_24h=round(min(hist + trend), 2), high_24h=round(max(hist + trend), 2))
        return screen, stats, hist, 900, 'bar'

    if s['plugin'] == 'pulse_meter':
        # Household use: morning and evening peaks; a leak adds a steady trickle that never stops
        def litres(bar):
            hour = (bar % 96) / 4
            use = 14 if 6.5 < hour < 8 else 9 if 18 < hour < 21 else 2 if 8 < hour < 23 else 0
            return max(0.0, use + noise(bar, use * 0.5)) + (1.5 if s['leak'] else 0)
        bar_now = int((BOOT_UPTIME + t) / 900)
        hist = [round(litres(bar_now - 95 + i), 1) for i in range(96)]
        usage = sum(hist)
        flow = (6.8 + noise(int(t / 7), 0.6)) if int(t / 60) % 5 < 2 else (0.1 if s['leak'] else 0.0)
        trend = [round((6.8 if (int(t / 60) - 55 + i) % 5 < 2 else (0.1 if s['leak'] else 0.0)) + noise(i, 0.4), 2) for i in range(56)]
        total = (4821300 if s.get('medium') == 'gas' else 1666600) + uptime() * 0.25
        cont = 27 if s['leak'] else 0
        stats = [dict(key='medium', label='Medium', value=s.get('medium', 'water'), numeric=0),
                 dict(key='total_m3', label='Meter Reading', value=f'{total / 1000:.3f} m³', numeric=round(total / 1000, 3)),
                 dict(key='flow_rate', label='Flow Rate', value=f'{flow:.1f} L/min', numeric=round(flow, 1)),
                 dict(key='usage_24h', label='Usage 24h', value=f'{usage:.0f} L', numeric=round(usage)),
                 dict(key='continuous_h', label='Continuous Flow', value=f'{cont} h', numeric=cont),
                 dict(key='pulses', label='Pulses since Start', value=str(int(uptime() * 0.25)), numeric=int(uptime() * 0.25)),
                 dict(key='liters_per_pulse', label='Litres per Pulse', value='1.0 L', numeric=1.0)]
        if s['leak']:
            stats.append(dict(key='leak', label='Leak', value='CONTINUOUS FLOW', numeric=1))
        screen = dict(kind='meter', title={'gas': 'GAS'}.get(s.get('medium'), 'WATR'), value=round(flow, 1), text=f'{flow:.1f}', unit='L/min', decimals=1, valid=True,
                      scale_min=0, scale_max=None, trend_bucket_s=60, trend=trend,
                      lines=[dict(label='TOT', value=f'{total / 1000:.1f}m3'), dict(label='24H', value=f'{usage:.0f}L')],
                      sensor_label='PULS', sensor_ok=True, raw=f'{total / 1000:.3f}m3', signal=f'{int(uptime() * 0.25)}p',
                      low_24h=0, high_24h=round(max(trend) + 4, 1))
        return screen, stats, hist, 900, 'L'

    base = s['dose']
    dose = max(0.0, base * (1 + noise(int(t), 0.35)))
    avg = base * (1 + noise(int(t / 30), 0.06))
    cpm = int(dose * 153.8)
    trend = [round(max(0, base * (1 + noise(int(t) - 55 + i, 0.35))), 3) for i in range(56)]
    hist = [round(max(0, (0.11 if name == 'radiation' or i < 110 else base) * (1 + noise(i, 0.12))), 3) for i in range(128)]
    stats = [dict(key='cpm', label='CPM', value=str(cpm), numeric=cpm, render='text', primary=True),
             dict(key='dose', label='Dose', value=f'{dose:.2f} µSv/h', numeric=dose, render='text', primary=True),
             dict(key='dose_avg_5m', label='Dose 5m avg', value=f'{avg:.2f} µSv/h', numeric=round(avg, 3), render='text', primary=True),
             dict(key='alert_threshold', label='Alert Threshold', value='0.30 µSv/h', numeric=0.3, render='text', primary=False),
             dict(key='counts_total', label='Total Counts', value=str(int(uptime() * base * 153.8 / 60)), numeric=int(uptime() * base * 153.8 / 60), render='text', primary=False)]
    screen = dict(kind='radiation', title='RAD', value=round(dose, 3), text=f'{dose:.2f}', unit='µSv/h', decimals=2, valid=True,
                  scale_min=0, scale_max=None, trend_bucket_s=1, trend=trend,
                  lines=[dict(label='CPM', value=str(cpm)), dict(label='5M', value=f'{avg:.2f}')],
                  sensor_label='TUBE', sensor_ok=True, raw=f'{cpm // 60}cps', signal=f'{uptime() * base * 153.8 / 60000:.1f}kp',
                  low_24h=round(min(hist), 3), high_24h=round(max(hist + [dose]), 3))
    return screen, stats, hist, 600, 'µSv/h'


def sensor_status(part, named):
    """One entry of status["sensors"], its limit state and its events (firmware: StatusJson / DeviceMonitor)."""
    s = SCENARIOS[part]
    r = rt(part)
    screen, stats, _, _, _ = simulate(part)
    cfg = r['config']
    low = num(cfg['limit_low']) if cfg['limit_low_on'] == '1' else None
    high = num(cfg['limit_high']) if cfg['limit_high_on'] == '1' else None
    basis = next((x['numeric'] for x in stats if x['key'] == 'dose_avg_5m'), screen['value'])
    st = 'normal'
    if screen['valid']:
        if low is not None and basis < low: st = 'low'
        elif high is not None and basis > high: st = 'high'
    if st != r['last_state']:
        r['ack'] = False
        r['last_state'] = st
    up = uptime()
    who = f"{screen['title']} " if named else ''
    events = []
    if st != 'normal':
        events.append(dict(t=up - 1260, title='MIN LIMIT!' if st == 'low' else 'MAX LIMIT!',
                           detail=(who + f"{screen['text']}{screen['unit'] if len(screen['unit']) <= 3 else ''}{'<' if st == 'low' else '>'}{cfg['limit_low'] if st == 'low' else cfg['limit_high']}")[:16]))
    if not screen['sensor_ok']:
        events.append(dict(t=up - 540, title='SENSOR FAULT', detail=(who + screen['signal'])[:16]))
    entry = {'id': s['plugin'], 'name': PLUGINS[s['plugin']], 'configured': part != 'tank-basic',
             'stats': [{k: v for k, v in x.items() if k in ('key', 'label', 'value', 'numeric')} for x in stats],
             'screen': screen, 'limits': {'low': low, 'high': high, 'state': st, 'alert': st != 'normal' and not r['ack'], 'trips': 1}}
    return entry, st, events


def status(name):
    s = SCENARIOS[name]
    r = rt(name)
    cfg = r['config']
    named = len(parts(name)) > 1
    sensors, events, states = [], [], {}
    for part in parts(name):
        entry, st, ev = sensor_status(part, named)
        sensors.append(entry)
        events += ev
        states[entry['id']] = st
    mode = cfg['relay_mode'] if s['relay'] else 'manual'
    source = cfg.get('relay_source') if cfg.get('relay_source') in states else sensors[0]['id']
    if s['relay'] and mode != 'manual':
        r['relay_on'] = (mode == 'on_alarm') == (states[source] != 'normal')
        if states[source] != 'normal':
            events.insert(0, dict(t=uptime() - 1260, title='RELAY ON' if r['relay_on'] else 'RELAY OFF', detail='AUTO LIMIT'))
    up = uptime()
    events.sort(key=lambda e: -e['t'])
    events += [dict(t=up - 7200, title='MQTT ONLINE', detail='192.168.0.10'), dict(t=up - 7212, title='MQTT OFFLINE', detail='192.168.0.10'),
               dict(t=12, title='MQTT ONLINE', detail='192.168.0.10'), dict(t=4, title='WIFI ONLINE', detail='HOME -58'),
               dict(t=0, title='SYSTEM BOOT', detail='FW V2026.10.23')]
    relay = {'available': s['relay'], 'on': r['relay_on'], 'activations': r['activations'], 'mode': mode}
    if mode != 'manual':
        relay['source'] = source
    return {
        'event': 'stats_update', 'chip_id': 'A4CF12B3C4D5',
        'wifi_network': 'HOME', 'wifi_signal': '-61', 'ip_address': '192.168.0.138', 'free_heap': 172032, 'mqtt_connected': True,
        'firmware_version': 'mock', 'errors': 0, 'warnings': 3, 'uptime': f'{up // 86400:02d}d {up % 86400 // 3600:02d}:{up % 3600 // 60:02d}:{up % 60:02d}',
        'uptime_s': up, 'configured': all(x['configured'] for x in sensors),
        'sensors': sensors, 'relay': relay, 'events': events[:16],
    }


def config(name):
    """GET /api/v1/config: every sensor type, enabled ones first (firmware: ConfigJson::writeConfig)."""
    s = SCENARIOS[name]
    r = rt(name)
    device = name.replace('-', '_')
    enabled = [SCENARIOS[p]['plugin'] for p in parts(name)]
    sensors = []
    for plugin in enabled + [k for k in PLUGINS if k not in enabled]:
        part = part_for(name, plugin)
        values = SCENARIOS[part]['values'] if part else {}
        lim = rt(part)['config'] if part else {}
        sensors.append(dict(
            id=plugin, name=PLUGINS[plugin], prefix=PREFIX[plugin], enabled=part is not None, topic=f'{device}/stat/{plugin}',
            inputs=[dict(pole=p, name=n) for p, n in INPUTS[plugin]],
            params=[dict(key=k, label=l, default=d, type=ty, required=req, value=values.get(k, d), **SELECT_EXTRA.get(k, {}))
                    for k, l, d, ty, req in PARAMS[plugin]],
            limits=dict(low=lim.get('limit_low', ''), high=lim.get('limit_high', ''), hysteresis=lim.get('limit_hysteresis', ''),
                        low_on=lim.get('limit_low_on', '0'), high_on=lim.get('limit_high_on', '0'))))
    return dict(chip_id='A4CF12B3C4D5', device_name=r['config']['device_name'], firmware_version='mock',
                mqtt_host='192.168.0.10', mqtt_port='1883', mqtt_user='', mqtt_pass_set=False, mqtt_device=device,
                relay_mode=r['config']['relay_mode'], relay_source=r['config'].get('relay_source', ''),
                relay_available=s['relay'], sensors=sensors)


def stamp(t):
    t = int(t)
    return f'{t // 86400:02d}d {t % 86400 // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}'


def mock_log(name):
    """The firmware's Logger lines ("00d 00:00:01 [INFO] text"), matching the events of status()."""
    up = uptime()
    lines = [(0, 'INFO', '=== ESP Measurement Platform ==='), (0, 'INFO', 'Firmware mock')]
    lines += [(1, 'INFO', f"Sensor: {PLUGINS[SCENARIOS[p]['plugin']]}") for p in parts(name)]
    lines += [(4, 'INFO', 'Connected to WiFi. IP: 192.168.0.138'), (12, 'INFO', 'Connected to MQTT broker'),
              (13, 'INFO', 'Home Assistant discovery published'),
              (up - 7212, 'WARN', 'MQTT connection lost, retrying in 5 s'), (up - 7200, 'INFO', 'Connected to MQTT broker')]
    for e in status(name)['events']:
        if e['title'] in ('MIN LIMIT!', 'MAX LIMIT!'):
            lines.append((e['t'], 'WARN', f"Limit alarm: {e['detail']}"))
        elif e['title'] == 'SENSOR FAULT':
            lines.append((e['t'], 'WARN', f"Sensor fault: {e['detail']}"))
        elif e['title'].startswith('RELAY'):
            lines.append((e['t'], 'INFO', f"Relay {e['title'][6:]} ({e['detail']})"))
    lines.append((up - 300, 'INFO', 'Settings saved'))
    return [f'{stamp(t)} [{lvl}] {msg}' for t, lvl, msg in sorted(lines, key=lambda x: x[0])]


MOCK_JS = """
(function () {
  const cur = (document.cookie.match(/mock_sensor=([^;]+)/) || [])[1] || 'tank';
  const bar = document.createElement('div');
  bar.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:99;background:#5b21b6;color:#fff;padding:6px 10px;border-radius:8px;font:13px system-ui;box-shadow:0 4px 12px rgba(0,0,0,.3)';
  bar.innerHTML = 'MOCK DEVICE &nbsp;<select style="font:inherit;border-radius:4px;padding:2px">' +
    %s.map(([k, l]) => `<option value="${k}" ${k === cur ? 'selected' : ''}>${l}</option>`).join('') + '</select>';
  bar.querySelector('select').onchange = e => { location.href = '/?sensor=' + e.target.value + location.hash; };
  document.body.appendChild(bar);
})();
""" % json.dumps([[k, v['label']] for k, v in SCENARIOS.items()])


def ws_send(conn, text):
    data = text.encode()
    n = len(data)
    head = b'\x81' + (bytes([n]) if n < 126 else bytes([126]) + struct.pack('>H', n) if n < 65536 else bytes([127]) + struct.pack('>Q', n))
    conn.sendall(head + data)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DATA, **k)

    def log_message(self, *a):
        pass

    def end_headers(self):
        if 'Cache-Control' not in ''.join(h.decode('latin-1') for h in getattr(self, '_headers_buffer', [])):
            self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def scenario(self):
        q = parse_qs(urlparse(self.path).query)
        if q.get('sensor', [''])[0] in SCENARIOS:
            return q['sensor'][0]
        c = SimpleCookie(self.headers.get('Cookie', ''))
        name = c['mock_sensor'].value if 'mock_sensor' in c else 'tank'
        return name if name in SCENARIOS else 'tank'

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        name = self.scenario()
        if u.path in ('/', '/index.html'):
            html = open(os.path.join(DATA, 'index.html')).read()
            if not parse_qs(u.query).get('clean'):
                html = html.replace('</body>', '<script src="/__mock.js"></script></body>')
            body = html.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Set-Cookie', f'mock_sensor={name}; Path=/')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == '/__phone':
            # 390 px phone frame on the same origin (desktop Chrome can't open a window that narrow)
            height = parse_qs(u.query).get('h', ['1600'])[0]
            body = (f'<body style="margin:0"><iframe src="/?sensor={name}&clean=1" width="390" height="{height}" '
                    f'style="border:0;display:block"></iframe></body>').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Set-Cookie', f'mock_sensor={name}; Path=/')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == '/__mock.js':
            body = MOCK_JS.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == '/ws':
            key = self.headers['Sec-WebSocket-Key']
            accept = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            self.send_response(101)
            self.send_header('Upgrade', 'websocket')
            self.send_header('Connection', 'Upgrade')
            self.send_header('Sec-WebSocket-Accept', accept)
            self.end_headers()
            self.wfile.flush()
            with lock:
                clients.append((self.connection, name))
            self.ws_loop(name)
            self.close_connection = True
        elif u.path == '/api/v1/status':
            self.send_json(status(name))
        elif u.path == '/api/v1/chart':
            want = parse_qs(u.query).get('sensor', [None])[0]
            part = part_for(name, want) if want else parts(name)[0]
            if not part:
                return self.send_json({})
            _, _, hist, step, unit = simulate(part)
            self.send_json({'sensor': SCENARIOS[part]['plugin'], 'points': hist, 'span_seconds': step, 'unit': unit})
        elif u.path == '/api/v1/config':
            self.send_json(config(name))
        else:
            super().do_GET()

    def ws_loop(self, name):
        conn = self.connection
        try:
            while True:
                h = conn.recv(2)
                if len(h) < 2:
                    break
                n = h[1] & 0x7F
                if n == 126:
                    n = struct.unpack('>H', conn.recv(2))[0]
                mask = conn.recv(4)
                body = bytearray(conn.recv(n))
                for i in range(len(body)):
                    body[i] ^= mask[i % 4]
                if h[0] & 0x0F == 8:
                    break
                msg = json.loads(body or b'{}')
                if msg.get('event') == 'request_status':
                    ws_send(conn, json.dumps(status(name)))
                elif msg.get('event') == 'request_logs':
                    ws_send(conn, json.dumps({'event': 'log_batch', 'messages': mock_log(name)}))
        except OSError:
            pass
        with lock:
            clients[:] = [c for c in clients if c[0] is not conn]

    def do_POST(self):
        u = urlparse(self.path)
        name = self.scenario()
        r = rt(name)
        q = parse_qs(u.query)
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else b''
        if u.path == '/api/v1/relay':
            if r['config']['relay_mode'] != 'manual':
                return self.send_json({'status': 'error', 'message': 'Relay follows the limit rule'}, 409)
            on = q.get('state', [''])[0] == 'on'
            if on and not r['relay_on']:
                r['activations'] += 1
            r['relay_on'] = on
        elif u.path == '/api/v1/alert/ack':
            want = q.get('sensor', [None])[0]
            for part in parts(name):
                if want is None or SCENARIOS[part]['plugin'] == want:
                    rt(part)['ack'] = True
        elif u.path == '/api/v1/config':
            cfg = json.loads(body or b'{}')
            # the same checks as ConfigJson::problem
            ids = [x for x in cfg.get('sensors', '').split(',') if x] if 'sensors' in cfg else []
            poles = [n for i in ids for _, n in INPUTS.get(i, [('', '?')])]
            if any(i not in PLUGINS for i in ids) or len(set(ids)) != len(ids):
                return self.send_json({'status': 'error', 'message': 'Unknown or repeated sensor'}, 400)
            if len(set(poles)) != len(poles):
                return self.send_json({'status': 'error', 'message': 'Two sensors need the same input'}, 400)
            for k in ('relay_mode', 'relay_source', 'device_name'):
                if k in cfg:
                    r['config'][k] = cfg[k]
            for plugin, prefix in PREFIX.items():
                part = part_for(name, plugin)
                if not part:
                    continue
                for k in LIMIT_KEYS:
                    if prefix + k in cfg:
                        rt(part)['config'][k] = cfg[prefix + k]
        self.send_json({'status': 'ok'})


def ticker():
    while True:
        time.sleep(2)
        with lock:
            targets = list(clients)
        for conn, name in targets:
            try:
                ws_send(conn, json.dumps(status(name)))
            except OSError:
                pass


if __name__ == '__main__':
    threading.Thread(target=ticker, daemon=True).start()
    print(f'Mock device on http://127.0.0.1:{PORT}/?sensor=house', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
