#ifndef PARAMETER_H
#define PARAMETER_H

class Parameter
{
    public:
        static constexpr const char* ACTIVE_PLUGIN = "active_plugin";

        static constexpr const char* MQTT_HOST = "mqtt_host";
        static constexpr const char* MQTT_PORT = "mqtt_port";
        static constexpr const char* MQTT_USER = "mqtt_user";
        static constexpr const char* MQTT_PASS = "mqtt_pass";
        static constexpr const char* MQTT_DEVICE = "mqtt_device";
        static constexpr const char* MQTT_TOPIC = "mqtt_topic";

        static constexpr const char* UPDATE_INTERVAL_MIN = "update_interval_min";

        static constexpr const char* FS_VERSION = "fs_version";
        static constexpr const char* FS_FAIL_COUNT = "fs_fail_count";
};

#endif
