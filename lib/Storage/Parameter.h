#ifndef PARAMETER_H
#define PARAMETER_H

class Parameter
{
    public:
        static constexpr const char* ACTIVE_PLUGIN = "active_plugin";
        static constexpr const char* DEVICE_NAME = "device_name";
        static constexpr const char* MQTT_HOST = "mqtt_host";
        static constexpr const char* MQTT_PORT = "mqtt_port";
        static constexpr const char* MQTT_USER = "mqtt_user";
        static constexpr const char* MQTT_PASS = "mqtt_pass";
        static constexpr const char* MQTT_DEVICE = "mqtt_device";
        static constexpr const char* MQTT_TOPIC = "mqtt_topic";

        // MIN/MAX limits in the active plugin's primary unit. *_ON = "1"/"0"
        // switches an alert without losing its value; missing = on if a value is set.
        static constexpr const char* LIMIT_LOW = "limit_low";
        static constexpr const char* LIMIT_HIGH = "limit_high";
        static constexpr const char* LIMIT_LOW_ON = "limit_low_on";
        static constexpr const char* LIMIT_HIGH_ON = "limit_high_on";
        static constexpr const char* LIMIT_HYSTERESIS = "limit_hysteresis";
        static constexpr const char* RELAY_MODE = "relay_mode";   // manual | on_alarm | off_alarm

        // Set by a 5 s RST/WIFI hold: next boot opens the WiFi setup portal
        static constexpr const char* PORTAL_ON_BOOT = "portal_on_boot";
};

#endif
