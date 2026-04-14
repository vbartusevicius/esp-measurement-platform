#include <gtest/gtest.h>
#include "Logger.h"

class LoggerTest : public ::testing::Test {
protected:
    Logger logger;
};

TEST_F(LoggerTest, InfoAddsToBuffer)
{
    logger.info("test message");
    EXPECT_EQ(logger.size(), 1u);
}

TEST_F(LoggerTest, MultipleLogLevels)
{
    logger.info("info");
    logger.warning("warning");
    logger.error("error");
    logger.debug("debug");
    EXPECT_EQ(logger.size(), 4u);
}

TEST_F(LoggerTest, BufferContainsLogLevel)
{
    logger.info("hello");
    const auto& buf = logger.getBuffer();
    ASSERT_EQ(buf.size(), 1u);
    // Entry should contain [INFO] and the message
    std::string entry(buf[0].c_str());
    EXPECT_NE(entry.find("[INFO]"), std::string::npos);
    EXPECT_NE(entry.find("hello"), std::string::npos);
}

TEST_F(LoggerTest, WarningContainsLevel)
{
    logger.warning("warn msg");
    const auto& buf = logger.getBuffer();
    std::string entry(buf[0].c_str());
    EXPECT_NE(entry.find("[WARN]"), std::string::npos);
}

TEST_F(LoggerTest, ErrorContainsLevel)
{
    logger.error("err msg");
    const auto& buf = logger.getBuffer();
    std::string entry(buf[0].c_str());
    EXPECT_NE(entry.find("[ERROR]"), std::string::npos);
}

TEST_F(LoggerTest, BufferLimitedToMaxEntries)
{
    // MAX_ENTRIES is 50
    for (int i = 0; i < 60; i++) {
        logger.info("msg " + String(i));
    }
    EXPECT_EQ(logger.size(), 50u);
}

TEST_F(LoggerTest, OldestEntriesDroppedFirst)
{
    for (int i = 0; i < 55; i++) {
        logger.info("msg " + String(i));
    }
    // First 5 entries should have been dropped
    const auto& buf = logger.getBuffer();
    std::string first(buf[0].c_str());
    EXPECT_NE(first.find("msg 5"), std::string::npos);
}
