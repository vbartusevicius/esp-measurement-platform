#include <gtest/gtest.h>
#include "HAL.h"
#include "RelayOutput.h"

TEST(RelayOutput, ParsesHomeAssistantPayloads)
{
    bool on = false;
    EXPECT_TRUE(RelayOutput::parseCommand("ON", on));
    EXPECT_TRUE(on);
    EXPECT_TRUE(RelayOutput::parseCommand("off", on));
    EXPECT_FALSE(on);
    EXPECT_TRUE(RelayOutput::parseCommand(" true\n", on));
    EXPECT_TRUE(on);
    EXPECT_TRUE(RelayOutput::parseCommand("0", on));
    EXPECT_FALSE(on);
}

TEST(RelayOutput, RejectsUnknownPayloadsWithoutChangingState)
{
    bool on = true;
    EXPECT_FALSE(RelayOutput::parseCommand("toggle", on));
    EXPECT_FALSE(RelayOutput::parseCommand("", on));
    EXPECT_FALSE(RelayOutput::parseCommand(nullptr, on));
    EXPECT_TRUE(on);
}

TEST(RelayOutput, StartsOffAndIgnoresCommandsWithoutAPin)
{
    HAL hal;
    RelayOutput none;
    none.begin(&hal, -1);
    none.set(true);
    EXPECT_FALSE(none.available());
    EXPECT_FALSE(none.isOn());

    RelayOutput relay;
    relay.begin(&hal, 19);
    EXPECT_TRUE(relay.available());
    EXPECT_FALSE(relay.isOn());
    relay.set(true);
    EXPECT_TRUE(relay.isOn());
}
