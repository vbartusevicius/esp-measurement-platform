#!/usr/bin/env python3
"""Regenerates the README images in doc/images/ from the real sources:

- OLED pages: lib/Display rendered by the real U8g2 core (oled_sim/)
- Web UI: data/ served by tools/webui_mock.py, captured with headless Chrome
- Hardware: crops of the release renders in hardware/releases/v1/

    python3 tools/readme_images/render.py

Needs Pillow, a C/C++ compiler, Google Chrome/Chromium (set CHROME to override)
and the U8g2 sources from a previous `pio run -e xiao_c6` (.pio/libdeps).
"""
import glob
import re
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "doc", "images")
BUILD = os.path.join(ROOT, ".pio", "readme_images")
RELEASE = os.path.join(ROOT, "hardware", "releases", "v1")
U8G2 = os.path.join(ROOT, ".pio", "libdeps", "xiao_c6", "U8g2", "src", "clib")
BG = (255, 255, 255)
OLED_ON, OLED_OFF, BEZEL = (200, 235, 255), (10, 12, 18), (34, 36, 42)


def chrome():
    for candidate in (os.environ.get("CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")):
        if candidate and os.path.exists(candidate):
            return candidate
    sys.exit("Chrome/Chromium not found: set CHROME=/path/to/chrome")


def font(size):
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def autocrop(image, margin=16):
    rgb = image.convert("RGB")
    corner = rgb.getpixel((0, 0))
    box = ImageChops.difference(rgb, Image.new("RGB", rgb.size, corner)).point(lambda v: 255 if v > 8 else 0).getbbox()
    if not box:
        return image
    l, t, r, b = box
    return image.crop((max(0, l - margin), max(0, t - margin), min(image.width, r + margin), min(image.height, b + margin)))


def fit(image, max_w, max_h):
    image = image.copy()
    image.thumbnail((max_w, max_h), Image.LANCZOS)
    return image


def save(image, name, colors=None):
    path = os.path.join(OUT, name)
    image = image.convert("RGB")
    if colors:
        image = image.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    image.save(path, optimize=True)
    print(f"  {os.path.relpath(path, ROOT)} {image.width}x{image.height} {os.path.getsize(path) // 1024} KB")


# ---------------------------------------------------------------- OLED

def build_oled_sim():
    if not os.path.isdir(U8G2):
        sys.exit(f"U8g2 sources missing ({U8G2}): run `pio run -e xiao_c6` once")
    objs = os.path.join(BUILD, "u8g2")
    os.makedirs(objs, exist_ok=True)
    cc = os.environ.get("CC", "cc")
    for c in glob.glob(os.path.join(U8G2, "*.c")):
        o = os.path.join(objs, os.path.basename(c)[:-2] + ".o")
        if not os.path.exists(o):
            subprocess.run([cc, "-c", "-O1", "-w", f"-I{U8G2}", c, "-o", o], check=True)
    sources = [os.path.join(HERE, "oled_sim", "oled_sim.cpp")] + [os.path.join(ROOT, "lib", p) for p in (
        "Display/Display.cpp", "Display/PortraitPages.cpp", "Core/DeviceMonitor.cpp", "Core/LimitMonitor.cpp",
        "Core/EventLog.cpp", "Core/RelayOutput.cpp", "Core/TimeHelper.cpp", "Storage/Storage.cpp", "Storage/ScopedSettings.cpp",
        "Logger/Logger.cpp")]
    includes = [f"-I{os.path.join(HERE, 'oled_sim')}", f"-I{os.path.join(ROOT, 'test', 'test_native', 'fakes')}", f"-I{U8G2}"]
    includes += [f"-I{d}" for d in sorted({os.path.dirname(h) for h in glob.glob(os.path.join(ROOT, 'lib', '**', '*.h'), recursive=True)})]
    binary = os.path.join(BUILD, "oled_sim")
    subprocess.run([os.environ.get("CXX", "c++"), "-std=gnu++17", "-w", "-Dprivate=public"]
                   + includes + sources + glob.glob(os.path.join(objs, "*.o")) + ["-o", binary], check=True)
    return binary


def decode_frame(path, scale):
    """SSD13xx page buffer -> logical (rotated) image, same mapping as U8g2 R0..R3."""
    data = open(path, "rb").read()
    phys_w, phys_h, rotation = data[1] * 8, data[2] * 8, data[3]
    portrait = rotation in (1, 3)
    w, h = (phys_h, phys_w) if portrait else (phys_w, phys_h)
    image = Image.new("RGB", (w, h), OLED_OFF)
    pixels = image.load()
    for py in range(phys_h):
        row = 4 + (py >> 3) * phys_w
        bit = 1 << (py & 7)
        for px in range(phys_w):
            if data[row + px] & bit:
                lx, ly = {0: (px, py), 1: (py, phys_w - 1 - px), 2: (phys_w - 1 - px, phys_h - 1 - py), 3: (phys_h - 1 - py, px)}[rotation]
                pixels[lx, ly] = OLED_ON
    return image.resize((w * scale, h * scale), Image.NEAREST)


def oled_panel(frame, label, pad=10):
    panel = Image.new("RGB", (frame.width + 2 * pad, frame.height + 2 * pad + 34), BG)
    ImageDraw.Draw(panel).rounded_rectangle((0, 0, frame.width + 2 * pad - 1, frame.height + 2 * pad - 1), 10, fill=BEZEL)
    panel.paste(frame, (pad, pad))
    draw = ImageDraw.Draw(panel)
    f = font(17)
    tw = draw.textlength(label, font=f)
    draw.text(((panel.width - tw) / 2, frame.height + 2 * pad + 8), label, fill=(70, 75, 85), font=f)
    return panel


def strip(panels, gap=18):
    image = Image.new("RGB", (sum(p.width for p in panels) + gap * (len(panels) - 1), max(p.height for p in panels)), BG)
    x = 0
    for p in panels:
        image.paste(p, (x, 0))
        x += p.width + gap
    return image


def render_oled():
    print("OLED pages")
    binary = build_oled_sim()
    frames = os.path.join(BUILD, "frames")
    os.makedirs(frames, exist_ok=True)
    subprocess.run([binary, frames], check=True)
    def frame(name, scale=3):
        return decode_frame(os.path.join(frames, f"{name}.bin"), scale)
    save(strip([oled_panel(frame(n), label) for n, label in (
        ("tank", "1 · Tank"), ("pressure", "2 · Pressure"), ("radiation", "3 · Radiation"), ("water", "4 · Water meter"),
        ("dev", "5 · DEV"), ("log", "6 · LOG"), ("wifi", "7 · WIFI"), ("alert", "Alert pop-up"), ("portal", "WiFi setup"))]), "oled-pages.png", colors=32)
    return frame("tank", 4)


# ---------------------------------------------------------------- Web UI

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def screenshot(browser, url, width, height, scale, out):
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-prefers-reduced-motion",
                        f"--user-data-dir={profile}", f"--window-size={width},{height}", f"--force-device-scale-factor={scale}",
                        "--virtual-time-budget=8000", f"--screenshot={out}", url],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return Image.open(out).convert("RGB")


def trim_bottom(image, bg=(236, 238, 241), margin=24):
    """Cuts the empty page background below the last card."""
    pixels = image.load()
    for y in range(image.height - 1, 0, -1):
        if any(abs(pixels[x, y][0] - bg[0]) > 6 for x in range(0, image.width, 7)):
            return image.crop((0, 0, image.width, min(image.height, y + margin)))
    return image


def loaded(image, scale):
    """False while the page shows the "Waiting for the first reading" skeleton:
    only a loaded overview has dark headline text below the header."""
    body = image.crop((0, 130 * scale, image.width, 520 * scale)).convert("L")
    return sum(1 for v in body.getdata() if v < 60) > 600 * scale * scale


def phone(browser, base, scenario, tmp, height=1600, scale=2):
    """Real 390 px layout, framed by the mock (desktop Chrome can't open a window that narrow)."""
    for _ in range(4):
        shot = screenshot(browser, f"{base}/__phone?sensor={scenario}&h={height}", 520, height, scale,
                          os.path.join(tmp, f"{scenario}.png")).crop((0, 0, 390 * scale, height * scale))
        if loaded(shot, scale):
            return trim_bottom(shot)
    sys.exit(f"web UI scenario {scenario} never loaded its first reading")


def render_webui(browser):
    print("Web UI")
    port = free_port()
    mock = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "webui_mock.py"), str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        with tempfile.TemporaryDirectory() as tmp:
            phones = {s: phone(browser, base, s, tmp) for s in ("tank", "pressure", "radiation-high")}
            for scenario, image in phones.items():
                first_screen = image.crop((0, 0, image.width, min(image.height, round(image.width * 2.1))))
                save(fit(first_screen, 520, 4000), f"webui-phone-{scenario}.png", colors=128)
            desktop = trim_bottom(screenshot(browser, f"{base}/?sensor=house-alarm&clean=1", 1200, 1300, 1, os.path.join(tmp, "desktop.png")))
            save(desktop, "webui-desktop.png", colors=128)
            settings = screenshot(browser, f"{base}/?sensor=house&clean=1#settings", 1200, 1150, 1, os.path.join(tmp, "settings.png"))
            save(settings, "webui-settings.png", colors=128)
            events = trim_bottom(screenshot(browser, f"{base}/?sensor=house-alarm&clean=1#events", 1200, 1100, 1, os.path.join(tmp, "events.png")))
            save(events, "webui-events.png", colors=128)
            return phones["tank"]
    finally:
        mock.terminate()


# ---------------------------------------------------------------- Hardware

def board_png(browser, svg, tmp, px_per_unit=9):
    """KiCad plot at a fixed scale (boards stay comparable), without its title line."""
    text = re.sub(r"<text[^>]*>[^<]*DRC errors[^<]*</text>", "", open(svg).read())
    vb_w, vb_h = (float(v) for v in re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', text).groups())
    clean = os.path.join(tmp, os.path.basename(os.path.dirname(os.path.dirname(svg))) + "-" + os.path.basename(svg))
    open(clean, "w").write(text)
    w, h = round(vb_w * px_per_unit), round(vb_h * px_per_unit)
    page = clean + ".html"
    open(page, "w").write(f'<body style="margin:0;background:#202020"><img src="{os.path.basename(clean)}" width="{w}" height="{h}"></body>')
    shot = screenshot(browser, f"file://{page}", max(w, 500), h, 1, page + ".png")
    return autocrop(shot.crop((0, 0, w, h)), margin=6)


def render_hardware(browser):
    print("Hardware")
    enclosure = {n: autocrop(Image.open(os.path.join(RELEASE, "enclosure", "renders", f"{n}.png")))
                 for n in ("iso", "front", "inside", "exploded")}
    row = strip([fit(enclosure[n], 420, 420) for n in ("front", "inside", "exploded")], gap=40)
    save(row, "hardware-enclosure.png")
    accessories = [autocrop(Image.open(os.path.join(RELEASE, "accessories", p))) for p in (
        "distance_sensor_pod/renders/distance_pod_exploded.png", "radiation_duct/renders/radiation_exploded.png")]
    save(strip([fit(a, 560, 380) for a in accessories], gap=40), "hardware-accessories.png")
    wall_box = [autocrop(Image.open(os.path.join(RELEASE, "box_enclosure", "renders", f"{n}.png")))
                for n in ("box_front", "box_iso", "box_exploded")]
    save(strip([fit(b, 420, 380) for b in wall_box], gap=40), "hardware-box.png")
    with tempfile.TemporaryDirectory() as tmp:
        boards = [board_png(browser, os.path.join(RELEASE, b, "renders", f"{v}.svg"), tmp)
                  for b, v in (("main", "top"), ("main", "overlay"), ("ui", "top"), ("ui", "overlay"))]
    save(strip(boards, gap=28), "hardware-pcbs.png")
    return enclosure["iso"]


# ---------------------------------------------------------------- hero

def render_hero(device, ui, oled):
    print("Hero")
    height = 560
    device = fit(device, 520, height)
    ui = ui.crop((0, 0, ui.width, min(ui.height, round(ui.width * 1.2))))   # header + main card
    ui = fit(ui, 400, height)
    oled = oled_panel(oled, "")
    oled = oled.crop((0, 0, oled.width, oled.height - 34))
    oled = fit(oled, 300, height - 120)
    parts = [device, oled, ui]
    gap = 56
    hero = Image.new("RGB", (sum(p.width for p in parts) + gap * 4, height + 40), BG)
    x = gap
    for p in parts:
        hero.paste(p, (x, (hero.height - p.height) // 2))
        x += p.width + gap
    save(hero, "hero.png")


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)
    browser = chrome()
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "embed_web.py")], check=True, stdout=subprocess.DEVNULL)
    oled = render_oled()
    ui = render_webui(browser)
    device = render_hardware(browser)
    render_hero(device, ui, oled)


if __name__ == "__main__":
    main()
