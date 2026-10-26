#include <gtest/gtest.h>
#include <cstring>
#include "DeviceMonitor.h"
#include "HAL.h"
#include "Logger.h"
#include "Parameter.h"
#include "RelayOutput.h"
#include "ScreenModel.h"
#include "ScopedSettings.h"
#include "Storage.h"

class DeviceMonitorTest : public ::testing::Test {
protected:
    HAL hal;
    Storage storage;
    Logger logger;
    RelayOutput relay;
    DeviceMonitor monitor;
    ScopedSettings tankSettings{&storage, String("ad.")};
    ScopedSettings radSettings{&storage, String("rc.")};

    void SetUp() override {
        storage.begin();
        storage.reset();
        relay.begin(&hal, 19);
    }

    void configure(const char* low, const char* high, const char* mode) {
        tankSettings.saveParameter(Parameter::LIMIT_LOW, String(low));
        tankSettings.saveParameter(Parameter::LIMIT_HIGH, String(high));
        tankSettings.saveParameter(Parameter::LIMIT_HYSTERESIS, String("5"));
        storage.saveParameter(Parameter::RELAY_MODE, String(mode));
        monitor = DeviceMonitor();
        monitor.begin(&storage, &logger, &relay);
        monitor.addSensor("analog_distance", &tankSettings);
    }

    static ScreenModel tank(float percent, bool ok = true) {
        ScreenModel m;
        m.title = "TANK";
        m.value = percent;
        m.unit = "%";
        m.valid = ok;
        m.sensorOk = ok;
        m.signal = "16.5mA";
        return m;
    }
};

TEST_F(DeviceMonitorTest, EmptyLimitsAreDisabled)
{
    configure("", "", "manual");
    EXPECT_FALSE(monitor.limits(0).hasLow());
    EXPECT_FALSE(monitor.limits(0).hasHigh());
    monitor.evaluate(0, tank(1.0f), 0);
    EXPECT_FALSE(monitor.alertPending());
}

TEST_F(DeviceMonitorTest, LimitRuleSwitchesTheRelayAndLogsEvents)
{
    configure("20", "95", "on_alarm");
    monitor.evaluate(0, tank(50.0f), 1000);
    EXPECT_FALSE(relay.isOn());

    monitor.evaluate(0, tank(18.0f), 2000);
    EXPECT_TRUE(relay.isOn());
    EXPECT_TRUE(monitor.alertPending());
    EXPECT_EQ(monitor.relayActivations(), 1u);
    EXPECT_STREQ(monitor.events().newest(0).title, "RELAY ON");
    EXPECT_STREQ(monitor.events().newest(1).title, "MIN LIMIT!");
    EXPECT_STREQ(monitor.events().newest(1).detail, "18%<20");

    monitor.evaluate(0, tank(26.0f), 3000);
    EXPECT_FALSE(relay.isOn());
    EXPECT_STREQ(monitor.events().newest(1).title, "LIMIT CLEAR");
}

TEST_F(DeviceMonitorTest, ManualCommandsAreRefusedWhileARuleOwnsTheRelay)
{
    configure("20", "", "on_alarm");
    EXPECT_FALSE(monitor.commandRelay(true, "WEB", 0));
    EXPECT_FALSE(relay.isOn());

    configure("20", "", "manual");
    EXPECT_TRUE(monitor.commandRelay(true, "WEB", 0));
    EXPECT_TRUE(relay.isOn());
    EXPECT_STREQ(monitor.events().newest(0).detail, "WEB");
}

TEST_F(DeviceMonitorTest, SensorFaultHoldsTheRelayAndIsLogged)
{
    configure("20", "", "on_alarm");
    monitor.evaluate(0, tank(10.0f), 0);
    ASSERT_TRUE(relay.isOn());
    monitor.evaluate(0, tank(0.0f, false), 1000);
    EXPECT_TRUE(relay.isOn());
    EXPECT_STREQ(monitor.events().newest(0).title, "SENSOR FAULT");
    monitor.evaluate(0, tank(10.0f), 2000);
    EXPECT_STREQ(monitor.events().newest(0).title, "SENSOR OK");
}

TEST_F(DeviceMonitorTest, DismissKeepsTheAlarmButHidesTheAlert)
{
    configure("", "90", "manual");
    monitor.evaluate(0, tank(95.0f), 0);
    ASSERT_TRUE(monitor.alertPending());
    monitor.dismissAlert();
    EXPECT_FALSE(monitor.alertPending());
    EXPECT_TRUE(monitor.limits(0).alarm());
}

TEST_F(DeviceMonitorTest, NetworkTransitionsAreLoggedOnce)
{
    configure("", "", "manual");
    monitor.updateNetwork(false, false, "", "", 0);
    EXPECT_EQ(monitor.events().size(), 0u);
    monitor.updateNetwork(true, false, "HOME -58DBM", "", 1000);
    monitor.updateNetwork(true, true, "", "10.0.0.2", 2000);
    monitor.updateNetwork(true, true, "", "10.0.0.2", 3000);
    ASSERT_EQ(monitor.events().size(), 2u);
    EXPECT_STREQ(monitor.events().newest(0).title, "MQTT ONLINE");
    EXPECT_STREQ(monitor.events().newest(1).title, "WIFI ONLINE");
}

TEST_F(DeviceMonitorTest, RuleIsIgnoredWithoutARelay)
{
    RelayOutput none;
    none.begin(&hal, -1);
    storage.saveParameter(Parameter::RELAY_MODE, String("on_alarm"));
    monitor.begin(&storage, &logger, &none);
    monitor.addSensor("analog_distance", &tankSettings);
    EXPECT_EQ(monitor.relayMode(), LimitMonitor::RelayMode::MANUAL);
}

TEST_F(DeviceMonitorTest, AlertSwitchKeepsTheValueButDisablesTheLimit)
{
    tankSettings.saveParameter(Parameter::LIMIT_LOW, String("20"));
    tankSettings.saveParameter(Parameter::LIMIT_LOW_ON, String("0"));
    tankSettings.saveParameter(Parameter::LIMIT_HIGH, String("95"));
    monitor.begin(&storage, &logger, &relay);   // high has no switch yet: on because a value is set
    monitor.addSensor("analog_distance", &tankSettings);
    EXPECT_FALSE(monitor.limits(0).hasLow());
    EXPECT_TRUE(monitor.limits(0).hasHigh());

    tankSettings.saveParameter(Parameter::LIMIT_LOW_ON, String("1"));
    tankSettings.saveParameter(Parameter::LIMIT_HIGH_ON, String("0"));
    monitor.loadLimits();
    EXPECT_FLOAT_EQ(monitor.limits(0).low(), 20.0f);
    EXPECT_FALSE(monitor.limits(0).hasHigh());
}

static ScreenModel radiation(float dose)
{
    ScreenModel m;
    m.title = "RAD";
    m.value = dose;
    m.unit = "uSv/h";
    m.decimals = 2;
    m.valid = true;
    m.sensorOk = true;
    return m;
}

TEST_F(DeviceMonitorTest, EachSensorHasItsOwnLimitsAndOnlyTheSourceDrivesTheRelay)
{
    configure("20", "", "on_alarm");
    radSettings.saveParameter(Parameter::LIMIT_HIGH, String("0.3"));
    storage.saveParameter(Parameter::RELAY_SOURCE, String("analog_distance"));
    monitor.addSensor("radiation_counter", &radSettings);
    EXPECT_EQ(monitor.relaySource(), 0);

    monitor.evaluate(1, radiation(0.5f), 1000);          // radiation alert: logged, relay untouched
    EXPECT_TRUE(monitor.limits(1).alarm());
    EXPECT_FALSE(relay.isOn());
    EXPECT_STREQ(monitor.events().newest(0).detail, "RAD 0.50>0.30");   // sensor named with two running
    EXPECT_EQ(monitor.pendingAlert(), 1);

    monitor.evaluate(0, tank(10.0f), 2000);              // tank alert: the relay follows it
    EXPECT_TRUE(relay.isOn());

    monitor.dismissAlert();                              // PAGE: the first pending one (the tank)
    EXPECT_EQ(monitor.pendingAlert(), 1);
    monitor.dismissAll();
    EXPECT_FALSE(monitor.alertPending());
}

TEST_F(DeviceMonitorTest, RelaySourceCanBeAnySensor)
{
    configure("", "", "on_alarm");
    radSettings.saveParameter(Parameter::LIMIT_HIGH, String("0.3"));
    storage.saveParameter(Parameter::RELAY_SOURCE, String("radiation_counter"));
    monitor.addSensor("radiation_counter", &radSettings);
    EXPECT_EQ(monitor.relaySource(), 1);
    monitor.evaluate(1, radiation(0.5f), 1000);
    EXPECT_TRUE(relay.isOn());
}
