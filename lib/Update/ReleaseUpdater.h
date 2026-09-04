#ifndef RELEASE_UPDATER_H
#define RELEASE_UPDATER_H

#include <Arduino.h>

class Logger;
class Storage;

class ReleaseUpdater
{
    public:
        static constexpr unsigned long FIRST_CHECK_DELAY_MS = 120000;

        // Call as the very first thing in setup(), before other subsystems
        // allocate. Installs a release parked by a previous run.
        void flashPendingAtBoot(Logger* logger, Storage* storage);

        // Logs the outcome of the previous attempt (RTC survives the reboot).
        void logLastAttempt(Logger* logger);

        void begin(Logger* logger, Storage* storage);

        // Call frequently; runs the actual check only when due.
        void run();

        // Schedule a check as soon as possible (web UI "check now" button).
        void requestCheck() { this->nextCheckAt = 0; this->forced = true; this->manualCheck = true; }

        // The periodic check performs a blocking TLS handshake (seconds),
        // which starves the async web server and drops websocket clients.
        // main() supplies this so checks are deferred while the UI is in use.
        void setBusyCallback(bool (*isBusy)()) { this->isBusy = isBusy; }

    private:
        Logger* logger = nullptr;
        Storage* storage = nullptr;
        unsigned long nextCheckAt = FIRST_CHECK_DELAY_MS;
        unsigned long checkIntervalMs = 600000;
        int32_t lastError = 0;
        bool forced = false;
        bool manualCheck = false;
        bool giveUpLogged = false;
        bool (*isBusy)() = nullptr;

        static constexpr const char* GITHUB_REPO = "vbartusevicius/esp-measurement-platform";

        void checkForUpdates();
        bool flashFilesystem(const String& tag);
        void repairFilesystemAtBoot();
        bool fetchLatestTag(String& tagOut);
        bool resolveAssetUrl(const String& tag, const char* asset, String& urlOut);
        bool downloadAndFlash(const String& url, bool filesystem);
        bool connectStoredWiFi(uint32_t timeoutMs);
        void log(const String& message);
};

#endif
