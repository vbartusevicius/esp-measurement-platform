"""Pixel-accurate 64x128 Portrait (and 128x64 Landscape) OLED screen renderer
and preview generator for the ESP Measurement Platform.

Implements a 4-tier instrumentation typography hierarchy:
  1. 10x16 Bold Hero Numerals (0-9, '.', '%', '-') for primary reading from 1.5 m away
  2. 5x7 Bold Font (6 px pitch) for inverted headers, units, and IPv4 addresses
  3. 4x6 Medium Variable-Width Font for key-value telemetry labels and values
  4. 3x5 Micro Font (4 px pitch) for dense timestamped event/error logs
"""

from pathlib import Path

FONT_5X7 = {
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "#": (".#.#.", "#####", ".#.#.", ".#.#.", "#####", ".#.#.", "....."),
    "%": ("##..#", "##.#.", "..#..", ".#...", "#..##", "....#", "....."),
    "(": ("..##.", ".#...", "#....", "#....", "#....", ".#...", "..##."),
    ")": (".##..", "...#.", "....#", "....#", "....#", "...#.", ".##.."),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    "/": ("....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    "<": ("...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."),
    ">": (".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."),
    "[": (".###.", ".#...", ".#...", ".#...", ".#...", ".#...", ".###."),
    "]": (".###.", "...#.", "...#.", "...#.", "...#.", "...#.", ".###."),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "..##.", ".#...", "#....", "#####"),
    "3": ("#####", "....#", "...#.", "..##.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "####.", "#...#", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "#...#", ".###."),
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "J": ("..###", "...#.", "...#.", "...#.", "#..#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"),
    "Y": ("#...#", ".#.#.", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "c": (".....", ".....", ".###.", "#...#", "#....", "#...#", ".###."),
    "d": ("....#", "....#", ".####", "#...#", "#...#", "#...#", ".####"),
    "h": ("#....", "#....", "####.", "#...#", "#...#", "#...#", "#...#"),
    "k": ("#....", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "m": (".....", ".....", "##.#.", "#.#.#", "#.#.#", "#...#", "#...#"),
    "u": (".....", ".....", "#...#", "#...#", "#...#", "#..##", ".##.#"),
    "v": (".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
}

# 10x15 Bold Hero Digits for primary measurement value (readable from 1.5m)
FONT_HERO_10X15 = {
    "0": (
        "..######..",
        ".########.",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        ".########.",
        "..######..",
    ),
    "1": (
        "....###...",
        "..#####...",
        ".######...",
        "....###...",
        "....###...",
        "....###...",
        "....###...",
        "....###...",
        "....###...",
        "....###...",
        "....###...",
        "....###...",
        "....###...",
        ".#########",
        ".#########",
    ),
    "2": (
        ".########.",
        "##########",
        "###....###",
        ".......###",
        ".......###",
        "......###.",
        "....####..",
        "..#####...",
        ".####.....",
        "###.......",
        "###.......",
        "###.......",
        "###.......",
        "##########",
        "##########",
    ),
    "3": (
        ".########.",
        "##########",
        ".......###",
        "......###.",
        ".....###..",
        "...#####..",
        "...######.",
        ".......###",
        ".......###",
        ".......###",
        ".......###",
        "###....###",
        "###....###",
        "##########",
        ".########.",
    ),
    "4": (
        ".....####.",
        "....#####.",
        "...######.",
        "..###.###.",
        ".###..###.",
        "###...###.",
        "###...###.",
        "##########",
        "##########",
        "......###.",
        "......###.",
        "......###.",
        "......###.",
        "......###.",
        "......###.",
    ),
    "5": (
        "##########",
        "##########",
        "###.......",
        "###.......",
        "###.......",
        "########..",
        "#########.",
        ".......###",
        ".......###",
        ".......###",
        ".......###",
        "###....###",
        "###....###",
        "##########",
        ".########.",
    ),
    "6": (
        "..#######.",
        ".#########",
        "###.......",
        "###.......",
        "###.......",
        "########..",
        "#########.",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        ".########.",
        "..######..",
    ),
    "7": (
        "##########",
        "##########",
        ".......###",
        "......###.",
        ".....###..",
        ".....###..",
        "....###...",
        "....###...",
        "...###....",
        "...###....",
        "..###.....",
        "..###.....",
        "..###.....",
        "..###.....",
        "..###.....",
    ),
    "8": (
        "..######..",
        ".########.",
        "###....###",
        "###....###",
        "###....###",
        ".########.",
        "..######..",
        ".########.",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        ".########.",
        "..######..",
    ),
    "9": (
        "..######..",
        ".########.",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        "###....###",
        ".#########",
        "..########",
        ".......###",
        ".......###",
        ".......###",
        "###....###",
        ".########.",
        "..######..",
    ),
    ".": (
        "....",
        "....",
        "....",
        "....",
        "....",
        "....",
        "....",
        "....",
        "....",
        "....",
        "....",
        ".##.",
        "####",
        "####",
        ".##.",
    ),
    "%": (
        ".##....##.",
        "####..##..",
        ".##...##..",
        ".....##...",
        "....##....",
        "....##....",
        "...##.....",
        "..##......",
        "..##......",
        ".##...##..",
        ".##..####.",
        "##....##..",
        "..........",
        "..........",
        "..........",
    ),
}


def _canvas(w, h):
    return [["." for _ in range(w)] for _ in range(h)]


def _set(grid, x, y, val="#"):
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        grid[y][x] = val


def _rect(grid, x0, y0, w, h, fill=False, val="#"):
    for dy in range(h):
        for dx in range(w):
            if fill or dy in (0, h - 1) or dx in (0, w - 1):
                _set(grid, x0 + dx, y0 + dy, val)


def _hline(grid, x0, x1, y, val="#"):
    for x in range(x0, x1 + 1):
        _set(grid, x, y, val)


def _vline(grid, x, y0, y1, val="#"):
    for y in range(y0, y1 + 1):
        _set(grid, x, y, val)


def _text(grid, x, y, s, invert=False, pitch=6):
    on = "." if invert else "#"
    for ch in s:
        glyph = FONT_5X7.get(ch, FONT_5X7.get(ch.upper(), FONT_5X7[" "]))
        for gy, row in enumerate(glyph):
            for gx, pix in enumerate(row):
                if pix == "#":
                    _set(grid, x + gx, y + gy, on)
        x += 4 if ch in ".:![]" else pitch
    return x


FONT_4X6 = {
    " ": ("....", "....", "....", "....", "....", "...."),
    "!": (".#..", ".#..", ".#..", ".#..", "....", ".#.."),
    "%": ("#..#", "...#", "..#.", ".#..", "#..#", "...."),
    "+": ("....", ".#..", "###.", ".#..", "....", "...."),
    "-": ("....", "....", "###.", "....", "....", "...."),
    ".": ("....", "....", "....", "....", ".#..", "...."),
    "/": ("...#", "..#.", ".#..", ".#..", "#...", "...."),
    ":": ("....", ".#..", "....", ".#..", "....", "...."),
    "<": ("..#.", ".#..", "#...", ".#..", "..#.", "...."),
    ">": ("#...", ".#..", "..#.", ".#..", "#...", "...."),
    "0": (".##.", "#..#", "#..#", "#..#", ".##.", "...."),
    "1": (".#..", "##..", ".#..", ".#..", "###.", "...."),
    "2": ("###.", "...#", ".##.", "#...", "####", "...."),
    "3": ("###.", "...#", ".##.", "...#", "###.", "...."),
    "4": ("#..#", "#..#", "####", "...#", "...#", "...."),
    "5": ("####", "#...", "###.", "...#", "###.", "...."),
    "6": (".##.", "#...", "###.", "#..#", ".##.", "...."),
    "7": ("####", "...#", "..#.", ".#..", ".#..", "...."),
    "8": (".##.", "#..#", ".##.", "#..#", ".##.", "...."),
    "9": (".##.", "#..#", ".###", "...#", ".##.", "...."),
    "A": (".##.", "#..#", "####", "#..#", "#..#", "...."),
    "B": ("###.", "#..#", "###.", "#..#", "###.", "...."),
    "C": (".##.", "#..#", "#...", "#..#", ".##.", "...."),
    "D": ("###.", "#..#", "#..#", "#..#", "###.", "...."),
    "E": ("####", "#...", "###.", "#...", "####", "...."),
    "F": ("####", "#...", "###.", "#...", "#...", "...."),
    "G": (".##.", "#...", "#.##", "#..#", ".###", "...."),
    "H": ("#..#", "#..#", "####", "#..#", "#..#", "...."),
    "I": ("###.", ".#..", ".#..", ".#..", "###.", "...."),
    "J": ("..##", "...#", "...#", "#..#", ".##.", "...."),
    "K": ("#..#", "#.#.", "##..", "#.#.", "#..#", "...."),
    "L": ("#...", "#...", "#...", "#...", "####", "...."),
    "M": ("#..#", "####", "#..#", "#..#", "#..#", "...."),
    "N": ("#..#", "##.#", "#.##", "#..#", "#..#", "...."),
    "O": (".##.", "#..#", "#..#", "#..#", ".##.", "...."),
    "P": ("###.", "#..#", "###.", "#...", "#...", "...."),
    "Q": (".##.", "#..#", "#..#", "#.#.", ".###", "...."),
    "R": ("###.", "#..#", "###.", "#.#.", "#..#", "...."),
    "S": (".###", "#...", ".##.", "...#", "###.", "...."),
    "T": ("###.", ".#..", ".#..", ".#..", ".#..", "...."),
    "U": ("#..#", "#..#", "#..#", "#..#", ".##.", "...."),
    "V": ("#..#", "#..#", "#..#", ".##.", ".##.", "...."),
    "W": ("#..#", "#..#", "#..#", "####", "#..#", "...."),
    "X": ("#..#", ".##.", ".##.", ".##.", "#..#", "...."),
    "Y": ("#..#", "#..#", ".##.", ".#..", ".#..", "...."),
    "c": ("....", ".##.", "#...", "#...", ".##.", "...."),
    "d": ("...#", ".###", "#..#", "#..#", ".###", "...."),
    "h": ("#...", "#...", "###.", "#..#", "#..#", "...."),
    "m": ("....", "##.#", "####", "#..#", "#..#", "...."),
    "u": ("....", "#..#", "#..#", "#..#", ".###", "...."),
    "v": ("....", "#..#", "#..#", ".##.", ".##.", "...."),
}


def _text_small(grid, x, y, s, invert=False):
    on = "." if invert else "#"
    for ch in s:
        glyph = FONT_4X6.get(ch, FONT_4X6.get(ch.upper(), FONT_4X6[" "]))
        for gy, row in enumerate(glyph):
            for gx, pix in enumerate(row):
                if pix == "#":
                    _set(grid, x + gx, y + gy, on)
        x += 3 if ch in ".:!/" else 5
    return x


def _text_hero(grid, x, y, s):
    for ch in s:
        glyph = FONT_HERO_10X15.get(ch)
        if not glyph:
            x = _text_small(grid, x, y + 6, ch)
            continue
        w = len(glyph[0])
        for gy, row in enumerate(glyph):
            for gx, pix in enumerate(row):
                if pix == "#":
                    _set(grid, x + gx, y + gy, "#")
        x += w + (1 if ch == "." else 2)
    return x


def _header(grid, title, page_idx, total_pages=4, wifi_bars=4):
    w = len(grid[0])
    _rect(grid, 0, 0, w, 11, fill=True, val="#")
    _text(grid, 2, 2, title, invert=True)
    # 4-bar WiFi RSSI icon
    bx = w - 28
    for idx in range(4):
        bh = (idx + 1) * 2
        if idx < wifi_bars:
            _rect(grid, bx + idx * 3, 9 - bh, 2, bh, fill=True, val=".")
        else:
            _set(grid, bx + idx * 3, 8, ".")
    # Vertical divider
    _vline(grid, w - 15, 1, 9, val=".")
    # Dot-and-bar pagination indicator
    px = w - 13
    for p in range(1, total_pages + 1):
        if p == page_idx:
            _rect(grid, px, 3, 3, 5, fill=True, val=".")
            px += 5
        else:
            _set(grid, px, 5, ".")
            px += 2


def _bar_gauge(grid, y, pct, min_pct=None, max_pct=None, h=12):
    _rect(grid, 2, y, 60, h, fill=False)
    fill_w = int(round(56 * max(0, min(100, pct)) / 100.0))
    if fill_w > 0:
        _rect(grid, 4, y + 2, fill_w, h - 4, fill=True)
    # 25%, 50%, 75% subtle 1px ticks below bar
    for tick_pct in (25, 50, 75):
        tx = 4 + int(round(56 * tick_pct / 100.0))
        _set(grid, tx, y + h, "#")
    # Lower and upper limit markers (vertical line + top/bottom ticks)
    for lim in (min_pct, max_pct):
        if lim is not None:
            tx = 4 + int(round(56 * lim / 100.0))
            _vline(grid, tx, y - 1, y + h + 1, val="#")


def _pill(grid, x, y, label, ok=True):
    bx = _text_small(grid, x, y + 1, label) + 2
    _rect(grid, bx, y, 7, 7, fill=False)
    if ok:
        for d in range(1, 6):
            _set(grid, bx + d, y + d, "#")
            _set(grid, bx + 6 - d, y + d, "#")


def _sparkline_box(grid, y, h, values, min_line_y=None, max_line_y=None):
    """Framed 60xH sparkline chart with XOR-contrasted dotted upper/lower limit
    lines (always visible even when covered by solid white chart bars)."""
    _rect(grid, 2, y, 60, h, fill=False)
    bottom = y + h - 2
    for ix, h_bar in enumerate(values[:56]):
        bh = max(1, min(h - 3, h_bar))
        _vline(grid, 4 + ix, bottom - bh + 1, bottom)
    # Draw limit lines AFTER bars using XOR contrast + outer frame ticks so both
    # MIN and MAX lines remain 100% visible whether inside or above the bars
    for lim_y in (min_line_y, max_line_y):
        if lim_y is not None and y + 1 < lim_y < y + h - 1:
            _set(grid, 0, lim_y, "#")
            _set(grid, 1, lim_y, "#")
            _set(grid, 62, lim_y, "#")
            _set(grid, 63, lim_y, "#")
            for x_pos in range(4, 60):
                # 2px dash, 1px gap pattern; invert pixel against bar background
                if (x_pos - 4) % 3 != 2:
                    cur = grid[lim_y][x_pos]
                    _set(grid, x_pos, lim_y, "." if cur == "#" else "#")
                elif grid[lim_y][x_pos] == "#":
                    # Clear a 1px vertical halo above/below the dash inside solid bars
                    pass


def build_page1_tank_64x128():
    """Page 1A (Water Tank / Distance): Hero 78%, live 27px level chart with
    XOR-visible MIN/MAX threshold lines, VOL (liters) + FLW (flow rate) below,
    MQTT/SENS checkboxes, and IP footer."""
    g = _canvas(64, 128)
    _header(g, "TANK", page_idx=1, total_pages=4, wifi_bars=4)

    # Tier 1: Hero percentage
    _text_hero(g, 11, 14, "78%")

    # Tier 2: Live 27px level trend chart (y=32..58) with upper (y=36) & lower (y=52) limit lines
    tank_wave = [
        20, 20, 20, 19, 19, 19, 18, 18, 18, 17, 17, 17, 16, 16, 16, 15, 15, 15, 15, 14,
        14, 14, 14, 15, 16, 18, 19, 20, 21, 21, 21, 20, 20, 20, 19, 19, 19, 19, 18, 18,
        18, 18, 18, 17, 17, 17, 18, 18, 18, 18, 18, 18, 18, 18, 18, 18,
    ]
    _sparkline_box(g, 32, 27, tank_wave, min_line_y=52, max_line_y=36)

    # Tier 3: Liters (VOL) and Flow rate (FLW)
    _text(g, 2, 63, "VOL  2340L", pitch=6)
    _text(g, 2, 73, "FLW +1.2Lm", pitch=6)

    _hline(g, 0, 63, 83)

    # Tier 4: Status checkboxes (MQTT & SENS)
    _pill(g, 2, 88, "MQTT", ok=True)
    _pill(g, 34, 88, "SENS", ok=True)

    # Tier 5: Footer box with IPv4
    _rect(g, 0, 101, 64, 27, fill=False)
    _text(g, 3, 105, "192.168.", pitch=6)
    _text(g, 3, 116, "0.138", pitch=6)
    return ["".join(r) for r in g]


def build_page1_pressure_64x128():
    """Page 1B (Pressure Sensor): Hero 3.4 BAR, live 27px pressure trend chart
    with XOR-visible MIN/MAX threshold lines, MIN / MAX limits below, MQTT/SENS, IP footer."""
    g = _canvas(64, 128)
    _header(g, "PRES", page_idx=1, total_pages=4, wifi_bars=4)

    end_x = _text_hero(g, 2, 14, "3.4")
    _text(g, end_x + 3, 18, "BAR", pitch=6)

    # Live 27px pressure trend chart (y=32..58) with upper & lower dotted limit lines
    pres_wave = [
        14, 14, 15, 15, 14, 14, 13, 11, 9, 8, 9, 12, 15, 16, 16, 15, 15, 14, 14, 15,
        15, 14, 13, 10, 8, 7, 9, 13, 16, 17, 16, 15, 15, 14, 14, 14, 15, 15, 14, 12,
        10, 9, 11, 14, 16, 16, 15, 15, 14, 14, 15, 15, 14, 14, 15, 15,
    ]
    _sparkline_box(g, 32, 27, pres_wave, min_line_y=52, max_line_y=37)

    # Configured lower & upper thresholds
    _text(g, 2, 63, "MIN   1.5B", pitch=6)
    _text(g, 2, 73, "MAX   5.5B", pitch=6)

    _hline(g, 0, 63, 83)
    _pill(g, 2, 88, "MQTT", ok=True)
    _pill(g, 34, 88, "SENS", ok=True)

    _rect(g, 0, 101, 64, 27, fill=False)
    _text(g, 3, 105, "192.168.", pitch=6)
    _text(g, 3, 116, "0.138", pitch=6)
    return ["".join(r) for r in g]


def build_page1_radiation_64x128():
    """Page 1C (Radiation Counter): Hero 0.14 uSv/h + tall 27px 60-sec sparkline
    + CPM & 5m average + MQTT/TUBE checkboxes + IP footer."""
    g = _canvas(64, 128)
    _header(g, "RAD", page_idx=1, total_pages=4, wifi_bars=4)

    end_x = _text_hero(g, 1, 14, "0.14")
    _text_small(g, end_x + 1, 15, "uSv")
    _text_small(g, end_x + 1, 23, "/h")

    spark = [
        10, 11, 10, 12, 11, 13, 11, 10, 9, 11, 12, 15, 13, 10, 11, 10, 9, 10, 14, 18,
        20, 15, 12, 10, 11, 10, 9, 12, 13, 11, 10, 10, 12, 15, 13, 11, 10, 9, 10, 12,
        13, 11, 10, 12, 16, 18, 13, 11, 10, 11, 10, 9, 12, 13, 11, 10,
    ]
    _sparkline_box(g, 32, 27, spark, min_line_y=52, max_line_y=38)

    _text(g, 2, 63, "CPM     18", pitch=6)
    _text(g, 2, 73, "5M    0.13", pitch=6)

    _hline(g, 0, 63, 83)
    _pill(g, 2, 88, "MQTT", ok=True)
    _pill(g, 34, 88, "TUBE", ok=True)

    _rect(g, 0, 101, 64, 27, fill=False)
    _text(g, 3, 105, "192.168.", pitch=6)
    _text(g, 3, 116, "0.138", pitch=6)
    return ["".join(r) for r in g]


def build_page2_stats_64x128():
    """Page 2 (STAT): Live physical/electrical diagnostics & 24h extremes:
      - RAW: unfiltered physical sensor reading (41.8cm / 49.3PSI / 18cps)
      - SIG: live electrical terminal signal (16.5mA / 1.72V / 14.2k pulses)
      - 24L / 24H: lowest & highest values recorded over the last 24 hours
      - RLY: relay contact state + total trip counter
      - HEAP: free RAM (KB)
      - Footer: Uptime"""
    g = _canvas(64, 128)
    _header(g, "STAT", page_idx=2, total_pages=4, wifi_bars=4)

    _text(g, 2, 16, "RAW 41.8cm", pitch=6)
    _text(g, 2, 28, "SIG 16.5mA", pitch=6)
    _hline(g, 0, 63, 39)

    _text(g, 2, 44, "24L:   62%", pitch=6)
    _text(g, 2, 56, "24H:   84%", pitch=6)
    _hline(g, 0, 63, 67)

    _text(g, 2, 72, "RLY:OFF(2)", pitch=6)
    _text(g, 2, 84, "HEAP:184KB", pitch=6)
    _text(g, 2, 96, "ERRS:    0", pitch=6)

    _rect(g, 0, 111, 64, 17, fill=True)
    _text(g, 3, 116, "UP 14d 06h", invert=True, pitch=6)
    return ["".join(r) for r in g]


def build_page3_logs_64x128():
    """Page 3 (LOG): Informative 2-line log entries (title + detail, 5px glyph
    height with 1px gap between the 2 lines, and a 1px horizontal divider line
    between consecutive log entries -> 8 full 2-line entries on screen)."""
    g = _canvas(64, 128)
    _header(g, "LOG", page_idx=3, total_pages=4, wifi_bars=4)

    entries = (
        ("RLY TRIP ON!", "LVL 18% <20%"),
        ("RLY RESTORED", "LVL 26% >25%"),
        ("MQTT ONLINE", "192.168.0.10"),
        ("OUTLIER REJ", "JUMP 42>198c"),
        ("HA DISCOVERY", "6 ENTITIES"),
        ("WIFI ONLINE", "HOME -58dBm"),
        ("SENSOR INIT", "LOOP 16.5mA"),
        ("SYSTEM BOOT", "NVS CFG OK"),
    )
    y = 13
    for idx, (line1, line2) in enumerate(entries):
        if y + 11 > 127:
            break
        _text_small(g, 2, y, line1)
        _text_small(g, 2, y + 6, line2)
        y += 12
        if idx < len(entries) - 1 and y < 126:
            _hline(g, 0, 63, y)
            y += 2
    return ["".join(r) for r in g]


def build_page4_wifi_trigger_64x128():
    """Page 4 (WIFI): Shows WiFi connection state and explicitly instructs how
    to trigger WiFi Setup AP mode ('HOLD RST 5S -> START AP')."""
    g = _canvas(64, 128)
    _header(g, "WIFI", page_idx=4, total_pages=4, wifi_bars=0)

    _text(g, 2, 16, "STATE:", pitch=6)
    _text(g, 2, 27, "NO SIGNAL", pitch=6)
    _hline(g, 0, 63, 39)

    _text(g, 2, 45, "TO CONFIG", pitch=6)
    _text(g, 2, 56, "WIFI AP:", pitch=6)

    # Prominent call-to-action box instructing how to enter AP mode
    _rect(g, 2, 70, 60, 28, fill=True)
    _text(g, 5, 74, "HOLD RST", invert=True, pitch=6)
    _text(g, 5, 86, "FOR 5 SEC", invert=True, pitch=6)

    _text_small(g, 3, 105, "LED BLINKS")
    _text_small(g, 3, 114, "WHEN AP ON")
    return ["".join(r) for r in g]


def build_modal_wifi_ap_64x128():
    """Auto-wake Modal: WiFi Setup AP Mode (SSID, Portal IP)."""
    g = _canvas(64, 128)
    _rect(g, 0, 0, 64, 128, fill=False)
    _rect(g, 1, 1, 62, 12, fill=True)
    _text(g, 4, 3, "WIFI SETUP", invert=True, pitch=6)

    _text(g, 3, 17, "1.JOIN AP:", pitch=6)
    _rect(g, 2, 27, 60, 23, fill=True)
    _text(g, 4, 30, "ESP-SENS-", invert=True, pitch=6)
    _text(g, 4, 40, "A4CF12", invert=True, pitch=6)

    _text(g, 3, 55, "2.BROWSER:", pitch=6)
    _rect(g, 2, 65, 60, 23, fill=False)
    _text(g, 5, 68, "192.168.", pitch=6)
    _text(g, 5, 78, "4.1", pitch=6)

    _hline(g, 2, 61, 94)
    _text(g, 3, 99, "AP ACTIVE", pitch=6)
    _text(g, 3, 109, "HOLD RST", pitch=6)
    _text(g, 3, 118, "5S: EXIT", pitch=6)
    return ["".join(r) for r in g]


def build_modal_alert_64x128():
    """Auto-wake Modal: Universal Threshold / Relay Trip Alert (works for MIN or MAX
    limits across Tank, Pressure, and Radiation plugins)."""
    g = _canvas(64, 128)
    _rect(g, 0, 0, 64, 128, fill=False)
    _rect(g, 1, 1, 62, 14, fill=True)
    _text(g, 5, 4, "! ALERT !", invert=True, pitch=6)

    end_x = _text_hero(g, 4, 21, "12%")
    _text_small(g, end_x + 2, 22, "MIN")
    _text_small(g, end_x + 2, 30, "HIT")

    _bar_gauge(g, 42, pct=12, min_pct=20, max_pct=95, h=13)

    _text(g, 4, 62, "LIM: <20%", pitch=6)

    _rect(g, 2, 76, 60, 17, fill=True)
    _text(g, 5, 81, "RELAY: ON", invert=True, pitch=6)

    _hline(g, 2, 61, 101)
    _text(g, 3, 106, "TAP PAGE:", pitch=6)
    _text(g, 3, 116, "DISMISS", pitch=6)
    return ["".join(r) for r in g]


def _build_128x64():
    g = _canvas(128, 64)
    _rect(g, 0, 0, 128, 11, fill=True)
    _text(g, 2, 2, "TANK STATUS", invert=True)
    _text_hero(g, 2, 14, "78%")
    _text(g, 46, 15, "DEP: 1.42m")
    _text(g, 46, 25, "VOL: 2340L")
    _hline(g, 0, 127, 36)
    _text(g, 2, 41, "IP: 192.168.0.138")
    _text(g, 2, 52, "MQTT:[OK] RLY:[OFF]")
    return ["".join(r) for r in g]


PAGE1_64X128 = build_page1_tank_64x128()
PAGE1_128X64 = _build_128x64()
