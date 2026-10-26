#ifndef DEVICE_MONITOR_H
#define DEVICE_MONITOR_H

#include <Arduino.h>
#include <vector>
#include "EventLog.h"
#include "LimitMonitor.h"

class Logger;
class RelayOutput;
class Settings;
struct ScreenModel;

// Device-level state shared by the OLED, WebUI and MQTT: each sensor's MIN/MAX
// limits, the relay rule (it follows one chosen sensor's alerts), relay
// ownership, and the short event log.
class DeviceMonitor
{
    public:
        void begin(Settings* storage, Logger* logger, RelayOutput* relay);
        // One watch per running sensor, in display order; limits live in its settings scope.
        void addSensor(const char* id, Settings* sensorSettings);
        void loadLimits();
        // Effective on/off state of an alert ("limit_low_on" / "limit_high_on").
        static bool limitEnabled(const Settings& settings, const char* switchKey, const char* valueKey);

        // Call after every sample of sensor `index`.
        void evaluate(size_t index, const ScreenModel& model, unsigned long nowMs);
        void updateNetwork(bool wifiConnected, bool mqttConnected, const String& wifiDetail, const String& mqttDetail, unsigned long nowMs);

        // Manual relay command (MQTT / WebUI). Refused while a limit rule owns the relay.
        bool commandRelay(bool on, const char* source, unsigned long nowMs);

        void event(const char* title, const char* detail, unsigned long nowMs);
        // First sensor with an unacknowledged alert, or -1.
        int pendingAlert() const;
        bool alertPending() const { return this->pendingAlert() >= 0; }
        void dismissAlert();                  // the first pending one (PAGE button)
        void dismissAlert(size_t index);
        void dismissAll();

        size_t sensorCount() const { return this->watches.size(); }
        const char* sensorId(size_t index) const { return this->watches[index].id; }
        const LimitMonitor& limits(size_t index) const { return this->watches[index].limits; }
        LimitMonitor::RelayMode relayMode() const { return this->mode; }
        // Sensor whose alerts drive the relay (-1: manual or no sensor).
        int relaySource() const { return this->mode == LimitMonitor::RelayMode::MANUAL ? -1 : this->source; }
        const EventLog& events() const { return this->eventLog; }
        bool relayAvailable() const;
        bool relayOn() const;
        unsigned long relayActivations() const { return this->relayOnCount; }

    private:
        struct Watch {
            const char* id;
            Settings* settings;
            LimitMonitor limits;
            bool sensorKnown;
            bool sensorOk;
        };

        Settings* storage = nullptr;
        Logger* logger = nullptr;
        RelayOutput* relay = nullptr;
        std::vector<Watch> watches;
        LimitMonitor::RelayMode mode = LimitMonitor::RelayMode::MANUAL;
        int source = -1;
        EventLog eventLog;
        unsigned long relayOnCount = 0;
        bool networkKnown = false;
        bool wifiUp = false;
        bool mqttUp = false;

        void applyRelay(bool on, const char* source, unsigned long nowMs);
        static float readLimit(const Settings& settings, const char* key);
        String named(const ScreenModel& model, const String& text) const;
};

#endif
