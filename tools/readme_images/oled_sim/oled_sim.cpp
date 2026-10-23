// Host simulator: renders the real OLED pages (lib/Display) with the real U8g2
// C core into raw framebuffers for the README images. Built and run by
// tools/readme_images/render.py; output: <dir>/<name>.bin ('F', tile w, tile h,
// U8g2 rotation, SSD13xx framebuffer).
#include <cmath>
#include <cstdio>
#include <string>
#include "DeviceMonitor.h"
#include "Display.h"
#include "HAL.h"
#include "Logger.h"
#include "Parameter.h"
#include "RelayOutput.h"
#include "Storage.h"

static Display display;
static std::string outDir;

static void dump(const char* name)
{
    U8G2& u = display.u8g2;   // simulator build: -Dprivate=public
    FILE* f = fopen((outDir + "/" + name + ".bin").c_str(), "wb");
    uint8_t header[4] = {'F', (uint8_t)u.getBufferTileWidth(), (uint8_t)u.getBufferTileHeight(), 1};
    fwrite(header, 1, 4, f);
    fwrite(u.getBufferPtr(), 1, u.getBufferTileWidth() * 8 * u.getBufferTileHeight(), f);
    fclose(f);
}

static ScreenModel tank(float percent)
{
    ScreenModel m;
    m.kind = "level";
    m.title = "TANK";
    m.value = percent;
    m.unit = "%";
    m.valid = true;
    m.scaleMin = 0;
    m.scaleMax = 100;
    m.sensorOk = true;
    m.raw = "41.8cm";
    m.signal = "16.5mA";
    for (int i = 0; i < 56; i++) m.trend.push_back(percent + 8 + 6 * sinf(i / 6.0f) - i * 0.15f);
    m.lines.push_back({"VOL", String("1920L")});
    m.lines.push_back({"FLW", String("-0.5Lm")});
    m.low24 = percent - 2;
    m.high24 = 84;
    return m;
}

static void limits(Storage& storage, DeviceMonitor& monitor, const char* low, const char* high)
{
    storage.saveParameter(Parameter::LIMIT_LOW, String(low));
    storage.saveParameter(Parameter::LIMIT_HIGH, String(high));
    monitor.loadLimits();
}

int main(int argc, char** argv)
{
    outDir = argc > 1 ? argv[1] : ".";
    HAL hal;
    Storage storage;
    Logger logger;
    RelayOutput relay;
    DeviceMonitor monitor;
    storage.begin();
    storage.reset();
    relay.begin(&hal, 19);
    storage.saveParameter(Parameter::LIMIT_HYSTERESIS, String("5"));
    storage.saveParameter(Parameter::RELAY_MODE, String("off_alarm"));
    limits(storage, monitor, "20", "95");
    monitor.begin(&storage, &logger, &relay);
    ESP.freeHeap = 188416;
    display.begin();

    monitor.event("SYSTEM BOOT", "FW v1.0", 0);
    monitor.updateNetwork(true, false, String("HOME -58"), String(""), 2000);
    monitor.updateNetwork(true, true, String(""), String("192.168.0.10"), 4000);
    ScreenModel level = tank(64);
    monitor.evaluate(level, 5000);
    FakeHAL::currentMillis = 3UL * 86400000UL + 5UL * 3600000UL;

    DisplayFrame frame;
    frame.screen = &level;
    frame.monitor = &monitor;
    frame.mqttConnected = true;
    const char* pages[] = {"tank", "stat", "log", "wifi"};
    for (const char* name : pages) {
        display.run(frame);
        dump(name);
        display.nextPage();
    }

    ScreenModel pressure;
    pressure.kind = "pressure";
    pressure.title = "PRES";
    pressure.value = 3.4f;
    pressure.unit = "bar";
    pressure.decimals = 1;
    pressure.valid = true;
    pressure.sensorOk = true;
    pressure.scaleMin = 0;
    pressure.scaleMax = 10;
    for (int i = 0; i < 56; i++) pressure.trend.push_back(3.5f + 0.7f * (i % 18) / 18.0f * ((i / 18) % 2 ? -1 : 1));
    pressure.lines.push_back({"IN", String("1.86V")});
    pressure.lines.push_back({"RNG", String("10bar")});
    limits(storage, monitor, "1.5", "5.5");
    frame.screen = &pressure;
    display.run(frame);
    dump("pressure");

    ScreenModel radiation;
    radiation.kind = "radiation";
    radiation.title = "RAD";
    radiation.value = 0.14f;
    radiation.unit = "uSv/h";
    radiation.decimals = 2;
    radiation.valid = true;
    radiation.sensorOk = true;
    radiation.sensorLabel = "TUBE";
    radiation.scaleMin = 0;
    for (int i = 0; i < 56; i++) radiation.trend.push_back(0.12f + 0.04f * ((i * 37) % 11) / 10.0f);
    radiation.lines.push_back({"CPM", String("18")});
    radiation.lines.push_back({"5M", String("0.13")});
    limits(storage, monitor, "", "0.3");
    frame.screen = &radiation;
    display.run(frame);
    dump("radiation");

    limits(storage, monitor, "20", "95");
    ScreenModel low = tank(12);
    monitor.evaluate(low, 6000);
    frame.screen = &low;
    display.run(frame);
    dump("alert");

    display.showSetupPortal("ESP_A4CF12B3");
    dump("portal");
    return 0;
}
