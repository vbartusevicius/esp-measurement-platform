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
#include "ScopedSettings.h"
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

static void limits(Settings& sensor, DeviceMonitor& monitor, const char* low, const char* high)
{
    sensor.saveParameter(Parameter::LIMIT_LOW, String(low));
    sensor.saveParameter(Parameter::LIMIT_HIGH, String(high));
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
    ScopedSettings sensor(&storage, String("ad."));
    sensor.saveParameter(Parameter::LIMIT_HYSTERESIS, String("5"));
    storage.saveParameter(Parameter::RELAY_MODE, String("off_alarm"));
    monitor.begin(&storage, &logger, &relay);
    monitor.addSensor("analog_distance", &sensor);
    limits(sensor, monitor, "20", "95");
    ESP.freeHeap = 188416;
    display.begin();

    monitor.event("SYSTEM BOOT", "FW v1.0", 0);
    monitor.updateNetwork(true, false, String("HOME -58"), String(""), 2000);
    monitor.updateNetwork(true, true, String(""), String("192.168.0.10"), 4000);
    // One device running four sensors: PAGE steps TANK 1/7, PRES, RAD, WATR, DEV, LOG, WIFI
    ScopedSettings pres(&storage, String("av."));
    ScopedSettings rad(&storage, String("rc."));
    monitor.addSensor("analog_voltage", &pres);
    monitor.addSensor("radiation_counter", &rad);
    ScopedSettings pm(&storage, String("pm."));
    monitor.addSensor("pulse_meter", &pm);
    limits(pm, monitor, "", "30");
    limits(pres, monitor, "1.5", "5.5");
    limits(rad, monitor, "", "0.3");

    ScreenModel level = tank(64);
    level.signal = "16.5mA";

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
    pressure.raw = "3.40bar";
    pressure.signal = "1.86V";
    pressure.low24 = 2.8f;
    pressure.high24 = 4.2f;

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
    radiation.raw = "0cps";
    radiation.signal = "4.7kp";
    radiation.low24 = 0.09f;
    radiation.high24 = 0.19f;

    // as PulseMeterPlugin::getScreen fills it: flow, register + 24 h usage, last pulse age + 24 h peak
    ScreenModel water;
    water.kind = "meter";
    water.title = "WATR";
    water.value = 6.2f;
    water.unit = "L/min";
    water.decimals = 1;
    water.valid = true;
    water.sensorOk = true;
    water.sensorLabel = "PULS";
    water.scaleMin = 0;
    for (int i = 0; i < 56; i++) water.trend.push_back((i % 14) < 4 ? 6.4f + 0.3f * ((i * 7) % 3) : (i % 14) == 9 ? 2.1f : 0.0f);
    water.lines.push_back({"TOT", String("1736m3")});
    water.lines.push_back({"24H", String("401L")});
    water.signal = "41237p";
    water.details.push_back({"LAST", String("4s")});
    water.details.push_back({"MAX", String("14.2L/m")});

    monitor.evaluate(0, level, 5000);
    monitor.evaluate(1, pressure, 5000);
    monitor.evaluate(2, radiation, 5000);
    monitor.evaluate(3, water, 5000);
    FakeHAL::currentMillis = 3UL * 86400000UL + 5UL * 3600000UL;

    DisplayFrame frame;
    frame.screens = {level, pressure, radiation, water};
    frame.monitor = &monitor;
    frame.mqttConnected = true;
    const char* pages[] = {"tank", "pressure", "radiation", "water", "dev", "log", "wifi"};
    for (const char* name : pages) {
        display.run(frame);
        dump(name);
        display.nextPage(frame.screens.size());
    }

    ScreenModel low = tank(12);
    monitor.evaluate(0, low, 6000);
    frame.screens[0] = low;
    display.run(frame);
    dump("alert");

    display.showSetupPortal("ESP_A4CF12B3");
    dump("portal");
    return 0;
}
