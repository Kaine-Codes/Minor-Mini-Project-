#include "aria_sensors.h"

#include <DHT.h>

#include "aria_config.h"

namespace {

DHT dht(PIN_DHT, DHT22);

// Cached DHT values: the sensor cannot be read faster than DHT_MIN_INTERVAL_MS, so
// polling it on every loop would mostly produce NaN.
float lastTempC = NAN;
float lastHumidityPct = NAN;
uint32_t lastDhtReadMs = 0;
bool dhtEverValid = false;

float toPercent(uint16_t raw) {
  return (float)raw * 100.0f / (float)ADC_MAX;
}

void readDhtIfDue() {
  const uint32_t now = millis();
  // Subtraction handles the ~49-day millis() rollover correctly with unsigned math.
  if (dhtEverValid && (now - lastDhtReadMs) < DHT_MIN_INTERVAL_MS) {
    return;
  }
  lastDhtReadMs = now;

  const float temp = dht.readTemperature();
  const float humidity = dht.readHumidity();

  // Keep the previous good reading on a failed poll rather than publishing a NaN
  // spike; the API still reports null if we have never had a valid read.
  if (!isnan(temp) && !isnan(humidity)) {
    lastTempC = temp;
    lastHumidityPct = humidity;
    dhtEverValid = true;
  }
}

}  // namespace

void sensorsBegin() {
  dht.begin();
  pinMode(PIN_PIR, INPUT);
  // GPIO 34/35 are input-only ADC1 pins; no pinMode needed for analogRead, but the
  // ADC range must be set explicitly or readings saturate near 2.5 V instead of 3.3 V.
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_MQ135, ADC_11db);
  analogSetPinAttenuation(PIN_LDR, ADC_11db);
  Serial.println("[sensors] initialised");
}

AriaSample sensorsRead() {
  readDhtIfDue();

  AriaSample sample;
  sample.gasRaw = (uint16_t)analogRead(PIN_MQ135);
  sample.gasPct = toPercent(sample.gasRaw);
  sample.lightRaw = (uint16_t)analogRead(PIN_LDR);
  sample.lightPct = toPercent(sample.lightRaw);
  sample.motion = digitalRead(PIN_PIR) == HIGH;
  sample.temperatureC = lastTempC;
  sample.humidityPct = lastHumidityPct;
  sample.dhtValid = dhtEverValid && !isnan(lastTempC) && !isnan(lastHumidityPct);
  return sample;
}
