#ifndef DISPLAY_FRAME_H
#define DISPLAY_FRAME_H

class DeviceMonitor;
class IDisplayContributor;
struct ScreenModel;

// Everything one display refresh needs. Portrait (64 px wide) boards render
// the page system from `screen` + `monitor`; landscape boards keep the
// plugin-drawn pages (`legacy`).
struct DisplayFrame {
    IDisplayContributor* legacy = nullptr;
    int legacyPage = 0;
    const ScreenModel* screen = nullptr;
    const DeviceMonitor* monitor = nullptr;
    bool mqttConnected = false;
    unsigned long errors = 0;
};

#endif
