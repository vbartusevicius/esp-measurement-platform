#ifndef RELEASE_UPDATER_H
#define RELEASE_UPDATER_H

#include <Arduino.h>

class Logger;
class Storage;

class ReleaseUpdater
{
    public:
        static constexpr unsigned long FIRST_CHECK_DELAY_MS = 120000;

        void flashPendingAtBoot(Logger* logger, Storage* storage);

        void logLastAttempt(Logger* logger);

        void begin(Logger* logger, Storage* storage);

        void run();

        void requestCheck() { this->nextCheckAt = 0; this->forced = true; this->manualCheck = true; }

        void setBusyCallback(bool (*isBusy)()) { this->isBusy = isBusy; }

    private:
        Logger* logger = nullptr;
        Storage* storage = nullptr;
        unsigned long nextCheckAt = FIRST_CHECK_DELAY_MS;
        unsigned long checkIntervalMs = 600000;
        int32_t lastError = 0;
        int32_t lastTlsError = 0;
        uint32_t lastTransferMs = 0;
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
