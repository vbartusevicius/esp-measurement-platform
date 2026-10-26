#ifndef DISPLAY_FRAME_H
#define DISPLAY_FRAME_H

#include <vector>
#include "ScreenModel.h"

class DeviceMonitor;

// Everything one display refresh needs: one screen per running sensor (in
// the monitor's sensor order) plus the device-level state.
struct DisplayFrame {
    std::vector<ScreenModel> screens;
    const DeviceMonitor* monitor = nullptr;
    bool mqttConnected = false;
    unsigned long errors = 0;
};

#endif
