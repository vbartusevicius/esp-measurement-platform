// Composition root: creates the components, wires them together and
// schedules the periodic work. Behaviour lives in the libraries.
#include <Arduino.h>
#include <TaskManagerIO.h>
#include "Board.h"
#include "ButtonLadder.h"
#include "ChipId.h"
#include "DeviceMonitor.h"
#include "Display.h"
#include "HAL.h"
#include "LedController.h"
#include "Logger.h"
#include "MqttClient.h"
#include "OtaUpdates.h"
#include "Parameter.h"
#include <WiFi.h>
#include "PluginRegistry.h"
#include "RelayOutput.h"
#include "Storage.h"
#include "Version.h"
#include "WebApi.h"
#include "WifiConnector.h"

#include "AnalogDistancePlugin.h"
#include "AnalogVoltagePlugin.h"
#include "RadiationCounterPlugin.h"
#include "UltrasonicDistancePlugin.h"

HAL hal;
Logger logger;
Storage storage;
LedController ledController;
Display display;
PluginRegistry registry;
RelayOutput relay;
ButtonLadder buttonLadder;
DeviceMonitor monitor;

AnalogDistancePlugin analogDistancePlugin;
UltrasonicDistancePlugin ultrasonicDistancePlugin;
RadiationCounterPlugin radiationCounterPlugin;
AnalogVoltagePlugin analogVoltagePlugin;

// Created in setup() once WiFi and the active plugin are known
WifiConnector* wifi = nullptr;
MqttClient* mqtt = nullptr;
WebApi* webApi = nullptr;
IPlugin* activePlugin = nullptr;

bool mqttConnected()
{
    return mqtt && mqtt->isConnected();
}

void restartIn(unsigned long ms)
{
    delay(ms);
    ESP.restart();
}

void resetDevice()
{
    storage.reset();
    if (wifi) wifi->resetSettings();
    restartIn(1000);
}

void refreshDisplay()
{
    DisplayFrame frame;
    ScreenModel screen;
    frame.screen = (activePlugin && activePlugin->getScreen(screen)) ? &screen : nullptr;
    frame.monitor = &monitor;
    frame.mqttConnected = mqttConnected();
    frame.errors = logger.errors();
    display.run(frame);
}

// PAGE: dismisses a pending alert first, otherwise cycles the display pages.
void pagePressed()
{
    if (monitor.alertPending()) monitor.dismissAlert();
    else display.nextPage();
    refreshDisplay();
}

void handleButton(ButtonLadder::Event event)
{
    switch (event) {
        case ButtonLadder::Event::PAGE_PRESSED:
            if (webApi) pagePressed();   // the setup portal keeps its own screen
            break;
        case ButtonLadder::Event::RESET_TAPPED:
            logger.info("RST/WIFI tapped, rebooting");
            restartIn(200);
            break;
        case ButtonLadder::Event::RESET_HELD:
            // Rebooting keeps the setup portal (port 80) and the Web API apart.
            if (wifi && wifi->isPortalActive()) {
                logger.info("RST/WIFI held 5 s: leaving WiFi setup portal");
            } else {
                logger.info("RST/WIFI held 5 s: rebooting into WiFi setup portal");
                storage.saveParameter(Parameter::PORTAL_ON_BOOT, String("1"));
            }
            restartIn(200);
            break;
        case ButtonLadder::Event::RESET_FACTORY:
            logger.warning("RST/WIFI held 15 s: factory reset");
            resetDevice();
            break;
        case ButtonLadder::Event::NONE:
            break;
    }
}

void pollButtons()
{
    if (webApi) webApi->processActions();
    handleButton(buttonLadder.update(hal.analogReadMilliVolts(Board::BUTTON_LADDER_PIN), millis()));
}

void updateNetworkLed(bool portal)
{
    ledController.setNetworkState(LedController::netStateFor(WiFi.status() == WL_CONNECTED, mqttConnected(), portal));
}

void sampleSensor()
{
    if (activePlugin) {
        activePlugin->loop();
        ScreenModel screen;
        if (activePlugin->getScreen(screen)) monitor.evaluate(screen, millis());
    }
    ledController.click();
}

void everySecond()
{
    monitor.updateNetwork(WiFi.status() == WL_CONNECTED, mqttConnected(), WiFi.SSID() + " " + String(WiFi.RSSI()),
                          storage.getParameter(Parameter::MQTT_HOST, ""), millis());
    refreshDisplay();
    updateNetworkLed(false);
}

void selectPlugin()
{
    IPlugin* plugins[] = {&analogDistancePlugin, &ultrasonicDistancePlugin, &radiationCounterPlugin, &analogVoltagePlugin};
    for (IPlugin* plugin : plugins) registry.add(plugin);

    activePlugin = registry.get(storage.getParameter(Parameter::ACTIVE_PLUGIN, "").c_str());
    if (activePlugin) {
        logger.info("Active plugin: " + String(activePlugin->getName()));
        activePlugin->setup(&hal, &storage, &logger, &ledController);
    } else {
        logger.warning("No plugin selected. Please configure one in the web interface.");
    }
}

// No WiFi yet: serve the setup portal and restart once it is done.
void runSetupPortal()
{
    taskManager.scheduleFixedRate(1000, [] { updateNetworkLed(true); });
    display.showSetupPortal(wifi->getAppName());
    taskManager.scheduleFixedRate(1000, [] {
        if (WiFi.status() == WL_CONNECTED) {
            // Full setup (Web API, MQTT, OTA, measurements) runs with a clean state.
            logger.info("WiFi configured via portal, restarting for full setup...");
            restartIn(500);
        }
        if (millis() > 10000 && !wifi->isPortalActive()) {
            logger.info("WiFi setup portal closed, restarting...");   // timed out: retry the saved network
            restartIn(500);
        }
    });
}

void startMqtt(const String& chipId)
{
    IMqttContributor* contributor = activePlugin ? activePlugin->mqtt() : nullptr;
    if (storage.getParameter(Parameter::MQTT_DEVICE).isEmpty() || !contributor) {
        logger.warning("MQTT device name not configured, skipping MQTT");
        return;
    }
    mqtt = new MqttClient(&storage, &logger, contributor, activePlugin->getId(), chipId);
    if (relay.available()) mqtt->setRelay(&relay, &monitor);
    mqtt->begin();
}

void setup()
{
    relay.begin(&hal, Board::RELAY_PIN);   // relay off before anything else
    Serial.begin(115200);
    delay(500);
    analogSetAttenuation(ADC_11db);   // 0..3.3 V range for the 4-20 mA, 0-10 V and button inputs

    storage.begin();
    monitor.begin(&storage, &logger, &relay);
    monitor.event("SYSTEM BOOT", "FW " FW_VERSION, millis());
    ledController.begin(&hal);
    display.begin();
    taskManager.scheduleFixedRate(20, [] { pollButtons(); });

    const String chipId = ChipId::get();
    logger.info("=== ESP Unified ===");
    logger.info("Chip ID: " + chipId);
    selectPlugin();

    const bool forcePortal = storage.getParameter(Parameter::PORTAL_ON_BOOT, "") == "1";
    if (forcePortal) storage.saveParameter(Parameter::PORTAL_ON_BOOT, String(""));
    wifi = new WifiConnector(&logger, chipId);
    const bool wifiConnected = wifi->begin(forcePortal);
    taskManager.schedule(repeatMillis(250), [] { wifi->run(); });
    if (!wifiConnected) {
        runSetupPortal();
        return;
    }

    webApi = new WebApi(&storage, &logger, activePlugin, &registry, &monitor, resetDevice);
    webApi->begin();
    startMqtt(chipId);
    OtaUpdates::begin(&logger);

    const int samplingInterval = activePlugin ? activePlugin->getSamplingInterval() : 10;
    const int publishInterval = activePlugin ? activePlugin->getPublishInterval() : samplingInterval;
    taskManager.scheduleFixedRate(2000, [] { webApi->run(mqttConnected()); });
    taskManager.scheduleFixedRate(5000, [] { if (mqtt) mqtt->run(); });
    taskManager.scheduleFixedRate(samplingInterval * 1000, [] { sampleSensor(); });
    taskManager.scheduleFixedRate(publishInterval * 1000, [] { if (mqtt) mqtt->publish(); });
    taskManager.scheduleFixedRate(1000, [] { everySecond(); });

    logger.info("Setup complete. Sampling every " + String(samplingInterval) +
                "s, publishing every " + String(publishInterval) + "s.");
}

void loop()
{
    OtaUpdates::handle();
    ledController.run();
    taskManager.runLoop();
}
