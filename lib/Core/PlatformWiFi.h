#ifndef PLATFORM_WIFI_H
#define PLATFORM_WIFI_H

// WiFi, WiFiClient and ESP for both cores: include this instead of the
// core-specific header.
#if defined(ESP32)
#include <WiFi.h>          // IWYU pragma: export
#else
#include <ESP8266WiFi.h>   // IWYU pragma: export
#endif

#endif
