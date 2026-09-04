#include <gtest/gtest.h>
#include "Storage.h"

class StorageTest : public ::testing::Test {
protected:
    Storage storage;
    void SetUp() override {
        storage.begin();
        storage.reset();
    }
};

TEST_F(StorageTest, MissingParameterReturnsDefault)
{
    EXPECT_STREQ(storage.getParameter("nope", "fallback").c_str(), "fallback");
    EXPECT_FALSE(storage.hasParameter("nope"));
}

TEST_F(StorageTest, SaveAndRead)
{
    storage.saveParameter("mqtt_host", String("192.168.1.10"));
    EXPECT_STREQ(storage.getParameter("mqtt_host").c_str(), "192.168.1.10");
    EXPECT_TRUE(storage.hasParameter("mqtt_host"));
}

TEST_F(StorageTest, OverwriteExistingKey)
{
    storage.saveParameter("mqtt_port", String("1883"));
    storage.saveParameter("mqtt_port", String("8883"));
    EXPECT_STREQ(storage.getParameter("mqtt_port").c_str(), "8883");
}

TEST_F(StorageTest, MultipleKeysIndependent)
{
    storage.saveParameter("a", String("1"));
    storage.saveParameter("b", String("2"));
    storage.saveParameter("c", String("3"));
    EXPECT_STREQ(storage.getParameter("a").c_str(), "1");
    EXPECT_STREQ(storage.getParameter("b").c_str(), "2");
    EXPECT_STREQ(storage.getParameter("c").c_str(), "3");
}

TEST_F(StorageTest, SurvivesReload)
{
    storage.saveParameter("mqtt_device", String("tank_sensor"));
    storage.saveParameter("total_volume", String("5000"));

    // Simulates a reboot: a fresh instance reads the persisted sector
    Storage reloaded;
    reloaded.begin();
    EXPECT_STREQ(reloaded.getParameter("mqtt_device").c_str(), "tank_sensor");
    EXPECT_STREQ(reloaded.getParameter("total_volume").c_str(), "5000");
}

TEST_F(StorageTest, ResetClearsEverything)
{
    storage.saveParameter("mqtt_host", String("host"));
    storage.reset();
    EXPECT_FALSE(storage.hasParameter("mqtt_host"));

    Storage reloaded;
    reloaded.begin();
    EXPECT_FALSE(reloaded.hasParameter("mqtt_host"));
}

TEST_F(StorageTest, EmptyValuePreserved)
{
    storage.saveParameter("mqtt_user", String(""));
    EXPECT_TRUE(storage.hasParameter("mqtt_user"));
    EXPECT_STREQ(storage.getParameter("mqtt_user", "default").c_str(), "");
}

TEST_F(StorageTest, LongValueRoundTrips)
{
    String topic = "some_quite_long_device_name/stat/ultrasonic_distance_meter";
    storage.saveParameter("mqtt_topic", topic);

    Storage reloaded;
    reloaded.begin();
    EXPECT_STREQ(reloaded.getParameter("mqtt_topic").c_str(), topic.c_str());
}

TEST_F(StorageTest, FullParameterSetFitsInSector)
{
    // The real firmware persists ~21 parameters; make sure a realistic set
    // round-trips rather than overflowing the sector.
    const char* keys[] = {
        "active_plugin", "mqtt_host", "mqtt_port", "mqtt_user", "mqtt_pass",
        "mqtt_device", "mqtt_topic", "update_interval_min", "distance_empty",
        "distance_full", "sensor_range", "avg_sample_count", "sampling_interval",
        "total_volume", "level_deadband_cm", "step_confirm_samples",
        "max_change_cm_min", "tube_conversion_factor", "display_graph_resolution",
        "tube_dead_time_us", "alert_dose_usv_h"
    };
    for (auto& key : keys) {
        storage.saveParameter(key, String("some_reasonable_value_1234"));
    }

    Storage reloaded;
    reloaded.begin();
    for (auto& key : keys) {
        EXPECT_TRUE(reloaded.hasParameter(key)) << "missing " << key;
        EXPECT_STREQ(reloaded.getParameter(key).c_str(), "some_reasonable_value_1234");
    }
}
