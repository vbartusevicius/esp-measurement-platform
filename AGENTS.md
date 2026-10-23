# Agent notes

## Verify firmware changes

- Native unit tests (host): `pio test -e native`
- Both firmware targets (Linux container, PlatformIO 6.1.19 pinned):
  `docker build -f Dockerfile.firmware -t esp-firmware .` once, then
  `docker run --rm -v "$PWD":/project -v esp-pio:/root/.platformio -e PLATFORMIO_BUILD_DIR=/tmp/build esp-firmware "pio run -e xiao_c6 && pio run -e nodemcu"`
  (`PLATFORMIO_BUILD_DIR` keeps container objects away from host `.pio/`; the ESP8266 toolchain doesn't run on Apple Silicon hosts.)
- Unused includes: `docker run ... esp-firmware "bash tools/check_includes.sh"`
- Hardware/mechanical: see `.claude/skills/manufacturing-readiness-review/SKILL.md`.

## Layout and conventions

- `src/main.cpp` is only the composition root (create, wire, schedule).
- `lib/Plugin`: plugin contracts (`IPlugin`, `ScreenModel`, `HaDiscovery`) and shared measurement helpers.
- `lib/Plugins/<Name>`: one sensor each. Home Assistant entities are `HaEntity` tables; keep `objectId` and `uniqueSuffix` stable or HA loses entity history (`test_ha_discovery.cpp` pins the topics).
- `lib/WebApi`: routes only; JSON is built in `StatusJson` / `ConfigJson`.
- `lib/Display`: `Display` owns the OLED, `PortraitPages` draws the 64x128 pages.
- Web UI lives in `data/`; `tools/embed_web.py` gzips it into `lib/WebApi/WebAssets.h` (generated, git-ignored) on every build.
- Use `hal->millis()` in plugins, not the global `millis()`, so tests control time.
- On ESP8266 include `WifiConnector.h` before `WebApi.h` (HTTP method enum clash, see `WebApi.h`).
