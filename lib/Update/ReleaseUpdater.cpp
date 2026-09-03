#include "ReleaseUpdater.h"

#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266httpUpdate.h>
#include <LittleFS.h>
#include <ArduinoJson.h>

#include "Logger.h"
#include "Storage.h"
#include "Parameter.h"
#include "Version.h"

ReleaseUpdater::ReleaseUpdater(Logger* logger, Storage* storage)
    : logger(logger)
{
    // Interval in minutes; changes require restart
    int minutes = storage->getParameter(Parameter::UPDATE_INTERVAL_MIN, "10").toInt();
    if (minutes < 1) minutes = 1;
    if (minutes > 1440) minutes = 1440;
    this->checkIntervalMs = (unsigned long)minutes * 60000UL;
}

void ReleaseUpdater::run()
{
    long untilDue = (long)(this->nextCheckAt - millis());
    if (untilDue > 0) return;
    this->nextCheckAt = millis() + this->checkIntervalMs;

    if (WiFi.status() != WL_CONNECTED) return;
    this->checkForUpdates();
}

void ReleaseUpdater::checkForUpdates()
{
    String tag;
    if (!this->fetchLatestTag(tag)) return;

    if (tag == FW_VERSION) {
        this->logger->debug("No new release available (current: " + String(FW_VERSION) + ")");
        return;
    }

    this->logger->info("New release available: " + tag + " (current: " + String(FW_VERSION) + ")");
    this->flashFromRelease(tag);
}

bool ReleaseUpdater::fetchLatestTag(String& tagOut)
{
    WiFiClientSecure client;
    client.setInsecure();
    client.setBufferSizes(512, 512);  // shrink TLS buffers to keep heap free

    HTTPClient http;
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);

    String url = String("https://api.github.com/repos/") + GITHUB_REPO + "/releases/latest";
    if (!http.begin(client, url)) {
        this->logger->warning("OTA check: failed to start request");
        return false;
    }

    http.addHeader("User-Agent", "esp-measurement-platform");
    http.addHeader("Accept", "application/vnd.github+json");

    int code = http.GET();
    if (code != HTTP_CODE_OK) {
        this->logger->warning("OTA check: GitHub API returned " + String(code));
        http.end();
        return false;
    }

    // Only the tag matters; filter avoids buffering the full release payload
    JsonDocument filter;
    filter["tag_name"] = true;

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, http.getStream(), DeserializationOption::Filter(filter));
    http.end();

    const char* tag = doc["tag_name"];
    if (err || !tag) {
        this->logger->warning("OTA check: failed to parse release JSON");
        return false;
    }

    tagOut = tag;
    return true;
}

bool ReleaseUpdater::flashFromRelease(const String& tag)
{
    WiFiClientSecure client;
    client.setInsecure();

    ESP8266HTTPUpdate httpUpdate;
    httpUpdate.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
    httpUpdate.rebootOnUpdate(false);

    String base = String("https://github.com/") + GITHUB_REPO + "/releases/download/" + tag;

    // Unmount the filesystem while it is being overwritten: the web server
    // serves files from it, and a concurrent request could read torn data.
    LittleFS.end();

    // Filesystem first: if it fails, the firmware is untouched and we retry later
    this->logger->info("OTA: updating LittleFS image...");
    t_httpUpdate_return fsResult = httpUpdate.updateFS(client, base + "/littlefs.bin");
    if (fsResult != HTTP_UPDATE_OK) {
        this->logger->error("OTA: LittleFS update failed, error " + String(httpUpdate.getLastError()) +
                            ": " + httpUpdate.getLastErrorString());
        LittleFS.begin();  // remount so the web UI keeps working (possibly partially)
        return false;
    }

    this->logger->info("OTA: updating firmware...");
    t_httpUpdate_return fwResult = httpUpdate.update(client, base + "/firmware.bin", FW_VERSION);
    if (fwResult != HTTP_UPDATE_OK) {
        this->logger->error("OTA: firmware update failed, error " + String(httpUpdate.getLastError()) +
                            ": " + httpUpdate.getLastErrorString());
        return false;
    }

    this->logger->info("OTA: update complete, restarting...");
    delay(500);
    ESP.restart();
    return true;
}
