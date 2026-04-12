#include "Display.h"

Display::Display()
    : u8g2(U8G2_R0, U8X8_PIN_NONE, D6, D5)
{
    u8g2.begin();
    this->displayWidth = u8g2.getDisplayWidth();
    this->displayHeight = u8g2.getDisplayHeight();
}

void Display::run(IPlugin* plugin, int page)
{
    u8g2.firstPage();
    do {
        plugin->renderDisplayPage(u8g2, page, displayWidth, displayHeight);
    } while (u8g2.nextPage());
}

void Display::configWizardFirstStep(const char* appName)
{
    this->configWizard("Welcome! (1/2)", "Connect to AP:", appName);
}

void Display::configWizardSecondStep(const char* ipAddress)
{
    this->configWizard("Welcome! (2/2)", "Configure device on:", ipAddress);
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

void Display::renderNetwork(const char* ssid, const char* ip, int rssi, int startY)
{
    unsigned int signalGlyph = 57887;
    if (rssi >= -95) signalGlyph = 57888;
    if (rssi >= -85) signalGlyph = 57889;
    if (rssi >= -75) signalGlyph = 57890;
    if (rssi == 0) signalGlyph = 57887;

    u8g2.setFont(u8g2_font_siji_t_6x10);
    u8g2.drawGlyph(displayWidth - 10, startY + 14, signalGlyph);

    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(0, startY + 7, (String("SSID: ") + ssid).c_str());
    u8g2.drawStr(0, startY + 15, (String("IP: ") + ip).c_str());
    u8g2.drawHLine(0, startY + 16, displayWidth);
}

void Display::renderBoolStatus(const char* name, bool status, int startY)
{
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(0, startY + 8, (String(name) + ":").c_str());

    const char* glyph = status ? "[+]" : "[ ]";
    int glyphWidth = u8g2.getStrWidth(glyph);
    u8g2.drawStr((displayWidth / 2) - glyphWidth, startY + 8, glyph);
}

void Display::renderUptime(const char* uptime, int startY)
{
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(0, startY + 8, "Uptime:");
    u8g2.drawStr(49, startY + 8, uptime);
}
