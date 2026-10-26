#include "DeviceMonitor.h"
#include <cstdio>
#include <cstring>
#include "Logger.h"
#include "Parameter.h"
#include "RelayOutput.h"
#include "ScreenModel.h"
#include "Settings.h"

void DeviceMonitor::begin(Settings* storage, Logger* logger, RelayOutput* relay)
{
    this->storage = storage;
    this->logger = logger;
    this->relay = relay;
    this->loadLimits();
}

void DeviceMonitor::addSensor(const char* id, Settings* sensorSettings)
{
    this->watches.push_back({id, sensorSettings, LimitMonitor(), false, false});
    this->loadLimits();
}

float DeviceMonitor::readLimit(const Settings& settings, const char* key)
{
    String text = settings.getParameter(key, "");
    return text.isEmpty() ? NAN : text.toFloat();
}

bool DeviceMonitor::limitEnabled(const Settings& settings, const char* switchKey, const char* valueKey)
{
    String on = settings.getParameter(switchKey, "");
    if (on.isEmpty()) return !settings.getParameter(valueKey, "").isEmpty();
    return on == "1";
}

void DeviceMonitor::loadLimits()
{
    if (!this->storage) return;
    String mode = this->storage->getParameter(Parameter::RELAY_MODE, "manual");
    this->mode = this->relayAvailable() ? LimitMonitor::parseMode(mode.c_str()) : LimitMonitor::RelayMode::MANUAL;
    const String sourceId = this->storage->getParameter(Parameter::RELAY_SOURCE, "");
    this->source = this->watches.empty() ? -1 : 0;   // default: the first sensor
    for (size_t i = 0; i < this->watches.size(); i++) {
        if (sourceId == this->watches[i].id) this->source = (int)i;
    }
    for (size_t i = 0; i < this->watches.size(); i++) {
        Watch& w = this->watches[i];
        const Settings& s = *w.settings;
        float low = limitEnabled(s, Parameter::LIMIT_LOW_ON, Parameter::LIMIT_LOW) ? readLimit(s, Parameter::LIMIT_LOW) : NAN;
        float high = limitEnabled(s, Parameter::LIMIT_HIGH_ON, Parameter::LIMIT_HIGH) ? readLimit(s, Parameter::LIMIT_HIGH) : NAN;
        w.limits.configure(low, high, readLimit(s, Parameter::LIMIT_HYSTERESIS),
                           (int)i == this->source ? this->mode : LimitMonitor::RelayMode::MANUAL);
    }
}

bool DeviceMonitor::relayAvailable() const
{
    return this->relay && this->relay->available();
}

bool DeviceMonitor::relayOn() const
{
    return this->relayAvailable() && this->relay->isOn();
}

void DeviceMonitor::event(const char* title, const char* detail, unsigned long nowMs)
{
    this->eventLog.add(title, detail, nowMs);
}

void DeviceMonitor::applyRelay(bool on, const char* source, unsigned long nowMs)
{
    if (!this->relayAvailable() || this->relay->isOn() == on) return;
    this->relay->set(on);
    if (on) this->relayOnCount++;
    this->event(on ? "RELAY ON" : "RELAY OFF", source, nowMs);
    if (this->logger) this->logger->info(String("Relay ") + (on ? "ON" : "OFF") + " (" + source + ")");
}

bool DeviceMonitor::commandRelay(bool on, const char* source, unsigned long nowMs)
{
    if (!this->relayAvailable()) return false;
    if (this->mode != LimitMonitor::RelayMode::MANUAL) {
        if (this->logger) this->logger->warning(String("Relay command from ") + source + " ignored: relay follows the limit rule");
        return false;
    }
    this->applyRelay(on, source, nowMs);
    return true;
}

int DeviceMonitor::pendingAlert() const
{
    for (size_t i = 0; i < this->watches.size(); i++) {
        if (this->watches[i].limits.alertPending()) return (int)i;
    }
    return -1;
}

void DeviceMonitor::dismissAlert()
{
    int i = this->pendingAlert();
    if (i >= 0) this->watches[i].limits.acknowledge();
}

void DeviceMonitor::dismissAlert(size_t index)
{
    if (index < this->watches.size()) this->watches[index].limits.acknowledge();
}

void DeviceMonitor::dismissAll()
{
    for (Watch& w : this->watches) w.limits.acknowledge();
}

// Event details name the sensor once more than one is running ("TANK 18%<20").
String DeviceMonitor::named(const ScreenModel& model, const String& text) const
{
    return this->watches.size() > 1 ? String(model.title) + " " + text : text;
}

void DeviceMonitor::evaluate(size_t index, const ScreenModel& model, unsigned long nowMs)
{
    if (index >= this->watches.size()) return;
    Watch& w = this->watches[index];
    if (!w.sensorKnown || model.sensorOk != w.sensorOk) {
        if (w.sensorKnown || !model.sensorOk) {
            this->event(model.sensorOk ? "SENSOR OK" : "SENSOR FAULT", this->named(model, model.signal).c_str(), nowMs);
        }
        w.sensorKnown = true;
        w.sensorOk = model.sensorOk;
    }

    LimitMonitor& limits = w.limits;
    if (limits.update(model.value, model.valid)) {
        char detail[EventLog::TEXT_LENGTH + 1];
        const char* unit = strlen(model.unit) <= 3 ? model.unit : "";
        if (limits.alarm()) {
            const bool below = limits.state() == LimitMonitor::State::BELOW;
            snprintf(detail, sizeof(detail), "%s", this->named(model, model.format(model.value) + unit + (below ? "<" : ">") +
                                                                  model.format(limits.activeLimit())).c_str());
            this->event(below ? "MIN LIMIT!" : "MAX LIMIT!", detail, nowMs);
            if (this->logger) this->logger->warning(String("Limit alarm: ") + detail);
        } else {
            snprintf(detail, sizeof(detail), "%s", this->named(model, model.format(model.value) + unit).c_str());
            this->event("LIMIT CLEAR", detail, nowMs);
            if (this->logger) this->logger->info(String("Limit cleared: ") + detail);
        }
    }

    bool demand = false;
    if ((int)index == this->source && limits.relayDemand(demand)) this->applyRelay(demand, "AUTO LIMIT", nowMs);
}

void DeviceMonitor::updateNetwork(bool wifiConnected, bool mqttConnected, const String& wifiDetail, const String& mqttDetail, unsigned long nowMs)
{
    if (!this->networkKnown || wifiConnected != this->wifiUp) {
        if (this->networkKnown || wifiConnected) this->event(wifiConnected ? "WIFI ONLINE" : "WIFI LOST", wifiDetail.c_str(), nowMs);
        this->wifiUp = wifiConnected;
    }
    if (!this->networkKnown || mqttConnected != this->mqttUp) {
        if (this->networkKnown || mqttConnected) this->event(mqttConnected ? "MQTT ONLINE" : "MQTT OFFLINE", mqttDetail.c_str(), nowMs);
        this->mqttUp = mqttConnected;
    }
    this->networkKnown = true;
}
