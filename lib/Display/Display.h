#ifndef DISPLAY_H
#define DISPLAY_H

#include <Arduino.h>
#include <U8g2lib.h>
#include "IDisplayContributor.h"

class Display
{
    private:
        U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2;
        int displayWidth;
        int displayHeight;

    public:
        Display();
        void begin();
        void run(IDisplayContributor* plugin, int page, bool mqttConnected);
        void configWizardFirstStep(const char* appName);
        void configWizardSecondStep(const char* ipAddress);

    private:
        void configWizard(const char* header, const char* helpLineOne, const char* helpLineTwo);
        void renderSystemInfo(int startY, bool mqttConnected);
};

#endif
