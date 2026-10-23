#ifndef FIRMWARE_IMAGE_H
#define FIRMWARE_IMAGE_H

#include <stddef.h>
#include <stdint.h>

// Checks the start of an uploaded file before it is written to the OTA slot:
// it must be an ESP32-C6 application image (firmware.bin), not the full USB
// image (bootloader + partitions + app from offset 0), whose first bytes are
// the bootloader's and would brick the slot.
namespace FirmwareImage
{
    constexpr size_t HEADER_BYTES = 0x24;

    enum class Kind { APP, FULL_FLASH_IMAGE, WRONG_CHIP, NOT_FIRMWARE };

    inline Kind classify(const uint8_t* data, size_t len)
    {
        constexpr uint8_t IMAGE_MAGIC = 0xE9;           // esp_image_header_t.magic
        constexpr uint16_t CHIP_ID_ESP32C6 = 0x000D;    // esp_image_header_t.chip_id
        constexpr uint32_t APP_DESC_MAGIC = 0xABCD5432; // esp_app_desc_t.magic_word, right after the first segment header
        if (len < HEADER_BYTES || data[0] != IMAGE_MAGIC) return Kind::NOT_FIRMWARE;
        if ((data[12] | (data[13] << 8)) != CHIP_ID_ESP32C6) return Kind::WRONG_CHIP;
        const uint32_t descMagic = data[0x20] | (data[0x21] << 8) | (data[0x22] << 16) | ((uint32_t)data[0x23] << 24);
        return descMagic == APP_DESC_MAGIC ? Kind::APP : Kind::FULL_FLASH_IMAGE;
    }

    inline const char* problem(Kind kind)
    {
        switch (kind) {
            case Kind::APP: return nullptr;
            case Kind::FULL_FLASH_IMAGE: return "This is firmware-full-usb.bin (USB only); upload firmware.bin instead";
            case Kind::WRONG_CHIP: return "Firmware is for a different ESP32 chip";
            default: return "Not an ESP32 firmware image";
        }
    }
}

#endif
