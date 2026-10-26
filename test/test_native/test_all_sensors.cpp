// Every sensor the board supports, running at once as on a fully wired v1:
// 4-20 mA probe, 0-10 V pressure sensor, ultrasonic on IO1/IO2, Geiger on IO3,
// pulse meter on IO4. Drives the real plugins through SensorHub with simulated
// terminal signals and interrupts, then checks the readings, the per-sensor
// MQTT / Home Assistant output and the web status document.
#include <gtest/gtest.h>
#include <map>
#include <set>
#include <string>
#include <vector>
#include "AnalogDistancePlugin.h"
#include "AnalogVoltagePlugin.h"
#include "Board.h"
#include "DeviceMonitor.h"
#include "HAL.h"
#include "HaDiscovery.h"
#include "Logger.h"
#include "Parameter.h"
#include "PluginRegistry.h"
#include "PulseMeterPlugin.h"
#include "RadiationCounterPlugin.h"
#include "RelayOutput.h"
#include "ScreenModel.h"
#include "SensorHub.h"
#include "StatusJson.h"
#include "Storage.h"
#include "UltrasonicDistancePlugin.h"

namespace {

// The board's terminals: a voltage per ADC pin, an echo time on IO1, and the
// interrupt handlers the plugins attach (fired by the test like real pulses).
class BoardHal : public HAL {
public:
    std::map<uint8_t, int> millivolts;
    unsigned long echoUs = 0;
    std::map<uint8_t, void (*)()> isr;
    std::map<uint8_t, uint8_t> modes;

    void pinMode(uint8_t pin, uint8_t mode) override { modes[pin] = mode; }
    void digitalWrite(uint8_t, uint8_t) override {}
    int analogReadMilliVolts(uint8_t pin) override { return millivolts.count(pin) ? millivolts[pin] : 0; }
    unsigned long pulseIn(uint8_t pin, uint8_t, unsigned long timeout) override
    {
        return pin == Board::ECHO_PIN && echoUs <= timeout ? echoUs : 0;
    }
    void delayMicroseconds(unsigned int) override {}
    unsigned long millis() override { return FakeHAL::currentMillis; }
    void attachInterrupt(uint8_t num, void (*fn)(), int) override { isr[num] = fn; }
    void detachInterrupt(uint8_t num) override { isr.erase(num); }
    uint8_t pinToInterrupt(uint8_t pin) override { return pin; }

    void pulse(int pin)
    {
        ASSERT_TRUE(isr.count(pin)) << "no interrupt on pin " << pin;
        isr[pin]();
    }
};

}  // namespace

class AllSensorsTest : public ::testing::Test {
protected:
    BoardHal hal;
    Storage storage;
    Logger logger;
    RelayOutput relay;
    PluginRegistry registry;
    AnalogDistancePlugin analog;
    UltrasonicDistancePlugin ultrasonic;
    RadiationCounterPlugin radiation;
    AnalogVoltagePlugin pressure;
    PulseMeterPlugin meter;
    SensorHub hub;
    DeviceMonitor monitor;

    void set(const char* prefix, const char* key, const char* value)
    {
        storage.saveParameter((String(prefix) + key).c_str(), String(value));
    }

    void SetUp() override
    {
        FakeHAL::currentMillis = 0;
        storage.begin();
        storage.reset();
        for (IPlugin* p : std::vector<IPlugin*>{&analog, &ultrasonic, &radiation, &pressure, &meter}) registry.add(p);

        storage.saveParameter(Parameter::SENSORS, String("analog_distance,ultrasonic_distance,radiation_counter,analog_voltage,pulse_meter"));
        storage.saveParameter(Parameter::MQTT_HOST, String("192.168.0.10"));
        storage.saveParameter(Parameter::MQTT_PORT, String("1883"));
        storage.saveParameter(Parameter::MQTT_DEVICE, String("house"));
        storage.saveParameter(Parameter::RELAY_MODE, String("off_alarm"));
        storage.saveParameter(Parameter::RELAY_SOURCE, String("analog_distance"));
        // 4-20 mA probe, 0-5 m range: 4 mA = 0 cm, 20 mA = 500 cm; tank empty at 10 cm, full at 210 cm of water
        set("ad.", "sensor_range", "5");
        set("ad.", "distance_empty", "10");
        set("ad.", "distance_full", "210");
        set("ad.", "sampling_interval", "2");
        set("ad.", "limit_low", "20");
        // ultrasonic: empty at 200 cm, full at 20 cm
        set("ud.", "distance_empty", "200");
        set("ud.", "distance_full", "20");
        set("ud.", "sampling_interval", "2");
        // 0.5-4.5 V = 0-10 bar pressure transducer
        set("av.", "voltage_min", "0.5");
        set("av.", "voltage_max", "4.5");
        set("av.", "value_min", "0");
        set("av.", "value_max", "10");
        // 10 L per pulse gas meter, J305 tube
        set("pm.", "meter_liters_per_pulse", "10");
        set("rc.", "tube_conversion_factor", "123.1");
        set("rc.", "tube_dead_time_us", "0");

        // Terminal signals: 12 mA (1440 mV on 120R) -> 250 cm head; 3.4 bar -> 1.86 V at the
        // sensor = 0.581 V after the 22k/10k divider; echo for 1.00 m at 343 m/s
        hal.millivolts[Board::MA_PIN] = 1440;
        hal.millivolts[Board::V0_10_PIN] = 581;
        hal.echoUs = 5831;

        relay.begin(&hal, Board::RELAY_PIN);
        hub.begin(&storage, registry, &hal, &logger, nullptr);
        monitor.begin(&storage, &logger, &relay);
        for (size_t i = 0; i < hub.size(); i++) monitor.addSensor(hub.plugin(i).getId(), &hub.settings(i));
    }

    // The firmware's 1 s tick (main.cpp sampleSensors), with Geiger clicks and meter pulses in between
    void run(unsigned long seconds, unsigned long geigerEveryMs, unsigned long meterEveryMs)
    {
        const unsigned long end = FakeHAL::currentMillis + seconds * 1000UL;
        while (FakeHAL::currentMillis < end) {
            const unsigned long next = FakeHAL::currentMillis + 1000UL;
            for (unsigned long t = FakeHAL::currentMillis + 1; t <= next; t++) {
                FakeHAL::currentMillis = t;
                if (t % geigerEveryMs == 0) hal.pulse(Board::PULSE_PIN);
                if (t % meterEveryMs == 0) hal.pulse(Board::METER_PULSE_PIN);
            }
            for (size_t i = 0; i < hub.size(); i++) {
                if (!hub.sampleDue(i, FakeHAL::currentMillis)) continue;
                hub.plugin(i).loop();
                ScreenModel screen;
                if (hub.plugin(i).getScreen(screen)) monitor.evaluate(i, screen, FakeHAL::currentMillis);
            }
        }
    }

    ScreenModel screenOf(const char* id)
    {
        ScreenModel s;
        hub.plugin(hub.indexOf(id)).getScreen(s);
        return s;
    }
};

TEST_F(AllSensorsTest, AllFiveRunWithoutAClashAndEachOnItsOwnPins)
{
    ASSERT_EQ(hub.size(), 5u);
    EXPECT_EQ(monitor.sensorCount(), 5u);
    EXPECT_EQ(hal.isr.size(), 2u);                         // Geiger on IO3, meter on IO4
    EXPECT_TRUE(hal.isr.count(Board::PULSE_PIN));
    EXPECT_TRUE(hal.isr.count(Board::METER_PULSE_PIN));
    EXPECT_EQ(hal.modes[Board::TRIG_PIN], OUTPUT);
    EXPECT_EQ(hal.modes[Board::ECHO_PIN], INPUT_PULLUP);
    EXPECT_EQ(hal.modes[Board::METER_PULSE_PIN], INPUT_PULLUP);
    // the five sensors' pins never overlap each other or the board's own pins
    std::set<int> sensorPins = {Board::MA_PIN, Board::V0_10_PIN, Board::TRIG_PIN, Board::ECHO_PIN, Board::PULSE_PIN, Board::METER_PULSE_PIN};
    EXPECT_EQ(sensorPins.size(), 6u);
    for (int own : {Board::BUTTON_LADDER_PIN, Board::LED_DATA_PIN, Board::I2C_SDA_PIN, Board::I2C_SCL_PIN, Board::RELAY_PIN}) {
        EXPECT_FALSE(sensorPins.count(own)) << own;
    }
}

TEST_F(AllSensorsTest, EverySensorMeasuresItsOwnSignalSideBySide)
{
    // Geiger 20 CPM (one click every 3 s), gas meter pulse every 6 s (10 L -> 100 L/min)
    run(600, 3000, 6000);

    const ScreenModel tank = screenOf("analog_distance");
    EXPECT_TRUE(tank.sensorOk);
    EXPECT_EQ(tank.signal, String("12.0mA"));
    // 12 mA on a 0-5 m probe = 250 cm head; tank span 10..210 cm -> clamped at full
    EXPECT_NEAR(tank.value, 100.0f, 0.5f);

    const ScreenModel well = screenOf("ultrasonic_distance");
    EXPECT_TRUE(well.sensorOk);
    // echo 1.00 m: empty 200 cm, full 20 cm -> (200-100)/180 = 55.6 %
    EXPECT_NEAR(well.value, 55.6f, 1.0f);

    const ScreenModel pres = screenOf("analog_voltage");
    EXPECT_TRUE(pres.sensorOk);
    EXPECT_NEAR(pres.value, 3.4f, 0.05f);

    const ScreenModel rad = screenOf("radiation_counter");
    std::vector<StatEntry> radStats;
    radiation.getStats(radStats);
    float cpm = -1;
    for (const StatEntry& e : radStats) if (String(e.key) == String("cpm")) cpm = e.numericValue;
    EXPECT_NEAR(cpm, 20.0f, 1.0f);
    EXPECT_NEAR(rad.value, 20.0f / 123.1f, 0.02f);

    EXPECT_DOUBLE_EQ(meter.totalLiters(), 100 * 10.0);   // 100 pulses in 600 s, none lost
    EXPECT_NEAR(meter.flowLitersPerMinute(), 100.0f, 2.0f);
}

TEST_F(AllSensorsTest, PulsesStillCountWhileTheOtherSensorsSample)
{
    // A fast Geiger (600 CPM) and a fast meter (5 pulses/s, above its 50 ms debounce) together
    run(60, 100, 200);
    std::vector<StatEntry> stats;
    radiation.getStats(stats);
    float total = -1;
    for (const StatEntry& e : stats) if (String(e.key) == String("counts_total")) total = e.numericValue;
    EXPECT_NEAR(total, 600.0f, 1.0f);
    EXPECT_DOUBLE_EQ(meter.totalLiters(), 300 * 10.0);
}

TEST_F(AllSensorsTest, LimitsStayPerSensorAndOnlyTheSourceDrivesTheRelay)
{
    hal.millivolts[Board::MA_PIN] = 480;   // 4 mA: probe at 0 cm -> tank empty, below its 20 % limit
    run(120, 3000, 6000);
    const int tank = hub.indexOf("analog_distance");
    EXPECT_TRUE(monitor.limits(tank).alarm());
    EXPECT_EQ(monitor.relaySource(), tank);
    EXPECT_FALSE(relay.isOn());   // off during an alert
    for (size_t i = 0; i < hub.size(); i++) {
        if ((int)i != tank) EXPECT_FALSE(monitor.limits(i).alarm()) << hub.plugin(i).getId();
    }
}

TEST_F(AllSensorsTest, MqttTopicsAndEntitiesNeverCollideAndFitTheClientBuffer)
{
    run(60, 3000, 6000);
    MQTTClient client;
    std::set<std::string> stateTopics;
    for (size_t i = 0; i < hub.size(); i++) {
        IMqttContributor* mqtt = hub.plugin(i).mqtt();
        ASSERT_NE(mqtt, nullptr) << hub.plugin(i).getId();
        const String topic = String("house/stat/") + hub.plugin(i).getId();
        stateTopics.insert(topic.c_str());
        HaDiscoveryContext ctx;
        ctx.deviceId = "A4CF12B3C4D5";
        ctx.stateTopic = topic;
        ctx.availabilityTopic = "house/availability";
        ctx.deviceName = "House";
        ctx.objectPrefix = String(hub.plugin(i).getId()) + "_";
        mqtt->publishHomeAssistantAutoconfig(client, ctx);
        mqtt->publishMqtt(client, topic);
    }
    EXPECT_EQ(stateTopics.size(), 5u);

    std::set<std::string> configTopics, uniqueIds;
    size_t largest = 0;
    std::string largestTopic;
    for (const auto& m : client.published) {
        // MQTT PUBLISH = fixed header (<= 5) + 2-byte topic length + topic + payload (QoS 0)
        const size_t packet = 5 + 2 + m.topic.size() + m.payload.size();
        if (packet > largest) { largest = packet; largestTopic = m.topic; }
        if (m.topic.rfind("homeassistant/", 0) != 0) continue;
        EXPECT_TRUE(configTopics.insert(m.topic).second) << "duplicate discovery topic " << m.topic;
        const size_t at = m.payload.find("\"unique_id\":\"");
        ASSERT_NE(at, std::string::npos) << m.topic;
        const std::string id = m.payload.substr(at + 13, m.payload.find('"', at + 13) - at - 13);
        EXPECT_TRUE(uniqueIds.insert(id).second) << "duplicate unique_id " << id;
    }
    EXPECT_GE(configTopics.size(), 15u);
    std::cout << "[ " << configTopics.size() << " discovery configs, largest MQTT message " << largest << " bytes: " << largestTopic << " ]" << std::endl;
    EXPECT_LE(largest, HaDiscovery::MQTT_BUFFER_SIZE) << "largest message: " << largestTopic << " (" << largest << " bytes)";
}

TEST_F(AllSensorsTest, WebStatusListsEverySensorAndStaysSmallEnoughToSendEveryTwoSeconds)
{
    run(600, 3000, 6000);
    JsonDocument doc;
    StatusJson::write(doc, {&hub, &logger, &monitor, &storage, true});
    ASSERT_EQ(doc["sensors"].size(), 5u);
    for (JsonObject s : doc["sensors"].as<JsonArray>()) {
        EXPECT_TRUE(s["configured"].as<bool>()) << s["id"].as<const char*>();
        EXPECT_FALSE(s["screen"].isNull()) << s["id"].as<const char*>();
    }
    EXPECT_STREQ(doc["relay"]["source"], "analog_distance");
    String text;
    serializeJson(doc, text);
    // the ESP32-C6 has ~180 KB free heap; doc + String + the async copy stay well below 32 KB
    EXPECT_LT(text.length(), 10000u) << text.length();
    std::cout << "[ status JSON with five sensors: " << text.length() << " bytes ]" << std::endl;
}
