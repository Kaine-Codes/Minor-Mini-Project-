#pragma once

#include <Arduino.h>

/**
 * Threshold settings, persisted to NVS (ESP32 Preferences).
 *
 * Persistence is what makes "edge-first automation" true rather than a slogan: the
 * thresholds survive a power cycle and stay enforced with the backend switched off. If
 * they lived only in RAM, or only on the server, a reboot would silently disarm the
 * node's safety rule.
 */
struct AriaSettings {
  float gasThresholdPct;
  float darkThresholdPct;
  float tempFanThresholdC;
  uint32_t motionLightHoldS;
  uint32_t warmupS;
};

/** Load from NVS, falling back to the compiled defaults on first boot. */
void settingsBegin();

/** Current settings (a copy — callers cannot mutate the stored state directly). */
AriaSettings settingsGet();

/**
 * Validate and apply a partial update, then persist it.
 *
 * All-or-nothing: if any supplied field is out of range, nothing is written and the
 * node keeps its previous configuration. `error` receives a human-readable reason.
 * Returns true on success.
 */
bool settingsApply(const bool present[5], const float values[5], String &error);

// Indices into the present/values arrays used by settingsApply.
enum SettingIndex {
  SETTING_GAS = 0,
  SETTING_DARK = 1,
  SETTING_TEMP_FAN = 2,
  SETTING_MOTION_HOLD = 3,
  SETTING_WARMUP = 4,
  SETTING_COUNT = 5
};
