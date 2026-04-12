#include "WifiConnector.h"

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

bool WifiConnector::begin()
{
    wm.setConfigPortalBlocking(false);
    wm.setConfigPortalTimeout(300);
    wm.setSaveConfigCallback([] {
        delay(1000);
        ESP.restart();
    });
    wm.setConfigPortalTimeoutCallback([] {
        delay(1000);
        ESP.restart();
    });

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
