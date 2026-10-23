#include <gtest/gtest.h>
#include "ButtonLadder.h"

using Button = ButtonLadder::Button;
using Event = ButtonLadder::Event;

static constexpr int IDLE_MV = 3300;
static constexpr int RESET_MV = 2200;
static constexpr int PAGE_MV = 1650;
static constexpr int BOTH_MV = 1320;

TEST(ButtonLadder, ClassifiesNominalLadderVoltagesWithAdcTolerance)
{
    for (int err : {-120, 0, 120}) {
        EXPECT_EQ(ButtonLadder::classify(IDLE_MV + err), Button::NONE);
        EXPECT_EQ(ButtonLadder::classify(RESET_MV + err), Button::RESET);
        EXPECT_EQ(ButtonLadder::classify(PAGE_MV + err), Button::PAGE);
        EXPECT_EQ(ButtonLadder::classify(BOTH_MV + err), Button::BOTH);
    }
}

TEST(ButtonLadder, ShortedLadderIsNotAPress)
{
    EXPECT_EQ(ButtonLadder::classify(0), Button::NONE);
}

TEST(ButtonLadder, PagePressNeedsTwoMatchingSamples)
{
    ButtonLadder ladder;
    EXPECT_EQ(ladder.update(IDLE_MV, 0), Event::NONE);
    EXPECT_EQ(ladder.update(IDLE_MV, 20), Event::NONE);
    EXPECT_EQ(ladder.update(PAGE_MV, 40), Event::NONE);
    EXPECT_EQ(ladder.update(PAGE_MV, 60), Event::PAGE_PRESSED);
    EXPECT_EQ(ladder.update(PAGE_MV, 80), Event::NONE);
}

TEST(ButtonLadder, SingleGlitchSampleIsIgnored)
{
    ButtonLadder ladder;
    ladder.update(IDLE_MV, 0);
    ladder.update(IDLE_MV, 20);
    EXPECT_EQ(ladder.update(PAGE_MV, 40), Event::NONE);
    EXPECT_EQ(ladder.update(IDLE_MV, 60), Event::NONE);
    EXPECT_EQ(ladder.update(IDLE_MV, 80), Event::NONE);
}

TEST(ButtonLadder, ResetTapReportsOnRelease)
{
    ButtonLadder ladder;
    ladder.update(RESET_MV, 0);
    EXPECT_EQ(ladder.update(RESET_MV, 20), Event::NONE);
    ladder.update(IDLE_MV, 500);
    EXPECT_EQ(ladder.update(IDLE_MV, 520), Event::RESET_TAPPED);
}

TEST(ButtonLadder, ResetHoldReportsOnceAndSuppressesTheTap)
{
    ButtonLadder ladder;
    ladder.update(RESET_MV, 0);
    ladder.update(RESET_MV, 20);
    EXPECT_EQ(ladder.update(RESET_MV, 4000), Event::NONE);
    EXPECT_EQ(ladder.update(RESET_MV, 5020), Event::RESET_HELD);
    EXPECT_EQ(ladder.update(RESET_MV, 6000), Event::NONE);
    ladder.update(IDLE_MV, 6020);
    EXPECT_EQ(ladder.update(IDLE_MV, 6040), Event::NONE);
}

TEST(ButtonLadder, PressingBothButtonsDoesNothing)
{
    ButtonLadder ladder;
    ladder.update(BOTH_MV, 0);
    EXPECT_EQ(ladder.update(BOTH_MV, 20), Event::NONE);
    ladder.update(IDLE_MV, 40);
    EXPECT_EQ(ladder.update(IDLE_MV, 60), Event::NONE);
}
