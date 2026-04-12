#ifndef DISPLAY_H
#define DISPLAY_H

#include <Arduino.h>
#include <U8g2lib.h>
#include "IPlugin.h"

class Display
{
    private:
        U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2;
        int displayWidth;
        int displayHeight;

    public:
        Display();
        void run(IPlugin* plugin, int page);
        void configWizardFirstStep(const char* appName);
        void configWizardSecondStep(const char* ipAddress);

        void renderNetwork(const char* ssid, const char* ip, int rssi, int startY);
        void renderBoolStatus(const char* name, bool status, int startY);
        void renderUptime(const char* uptime, int startY);

    private:
        void configWizard(const char* header, const char* helpLineOne, const char* helpLineTwo);
};

#endif
