---
name: manufacturing-readiness-review
description: Pre-order go/no-go review of the PCBs, BOM, enclosure STLs and sensor accessories. Checks datasheets, pinouts, stock/prices, PCB/enclosure fit, assemblability, retention and sensor physics before paying for manufacturing.
argument-hint: "[release dir, default hardware/releases/v1]"
triggers:
  - user
  - model
---

# Manufacturing readiness review (go / no-go before paying JLCPCB / printing)

Purpose: before the user pays for PCB/PCBA or prints enclosures, independently
prove that the release will (a) be manufacturable, (b) physically assemble,
(c) be electrically correct against **manufacturer datasheets**, and (d) produce
meaningful measurements. Never trust the repo's own README/claims or green
tests on their own - they have been wrong before (see "Known traps").

Do not promise a guarantee. Report a verdict per area: PASS / RISK / FAIL, with
evidence (file + line, datasheet URL, computed number). An order is GO only if
there are zero FAIL items.

## 0. Toolchain (this repo)

- EDA image: `knx-dali-gateway-eda` (KiCad 10, SKiDL, pcbnew). CAD image: `knx-dali-gateway-cad`
  (CadQuery 2.8 + numpy). `compose.yaml` names them; build with `docker compose --profile hardware build`.
- Existing suites (necessary, NOT sufficient):
  - `docker run --rm -v "$PWD":/work -w /work knx-dali-gateway-eda "python3 -m pytest -q hardware/tests"`
  - `docker run --rm -v "$PWD":/work -w /work knx-dali-gateway-cad "python3 -m pytest -q mechanical/tests"`
- Independent audits shipped with this skill (run from repo root in the CAD image):
  - `python3 .claude/skills/manufacturing-readiness-review/scripts/mesh_audit.py hardware/releases/v1 --pairs <a.step,b.step> ...`
    STL watertightness, number of separate bodies per STL (floating/unattached features), STEP solid
    counts, pairwise interference/gap between parts that assemble together.
  - `python3 .claude/skills/manufacturing-readiness-review/scripts/enclosure_fit_audit.py hardware/releases/v1/enclosure`
    (and `.../box_enclosure` for the wall-mount box: detected by its `box_base`/`box_lid` files)
    board/component vs base/cover interference, tight clearances, which faces of each board are
    actually restrained, insertion sweeps (can the populated board physically go in?), base/cover overlap.
    Slow (several minutes) because it point-samples; OCC booleans on imported STEP silently return
    empty results, so never rely on `a.intersect(b)` alone.
- Live JLC data (stock, price, Basic/Extended, footprint): `https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode=<LCSC>`
  (see `hardware/scripts/jlc_parts.py` for headers; sleep ~1 s between calls).

## 1. Inventory and consistency

1. `git status`, `git log -5`; confirm the release dir matches the sources (`hardware/tests/test_release_current.py`).
2. Read `hardware/product/spec.yaml`, `hardware/circuits/blocks/*.py`, `variants/<v>/main.py|ui.py`,
   `layout_*.yaml`, `releases/<v>/README.md`, `*_bom_jlc.csv`, `*_cpl_jlc.csv`, `*_hand_fit.csv`, `assembly_parts.csv`.
3. Diff every claim in README / docstrings / silkscreen / enclosure legend against the actual netlist
   and BOM (part numbers, terminal pole counts, ratings, diode types, relay model). Stale docs are
   findings - the enclosure legend text is printed on the product.
4. Open `releases/<v>/*/drc.json`: list severities. Check `.kicad_dru` for rules that disable checks
   (e.g. `courtyard_clearance (min -100mm)`) and footprints whose courtyard is smaller than the body.

## 2. Electrical review against datasheets (fetch each datasheet; cite URL)

For every active/protection part verify: abs-max vs worst-case (incl. surge clamp voltage), operating
range, pin mapping, reference-circuit values. Minimum checklist:
- Input protection: TVS clamp voltage V_C at I_PP must be < abs-max of everything on that rail
  (buck VIN, caps, PTC V_max).
- Buck: V_FB / divider, EN threshold / UVLO, min on-time at max V_IN and f_sw
  (V_out / (t_on_min * f_sw) = max V_IN before pulse skipping), inductor I_sat, output cap DC-bias derating.
- Power budget at peak (ESP32 TX ~350 mA via LDO, LEDs at full white, relay coil, all sensors) vs regulator rating.
- Relay: rated load (AC and DC separately!), max switching capacity (VA), coil-contact dielectric strength and
  insulation class. A telecom/signal relay is NOT a mains relay; SELV separation needs reinforced insulation.
- Analog front-ends: ADC usable range (ESP32-C6 ATTEN 12 dB: 0-3300 mV, +-40 mV) vs full-scale incl. over-range
  (4-20 mA NAMUR up to 21-23 mA); clamp diode reverse leakage x source impedance = error (power Schottkys
  like SS34 leak tens-hundreds of uA hot); shunt power on a mis-wire to the adjacent supply terminal.
- Digital I/O: clamp diode capacitance + pull-up -> I2C rise time (<= 1000 ns at 100 kHz, 300 ns at 400 kHz)
  incl. cable capacitance; logic levels of 5 V sensors into 3.3 V pins.
- Hand-fit modules (XIAO, OLED FPC): pin order from the vendor drawing, not from a similar part number.

## 3. Parts, availability, price

- For every LCSC number in all `*_bom_jlc.csv`: model matches MPN, stock >= order qty x 2, Basic vs Extended
  (JLC charges a per-unique-Extended-part fee), unit price at order quantity. Flag stock < 1000 and single-source parts.
- Hand-fit parts: an orderable source, lead time, and that the exact variant (pre-soldered headers, FPC tail) exists.
- Other fabs (AISLER, Eurocircuits, PCBWay): each board also ships `<b>_odb.zip` (ODB++, MPN/Manufacturer/LCSC
  fields, hand-fit parts flagged `.no_pop`), `<b>_ipc2581.zip`, and a fab-neutral `<b>_bom.csv` / `<b>_cpl.csv`
  (KiCad origin and rotation, Gerber coordinates); the Gerber zip carries the IPC-D-356 netlist.
  `test_release_current.py` checks these against a fresh export. JLC rotations differ from KiCad's for some parts,
  so for non-JLC assembly confirm polarised parts in that fab's preview.
- Sum BOM cost per board + Extended-part fees + hand-fit parts.

## 4. PCB layout / assembly

- DRC 0 errors and 0 unconnected; review warnings (silk over pads, hole-to-hole).
- `hardware/tests/test_jlc_assembly.py` proves JLC footprints/rotations. Also check: THT parts assembled by JLC,
  interlocking/stacked parts (modular terminal blocks) physically mate at the placed pitch, courtyard overlaps
  that DRC was told to ignore, connector orientation (FFC contact side A/B vs fold count; draw the fold).
- Creepage/clearance claims vs the actual insulation of the bridging component.

## 5. Enclosure / mechanical (run both audit scripts)

- Every printed STL: watertight and exactly 1 body (unless loose pieces are intended). Features that do not touch
  the main body are a FAIL.
- Board slabs and component envelopes: zero interference with base/cover; >= 0.2-0.3 mm clearance for FDM
  (tolerance +-0.2 mm); PCB outline tolerance +-0.2 mm too.
- Retention: every board must be restrained in all 6 directions by designed features (slots, ribs, pegs, snaps),
  not by interference or friction.
- Assemblability: the populated board must have a collision-free insertion path; parts that overhang the board edge
  into wall windows (terminal blocks) make closed windows impossible to enter. Cover must have a clear mating path.
- Sliding fits between printed parts need >= 0.2 mm gap per side (0 or negative = will not fit).
- Front panel: display panel outline (not just active area) vs window/pocket/rails; button actuator reach (if a
  plunger is required, it must exist as a released STL); LED windows over LEDs with real LED heights.
- Accessories: sensor envelopes vs pod, mounting surface curvature (flat base on round duct?), cable glands, sealing.
- Use real part heights; layout `heights.default` fallbacks hide clashes.

## 6. Sensor physics / will it measure

For each plugin compute expected signal and error budget: range, resolution at the ADC, noise, temperature drift,
environmental failure modes (condensation, salt crust, beam angle vs tank walls, multipath), and whether the
physical quantity is actually observable (e.g. a glass GM tube in a duct measures ambient gamma background, not radon).

## 7. Firmware readiness

Check `platformio.ini` targets the MCU on the board and that pins/peripherals in firmware match `spec.yaml`
`derived.mcu_pins`. Hardware with no firmware target is not "working" on arrival.

## 8. Report

Table per area with PASS/RISK/FAIL, evidence, and a concrete fix. Put FAILs first. End with GO / NO-GO and the
minimal list of changes required for GO. Recommend ordering 5 bare-board prototypes and a test print before volume.

## Known traps in this repo (found in the 2026-10 review of v1)

Fixed in the follow-up (re-check they stay fixed; regressions are easy):
- Relay: the G6S-2F signal relay (0.5 A @ 125 VAC) was replaced by Omron G6B-2114P-US DC5 (1a+1b joined as
  changeover, 5 A 250 VAC, 3 kVAC / 6 kV coil-contacts, 11.0 mm max = the full height budget) for 230 VAC 2 A.
  J4 order is COM / NO / NC (the only crossing-free route at 2.5 mm relay-net spacing). Check: K1 height vs
  inner wall, RELAY-Power clearance 2.5 mm in layout.py, coil pads in the SELV region, V-0 filament note.
- YAML 1.1: a bare `NO` in spec.yaml parses as false (broke the J4 legend); quote such labels.
- CI/Dockerfile.firmware pin PlatformIO 6.1.19 with pioarduino 55.03.311 for `xiao_c6` (the only firmware
  target since the NodeMCU/ESP8266 one was removed). Verify `pio run -e xiao_c6` before ordering.
- Surge: SMAJ33A (53 V clamp) vs SCT2400 (42 V abs max) -> replaced by SMAJ30A (48.4 V clamp) + SCT2601
  (65 V abs max, async: needs the SS36 catch diode D9 and 22 uH per its datasheet table 2).
- ADC clamps: SS34 (0.5 mA leak, 250 pF) -> BAT54S to GND and +3V3 (2 uA, 10 pF).
- 4-20 mA: 165 ohm (20 mA = 3.30 V, no headroom, burns on a +24 V mis-wire) -> 50 mA PTC F2 + 120 ohm (2x240R 1206).
- Main board 78.0 mm in a 77.8 mm cavity -> 77.4 mm, y_offset 1.8; terminal faces flush (J1/J4 KF142R at y 6.6;
  J2/J5/J6 WAGO 2086 at y 70.15, front 9.05 mm ahead of the pads = board y 79.2).
- Sensor bank (2026-10-24): 7-pole KF142R 4P+3P -> 10-pole WAGO 2086 3.5 mm SMD (J2 2086-1204, J5/J6 2086-1203):
  +5V, +24V, 4-20mA, 0-10V, IO1..IO4, GND, GND. IO3 = D9/GPIO20 (Geiger), IO4 = D10/GPIO18 (water meter), with
  R18-R21 / D10-D11 (explicit refs; the OLED pull-ups are pinned to R16/R17 so auto-numbering can't shift them).
  EasyEDA has no footprint for C3309626: jlc_parts.py checks it against pinouts.yaml (derived from the 4-pole
  footprint); confirm J5/J6 rotation in JLC's preview. JLC stock is prototype-sized (~150 each).
- Terminal windows closed on all sides -> slots open to the left side with 0.2 mm clearance; cover filler bars close them.
- Cover lip vs J1, cover side wall 0 mm clearance, OLED rails inside the 14 mm panel, missing button plungers
  (now C-shaped spring tabs with front bump + plunger, same geometry as knx-dali-gateway v3 BUTTON_TAB), UI board free in x/y (now ribs), THT tails vs cover wall (now recesses).
- Freerouting necks RELAY-Power tracks to 0.64 mm on In2; layout.py restore_relay_widths() puts them back to 0.85.
- Track joints (2026-10-29): 18 GND track ends on main/ui only grazed their target (4 stopped 0.035-0.07 mm short of
  pads D3.1/D4.1/D8.2 on main and R3.2 on ui; others overlapped a track off its centreline or were ground-pruning stubs).
  KiCad DRC counts those as connected. `test_track_joints.py` checks every end lands in a pad / via / pour or on a
  track centreline; `layout.py <board> seat-joints` (also run by every layout save) seats or removes them.
- MQTT (2026-10-26): `MQTTClient client;` used arduino-mqtt's 128-byte default buffer, which silently refuses every
  HA discovery config (largest ~620 B) and most state payloads, so Home Assistant would have discovered nothing.
  Now `HaDiscovery::MQTT_BUFFER_SIZE` (1024); `test_all_sensors.cpp` runs all five plugins at once through SensorHub
  (pins, ISRs, readings, relay source, unique HA topics/ids, largest message vs the buffer, status JSON size).

Still open (verify every time):
- Firmware `xiao_c6` builds but is untested on hardware: OLED rotation (U8G2_R1 vs R3), ladder thresholds,
  LED colours, relay MQTT/HA switch, 120 ohm shunt scaling (lib/Core/Board.h holds the pin map; keep it in
  sync with spec.yaml derived.mcu_pins).
- OLED pinout and IREF are verified against the JLX12864OLED-S096W drawing (2025-09-17); tail fold reach to
  ui J2 is still a hand-assembly judgement.
- FFC Type A/B vs connector contact sides.
- Side-wall/lid legend for the sensor bank is generated from the pad positions (SENSOR_NAMES / SENSOR_NOTES in
  build_enclosure.py); keep it in sync with main.py and spec.yaml terminals.sensor_io.labels.
- DRU `courtyard_clearance (min -100mm)` applies to anything near U3 (parts under the raised XIAO) and the
  KF142R courtyards are trimmed: DRC will not catch overlaps there; check component boxes in 3D instead.
- Accessory boards (`spec.yaml variants.v1.accessory_boards`, now `reader`): generated, routed, JLC-checked and
  released like main/ui but never panelised (`release.py PANEL_BOARDS`). Optical dial reader housing
  (`build_dial_reader.py`, `test_dial_reader.py`): lock ring (bayonet + spring fingers) over a rotatable carrier; hook
  geometry is from calipers + photos, so the CAD tests prove the bayonet against that model only. Assembly paths are
  tested too (ring lowered over the closed carrier, carrier lowered between the hooks): an earlier version with a
  wide carrier shoulder passed every final-position test but could not be assembled. Ask for the test-ring print result. TCRT5000 numbering: EasyEDA 1 A, 2 K, 3 E,
  4 C vs our CNY70-style 1 A, 2 K, 3 C, 4 E (jlc_pad_maps.yaml); the IR contrast through the glass is unproven.
- Pulse ISRs (radiation IO3, water IO4) must stay in IRAM end to end (ISR, the member it calls, LedController::click):
  settings writes disable the flash cache, and a pulse then would crash a flash-resident handler.
- The audit script's LED/part heights come from layout `heights`; missing entries fall back to the default.
- Radiation duct = ambient gamma only (not radon); flat base on a round duct; HV leads in humid air.
- Wall-mount box (`box_enclosure/`, `mechanical/scripts/build_box_enclosure.py`): reuses the DIN cover's UI
  front rotated 90 deg about y; the FFC route differs from the DIN case (check the A/B contact side for this
  fold too), and the button plungers must be unioned AFTER the tab-thinning cuts or they print loose.
