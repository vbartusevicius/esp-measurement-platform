#include <gtest/gtest.h>
#include "IMqttContributor.h"

TEST(HaDiscoveryContext, FallsBackToPluginNameWhenUnset)
{
    HaDiscoveryContext ctx;
    EXPECT_STREQ(ctx.nameOr("ESP Analog Distance Meter"), "ESP Analog Distance Meter");
}

TEST(HaDiscoveryContext, FallsBackWhenExplicitlyEmpty)
{
    HaDiscoveryContext ctx;
    ctx.deviceName = "";
    EXPECT_STREQ(ctx.nameOr("ESP Radiation Counter"), "ESP Radiation Counter");
}

TEST(HaDiscoveryContext, ConfiguredNameWins)
{
    HaDiscoveryContext ctx;
    ctx.deviceName = "Rainwater Tank";
    EXPECT_STREQ(ctx.nameOr("ESP Analog Distance Meter"), "Rainwater Tank");
}
