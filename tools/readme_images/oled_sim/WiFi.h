#pragma once
#include "Arduino.h"
#define WL_CONNECTED 3
struct FakeIp { String s; String toString() const { return s; } };
struct FakeWiFi {
    int st = WL_CONNECTED; int rssi = -58;
    int status() { return st; }
    int RSSI() { return rssi; }
    String SSID() { return String("HOME"); }
    FakeIp localIP() { return FakeIp{String("192.168.0.138")}; }
};
inline FakeWiFi WiFi;
