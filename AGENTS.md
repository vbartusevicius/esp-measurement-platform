# Agent instructions

Firmware (`src/`, `lib/`, `data/`) and hardware (`hardware/`, `mechanical/`) for a 1-DIN sensor node.
The only target is the v1 board (XIAO ESP32-C6). Read the section for the area you change, follow its rules and run
its checks before you report the work as done.

## Firmware

### Check your change

- Unit tests on the host: `pio test -e native` (CI runs them in `Dockerfile.test`).
- Firmware build, in the container CI uses (PlatformIO 6.1.19 pinned). Build the image once:
  `docker build -f Dockerfile.firmware -t esp-firmware .`
  Then build:
  `docker run --rm -v "$PWD":/project -v esp-pio:/root/.platformio -e PLATFORMIO_BUILD_DIR=/tmp/build esp-firmware "pio run -e xiao_c6"`
  Keep `PLATFORMIO_BUILD_DIR` so container objects don't end up in the host's `.pio/`.
- Unused includes: `docker run ... esp-firmware "bash tools/check_includes.sh"`.
- Web UI without hardware: `python3 tools/webui_mock.py`, then `http://127.0.0.1:8790/?sensor=<scenario>`
  (scenario names are the keys of `SCENARIOS` in `tools/webui_mock.py`; `house` / `house-alarm` run several sensors).

### Where code goes

- `src/main.cpp` is only the composition root: create, wire, schedule. Put no logic there.
- `lib/Plugin`: plugin contracts (`IPlugin`, `ScreenModel`, `HaDiscovery`) and shared measurement helpers.
- `lib/Plugins/<Name>`: one sensor each.
- `lib/WebApi`: HTTP routes only. Build the JSON in `lib/ApiJson` (`StatusJson`, `ConfigJson`), where the native tests
  run it with the real ArduinoJson.
- `lib/Display`: `Display` owns the OLED, `PortraitPages` draws the 64x128 pages.
- `data/`: the web UI. `tools/embed_web.py` gzips it into `lib/WebApi/WebAssets.h` on every build; that file is
  generated and git-ignored, so never edit it.
- `FW_VERSION` comes from git at build time (`tools/version.py` writes the git-ignored `lib/Core/BuildVersion.h`;
  the release workflow passes the tag in `FW_VERSION`). Don't hard-code a version.

### Rules

- In plugins use `hal->millis()`, never the global `millis()`, so tests control time.
- Home Assistant entities are `HaEntity` tables. Never change an existing `objectId` or `uniqueSuffix`: HA would lose
  the entity's history. `test_ha_discovery.cpp` pins the topics.
- Plugin settings go through the `Settings*` the plugin gets: a `ScopedSettings` with the plugin prefix
  (`ScopedSettings::prefixFor`: `ad.`, `ud.`, `rc.`, `av.`, `pm.`). Per-sensor limits (`limit_*`) live in that scope;
  `relay_mode`, `relay_source` and the MQTT settings are device-wide. Saving an empty value removes the key.
- Settings storage is 3 KB. When you add a setting, `test_sensor_hub` must still show that every setting of all five
  sensors fits.
- Event texts are at most `EventLog::TEXT_LENGTH` (16) characters, including the sensor name added when more than one
  sensor runs.

### How several sensors run at once

- `SensorHub` (`lib/Plugin`) runs the plugins listed in `sensors` (falls back to the old single `active_plugin`),
  refuses ones that clash on a board input (`IPlugin::inputs()`, `Board::INPUT_*`) and schedules each on its own
  sampling / publish interval (the main loop ticks every second).
- `DeviceMonitor`: one `LimitMonitor` per sensor (`addSensor`); the relay follows `relay_source`.
- MQTT: `<device>/stat/<plugin id>` per sensor; HA object ids are `<plugin id>_<objectId>`
  (`HaDiscoveryContext::objectPrefix`); diagnostics and relay once per device.
- OLED: one page per sensor, then DEV / LOG / WIFI (`PortraitPages::pageCount`); PAGE steps through them.
- Web: `sensors[]` in status and config, `?sensor=<id>` on chart and alert ack. Overview sub-tabs: `state.view` is
  `'all'` (summary cards) or a sensor id (detail, `#overview/<id>`); the relay is one bar on top of every Overview view
  (`renderRelay` / `relayRule`). The Events tab merges `status.events` and the WebSocket `log_batch` lines
  (`timelineEntries`), filtered by `state.filter`.

## Hardware and enclosure

All EDA and CAD work runs in containers. Build them with `docker compose --profile hardware build eda cad`, then run
commands as `docker compose --profile hardware run --rm eda "<command>"` (or `cad`). The repository is mounted at
`/work`. The images are amd64 and run emulated on Apple Silicon, so allow for slow runs.

### Pipeline

- Everything at once: `python3 hardware/scripts/build.py [--eda] [--cad] [--release] [--test] [--fresh]` from the host.
- Boards are `main`, `ui` and `reader`. The stored layout is `hardware/layout/v1/<board>/<board>.kicad_pcb`;
  `hardware/scripts/layout.py <board> <command>` changes it. Its docstring lists the commands.
- Placement: `layout_<board>.yaml` holds only `locked: true` mechanical/enclosure-mated anchors and keepouts; never
  hand-maintain passive or IC coordinate tables. `hardware/scripts/placer.py` (`layout.py <board> autoplace`, or
  `build.py --eda --fresh`) runs a deterministic two-stage Google OR-Tools CP-SAT placer (`ortools.sat.python.cp_model`,
  0.05 mm integer grid, fixed seed, single worker): Stage 1 solves all active ICs (with a Stage-1 moat reserved for HF
  passives), magnetics, discrete semiconductors and fuses simultaneously (`AddNoOverlap2D` on `F.Cu`, `B.Cu`, 3D height
  limits under raised socketed modules, and cross-face `F<->B` drill/escape shadows) minimizing weighted L1 pad-to-pad
  Manhattan wirelength with 3-4x priority on unprotected power/field-terminal entry nets (`VIN_RAW`, `VIN_FUSED`,
  `*_TERM`) and switching nodes (`BUCK5_SW`); Stage 2 freezes Stage 1 with routing-escape halos and solves 2-pin
  passives in functional batches (`is_vert` 0/90 width/height swap with full 4-orientation per-pad modeling, HF
  input/bootstrap caps solved before bulk caps) with shared-parent pin attraction so decoupling/filter passives pull
  directly to their parent IC's local power and ground pins, followed by `uncross_and_align_passives` (zero-courtyard
  180-deg uncrossing and clash-free adjacent pin-pair midpoint alignment). Before `.dsn` export, `add_gnd_vias` drops
  locked through-vias beside SMD `GND` pads into the `In1.Cu` ground plane.
- Autorouting: `layout.py <board> route [seconds]` (default time limit 600 s) uses fastroute (`--router.fanout.enabled=false`), installed from a
  pinned release in `docker/eda/Dockerfile`. The exported `.dsn` adds a +3 um rounding margin above KiCad DRC clearance
  minimums, overriding `(type wire_smd)` back to `base_clearance + 3 um` and `(type smd_smd)` to `50 um` on SELV
  netclasses so traces escape fine-pitch IC/FFC pads cleanly while `RELAY-Power` keeps its full 2503 um mains spacing.
  If `.tune` length-matching is ever used, keep it strictly on 2-pin point-to-point branches (never 3+-pin nets).
  `route` runs DRC on the unrouted board first, routes the exported DSN, imports
  the SES and fails unless every connection is routed and `kicad-cli pcb drc` shows no violation that wasn't already
  on the unrouted board. Treat that DRC as the only pass/fail: fastroute exits 0 even with connections left unrouted,
  and non-zero only when the run itself fails.
- fastroute gives the same session for the same DSN. A change anywhere in the exported DSN (placement, rules, locked
  tracks) can move the whole result, so compare vias and track length after rerouting.
- After import, `through_vias` converts buried F.Cu-B.Cu vias back to through vias (the DSN hides the In1 plane because
  fastroute 0.1.14 can't route the relay's THT nets with a power layer and places no vias under a `wire_keepout`), and
  `smooth_tracks.smooth_board` runs a DRC-safe octilinear (0/45/90 deg) track smoother across non-pour nets to remove
  autorouter V-detours and micro-staircase jogs before saving and DRC verification (`layout.py <board> smooth` also runs
  it standalone):
  - fastroute narrows tracks at pins (0.2 -> 0.15 mm signal, 0.3 -> 0.225 mm power); the DRC rules allow that, and
    the boards don't route without it. Relay tracks keep their width (`--no-neckdown-classes=RELAY-Power`).
  - Ground is routed as an ordinary net (with locked `add_gnd_vias` plane ties) and skipped by the smoother; its extra
    tracks and vias to the In1 plane stay.
  - `seat_track_ends` runs on every save for tracks carried onto moved footprints; it finds nothing on a fresh route.
- To bump fastroute, use a release at least 7 days old and update `FASTROUTE_VERSION` and `FASTROUTE_SHA256` (from the
  release's `SHA256SUMS.txt`, `linux-x64` asset), then reroute every board and release.

### Check your change

- Board tests: `docker compose --profile hardware run --rm eda "cd hardware/tests && python3 -m pytest -q"`.
  `test_boards_routed.py` (routed, DRC clean), `test_track_joints.py`, `test_consistency.py`,
  `test_jlc_assembly.py`, `test_release_current.py` (the release matches the stored layouts) and the two generator-independent
  verification gates (`test_pinout_chirality_polarity.py` for mounting-face shoelace chirality, standalone datasheet MPN
  pin roles, bus parity and diode bias + silkscreen cathode proximity; `test_spice_copper.py` for physical copper
  Union-Find extraction, trace R/C parasitics, 3D FFC/terminal stitching and `libngspice` `.op`/`.ac`/`.noise`/`.tran`
  checks using `.options rshunt=1e11` and bounded `tanh()` models) must pass.
- Enclosure and print rules: the `mechanical/tests` suites in the `cad` container (see `.github/workflows/ci.yml`).
- Before anything is ordered, run the review in `.claude/skills/manufacturing-readiness-review/SKILL.md`.

### Releasing

- After any change to a stored layout, regenerate the release:
  `docker compose --profile hardware run --rm eda "python3 hardware/scripts/release.py v1 [<board>...]"`.
  It refuses a board with DRC errors, unrouted connections or a JLC part that doesn't fit or is out of stock.
- The release also copies the enclosure STEP files from your local `mechanical/build/`. If their only diff is the
  `FILE_NAME` timestamp, restore them with `git checkout` instead of committing them.
- Then regenerate the README images (next section).

## README images

- Run `python3 tools/readme_images/render.py` after changing `data/`, `lib/Display/` or the hardware renders in
  `hardware/releases/v1`. It needs Pillow, Chrome and one prior `pio run -e xiao_c6`.
- It rewrites every image in `doc/images/`. Commit only the images your change affects and restore the rest with
  `git checkout` (re-rendering alone changes their bytes). The board renders only feed `hardware-pcbs.png`.

## Environment

- If a Docker build fails with "not enough free space", the Docker VM disk is full. Ask before pruning anything.
