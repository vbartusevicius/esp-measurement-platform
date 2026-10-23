#include "DeviceMonitor.h"
#include "Logger.h"
#include "Parameter.h"
#include "RelayOutput.h"
#include "ScreenModel.h"
#include "Storage.h"
#include <cstdio>
#include <cstring>

void DeviceMonitor::begin(Storage* storage, Logger* logger, RelayOutput* relay)
{
    this->storage = storage;
    this->logger = logger;
    this->relay = relay;
    this->loadLimits();
}

float DeviceMonitor::readLimit(const char* key) const
{
    String text = this->storage->getParameter(key, "");
    return text.isEmpty() ? NAN : text.toFloat();
}

bool DeviceMonitor::limitEnabled(const char* switchKey, const char* valueKey) const
{
    String on = this->storage->getParameter(switchKey, "");
    if (on.isEmpty()) return !this->storage->getParameter(valueKey, "").isEmpty();
    return on == "1";
}

void DeviceMonitor::loadLimits()
{
    if (!this->storage) return;
    float low = this->limitEnabled(Parameter::LIMIT_LOW_ON, Parameter::LIMIT_LOW) ? this->readLimit(Parameter::LIMIT_LOW) : NAN;
    float high = this->limitEnabled(Parameter::LIMIT_HIGH_ON, Parameter::LIMIT_HIGH) ? this->readLimit(Parameter::LIMIT_HIGH) : NAN;
    float hysteresis = this->readLimit(Parameter::LIMIT_HYSTERESIS);
    String mode = this->storage->getParameter(Parameter::RELAY_MODE, "manual");
    LimitMonitor::RelayMode relayMode = this->relayAvailable() ? LimitMonitor::parseMode(mode.c_str()) : LimitMonitor::RelayMode::MANUAL;
    this->limitMonitor.configure(low, high, hysteresis, relayMode);
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
    if (this->limitMonitor.relayMode() != LimitMonitor::RelayMode::MANUAL) {
        if (this->logger) this->logger->warning(String("Relay command from ") + source + " ignored: relay follows the limit rule");
        return false;
    }
    this->applyRelay(on, source, nowMs);
    return true;
}

void DeviceMonitor::evaluate(const ScreenModel& model, unsigned long nowMs)
{
    if (!this->sensorKnown || model.sensorOk != this->sensorOk) {
        if (this->sensorKnown || !model.sensorOk) {
            this->event(model.sensorOk ? "SENSOR OK" : "SENSOR FAULT", model.signal.c_str(), nowMs);
        }
        this->sensorKnown = true;
        this->sensorOk = model.sensorOk;
    }

    if (this->limitMonitor.update(model.value, model.valid)) {
        char detail[EventLog::TEXT_LENGTH + 1];
        if (this->limitMonitor.alarm()) {
            const char* unit = strlen(model.unit) <= 3 ? model.unit : "";
            snprintf(detail, sizeof(detail), "%s%s%c%s", model.format(model.value).c_str(), unit,
                     this->limitMonitor.state() == LimitMonitor::State::BELOW ? '<' : '>',
                     model.format(this->limitMonitor.activeLimit()).c_str());
            this->event(this->limitMonitor.state() == LimitMonitor::State::BELOW ? "MIN LIMIT!" : "MAX LIMIT!", detail, nowMs);
            if (this->logger) this->logger->warning(String("Limit alarm: ") + detail);
        } else {
            snprintf(detail, sizeof(detail), "%s%s", model.format(model.value).c_str(), strlen(model.unit) <= 3 ? model.unit : "");
            this->event("LIMIT CLEAR", detail, nowMs);
            if (this->logger) this->logger->info(String("Limit cleared: ") + detail);
        }
    }

    bool demand = false;
    if (this->limitMonitor.relayDemand(demand)) this->applyRelay(demand, "AUTO LIMIT", nowMs);
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
