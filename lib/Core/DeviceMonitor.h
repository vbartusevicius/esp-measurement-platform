#ifndef DEVICE_MONITOR_H
#define DEVICE_MONITOR_H

#include <Arduino.h>
#include "EventLog.h"
#include "LimitMonitor.h"
#include "ScreenModel.h"

class Storage;
class Logger;
class RelayOutput;

// Device-level state shared by the OLED, WebUI and MQTT: MIN/MAX limits and
// the relay rule, relay ownership, and the short event log.
class DeviceMonitor
{
    public:
        void begin(Storage* storage, Logger* logger, RelayOutput* relay);
        void loadLimits();
        // Effective on/off state of an alert ("limit_low_on" / "limit_high_on").
        bool limitEnabled(const char* switchKey, const char* valueKey);

        // Call after every plugin sample.
        void evaluate(const ScreenModel& model, unsigned long nowMs);
        void updateNetwork(bool wifiConnected, bool mqttConnected, const String& wifiDetail, const String& mqttDetail, unsigned long nowMs);

        // Manual relay command (MQTT / WebUI). Refused while a limit rule owns the relay.
        bool commandRelay(bool on, const char* source, unsigned long nowMs);

        void event(const char* title, const char* detail, unsigned long nowMs);
        void dismissAlert() { this->limitMonitor.acknowledge(); }
        bool alertPending() const { return this->limitMonitor.alertPending(); }

        const LimitMonitor& limits() const { return this->limitMonitor; }
        const EventLog& events() const { return this->eventLog; }
        bool relayAvailable() const;
        bool relayOn() const;
        unsigned long relayActivations() const { return this->relayOnCount; }

    private:
        Storage* storage = nullptr;
        Logger* logger = nullptr;
        RelayOutput* relay = nullptr;
        LimitMonitor limitMonitor;
        EventLog eventLog;
        unsigned long relayOnCount = 0;
        bool sensorKnown = false;
        bool sensorOk = false;
        bool networkKnown = false;
        bool wifiUp = false;
        bool mqttUp = false;

        void applyRelay(bool on, const char* source, unsigned long nowMs);
        float readLimit(const char* key);
};

#endif
