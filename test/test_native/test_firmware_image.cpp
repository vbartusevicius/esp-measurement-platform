#include <gtest/gtest.h>
#include <vector>
#include "FirmwareImage.h"

namespace
{
    // First 0x24 bytes as built by pioarduino 55.03.311 for xiao_c6 (image header + first segment header + 4 bytes)
    std::vector<uint8_t> image(uint8_t magic, uint16_t chip, uint32_t descMagic)
    {
        std::vector<uint8_t> b(FirmwareImage::HEADER_BYTES, 0);
        b[0] = magic;
        b[12] = chip & 0xFF;
        b[13] = chip >> 8;
        for (int i = 0; i < 4; i++) b[0x20 + i] = (descMagic >> (8 * i)) & 0xFF;
        return b;
    }
}

TEST(FirmwareImage, AcceptsAnEsp32C6AppImage)
{
    auto b = image(0xE9, 0x000D, 0xABCD5432);
    EXPECT_EQ(FirmwareImage::classify(b.data(), b.size()), FirmwareImage::Kind::APP);
    EXPECT_EQ(FirmwareImage::problem(FirmwareImage::Kind::APP), nullptr);
}

TEST(FirmwareImage, RejectsTheFullUsbImage)
{
    auto b = image(0xE9, 0x000D, 0x00000050);   // bootloader at offset 0
    EXPECT_EQ(FirmwareImage::classify(b.data(), b.size()), FirmwareImage::Kind::FULL_FLASH_IMAGE);
}

TEST(FirmwareImage, RejectsAnotherChip)
{
    auto b = image(0xE9, 0x0000, 0xABCD5432);   // classic ESP32
    EXPECT_EQ(FirmwareImage::classify(b.data(), b.size()), FirmwareImage::Kind::WRONG_CHIP);
}

TEST(FirmwareImage, RejectsOtherFilesAndShortChunks)
{
    auto b = image(0x7F, 0x000D, 0xABCD5432);
    EXPECT_EQ(FirmwareImage::classify(b.data(), b.size()), FirmwareImage::Kind::NOT_FIRMWARE);
    auto app = image(0xE9, 0x000D, 0xABCD5432);
    EXPECT_EQ(FirmwareImage::classify(app.data(), 0x10), FirmwareImage::Kind::NOT_FIRMWARE);
}
