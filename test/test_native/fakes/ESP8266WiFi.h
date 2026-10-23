#pragma once

#include "Arduino.h"

class FakeIPAddress {
public:
    FakeIPAddress() = default;
    FakeIPAddress(int) {}
    String toString() const { return String("0.0.0.0"); }
};

class FakeWiFiClass {
public:
    FakeIPAddress localIP() { return FakeIPAddress(); }
    int RSSI() { return -60; }
    String SSID() { return String("fake-ssid"); }
};
inline FakeWiFiClass WiFi;
