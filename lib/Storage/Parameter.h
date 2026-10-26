#ifndef PARAMETER_H
#define PARAMETER_H

class Parameter
{
    public:
        // Enabled sensors, comma-separated plugin ids in display order. Each
        // sensor's own settings (and limits) are stored under its prefix (ScopedSettings).
        static constexpr const char* SENSORS = "sensors";
        static constexpr const char* ACTIVE_PLUGIN = "active_plugin";   // before multi-sensor: one plugin id
        static constexpr const char* DEVICE_NAME = "device_name";
        static constexpr const char* MQTT_HOST = "mqtt_host";
        static constexpr const char* MQTT_PORT = "mqtt_port";
        static constexpr const char* MQTT_USER = "mqtt_user";
        static constexpr const char* MQTT_PASS = "mqtt_pass";
        static constexpr const char* MQTT_DEVICE = "mqtt_device";

        // Per sensor (under its prefix): MIN/MAX limits in its primary unit. *_ON = "1"/"0"
        // switches an alert without losing its value; missing = on if a value is set.
        static constexpr const char* LIMIT_LOW = "limit_low";
        static constexpr const char* LIMIT_HIGH = "limit_high";
        static constexpr const char* LIMIT_LOW_ON = "limit_low_on";
        static constexpr const char* LIMIT_HIGH_ON = "limit_high_on";
        static constexpr const char* LIMIT_HYSTERESIS = "limit_hysteresis";
        static constexpr const char* RELAY_MODE = "relay_mode";       // manual | on_alarm | off_alarm
        static constexpr const char* RELAY_SOURCE = "relay_source";   // plugin id whose alerts drive the relay

        // Set by a 5 s RST/WIFI hold: next boot opens the WiFi setup portal
        static constexpr const char* PORTAL_ON_BOOT = "portal_on_boot";
};

#endif
