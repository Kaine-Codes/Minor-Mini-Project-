#pragma once

#include <Arduino.h>

#include "aria_sensors.h"

/** Actuator + automation state as reported over the API. */
struct AriaActuators {
  bool led;
  bool fan;
  bool manualMode;
  bool gasAlarm;
  bool warmedUp;
};

void automationBegin();

/**
 * Re-evaluate the edge rules and drive the actuators.
 *
 * This is the whole point of the architecture: it runs on the node, on a timer, with no
 * network involvement. The backend being down, asleep, or unreachable changes nothing
 * about whether the gas rule fires.
 *
 * Rule priority (see docs/CONTRACT.md):
 *   1. Gas alarm  — overrides everything, including manual mode
 *   2. Manual mode — hold the last commanded state
 *   3. Motion + darkness -> light on, held after last motion
 *   4. Temperature -> fan on
 */
void automationEvaluate(const AriaSample &sample);

/** Current actuator/automation state. */
AriaActuators automationState();

/** Apply a manual override. Returns the state actually in effect afterwards. */
AriaActuators automationSetActuators(bool hasLed, bool led, bool hasFan, bool fan,
                                     bool hasMode, bool manualMode);
