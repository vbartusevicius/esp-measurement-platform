#ifndef WIFI_CONNECTOR_H
#define WIFI_CONNECTOR_H

#include <WiFiManager.h>
#include "Logger.h"

class WifiConnector
{
    private:
        WiFiManager wm;
        Logger* logger;
        String appName;

    public:
        WifiConnector(Logger* logger, const String& chipId);
        void run();
        // forcePortal: skip the saved network and open the setup portal (RST/WIFI 5 s hold).
        bool begin(bool forcePortal = false);
        bool isPortalActive() { return wm.getConfigPortalActive(); }
        void resetSettings();
        const char* getAppName();
};

#endif
