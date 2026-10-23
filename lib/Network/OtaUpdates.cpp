#include "OtaUpdates.h"
#include <ArduinoOTA.h>
#include "Logger.h"

static Logger* otaLogger = nullptr;

void OtaUpdates::begin(Logger* logger)
{
    otaLogger = logger;
    ArduinoOTA.onStart([]() { otaLogger->info("OTA update starting..."); });
    ArduinoOTA.onEnd([]() { otaLogger->info("OTA update complete."); });
    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        Serial.printf("OTA progress: %u%%\r", total >= 100 ? (progress / (total / 100)) : 0u);
    });
    ArduinoOTA.onError([](ota_error_t error) { otaLogger->error("OTA error: " + String(error)); });
    ArduinoOTA.begin();
}

void OtaUpdates::handle()
{
    ArduinoOTA.handle();
}
