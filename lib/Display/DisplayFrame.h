#ifndef DISPLAY_FRAME_H
#define DISPLAY_FRAME_H

class DeviceMonitor;
struct ScreenModel;

// Everything one display refresh needs.
struct DisplayFrame {
    const ScreenModel* screen = nullptr;
    const DeviceMonitor* monitor = nullptr;
    bool mqttConnected = false;
    unsigned long errors = 0;
};

#endif
