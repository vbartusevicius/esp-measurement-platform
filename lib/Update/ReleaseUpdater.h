#ifndef RELEASE_UPDATER_H
#define RELEASE_UPDATER_H

#include <Arduino.h>

class Logger;

// Periodically checks the GitHub repository's latest release and OTA-updates
// the LittleFS image and firmware from the release assets.
//
// Assets are fetched from the release's fixed download URLs:
//   https://github.com/<repo>/releases/download/<tag>/littlefs.bin
//   https://github.com/<repo>/releases/download/<tag>/firmware.bin
class ReleaseUpdater
{
    public:
        // Seconds after boot before the first check; interval between checks.
        static constexpr unsigned long FIRST_CHECK_DELAY_MS = 120000;
        static constexpr unsigned long CHECK_INTERVAL_MS = 10UL * 60 * 1000;

        ReleaseUpdater(Logger* logger);

        // Call frequently; runs the actual check only when due.
        void run();

    private:
        Logger* logger;
        unsigned long nextCheckAt = FIRST_CHECK_DELAY_MS;

        // Repo that publishes release binaries ("owner/name").
        static constexpr const char* GITHUB_REPO = "vbartusevicius/esp-measurement-platform";

        void checkForUpdates();
        bool fetchLatestTag(String& tagOut);
        bool flashFromRelease(const String& tag);
};

#endif
