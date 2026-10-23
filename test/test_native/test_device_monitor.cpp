#include <gtest/gtest.h>
#include <cstring>
#include "DeviceMonitor.h"
#include "HAL.h"
#include "Logger.h"
#include "Parameter.h"
#include "RelayOutput.h"
#include "Storage.h"

class DeviceMonitorTest : public ::testing::Test {
protected:
    HAL hal;
    Storage storage;
    Logger logger;
    RelayOutput relay;
    DeviceMonitor monitor;

    void SetUp() override {
        storage.begin();
        storage.reset();
        relay.begin(&hal, 19);
    }

    void configure(const char* low, const char* high, const char* mode) {
        storage.saveParameter(Parameter::LIMIT_LOW, String(low));
        storage.saveParameter(Parameter::LIMIT_HIGH, String(high));
        storage.saveParameter(Parameter::LIMIT_HYSTERESIS, String("5"));
        storage.saveParameter(Parameter::RELAY_MODE, String(mode));
        monitor.begin(&storage, &logger, &relay);
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
    EXPECT_FALSE(monitor.limits().hasLow());
    EXPECT_FALSE(monitor.limits().hasHigh());
    monitor.evaluate(tank(1.0f), 0);
    EXPECT_FALSE(monitor.alertPending());
}

TEST_F(DeviceMonitorTest, LimitRuleSwitchesTheRelayAndLogsEvents)
{
    configure("20", "95", "on_alarm");
    monitor.evaluate(tank(50.0f), 1000);
    EXPECT_FALSE(relay.isOn());

    monitor.evaluate(tank(18.0f), 2000);
    EXPECT_TRUE(relay.isOn());
    EXPECT_TRUE(monitor.alertPending());
    EXPECT_EQ(monitor.relayActivations(), 1u);
    EXPECT_STREQ(monitor.events().newest(0).title, "RELAY ON");
    EXPECT_STREQ(monitor.events().newest(1).title, "MIN LIMIT!");
    EXPECT_STREQ(monitor.events().newest(1).detail, "18%<20");

    monitor.evaluate(tank(26.0f), 3000);
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
    monitor.evaluate(tank(10.0f), 0);
    ASSERT_TRUE(relay.isOn());
    monitor.evaluate(tank(0.0f, false), 1000);
    EXPECT_TRUE(relay.isOn());
    EXPECT_STREQ(monitor.events().newest(0).title, "SENSOR FAULT");
    monitor.evaluate(tank(10.0f), 2000);
    EXPECT_STREQ(monitor.events().newest(0).title, "SENSOR OK");
}

TEST_F(DeviceMonitorTest, DismissKeepsTheAlarmButHidesTheAlert)
{
    configure("", "90", "manual");
    monitor.evaluate(tank(95.0f), 0);
    ASSERT_TRUE(monitor.alertPending());
    monitor.dismissAlert();
    EXPECT_FALSE(monitor.alertPending());
    EXPECT_TRUE(monitor.limits().alarm());
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
    EXPECT_EQ(monitor.limits().relayMode(), LimitMonitor::RelayMode::MANUAL);
}

TEST_F(DeviceMonitorTest, AlertSwitchKeepsTheValueButDisablesTheLimit)
{
    storage.saveParameter(Parameter::LIMIT_LOW, String("20"));
    storage.saveParameter(Parameter::LIMIT_LOW_ON, String("0"));
    storage.saveParameter(Parameter::LIMIT_HIGH, String("95"));
    monitor.begin(&storage, &logger, &relay);   // high has no switch yet: on because a value is set
    EXPECT_FALSE(monitor.limits().hasLow());
    EXPECT_TRUE(monitor.limits().hasHigh());

    storage.saveParameter(Parameter::LIMIT_LOW_ON, String("1"));
    storage.saveParameter(Parameter::LIMIT_HIGH_ON, String("0"));
    monitor.loadLimits();
    EXPECT_FLOAT_EQ(monitor.limits().low(), 20.0f);
    EXPECT_FALSE(monitor.limits().hasHigh());
}
