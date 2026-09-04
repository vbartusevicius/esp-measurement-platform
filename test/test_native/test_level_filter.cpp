#include <gtest/gtest.h>
#include "LevelFilter.h"

class LevelFilterTest : public ::testing::Test {
protected:
    LevelFilter filter;
    unsigned long now = 0;
    void SetUp() override { filter.reset(); now = 0; }

    float feed(float value, int n = 1, unsigned long stepMs = 10000) {
        float out = 0;
        for (int i = 0; i < n; i++) {
            out = filter.process(value, 10, 0.10f, 5, 0.0f, now);
            now += stepMs;
        }
        return out;
    }
};

TEST_F(LevelFilterTest, InvalidReadingsSkipped)
{
    feed(1.5f, 5);
    float before = filter.getFiltered();
    EXPECT_GT(before, 1.0f);
    feed(0.0f, 5);  // sensor timeouts
    EXPECT_FLOAT_EQ(filter.getFiltered(), before);
}

TEST_F(LevelFilterTest, SpikesRejectedByMedian)
{
    feed(1.5f, 10);
    filter.process(5.0f, 10, 0.10f, 5, 0.0f, now); now += 10000;  // spike
    filter.process(1.5f, 10, 0.10f, 5, 0.0f, now);
    EXPECT_NEAR(filter.getFiltered(), 1.5f, 0.05f);
}

TEST_F(LevelFilterTest, FirstSampleInitializesOutput)
{
    float out = filter.process(1.5f, 10, 0.10f, 5, 0.0f, now);
    EXPECT_NEAR(out, 1.5f, 0.001f);
    EXPECT_TRUE(filter.hasValue());
}

TEST_F(LevelFilterTest, SmallChangesPassThrough)
{
    feed(1.5f, 10);
    // change of 5cm is within the 10cm deadband and should move the output
    float out = feed(1.55f, 10);
    EXPECT_GT(out, 1.5f);
    EXPECT_LE(out, 1.55f);
}

TEST_F(LevelFilterTest, BigStepNotImmediate)
{
    feed(1.5f, 10);
    // one big reading - held (pending confirmation)
    float out = filter.process(0.5f, 10, 0.10f, 5, 0.0f, now);
    EXPECT_NEAR(out, 1.5f, 0.01f);
}

TEST_F(LevelFilterTest, PersistentStepAccepted)
{
    feed(2.0f, 10);
    // tank dumped to 0.5m and stays there: median needs half the window to
    // flip, then snap-after count runs -> eventually the new level wins
    float out = feed(0.5f, 20);
    EXPECT_NEAR(out, 0.5f, 0.2f);
}

TEST_F(LevelFilterTest, LimboImpossible)
{
    // Perf tank dump, device was rejecting new values - must recover
    feed(2.0f, 10);
    for (int i = 0; i < 100; i++) {
        filter.process(0.3f, 10, 0.10f, 5, 0.0f, now);
        now += 10000;
    }
    EXPECT_NEAR(filter.getFiltered(), 0.3f, 0.05f);
}

TEST_F(LevelFilterTest, SlewLimiterCapsChangeRate)
{
    LevelFilter f;
    unsigned long t = 0;
    float out = f.process(1.0f, 10, 0.0f, 5, 10.0f, t);   // 0 m/min -> deadband 0: step branch!
    out = f.process(1.0f, 10, 0.0f, 5, 10.0f, t += 60000);
    EXPECT_NEAR(out, 1.0f, 0.001f);
}

TEST_F(LevelFilterTest, SlewLimiterWithinDeadband)
{
    // deadband 1m so changes pass through; slew 10 cm/min, 1 min per sample
    unsigned long t = 0;
    filter.process(1.0f, 10, 1.0f, 5, 10.0f, t);
    for (int i = 0; i < 10; i++) {
        filter.process(1.0f, 10, 1.0f, 5, 10.0f, t += 60000);
    }
    // median half-flips after 6 samples of 1.0 at window 10? window full of 1.3 now
    for (int i = 0; i < 10; i++) {
        filter.process(1.3f, 10, 1.0f, 5, 10.0f, t += 60000);
    }
    // Each minute the ceiling adds at most 0.1 m
    EXPECT_LE(filter.getFiltered(), 1.0f + 0.1f * 10);
    EXPECT_GT(filter.getFiltered(), 1.0f);
}

TEST_F(LevelFilterTest, ResetClearsState)
{
    feed(1.5f, 5);
    filter.reset();
    EXPECT_FALSE(filter.hasValue());
    EXPECT_FLOAT_EQ(filter.getFiltered(), 0.0f);
}
