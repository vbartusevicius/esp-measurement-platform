#ifndef LED_CONTROLLER_H
#define LED_CONTROLLER_H

class HAL;

// Three SK6805 LEDs on the UI board: STATUS (heartbeat), NET (portal / WiFi /
// MQTT), SENS (flash per sample).
class LedController
{
    public:
        enum class NetState { OFFLINE, PORTAL, WIFI, MQTT };

        void begin(HAL* hal);
        void run();
        void click();
        void setNetworkState(NetState state);

        static NetState netStateFor(bool wifiConnected, bool mqttConnected, bool portalActive);

    private:
        HAL* hal = nullptr;
        bool pendingClick = false;
        bool sensOn = false;
        unsigned long sensFlashAt = 0;
        unsigned long lastRefresh = 0;
        NetState netState = NetState::OFFLINE;
};

#endif
