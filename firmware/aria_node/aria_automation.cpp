#include "aria_automation.h"

#include "aria_config.h"
#include "aria_settings.h"

namespace {

bool ledOn = false;
bool fanOn = false;
bool manual = false;
bool alarmActive = false;
bool warmedUp = false;
uint32_t lastMotionMs = 0;
bool everSawMotion = false;

void driveLed(bool on) {
  ledOn = on;
  digitalWrite(PIN_LED, on ? HIGH : LOW);
}

void driveFan(bool on) {
  fanOn = on;
  // L298N: IN1/IN2 set direction, ENA enables the channel. One fixed direction is all
  // a demo fan needs, so IN2 stays low and ENA gates the motor.
  digitalWrite(PIN_MOTOR_IN1, on ? HIGH : LOW);
  digitalWrite(PIN_MOTOR_IN2, LOW);
  digitalWrite(PIN_MOTOR_ENA, on ? HIGH : LOW);
}

}  // namespace

void automationBegin() {
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_MOTOR_IN1, OUTPUT);
  pinMode(PIN_MOTOR_IN2, OUTPUT);
  pinMode(PIN_MOTOR_ENA, OUTPUT);
  driveLed(false);
  driveFan(false);
  Serial.println("[automation] initialised (edge-first, no server required)");
}

void automationEvaluate(const AriaSample &sample) {
  const AriaSettings settings = settingsGet();
  const uint32_t now = millis();

  warmedUp = (now / 1000UL) >= settings.warmupS;

  if (sample.motion) {
    lastMotionMs = now;
    everSawMotion = true;
  }

  // --- Rule 1: gas alarm. Highest priority, not overridable from the network. ---
  const bool alarm = warmedUp && sample.gasPct >= settings.gasThresholdPct;
  if (alarm != alarmActive) {
    Serial.printf("[automation] gas alarm %s (%.1f%% vs threshold %.1f%%)\n",
                  alarm ? "TRIGGERED" : "cleared", sample.gasPct, settings.gasThresholdPct);
  }
  alarmActive = alarm;

  if (alarm) {
    driveFan(true);
    driveLed(true);
    return;
  }

  // --- Rule 2: manual mode holds whatever was last commanded. ---
  if (manual) {
    return;
  }

  // --- Rule 3: motion in the dark turns the light on, with a hold-off. ---
  const bool withinHold =
      everSawMotion && (now - lastMotionMs) <= (settings.motionLightHoldS * 1000UL);
  const bool dark = sample.lightPct < settings.darkThresholdPct;
  driveLed(withinHold && dark);

  // --- Rule 4: temperature drives the fan. A failed DHT read leaves it off rather
  // than guessing. ---
  driveFan(sample.dhtValid && sample.temperatureC >= settings.tempFanThresholdC);
}

AriaActuators automationState() {
  AriaActuators state;
  state.led = ledOn;
  state.fan = fanOn;
  state.manualMode = manual;
  state.gasAlarm = alarmActive;
  state.warmedUp = warmedUp;
  return state;
}

AriaActuators automationSetActuators(bool hasLed, bool led, bool hasFan, bool fan,
                                     bool hasMode, bool manualMode) {
  if (hasMode) {
    manual = manualMode;
  }
  if (hasLed) {
    driveLed(led);
  }
  if (hasFan) {
    driveFan(fan);
  }

  // Re-assert the alarm response before returning, so the caller is told the state
  // actually in effect instead of one the next automation tick will overturn.
  if (alarmActive) {
    driveLed(true);
    driveFan(true);
  }
  return automationState();
}
