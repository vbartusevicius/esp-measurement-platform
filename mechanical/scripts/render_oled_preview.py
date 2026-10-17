"""Render pixel-accurate SVG & PNG showcase of all 64x128 portrait OLED screens."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
import oled_page1_bitmap as ob

REPO = Path(__file__).resolve().parents[2]
OUT_SVG = REPO / "doc/oled-v1-portrait.svg"
OUT_PNG = REPO / "doc/oled-v1-portrait.png"


MONO_WHITE = "#e6edf3"

SCREENS = [
    ("1A. Tank / Distance", ob.build_page1_tank_64x128(), MONO_WHITE),
    ("1B. Pressure (BAR)", ob.build_page1_pressure_64x128(), MONO_WHITE),
    ("1C. Radiation", ob.build_page1_radiation_64x128(), MONO_WHITE),
    ("2. System Stats", ob.build_page2_stats_64x128(), MONO_WHITE),
    ("3. Event Log", ob.build_page3_logs_64x128(), MONO_WHITE),
    ("4. WiFi AP Trigger", ob.build_page4_wifi_trigger_64x128(), MONO_WHITE),
    ("Modal: WiFi AP", ob.build_modal_wifi_ap_64x128(), MONO_WHITE),
    ("Modal: Limit Alert", ob.build_modal_alert_64x128(), MONO_WHITE),
]


def generate_svg():
    scale = 3
    px_size = 2.65
    w, h = 64, 128
    cell_w = w * scale + 34
    cell_h = h * scale + 64
    total_w = 28 + len(SCREENS) * cell_w
    total_h = 66 + cell_h

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" width="{total_w}" height="{total_h}" shape-rendering="crispEdges">',
        '<rect width="100%" height="100%" rx="10" fill="#0d1117"/>',
        '<text x="28" y="30" fill="#e6edf3" font-family="monospace" font-size="15" font-weight="bold">'
        'ESP Measurement Platform — 0.96" 64×128 Portrait OLED Screens (Hero Value + Gauge/Sparkline + WiFi AP + Event Log)</text>',
        '<text x="28" y="50" fill="#8b949e" font-family="monospace" font-size="11.5">'
        '10×15 Hero Digits (readable from 1.5m) | Segmented Bar &amp; 60s Sparkline | PAGE Button Cycles 1→2→3 | Auto-Wake Modals for WiFi AP &amp; Alerts</text>',
    ]

    for i, (title, rows, color) in enumerate(SCREENS):
        bx = 28 + i * cell_w
        by = 86
        svg.append(
            f'<text x="{bx}" y="{by - 12}" fill="#c9d1d9" font-family="monospace" font-size="11" font-weight="bold">{title}</text>'
        )
        svg.append(
            f'<rect x="{bx - 5}" y="{by - 5}" width="{w * scale + 10}" height="{h * scale + 10}" rx="5" fill="#05070a" stroke="#30363d" stroke-width="2"/>'
        )
        for py, r in enumerate(rows):
            for px, ch in enumerate(r):
                if ch == "#":
                    svg.append(
                        f'<rect x="{bx + px * scale:.2f}" y="{by + py * scale:.2f}" width="{px_size}" height="{px_size}" fill="{color}"/>'
                    )

    svg.append("</svg>")
    OUT_SVG.write_text("\n".join(svg))
    print(f"Wrote {OUT_SVG.relative_to(REPO)}")


def generate_png():
    fig, axes = plt.subplots(1, len(SCREENS), figsize=(21.0, 5.6), facecolor="#0d1117")
    fig.suptitle(
        'ESP Measurement Platform — 0.96" 64×128 Portrait OLED UI (Hero Reading + Bar/Sparkline + WiFi AP + Log + Alert)',
        color="#e6edf3", fontsize=13, fontweight="bold", fontfamily="monospace", y=0.96,
    )
    for ax, (title, rows, color) in zip(axes, SCREENS):
        ax.set_facecolor("#05070a")
        ax.set_xlim(-2, 66)
        ax.set_ylim(130, -2)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(title, color="#c9d1d9", fontsize=8.5, fontweight="bold", fontfamily="monospace", pad=8)
        ax.add_patch(FancyBboxPatch((-1.5, -1.5), 67, 131, boxstyle="round,pad=0.5,rounding_size=2",
                                    fc="#05070a", ec="#30363d", lw=1.8))
        for py, r in enumerate(rows):
            for px, ch in enumerate(r):
                if ch == "#":
                    ax.add_patch(Rectangle((px + 0.08, py + 0.08), 0.84, 0.84, fc=color, ec="none"))
    plt.tight_layout(rect=(0, 0, 1, 0.91))
    fig.savefig(OUT_PNG, dpi=160, facecolor="#0d1117")
    plt.close(fig)
    print(f"Wrote {OUT_PNG.relative_to(REPO)}")


if __name__ == "__main__":
    generate_svg()
    generate_png()
