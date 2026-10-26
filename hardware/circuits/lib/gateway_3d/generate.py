"""Box models (STEP) for the project parts KiCad ships no 3D model for.

The STEP files next to this script are library assets referenced by
hardware/scripts/layout.py; rerun after changing a body size (`cad` container):

    python3 hardware/circuits/lib/gateway_3d/generate.py
"""

from pathlib import Path

import cadquery as cq

OUT_DIR = Path(__file__).resolve().parent

# Part dimensions (body size + height) from datasheets / height table.
# Format: (name, width_mm, depth_mm, height_mm)
# Bodies are centered at origin in X/Y, sitting on the PCB (bottom at z=0).
PARTS = {
    "XIAO_ESP32C6": (17.8, 22.0, 3.5),  # 21 mm board + 1 mm USB-C overhang, along the pin rows
    "REM3_DIP24": (31.8, 20.3, 10.7),
    "TerminalBlock_MaiXu_MX126-5.0-02P": (11.6, 9.1, 8.0),
    "TerminalBlock_Kefa_KF142R-5.08-2P": (11.7, 14.2, 11.1),
    "TerminalBlock_Kefa_KF142R-5.08-3P": (16.8, 14.2, 11.1),
    "TerminalBlock_Kefa_KF142R-5.08-4P": (21.9, 14.2, 11.1),
    "TerminalBlock_Kefa_KF142R-5.08-5P": (27.0, 14.2, 11.1),
    "TerminalBlock_Kefa_KF142R-5.08-6P": (32.0, 14.2, 11.1),
    "TerminalBlock_Kefa_KF142R-5.08-7P": (37.1, 14.2, 11.1),
    "TerminalBlock_WAGO_2086-1204_SMD": (14.7, 13.6, 8.3),
    "TerminalBlock_WAGO_2086-1203_SMD": (11.2, 13.6, 8.3),
    "TerminalBlock_WAGO_2059-303_SMD": (7.9, 8.9, 2.7),
    "Vishay_TCRT5000_Clips": (10.2, 5.8, 7.0),
    "Relay_DPDT_Omron_G6K-2F-Y": (6.5, 10.0, 5.2),
    "Relay_DPDT_Omron_G6S-2F": (7.3, 14.8, 9.2),
    "Relay_1A1B_Omron_G6B-2114P": (20.0, 10.9, 11.0),
    "Fuse_1812_4532Metric": (4.5, 3.2, 1.2),
    "Phoenix_PST_1,0-2-5,75_R32": (8.55, 2.8, 9.9),
    "LED_SK6805-EC15_1.5x1.5mm": (1.5, 1.5, 0.65),
    "FPC_Kinghelm_KH-FPC0.5-H1.2SMT-8P": (8.9, 4.2, 1.2),
    "FPC_XUNPU_FPC-05F-14PH20": (11.6, 4.5, 2.0),
}


def make_box_model(name, width, depth, height):
    """Create a simple box model centered at origin, sitting on the PCB
    (bottom face at z=0, top face at z=height)."""
    result = cq.Workplane("XY").box(width, depth, height, centered=(True, True, False))
    step_path = OUT_DIR / f"{name}.step"
    cq.exporters.export(result, str(step_path))
    print(f"  {name}: {width}x{depth}x{height} mm -> {step_path.name}")
    return step_path


def make_bent_capacitor(name="CP_Radial_D10.0mm_P5.00mm_Horizontal_Bent", diameter=10.0, length=16.0,
                        pitch=5.0, bend=3.0, axis_height=7.0, lead=0.6, courtyard=(-1.25, 19.25)):
    """Capacitor lying on its side: leads rise from the pads, bend 90 deg and
    enter the body end. Centred on the footprint courtyard like the boxes
    (KiCad model y is the footprint's -y)."""
    centre = sum(courtyard) / 2
    pad_y, body_end = centre, centre - bend
    body = (cq.Workplane("XZ").center(0, axis_height).circle(diameter / 2).extrude(length)
            .translate((0, body_end, 0)))
    for x in (-pitch / 2, pitch / 2):
        rise = cq.Workplane("XY").center(x, pad_y).circle(lead / 2).extrude(axis_height)
        run = (cq.Workplane("XZ").center(x, axis_height).circle(lead / 2).extrude(bend)
               .translate((0, pad_y, 0)))
        body = body.union(rise).union(run)
    step_path = OUT_DIR / f"{name}.step"
    cq.exporters.export(body, str(step_path))
    print(f"  {name}: D{diameter} x {length} mm lying down -> {step_path.name}")


def main():
    print("Generating 3D box models:")
    for name, (w, d, h) in PARTS.items():
        make_box_model(name, w, d, h)
    make_bent_capacitor()
    print(f"\nAll models saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
