#include "aria_settings.h"

#include <Preferences.h>

#include "aria_config.h"

namespace {

Preferences prefs;
AriaSettings current;

const char *NAMESPACE = "aria";

// Short keys: NVS keys are capped at 15 characters.
const char *KEY_GAS = "gas_th";
const char *KEY_DARK = "dark_th";
const char *KEY_TEMP = "temp_th";
const char *KEY_HOLD = "hold_s";
const char *KEY_WARMUP = "warmup_s";

bool inRange(float value, float low, float high) {
  return value >= low && value <= high;
}

void persist() {
  prefs.begin(NAMESPACE, false);
  prefs.putFloat(KEY_GAS, current.gasThresholdPct);
  prefs.putFloat(KEY_DARK, current.darkThresholdPct);
  prefs.putFloat(KEY_TEMP, current.tempFanThresholdC);
  prefs.putUInt(KEY_HOLD, current.motionLightHoldS);
  prefs.putUInt(KEY_WARMUP, current.warmupS);
  prefs.end();
}

}  // namespace

void settingsBegin() {
  prefs.begin(NAMESPACE, true);  // read-only
  current.gasThresholdPct = prefs.getFloat(KEY_GAS, DEFAULT_GAS_THRESHOLD_PCT);
  current.darkThresholdPct = prefs.getFloat(KEY_DARK, DEFAULT_DARK_THRESHOLD_PCT);
  current.tempFanThresholdC = prefs.getFloat(KEY_TEMP, DEFAULT_TEMP_FAN_THRESHOLD_C);
  current.motionLightHoldS = prefs.getUInt(KEY_HOLD, DEFAULT_MOTION_LIGHT_HOLD_S);
  current.warmupS = prefs.getUInt(KEY_WARMUP, DEFAULT_WARMUP_S);
  prefs.end();

  // A corrupted or hand-edited NVS entry must not leave the safety rule disarmed.
  if (!inRange(current.gasThresholdPct, GAS_THRESHOLD_MIN, GAS_THRESHOLD_MAX)) {
    current.gasThresholdPct = DEFAULT_GAS_THRESHOLD_PCT;
  }
  if (!inRange(current.darkThresholdPct, DARK_THRESHOLD_MIN, DARK_THRESHOLD_MAX)) {
    current.darkThresholdPct = DEFAULT_DARK_THRESHOLD_PCT;
  }
  if (!inRange(current.tempFanThresholdC, TEMP_FAN_MIN, TEMP_FAN_MAX)) {
    current.tempFanThresholdC = DEFAULT_TEMP_FAN_THRESHOLD_C;
  }
  if (current.motionLightHoldS < MOTION_HOLD_MIN || current.motionLightHoldS > MOTION_HOLD_MAX) {
    current.motionLightHoldS = DEFAULT_MOTION_LIGHT_HOLD_S;
  }
  if (current.warmupS > WARMUP_MAX) {
    current.warmupS = DEFAULT_WARMUP_S;
  }

  Serial.printf(
      "[settings] gas=%.1f%% dark=%.1f%% fan=%.1fC hold=%us warmup=%us\n",
      current.gasThresholdPct, current.darkThresholdPct, current.tempFanThresholdC,
      current.motionLightHoldS, current.warmupS);
}

AriaSettings settingsGet() { return current; }

bool settingsApply(const bool present[SETTING_COUNT], const float values[SETTING_COUNT],
                   String &error) {
  // Validate every supplied field first, so a partly-valid body changes nothing.
  if (present[SETTING_GAS] &&
      !inRange(values[SETTING_GAS], GAS_THRESHOLD_MIN, GAS_THRESHOLD_MAX)) {
    error = "gas_threshold_pct must be between 0 and 100";
    return false;
  }
  if (present[SETTING_DARK] &&
      !inRange(values[SETTING_DARK], DARK_THRESHOLD_MIN, DARK_THRESHOLD_MAX)) {
    error = "dark_threshold_pct must be between 0 and 100";
    return false;
  }
  if (present[SETTING_TEMP_FAN] &&
      !inRange(values[SETTING_TEMP_FAN], TEMP_FAN_MIN, TEMP_FAN_MAX)) {
    error = "temp_fan_threshold_c must be between 0 and 60";
    return false;
  }
  if (present[SETTING_MOTION_HOLD] &&
      !inRange(values[SETTING_MOTION_HOLD], MOTION_HOLD_MIN, MOTION_HOLD_MAX)) {
    error = "motion_light_hold_s must be between 5 and 3600";
    return false;
  }
  if (present[SETTING_WARMUP] && !inRange(values[SETTING_WARMUP], WARMUP_MIN, WARMUP_MAX)) {
    error = "warmup_s must be between 0 and 600";
    return false;
  }

  // Build the new state as a copy, then swap it in — no half-applied config.
  AriaSettings updated = current;
  if (present[SETTING_GAS]) updated.gasThresholdPct = values[SETTING_GAS];
  if (present[SETTING_DARK]) updated.darkThresholdPct = values[SETTING_DARK];
  if (present[SETTING_TEMP_FAN]) updated.tempFanThresholdC = values[SETTING_TEMP_FAN];
  if (present[SETTING_MOTION_HOLD]) {
    updated.motionLightHoldS = (uint32_t)values[SETTING_MOTION_HOLD];
  }
  if (present[SETTING_WARMUP]) updated.warmupS = (uint32_t)values[SETTING_WARMUP];

  current = updated;
  persist();
  Serial.println("[settings] updated and persisted to NVS");
  return true;
}
