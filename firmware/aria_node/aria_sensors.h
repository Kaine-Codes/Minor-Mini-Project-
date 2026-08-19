#pragma once

#include <Arduino.h>

/** One sampled set of sensor values. */
struct AriaSample {
  float temperatureC;   // NAN when the DHT22 read failed
  float humidityPct;    // NAN when the DHT22 read failed
  uint16_t gasRaw;
  float gasPct;
  uint16_t lightRaw;
  float lightPct;
  bool motion;
  bool dhtValid;
};

void sensorsBegin();

/**
 * Read all sensors.
 *
 * The DHT22 is rate-limited internally (it physically cannot be read faster than
 * ~2 s); between reads the last good value is returned so callers can poll freely.
 */
AriaSample sensorsRead();
