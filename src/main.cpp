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
#include "SensorHub.h"
#include "Storage.h"
#include "Version.h"
#include "WebApi.h"
#include "WifiConnector.h"

#include "AnalogDistancePlugin.h"
#include "AnalogVoltagePlugin.h"
#include "RadiationCounterPlugin.h"
#include "UltrasonicDistancePlugin.h"
#include "PulseMeterPlugin.h"

HAL hal;
Logger logger;
Storage storage;
LedController ledController;
Display display;
PluginRegistry registry;
SensorHub hub;
RelayOutput relay;
ButtonLadder buttonLadder;
DeviceMonitor monitor;

AnalogDistancePlugin analogDistancePlugin;
UltrasonicDistancePlugin ultrasonicDistancePlugin;
RadiationCounterPlugin radiationCounterPlugin;
AnalogVoltagePlugin analogVoltagePlugin;
PulseMeterPlugin pulseMeterPlugin;

// Created in setup() once WiFi and the sensors are known
WifiConnector* wifi = nullptr;
MqttClient* mqtt = nullptr;
WebApi* webApi = nullptr;

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
    for (size_t i = 0; i < hub.size(); i++) {
        ScreenModel screen;
        hub.plugin(i).getScreen(screen);
        frame.screens.push_back(screen);
    }
    frame.monitor = &monitor;
    frame.mqttConnected = mqttConnected();
    frame.errors = logger.errors();
    display.run(frame);
}

// PAGE: dismisses a pending alert first, otherwise moves to the next sensor
// (then the device, log and WiFi pages).
void pagePressed()
{
    if (monitor.alertPending()) monitor.dismissAlert();
    else display.nextPage(hub.size());
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

// Every second: each sensor samples on its own interval, then its limits are checked.
void sampleSensors()
{
    const unsigned long now = millis();
    bool sampled = false;
    for (size_t i = 0; i < hub.size(); i++) {
        if (!hub.sampleDue(i, now)) continue;
        hub.plugin(i).loop();
        ScreenModel screen;
        if (hub.plugin(i).getScreen(screen)) monitor.evaluate(i, screen, now);
        sampled = true;
    }
    if (sampled) ledController.click();
}

void everySecond()
{
    monitor.updateNetwork(WiFi.status() == WL_CONNECTED, mqttConnected(), WiFi.SSID() + " " + String(WiFi.RSSI()),
                          storage.getParameter(Parameter::MQTT_HOST, ""), millis());
    refreshDisplay();
    updateNetworkLed(false);
}

void startSensors()
{
    IPlugin* plugins[] = {&analogDistancePlugin, &ultrasonicDistancePlugin, &radiationCounterPlugin, &analogVoltagePlugin,
                          &pulseMeterPlugin};
    for (IPlugin* plugin : plugins) registry.add(plugin);

    hub.begin(&storage, registry, &hal, &logger, &ledController);
    for (size_t i = 0; i < hub.size(); i++) monitor.addSensor(hub.plugin(i).getId(), &hub.settings(i));
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
    if (storage.getParameter(Parameter::MQTT_DEVICE).isEmpty()) {
        logger.warning("MQTT device name not configured, skipping MQTT");
        return;
    }
    mqtt = new MqttClient(&storage, &logger, &hub, chipId);
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
    startSensors();

    const bool forcePortal = storage.getParameter(Parameter::PORTAL_ON_BOOT, "") == "1";
    if (forcePortal) storage.saveParameter(Parameter::PORTAL_ON_BOOT, String(""));
    wifi = new WifiConnector(&logger, chipId);
    const bool wifiConnected = wifi->begin(forcePortal);
    taskManager.schedule(repeatMillis(250), [] { wifi->run(); });
    if (!wifiConnected) {
        runSetupPortal();
        return;
    }

    webApi = new WebApi(&storage, &logger, &hub, &registry, &monitor, resetDevice);
    webApi->begin();
    startMqtt(chipId);
    OtaUpdates::begin(&logger);

    taskManager.scheduleFixedRate(2000, [] { webApi->run(mqttConnected()); });
    taskManager.scheduleFixedRate(5000, [] { if (mqtt) mqtt->run(); });
    // Sensors keep their own sampling and publishing intervals (SensorHub)
    taskManager.scheduleFixedRate(1000, [] {
        sampleSensors();
        if (mqtt) mqtt->publish(millis());
        everySecond();
    });

    logger.info("Setup complete. " + String((unsigned long)hub.size()) + " sensor(s) running.");
}

void loop()
{
    OtaUpdates::handle();
    ledController.run();
    taskManager.runLoop();
}
