#include <Arduino.h>
#include "PlatformWiFi.h"
#include <ArduinoOTA.h>
#include <TaskManagerIO.h>

#include "Board.h"
#include "ButtonLadder.h"
#include "ChipId.h"
#include "HAL.h"
#include "LedController.h"
#include "RelayOutput.h"
#include "DeviceMonitor.h"
#include "Version.h"
#include "Logger.h"
#include "Storage.h"
#include "Parameter.h"
#include "WifiConnector.h"
#include "MqttClient.h"
#include "Display.h"
#include "WebApi.h"
#include "PluginRegistry.h"
#include "PluginConfig.h"

// Plugins
#include "AnalogDistancePlugin.h"
#include "UltrasonicDistancePlugin.h"
#include "RadiationCounterPlugin.h"
#include "AnalogVoltagePlugin.h"

WiFiClient network;

// Core components
HAL hal;
Logger logger;
Storage storage;
LedController ledController;
Display display;
PluginRegistry registry;
RelayOutput relay;
ButtonLadder buttonLadder;
DeviceMonitor monitor;

// Plugins
AnalogDistancePlugin analogDistancePlugin;
UltrasonicDistancePlugin ultrasonicDistancePlugin;
RadiationCounterPlugin radiationCounterPlugin;
AnalogVoltagePlugin analogVoltagePlugin;

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

void refreshDisplay()
{
    DisplayFrame frame;
    ScreenModel screen;
    frame.legacy = activePlugin ? activePlugin->display() : nullptr;
    frame.legacyPage = frame.legacy ? frame.legacy->getCurrentDisplayPage() : 0;
    frame.screen = (activePlugin && activePlugin->getScreen(screen)) ? &screen : nullptr;
    frame.monitor = &monitor;
    frame.mqttConnected = mqtt ? mqtt->isConnected() : false;
    frame.errors = logger.errors();
    display.run(frame);
}

// PAGE button (and the WebUI PAGE button): dismisses a pending alert first,
// otherwise cycles the display pages.
void pagePressed()
{
    if (monitor.alertPending()) {
        monitor.dismissAlert();
    } else if (display.isPortrait()) {
        display.nextPage();
    } else {
        IDisplayContributor* contributor = activePlugin ? activePlugin->display() : nullptr;
        if (contributor) contributor->nextDisplayPage();
    }
    if (webApi) refreshDisplay();   // the setup portal keeps its own screen
}

void pollButtons()
{
    if (webApi) webApi->processActions();
#if defined(BOARD_XIAO_ESP32C6)
    switch (buttonLadder.update(hal.analogReadMilliVolts(Board::BUTTON_LADDER_PIN), millis())) {
        case ButtonLadder::Event::PAGE_PRESSED:
            if (webApi) pagePressed();
            break;
        case ButtonLadder::Event::RESET_TAPPED:
            logger.info("RST/WIFI tapped, rebooting");
            delay(200);
            ESP.restart();
            break;
        case ButtonLadder::Event::RESET_HELD:
            // Rebooting keeps the setup portal (port 80) and the Web API apart.
            if (wifi && wifi->isPortalActive()) {
                logger.info("RST/WIFI held 5 s: leaving WiFi setup portal");
            } else {
                logger.info("RST/WIFI held 5 s: rebooting into WiFi setup portal");
                storage.saveParameter(Parameter::PORTAL_ON_BOOT, String("1"));
            }
            delay(200);
            ESP.restart();
            break;
        case ButtonLadder::Event::RESET_FACTORY:
            logger.warning("RST/WIFI held 15 s: factory reset");
            resetDevice();
            break;
        case ButtonLadder::Event::NONE:
            break;
    }
#endif
}

void updateNetworkLed(bool portal)
{
    LedController::NetState state = LedController::NetState::OFFLINE;
    if (WiFi.status() == WL_CONNECTED) {
        state = (mqtt && mqtt->isConnected()) ? LedController::NetState::MQTT : LedController::NetState::WIFI;
    } else if (portal) {
        state = LedController::NetState::PORTAL;
    }
    ledController.setNetworkState(state);
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
        Serial.printf("OTA progress: %u%%\r", total >= 100 ? (progress / (total / 100)) : 0u);
    });
    ArduinoOTA.onError([](ota_error_t error) {
        logger.error("OTA error: " + String(error));
    });
    ArduinoOTA.begin();
}

void setup()
{
    relay.begin(&hal, Board::RELAY_PIN);
    Serial.begin(115200);
    delay(500);
#if defined(ESP32)
    analogSetAttenuation(ADC_11db);   // 0..3.3 V range for the 4-20 mA, 0-10 V and button inputs
#endif

    storage.begin();
    monitor.begin(&storage, &logger, &relay);
    monitor.event("SYSTEM BOOT", "FW " FW_VERSION, millis());

    ledController.begin(&hal);
    display.begin();
    taskManager.scheduleFixedRate(20, [] { pollButtons(); });

    String chipId = ChipId::get();
    logger.info("=== ESP Unified ===");
    logger.info("Chip ID: " + chipId);

    // Register all available plugins
    registry.add(&analogDistancePlugin);
    registry.add(&ultrasonicDistancePlugin);
    registry.add(&radiationCounterPlugin);
    registry.add(&analogVoltagePlugin);

    // Determine active plugin (storage was initialised before the OTA check)
    String activePluginId = storage.getParameter(Parameter::ACTIVE_PLUGIN, "");
    activePlugin = registry.get(activePluginId.c_str());

    if (activePlugin) {
        logger.info("Active plugin: " + String(activePlugin->getName()));
        activePlugin->setup(&hal, &storage, &logger, &ledController);
    } else {
        logger.warning("No plugin selected. Please configure one in the web interface.");
    }

    // WiFi
    bool forcePortal = storage.getParameter(Parameter::PORTAL_ON_BOOT, "") == "1";
    if (forcePortal) storage.saveParameter(Parameter::PORTAL_ON_BOOT, String(""));

    wifi = new WifiConnector(&logger, chipId);
    bool wifiConnected = wifi->begin(forcePortal);

    taskManager.schedule(repeatMillis(250), [] { wifi->run(); });

    if (!wifiConnected) {
        taskManager.scheduleFixedRate(1000, [] { updateNetworkLed(true); });
        display.configWizardFirstStep(wifi->getAppName());
        // Restart once the portal has saved working credentials so the full
        // setup (Web API, MQTT, OTA, measurements) runs with a clean state.
        taskManager.scheduleFixedRate(1000, [] {
            if (WiFi.status() == WL_CONNECTED) {
                logger.info("WiFi configured via portal, restarting for full setup...");
                delay(500);
                ESP.restart();
            }
            // Portal timed out (300 s): retry the saved network.
            if (millis() > 10000 && !wifi->isPortalActive()) {
                logger.info("WiFi setup portal closed, restarting...");
                delay(500);
                ESP.restart();
            }
        });
        return;
    }

    if (!PluginConfig::isComplete(storage, activePlugin)) {
        display.configWizardSecondStep(WiFi.localIP().toString().c_str());
    }

    webApi = new WebApi(&storage, &logger, activePlugin, &registry, resetDevice);
    webApi->setDevice(&monitor, &display, pagePressed);
    webApi->begin();

    String mqttDevice = storage.getParameter(Parameter::MQTT_DEVICE);
    IMqttContributor* mqttContributor = activePlugin ? activePlugin->mqtt() : nullptr;
    if (mqttDevice.length() > 0 && mqttContributor) {
        mqtt = new MqttClient(&storage, &logger, mqttContributor, activePlugin->getId(), chipId);
        if (relay.available()) mqtt->setRelay(&relay, &monitor);
        mqtt->begin();
    } else {
        logger.warning("MQTT device name not configured, skipping MQTT");
    }

    setupOTA();

    int samplingInterval = activePlugin ? activePlugin->getSamplingInterval() : 10;
    int publishInterval = activePlugin ? activePlugin->getPublishInterval() : samplingInterval;

    taskManager.scheduleFixedRate(2000, [] {
        bool mqttOk = mqtt ? mqtt->isConnected() : false;
        if (webApi) webApi->run(mqttOk);
    });

    taskManager.scheduleFixedRate(5000, [] {
        if (mqtt) mqtt->run();
    });

    taskManager.scheduleFixedRate(samplingInterval * 1000, [] {
        if (activePlugin) {
            activePlugin->loop();
            ScreenModel screen;
            if (activePlugin->getScreen(screen)) monitor.evaluate(screen, millis());
        }
        ledController.click();
    });

    taskManager.scheduleFixedRate(publishInterval * 1000, [] {
        if (mqtt) mqtt->publish();
    });

    taskManager.scheduleFixedRate(1000, [] {
        bool wifiOk = WiFi.status() == WL_CONNECTED;
        bool mqttOk = mqtt ? mqtt->isConnected() : false;
        monitor.updateNetwork(wifiOk, mqttOk, WiFi.SSID() + " " + String(WiFi.RSSI()),
                              storage.getParameter(Parameter::MQTT_HOST, ""), millis());
        refreshDisplay();
        updateNetworkLed(false);
    });

    logger.info("Setup complete. Sampling every " + String(samplingInterval) +
                "s, publishing every " + String(publishInterval) + "s.");
}

void loop()
{
    ArduinoOTA.handle();
    ledController.run();
    taskManager.runLoop();
}
