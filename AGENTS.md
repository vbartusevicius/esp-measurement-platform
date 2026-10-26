# Agent notes

## Verify firmware changes

- Native unit tests (host): `pio test -e native`
- Firmware (Linux container, PlatformIO 6.1.19 pinned):
  `docker build -f Dockerfile.firmware -t esp-firmware .` once, then
  `docker run --rm -v "$PWD":/project -v esp-pio:/root/.platformio -e PLATFORMIO_BUILD_DIR=/tmp/build esp-firmware "pio run -e xiao_c6"`
  (`PLATFORMIO_BUILD_DIR` keeps container objects away from host `.pio/`.) The only target is the v1 board (XIAO ESP32-C6).
- Unused includes: `docker run ... esp-firmware "bash tools/check_includes.sh"`
- Hardware/mechanical: see `.claude/skills/manufacturing-readiness-review/SKILL.md`.
- Web UI without hardware: `python3 tools/webui_mock.py` (scenarios via `?sensor=`).
- README images: `python3 tools/readme_images/render.py` after changing `data/`, `lib/Display/` or the hardware renders; commit the updated `doc/images/`.

## Layout and conventions

- `src/main.cpp` is only the composition root (create, wire, schedule).
- `lib/Plugin`: plugin contracts (`IPlugin`, `ScreenModel`, `HaDiscovery`) and shared measurement helpers.
- `lib/Plugins/<Name>`: one sensor each. Home Assistant entities are `HaEntity` tables; keep `objectId` and `uniqueSuffix` stable or HA loses entity history (`test_ha_discovery.cpp` pins the topics).
- `lib/WebApi`: routes only. The JSON is built in `lib/ApiJson` (`StatusJson`, `ConfigJson`), which the native tests run with the real ArduinoJson.
- `FW_VERSION` comes from git at build time (`tools/version.py` -> git-ignored `lib/Core/BuildVersion.h`; the release workflow passes the tag in `FW_VERSION`).
- `lib/Display`: `Display` owns the OLED, `PortraitPages` draws the 64x128 pages.
- Web UI lives in `data/`; `tools/embed_web.py` gzips it into `lib/WebApi/WebAssets.h` (generated, git-ignored) on every build.
- Use `hal->millis()` in plugins, not the global `millis()`, so tests control time.

## Several sensors at once

- `SensorHub` (`lib/Plugin`) runs the plugins listed in `sensors` (falls back to the old single `active_plugin`),
  refuses ones that clash on a board input (`IPlugin::inputs()`, `Board::INPUT_*`) and schedules each on its own
  sampling / publish interval (main loop ticks every second).
- Plugins get a `Settings*`: a `ScopedSettings` with the plugin prefix (`ScopedSettings::prefixFor`: `ad.`, `ud.`,
  `rc.`, `av.`, `pm.`). Per-sensor limits (`limit_*`) live in that scope too; `relay_mode` / `relay_source` and
  MQTT settings are device-wide. Storage is 3 KB; `test_sensor_hub` checks every setting of all five sensors fits.
  Saving an empty value removes the key.
- `DeviceMonitor`: one `LimitMonitor` per sensor (`addSensor`), the relay follows `relay_source`; events name the
  sensor once more than one runs (`EventLog::TEXT_LENGTH` 16).
- MQTT: `<device>/stat/<plugin id>` per sensor; HA object ids are `<plugin id>_<objectId>`
  (`HaDiscoveryContext::objectPrefix`); diagnostics and relay once per device.
- OLED: one page per sensor, then DEV / LOG / WIFI (`PortraitPages::pageCount`); PAGE steps through them.
- Web: `sensors[]` in status and config, `?sensor=<id>` on chart and alert ack; mock scenarios `house`, `house-alarm`.
  Overview sub-tabs: `state.view` = `'all'` (summary cards) or a sensor id (detail, `#overview/<id>`); the relay is
  one bar on top of every Overview view (`renderRelay` / `relayRule`). The Events tab merges `status.events` and the
  WebSocket `log_batch` lines (`timelineEntries`), filtered by `state.filter`.
