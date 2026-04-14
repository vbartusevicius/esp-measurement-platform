#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ArduinoOTA.h>
#include <TaskManagerIO.h>

#include "ChipId.h"
#include "HAL.h"
#include "LedController.h"
#include "Logger.h"
#include "Storage.h"
#include "Parameter.h"
#include "WifiConnector.h"
#include "MqttClient.h"
#include "Display.h"
#include "WebApi.h"
#include "PluginRegistry.h"

// Plugins
#include "AnalogDistancePlugin.h"
#include "UltrasonicDistancePlugin.h"
#include "RadiationCounterPlugin.h"

WiFiClient network;

// Core components
HAL hal;
Logger logger;
Storage storage;
LedController ledController;
Display display;
PluginRegistry registry;

// Plugins
AnalogDistancePlugin analogDistancePlugin;
UltrasonicDistancePlugin ultrasonicDistancePlugin;
RadiationCounterPlugin radiationCounterPlugin;

// Pointers to be initialized after plugin selection
WifiConnector* wifi = nullptr;
MqttClient* mqtt = nullptr;
WebApi* webApi = nullptr;
IPlugin* activePlugin = nullptr;

void resetDevice()
{
    storage.reset();
    if (wifi) wifi->resetSettings();
    delay(1000);
    ESP.restart();
}

void setupOTA()
{
    ArduinoOTA.onStart([]() {
        logger.info("OTA update starting...");
    });
    ArduinoOTA.onEnd([]() {
        logger.info("OTA update complete.");
    });
    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        Serial.printf("OTA progress: %u%%\r", (progress / (total / 100)));
    });
    ArduinoOTA.onError([](ota_error_t error) {
        logger.error("OTA error: " + String(error));
    });
    ArduinoOTA.begin();
}

void setup()
{
    Serial.begin(9600);
    delay(500);

    ledController.begin(&hal);

    String chipId = ChipId::get();
    logger.info("=== ESP Unified ===");
    logger.info("Chip ID: " + chipId);

    // Register all available plugins
    registry.add(&analogDistancePlugin);
    registry.add(&ultrasonicDistancePlugin);
    registry.add(&radiationCounterPlugin);

    // Initialize storage and determine active plugin
    storage.begin();
    String activePluginId = storage.getParameter(Parameter::ACTIVE_PLUGIN, "");
    activePlugin = registry.get(activePluginId.c_str());

    if (activePlugin) {
        logger.info("Active plugin: " + String(activePlugin->getName()));
        activePlugin->setup(&hal, &storage, &logger, &ledController);
    } else {
        logger.warning("No plugin selected. Please configure one in the web interface.");
    }

    // WiFi
    wifi = new WifiConnector(&logger, chipId);
    bool wifiConnected = wifi->begin();

    taskManager.schedule(repeatMillis(250), [] { wifi->run(); });

    if (!wifiConnected) {
        display.configWizardFirstStep(wifi->getAppName());
        return;
    }

    if (storage.isEmpty(activePlugin)) {
        display.configWizardSecondStep(WiFi.localIP().toString().c_str());
    }

    // Web API
    webApi = new WebApi(&storage, &logger, activePlugin, &registry, resetDevice);
    webApi->begin();

    // MQTT
    String mqttDevice = storage.getParameter(Parameter::MQTT_DEVICE);
    if (mqttDevice.length() > 0) {
        mqtt = new MqttClient(&storage, &logger, activePlugin, chipId);
        mqtt->begin();
    } else {
        logger.warning("MQTT device name not configured, skipping MQTT");
    }

    // OTA
    setupOTA();

    // Task scheduling
    int samplingInterval = activePlugin ? activePlugin->getSamplingInterval() : 10;

    // Web API updates
    taskManager.scheduleFixedRate(2000, [] {
        bool mqttOk = mqtt ? mqtt->isConnected() : false;
        if (webApi) webApi->run(mqttOk);
    });

    // LED heartbeat
    taskManager.scheduleFixedRate(1000, [] {
        ledController.click();
        ledController.run();
    });

    // MQTT maintenance
    taskManager.scheduleFixedRate(5000, [] {
        if (mqtt) mqtt->run();
    });

    // Plugin measurement loop
    taskManager.scheduleFixedRate(samplingInterval * 1000, [] {
        if (activePlugin) activePlugin->loop();
    });

    // MQTT publish
    taskManager.scheduleFixedRate(samplingInterval * 1000, [] {
        if (mqtt) mqtt->publish();
    });

    // Display update
    taskManager.scheduleFixedRate(1000, [] {
        bool mqttOk = mqtt ? mqtt->isConnected() : false;
        int page = activePlugin ? activePlugin->getCurrentDisplayPage() : 0;
        display.run(activePlugin, page, mqttOk);
    });

    logger.info("Setup complete. Scheduling with " + String(samplingInterval) + "s sampling interval.");
}

void loop()
{
    ArduinoOTA.handle();
    taskManager.runLoop();
}
