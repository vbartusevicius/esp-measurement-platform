#ifndef RELEASE_UPDATER_H
#define RELEASE_UPDATER_H

#include <Arduino.h>

class Logger;
class Storage;

// OTA from the GitHub repo's latest release assets:
//   https://github.com/<repo>/releases/download/<tag>/littlefs.bin
//   https://github.com/<repo>/releases/download/<tag>/firmware.bin
//
// A TLS download needs ~22 KB contiguous heap plus a large stack, which is
// not available once WiFiManager / display / MQTT / web server are running.
// So a runtime check only parks the release tag in RTC memory and reboots;
// the flash itself runs from flashPendingAtBoot() before anything else
// allocates (and before LittleFS is mounted, so the FS image can be
// rewritten safely).
class ReleaseUpdater
{
    public:
        static constexpr unsigned long FIRST_CHECK_DELAY_MS = 120000;

        // Call as the very first thing in setup(), before other subsystems
        // allocate. Installs a release parked by a previous run.
        void flashPendingAtBoot(Logger* logger);

        // Logs the outcome of the previous attempt (RTC survives the reboot).
        void logLastAttempt(Logger* logger);

        void begin(Logger* logger, Storage* storage);

        // Call frequently; runs the actual check only when due.
        void run();

        // Schedule a check as soon as possible (web UI "check now" button).
        void requestCheck() { this->nextCheckAt = 0; this->forced = true; }

        // The periodic check performs a blocking TLS handshake (seconds),
        // which starves the async web server and drops websocket clients.
        // main() supplies this so checks are deferred while the UI is in use.
        void setBusyCallback(bool (*isBusy)()) { this->isBusy = isBusy; }

    private:
        Logger* logger = nullptr;
        unsigned long nextCheckAt = FIRST_CHECK_DELAY_MS;
        unsigned long checkIntervalMs = 600000;
        int32_t lastError = 0;
        bool forced = false;
        bool (*isBusy)() = nullptr;

        static constexpr const char* GITHUB_REPO = "vbartusevicius/esp-measurement-platform";

        void checkForUpdates();
        bool fetchLatestTag(String& tagOut);
        bool resolveAssetUrl(const String& tag, const char* asset, String& urlOut);
        bool downloadAndFlash(const String& url, bool filesystem);
        bool connectStoredWiFi(uint32_t timeoutMs);
        void log(const String& message);
};

#endif
