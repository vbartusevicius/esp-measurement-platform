#include "WifiConnector.h"
#include "Logger.h"

WifiConnector::WifiConnector(Logger* logger, const String& chipId)
{
    this->logger = logger;
    this->appName = "ESP_" + chipId;

    WiFi.mode(WIFI_STA);
    WiFi.setHostname(this->appName.c_str());
}

void WifiConnector::run()
{
    wm.process();
}

bool WifiConnector::begin(bool forcePortal)
{
    wm.setConfigPortalBlocking(false);
    wm.setConfigPortalTimeout(300);

    if (forcePortal) {
        this->logger->info("Opening WiFi setup portal on request.");
        wm.startConfigPortal(this->appName.c_str());
        return false;
    }

    bool connected = wm.autoConnect(this->appName.c_str());

    if (connected) {
        this->logger->info("Connected to WiFi.");
    } else {
        this->logger->info("Serving WiFi configuration portal.");
    }

    return connected;
}

const char* WifiConnector::getAppName()
{
    return this->appName.c_str();
}

void WifiConnector::resetSettings()
{
    wm.resetSettings();
    WiFi.disconnect(true);
}
