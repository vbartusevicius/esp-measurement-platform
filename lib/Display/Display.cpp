#include "Display.h"
#include "Board.h"
#include "PlatformWiFi.h"
#include "PortraitPages.h"
#include "TimeHelper.h"

#if defined(BOARD_XIAO_ESP32C6)
// RES# has its own RC power-on reset on the UI board. If the first prototype
// shows the image upside down, set DISPLAY_ROTATION to 3 (U8G2_R3).
static constexpr int DISPLAY_ROTATION = 1;
Display::Display()
    : u8g2(DISPLAY_ROTATION == 3 ? U8G2_R3 : U8G2_R1, U8X8_PIN_NONE, Board::I2C_SCL_PIN, Board::I2C_SDA_PIN)
{
}
#else
Display::Display()
    : u8g2(U8G2_R0, U8X8_PIN_NONE, D6, D5)
{
}
#endif

void Display::begin()
{
    u8g2.begin();
#if defined(BOARD_XIAO_ESP32C6)
    u8g2.setContrast(0x7F);
#endif
    this->displayWidth = u8g2.getDisplayWidth();
    this->displayHeight = u8g2.getDisplayHeight();
}

void Display::run(const DisplayFrame& frame)
{
    if (this->isPortrait()) {
        u8g2.clearBuffer();
        PortraitPages(u8g2).draw(frame, this->page);
        u8g2.sendBuffer();
        return;
    }
    u8g2.firstPage();
    do {
        int usedY = frame.legacy ? frame.legacy->renderDisplayPage(u8g2, frame.legacyPage, displayWidth, displayHeight) : 0;
        if (usedY < displayHeight) {
            renderSystemInfo(usedY, frame.mqttConnected);
        }
    } while (u8g2.nextPage());
}

void Display::renderSystemInfo(int startY, bool mqttConnected)
{
    int cursorY = startY;

    // Network
    int rssi = WiFi.RSSI();
    unsigned int glyph = 57887;
    if (rssi >= -95) glyph = 57888;
    if (rssi >= -85) glyph = 57889;
    if (rssi >= -75) glyph = 57890;
    if (rssi == 0) glyph = 57887;

    u8g2.setFont(u8g2_font_siji_t_6x10);
    u8g2.drawGlyph(displayWidth - 10, cursorY + 14, glyph);

    u8g2.setFont(u8g2_font_5x7_tr);
    const char* mqttGlyph = mqttConnected ? "[+]" : "[ ]";
    char uptimeBuf[32];
    TimeHelper::getUptime(uptimeBuf);

    u8g2.drawStr(0, cursorY + 7, ("SSID: " + WiFi.SSID()).c_str());
    u8g2.drawStr(0, cursorY + 15, ("IP: " + WiFi.localIP().toString()).c_str());
    u8g2.drawHLine(0, cursorY + 16, displayWidth);
    cursorY += 17;

    u8g2.drawStr(0, cursorY + 8, "MQTT:");
    int gw = u8g2.getStrWidth(mqttGlyph);
    u8g2.drawStr((displayWidth / 2) - gw, cursorY + 8, mqttGlyph);
    cursorY += 8;

    u8g2.drawStr(0, cursorY + 8, "Uptime:");
    u8g2.drawStr(49, cursorY + 8, uptimeBuf);
}

void Display::configWizardFirstStep(const char* appName)
{
    if (this->isPortrait()) {
        u8g2.clearBuffer();
        PortraitPages(u8g2).drawPortalModal(appName, "192.168.4.1");
        u8g2.sendBuffer();
        return;
    }
    this->configWizard("Welcome! (1/2)", "Connect to AP:", appName);
}

void Display::configWizard(const char* header, const char* helpLineOne, const char* helpLineTwo)
{
    int cursor = 0;

    u8g2.firstPage();
    do {
        u8g2.setFont(u8g2_font_6x12_mf);
        int headerHeight = 16;
        cursor = (headerHeight + u8g2.getAscent()) / 2;
        u8g2.drawStr(1, cursor, header);

        u8g2.setFont(u8g2_font_5x7_tr);
        int lineHeight = u8g2.getAscent() - u8g2.getDescent();
        cursor += 6 + lineHeight;

        u8g2.drawStr(0, cursor, helpLineOne);
        cursor += lineHeight + 2;
        u8g2.drawStr(0, cursor, helpLineTwo);
    } while (u8g2.nextPage());
}
