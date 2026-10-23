#include <gtest/gtest.h>
#include "AnalogVoltagePlugin.h"
#include "HAL.h"
#include "Storage.h"
#include "Logger.h"

class VoltageHal : public HAL {
public:
    int millivolts = 0;
    void pinMode(uint8_t, uint8_t) override {}
    int analogReadMilliVolts(uint8_t) override { return millivolts; }
    unsigned long millis() override { return FakeHAL::currentMillis; }
};

class AnalogVoltagePluginTest : public ::testing::Test {
protected:
    VoltageHal hal;
    Storage storage;
    Logger logger;
    AnalogVoltagePlugin plugin;

    void SetUp() override {
        storage.begin();
        storage.reset();
        FakeHAL::currentMillis = 0;
    }
};

TEST_F(AnalogVoltagePluginTest, DefaultsMapAHalfScalePressureTransducer)
{
    // Native builds use the NodeMCU divider (1:1): 2.5 V = mid-scale of 0.5-4.5 V / 0-10 bar
    hal.millivolts = 2500;
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();

    ScreenModel screen;
    ASSERT_TRUE(plugin.getScreen(screen));
    EXPECT_STREQ(screen.title, "PRES");
    EXPECT_STREQ(screen.unit, "bar");
    EXPECT_NEAR(screen.value, 5.0f, 0.01f);
    EXPECT_TRUE(screen.valid);
    EXPECT_STREQ(screen.signal.c_str(), "2.50V");
    EXPECT_FLOAT_EQ(screen.scaleMax, 10.0f);
}

TEST_F(AnalogVoltagePluginTest, OpenWireIsAFault)
{
    hal.millivolts = 10;
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();

    ScreenModel screen;
    plugin.getScreen(screen);
    EXPECT_FALSE(screen.valid);
    EXPECT_FALSE(screen.sensorOk);
}

TEST_F(AnalogVoltagePluginTest, CustomRangeUnitAndTitle)
{
    storage.saveParameter(AnalogVoltagePlugin::PARAM_VOLTAGE_MIN, String("0"));
    storage.saveParameter(AnalogVoltagePlugin::PARAM_VOLTAGE_MAX, String("3"));
    storage.saveParameter(AnalogVoltagePlugin::PARAM_VALUE_MAX, String("150"));
    storage.saveParameter(AnalogVoltagePlugin::PARAM_VALUE_UNIT, String("psi"));
    storage.saveParameter(AnalogVoltagePlugin::PARAM_TITLE, String("PUMPX"));
    hal.millivolts = 1000;
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();

    ScreenModel screen;
    plugin.getScreen(screen);
    EXPECT_STREQ(screen.title, "PUMP");
    EXPECT_STREQ(screen.unit, "psi");
    EXPECT_NEAR(screen.value, 50.0f, 0.01f);
}

TEST_F(AnalogVoltagePluginTest, KindFollowsTheUnit)
{
    hal.millivolts = 2500;
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();
    ScreenModel pressure;
    plugin.getScreen(pressure);
    EXPECT_STREQ(pressure.kind, "pressure");

    storage.saveParameter(AnalogVoltagePlugin::PARAM_VALUE_UNIT, String("%RH"));
    plugin.setup(&hal, &storage, &logger, nullptr);
    plugin.loop();
    ScreenModel generic;
    plugin.getScreen(generic);
    EXPECT_STREQ(generic.kind, "voltage");
}
