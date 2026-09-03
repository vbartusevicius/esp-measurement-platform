#include <gtest/gtest.h>
#include "DailyUsageTracker.h"

static constexpr unsigned long HOUR = 3600000UL;

class DailyUsageTrackerTest : public ::testing::Test {
protected:
    DailyUsageTracker tracker;
    void SetUp() override { tracker.reset(); }
};

TEST_F(DailyUsageTrackerTest, NoUsageAfterFirstSample)
{
    tracker.update(1000.0f, 0);
    EXPECT_FLOAT_EQ(tracker.getUsageLiters(), 0.0f);
}

TEST_F(DailyUsageTrackerTest, AccumulatesDrops)
{
    tracker.update(1000.0f, 0);
    tracker.update(800.0f, 10000);   // -200 L
    tracker.update(700.0f, 20000);   // -100 L
    EXPECT_FLOAT_EQ(tracker.getUsageLiters(), 300.0f);
}

TEST_F(DailyUsageTrackerTest, IgnoresRefill)
{
    tracker.update(500.0f, 0);
    tracker.update(900.0f, 10000);   // refill, not usage
    tracker.update(800.0f, 20000);   // -100 L
    EXPECT_FLOAT_EQ(tracker.getUsageLiters(), 100.0f);
}

TEST_F(DailyUsageTrackerTest, BucketsAcrossHours)
{
    tracker.update(1000.0f, 0);
    tracker.update(900.0f, HOUR);        // -100 L in hour 1
    tracker.update(800.0f, 2 * HOUR);    // -100 L in hour 2
    EXPECT_FLOAT_EQ(tracker.getUsageLiters(), 200.0f);
}

TEST_F(DailyUsageTrackerTest, OldBucketsExpireAfter24h)
{
    tracker.update(1000.0f, 0);
    tracker.update(500.0f, 1000);         // -500 L in hour 0
    // 25 hours later, hour 0 data has expired
    tracker.update(400.0f, 25 * HOUR);   // -100 L in hour 25 (== bucket 1)
    float usage = tracker.getUsageLiters();
    EXPECT_FLOAT_EQ(usage, 100.0f);
}

TEST_F(DailyUsageTrackerTest, SameBucketIndexNewHourResetsBucket)
{
    tracker.update(1000.0f, HOUR);        // hour 1
    tracker.update(900.0f, HOUR + 1000);  // -100 L in hour 1
    tracker.update(800.0f, 25 * HOUR);    // hour 25 % 24 == 1 -> bucket reset, -100 L
    EXPECT_FLOAT_EQ(tracker.getUsageLiters(), 100.0f);
}

TEST_F(DailyUsageTrackerTest, ResetClearsState)
{
    tracker.update(1000.0f, 0);
    tracker.update(800.0f, 10000);
    EXPECT_GT(tracker.getUsageLiters(), 0.0f);
    tracker.reset();
    EXPECT_FLOAT_EQ(tracker.getUsageLiters(), 0.0f);
    tracker.update(1000.0f, 0);
    EXPECT_FLOAT_EQ(tracker.getUsageLiters(), 0.0f);
}
