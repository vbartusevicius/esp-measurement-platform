#ifndef LED_CONTROLLER_H
#define LED_CONTROLLER_H

class HAL;

// NodeMCU: built-in LED flashes on every sample. v1 board: three SK6805
// LEDs - STATUS (heartbeat), NET (portal / WiFi / MQTT), SENS (sample flash).
class LedController
{
    public:
        enum class NetState { OFFLINE, PORTAL, WIFI, MQTT };

    private:
        HAL* hal;
        bool lastState;
        unsigned long lastBlink;
        unsigned long blinkDuration;
        bool pendingClick;
        NetState netState;
        unsigned long lastRefresh;

        void refreshRgb(unsigned long now);

    public:
        LedController();
        void begin(HAL* hal);
        void run();
        void click();
        void setNetworkState(NetState state);

        static NetState netStateFor(bool wifiConnected, bool mqttConnected, bool portalActive);
};

#endif
