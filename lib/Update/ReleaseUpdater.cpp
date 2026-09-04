#include "ReleaseUpdater.h"

#include <memory>
#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266httpUpdate.h>
#include <ArduinoJson.h>

#include "Logger.h"
#include "Storage.h"
#include "Parameter.h"
#include "Version.h"

#define RTC_OTA_OFFSET 96            // uint32 block offset in RTC user memory
#define RTC_OTA_MAGIC  0x4F544131UL

namespace {
enum : uint16_t {
    ST_NONE = 0, ST_PARKED, ST_BOOT_START, ST_WIFI_FAIL,
    ST_REDIRECT_FAIL, ST_FS_FLASHING, ST_FS_FAIL,
    ST_FW_FLASHING, ST_FW_FAIL, ST_DONE, ST_GAVE_UP
};

const char* stageName(uint16_t s) {
    switch (s) {
        case ST_PARKED:        return "parked, awaiting reboot";
        case ST_BOOT_START:    return "boot flash started";
        case ST_WIFI_FAIL:     return "no WiFi at boot";
        case ST_REDIRECT_FAIL: return "asset URL not resolved";
        case ST_FS_FLASHING:   return "filesystem download in progress";
        case ST_FS_FAIL:       return "filesystem flash failed";
        case ST_FW_FLASHING:   return "firmware download in progress";
        case ST_FW_FAIL:       return "firmware flash failed";
        case ST_DONE:          return "installed OK";
        case ST_GAVE_UP:       return "gave up after one attempt";
        default:               return "none";
    }
}

struct RtcOtaState {
    uint32_t magic;
    uint8_t  pending;
    uint8_t  attempts;
    uint16_t stage;
    int32_t  err;
    uint32_t freeHeap;
    uint32_t maxBlock;
    char     tag[24];
    uint32_t checksum;
};
// system_rtc_mem_* requires a size that is a multiple of 4 bytes
static_assert(sizeof(RtcOtaState) % 4 == 0, "RTC state must be 4-byte sized");

uint32_t rtcChecksum(const RtcOtaState& s) {
    uint32_t sum = s.magic ^ (s.pending * 31u) ^ (s.attempts * 131u)
                 ^ (s.stage * 7919u) ^ (uint32_t)s.err
                 ^ s.freeHeap ^ s.maxBlock;
    for (size_t i = 0; i < sizeof(s.tag); i++) sum = sum * 33 + (uint8_t)s.tag[i];
    return sum;
}

bool rtcRead(RtcOtaState& s) {
    // NOTE: size is in BYTES (offset is in 4-byte blocks)
    if (!ESP.rtcUserMemoryRead(RTC_OTA_OFFSET, (uint32_t*)&s, sizeof(s))) return false;
    return s.magic == RTC_OTA_MAGIC && s.checksum == rtcChecksum(s);
}

void rtcWrite(RtcOtaState& s) {
    s.magic    = RTC_OTA_MAGIC;
    s.checksum = rtcChecksum(s);
    ESP.rtcUserMemoryWrite(RTC_OTA_OFFSET, (uint32_t*)&s, sizeof(s));
}
} // namespace

void ReleaseUpdater::log(const String& message)
{
    if (this->logger) this->logger->info("OTA: " + message);
}

void ReleaseUpdater::begin(Logger* logger, Storage* storage)
{
    this->logger = logger;

    // Interval in minutes; changes require restart
    int minutes = storage->getParameter(Parameter::UPDATE_INTERVAL_MIN, "10").toInt();
    if (minutes < 1) minutes = 1;
    if (minutes > 1440) minutes = 1440;
    this->checkIntervalMs = (unsigned long)minutes * 60000UL;
}

// --- Boot-time install -------------------------------------------------

void ReleaseUpdater::flashPendingAtBoot(Logger* logger)
{
    this->logger = logger;

    RtcOtaState st;
    if (!rtcRead(st) || !st.pending) return;

    String tag(st.tag);
    this->log("installing " + tag + " (current " + FW_VERSION + ")");

    auto trace = [&](uint16_t stage, int32_t err = 0) {
        st.stage    = stage;
        st.err      = err;
        st.freeHeap = ESP.getFreeHeap();
        st.maxBlock = ESP.getMaxFreeBlockSize();
        rtcWrite(st);
        this->log(String(stageName(stage)) + " (err=" + String((long)err) +
                  " free=" + String(st.freeHeap) + " blk=" + String(st.maxBlock) + ")");
    };

    if (st.attempts >= 1) {
        st.pending = 0;
        trace(ST_GAVE_UP);
        return;
    }
    st.attempts = 1;
    trace(ST_BOOT_START);

    if (!this->connectStoredWiFi(30000)) {
        st.pending = 0;
        trace(ST_WIFI_FAIL);
        return;
    }

    String fsUrl;
    if (!this->resolveAssetUrl(tag, "littlefs.bin", fsUrl)) {
        st.pending = 0;
        trace(ST_REDIRECT_FAIL);
        return;
    }
    trace(ST_FS_FLASHING);
    if (!this->downloadAndFlash(fsUrl, true)) {
        st.pending = 0;
        trace(ST_FS_FAIL, this->lastError);
        return;
    }

    String fwUrl;
    if (!this->resolveAssetUrl(tag, "firmware.bin", fwUrl)) {
        st.pending = 0;
        trace(ST_REDIRECT_FAIL);
        return;
    }
    trace(ST_FW_FLASHING);
    if (this->downloadAndFlash(fwUrl, false)) {
        st.pending = 0;
        trace(ST_DONE);
        delay(200);
        ESP.restart();
    }

    st.pending = 0;
    trace(ST_FW_FAIL, this->lastError);
}

void ReleaseUpdater::logLastAttempt(Logger* logger)
{
    this->logger = logger;

    RtcOtaState st;
    if (!rtcRead(st) || st.stage == ST_NONE) return;

    this->log(String("last attempt: ") + st.tag + " [" + stageName(st.stage) +
              "] err=" + String((long)st.err) + " free=" + String(st.freeHeap) +
              " blk=" + String(st.maxBlock));
}

bool ReleaseUpdater::connectStoredWiFi(uint32_t timeoutMs)
{
    if (WiFi.status() == WL_CONNECTED) return true;
    WiFi.mode(WIFI_STA);
    WiFi.begin();                      // credentials persisted by the SDK
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeoutMs) {
        delay(100);
    }
    return WiFi.status() == WL_CONNECTED;
}

// --- Runtime check -----------------------------------------------------

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
        this->log(String("up to date (") + FW_VERSION + ")");
        return;
    }

    // Park the tag and reboot: the flash needs a clean heap (see header).
    RtcOtaState st = {};
    strncpy(st.tag, tag.c_str(), sizeof(st.tag) - 1);
    st.pending  = 1;
    st.attempts = 0;
    st.stage    = ST_PARKED;
    st.freeHeap = ESP.getFreeHeap();
    st.maxBlock = ESP.getMaxFreeBlockSize();
    rtcWrite(st);

    this->log("new release " + tag + " (current " + FW_VERSION + "), rebooting to install");
    delay(300);
    ESP.restart();
}

bool ReleaseUpdater::fetchLatestTag(String& tagOut)
{
    // Heap-allocated: a WiFiClientSecure is far too large for the 4 KB stack
    std::unique_ptr<WiFiClientSecure> client(new WiFiClientSecure);
    if (!client) return false;
    client->setInsecure();
    client->setBufferSizes(1024, 512);   // API responses are small
    client->setTimeout(15000);

    HTTPClient http;
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
    http.setReuse(false);

    String url = String("https://api.github.com/repos/") + GITHUB_REPO + "/releases/latest";
    if (!http.begin(*client, url)) {
        this->log("check: begin failed");
        return false;
    }
    http.addHeader("User-Agent", "esp-measurement-platform");
    http.addHeader("Accept", "application/vnd.github+json");

    int code = http.GET();
    if (code != HTTP_CODE_OK) {
        this->log("check: HTTP " + String(code));
        http.end();
        return false;
    }

    // Only the tag matters; the filter avoids buffering the whole payload
    JsonDocument filter;
    filter["tag_name"] = true;
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, http.getStream(),
                                               DeserializationOption::Filter(filter));
    http.end();

    const char* tag = doc["tag_name"];
    if (err || !tag) {
        this->log("check: bad JSON");
        return false;
    }
    tagOut = tag;
    return true;
}

// github.com 302s to the asset CDN. Resolve it here so the download runs on
// a fresh TLS session - carrying one client across hosts breaks BearSSL.
bool ReleaseUpdater::resolveAssetUrl(const String& tag, const char* asset, String& urlOut)
{
    String url = String("https://github.com/") + GITHUB_REPO +
                 "/releases/download/" + tag + "/" + asset;

    std::unique_ptr<WiFiClientSecure> client(new WiFiClientSecure);
    if (!client) return false;
    client->setInsecure();
    client->setBufferSizes(1024, 512);
    client->setTimeout(15000);

    HTTPClient http;
    http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
    http.setReuse(false);
    const char* keys[] = { "Location" };
    http.collectHeaders(keys, 1);
    if (!http.begin(*client, url)) {
        this->log("redirect: begin failed");
        return false;
    }
    http.addHeader("User-Agent", "esp-measurement-platform");

    int code = http.GET();
    if (code == HTTP_CODE_FOUND || code == HTTP_CODE_MOVED_PERMANENTLY) {
        urlOut = http.header("Location");
    } else if (code == HTTP_CODE_OK) {
        urlOut = url;
    }
    http.end();

    if (urlOut.length() == 0) {
        this->log("redirect: HTTP " + String(code));
        return false;
    }
    return true;
}

bool ReleaseUpdater::downloadAndFlash(const String& url, bool filesystem)
{
    std::unique_ptr<WiFiClientSecure> client(new WiFiClientSecure);
    if (!client) {
        this->lastError = -100;
        this->log("flash: client alloc failed");
        return false;
    }
    client->setInsecure();
    client->setTimeout(30000);

    // TLS buffer policy: small buffers are only legal if the server honours
    // MFLN (RFC6066). GitHub's asset CDN may not - a full-size TLS record
    // into a small BearSSL buffer kills the connection mid-transfer
    // (error -5). Probe first; fall back to full buffers if heap allows.
    String host = url;
    int hs = host.indexOf("://");
    if (hs >= 0) host.remove(0, hs + 3);
    int pe = host.indexOf('/');
    if (pe >= 0) host.remove(pe);

    if (client->probeMaxFragmentLength(host.c_str(), 443, 1024)) {
        client->setBufferSizes(1024, 512);
        this->log("server supports MFLN (small TLS buffers)");
    } else {
        uint32_t blk = ESP.getMaxFreeBlockSize();
        if (blk < 24 * 1024) {
            this->lastError = -101;
            this->log("no MFLN and heap block too small for full TLS buffers");
            return false;
        }
        // default buffers (16384/512): the download needs ~22 KB contiguous
        // for the BearSSL context
        this->log("no MFLN, using full TLS buffers");
    }

    ESPhttpUpdate.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
    ESPhttpUpdate.rebootOnUpdate(false);
    ESPhttpUpdate.closeConnectionsOnUpdate(true);

    // No currentVersion argument: the tag comparison already decided that
    // this release is new. Passing it would send x-ESP8266-version and let a
    // 304 response silently turn into "no update".
    t_httpUpdate_return result = filesystem
        ? ESPhttpUpdate.updateFS(*client, url)
        : ESPhttpUpdate.update(*client, url);

    if (result == HTTP_UPDATE_OK) return true;

    this->lastError = ESPhttpUpdate.getLastError();
    this->log("flash failed " + String((long)this->lastError) + ": " +
              ESPhttpUpdate.getLastErrorString());
    return false;
}
