#include "aria_api.h"

#include <ArduinoJson.h>

#include "aria_automation.h"
#include "aria_config.h"
#include "aria_sensors.h"
#include "aria_settings.h"

namespace {

const size_t MAX_BODY_BYTES = 1024;

void sendJson(AsyncWebServerRequest *request, int status, const JsonDocument &doc) {
  String body;
  serializeJson(doc, body);
  request->send(status, "application/json", body);
}

void sendError(AsyncWebServerRequest *request, int status, const String &message) {
  JsonDocument doc;
  doc["error"] = message;
  sendJson(request, status, doc);
}

void fillConfig(JsonDocument &doc) {
  const AriaSettings settings = settingsGet();
  doc["gas_threshold_pct"] = settings.gasThresholdPct;
  doc["dark_threshold_pct"] = settings.darkThresholdPct;
  doc["temp_fan_threshold_c"] = settings.tempFanThresholdC;
  doc["motion_light_hold_s"] = settings.motionLightHoldS;
  doc["warmup_s"] = settings.warmupS;
}

void fillActuators(JsonDocument &doc, const AriaActuators &state) {
  doc["led"] = state.led;
  doc["fan"] = state.fan;
  doc["mode"] = state.manualMode ? "manual" : "auto";
}

// --- GET /health -----------------------------------------------------------
void handleHealth(AsyncWebServerRequest *request) {
  JsonDocument doc;
  doc["ok"] = true;
  doc["node_id"] = NODE_ID;
  doc["firmware"] = FIRMWARE_VERSION;
  doc["uptime_ms"] = millis();
  sendJson(request, 200, doc);
}

// --- GET /sensors ----------------------------------------------------------
void handleSensors(AsyncWebServerRequest *request) {
  const AriaSample sample = sensorsRead();
  const AriaActuators state = automationState();

  JsonDocument doc;
  doc["node_id"] = NODE_ID;
  doc["uptime_ms"] = millis();

  // Report null rather than a fabricated number when the DHT22 has not given us a
  // valid reading — the backend and dashboard both handle nulls explicitly.
  if (sample.dhtValid) {
    doc["temperature_c"] = serialized(String(sample.temperatureC, 1));
    doc["humidity_pct"] = serialized(String(sample.humidityPct, 1));
  } else {
    doc["temperature_c"] = nullptr;
    doc["humidity_pct"] = nullptr;
  }

  doc["gas_raw"] = sample.gasRaw;
  doc["gas_pct"] = serialized(String(sample.gasPct, 1));
  doc["light_raw"] = sample.lightRaw;
  doc["light_pct"] = serialized(String(sample.lightPct, 1));
  doc["motion"] = sample.motion;

  JsonObject actuators = doc["actuators"].to<JsonObject>();
  actuators["led"] = state.led;
  actuators["fan"] = state.fan;

  JsonObject edge = doc["edge"].to<JsonObject>();
  edge["gas_alarm"] = state.gasAlarm;
  edge["warmed_up"] = state.warmedUp;
  edge["mode"] = state.manualMode ? "manual" : "auto";

  sendJson(request, 200, doc);
}

// --- GET /config -----------------------------------------------------------
void handleGetConfig(AsyncWebServerRequest *request) {
  JsonDocument doc;
  fillConfig(doc);
  sendJson(request, 200, doc);
}

/** Parse an accumulated request body into a JsonDocument. */
bool parseBody(uint8_t *data, size_t len, JsonDocument &doc, String &error) {
  if (len == 0) {
    error = "empty request body";
    return false;
  }
  if (len > MAX_BODY_BYTES) {
    error = "request body too large";
    return false;
  }
  const DeserializationError err = deserializeJson(doc, data, len);
  if (err) {
    error = String("malformed JSON: ") + err.c_str();
    return false;
  }
  if (!doc.is<JsonObject>()) {
    error = "body must be a JSON object";
    return false;
  }
  return true;
}

// --- POST /actuators -------------------------------------------------------
void handleSetActuators(AsyncWebServerRequest *request, uint8_t *data, size_t len) {
  JsonDocument doc;
  String error;
  if (!parseBody(data, len, doc, error)) {
    sendError(request, 400, error);
    return;
  }

  JsonObject body = doc.as<JsonObject>();
  for (JsonPair kv : body) {
    const String key = kv.key().c_str();
    if (key != "led" && key != "fan" && key != "mode") {
      sendError(request, 400, "unknown field: " + key);
      return;
    }
  }

  const bool hasLed = body["led"].is<bool>();
  const bool hasFan = body["fan"].is<bool>();
  if (body["led"].is<JsonVariant>() && !body["led"].isNull() && !hasLed) {
    sendError(request, 400, "led must be a boolean");
    return;
  }
  if (body["fan"].is<JsonVariant>() && !body["fan"].isNull() && !hasFan) {
    sendError(request, 400, "fan must be a boolean");
    return;
  }

  bool hasMode = false;
  bool manualMode = false;
  if (!body["mode"].isNull()) {
    const String mode = body["mode"].as<String>();
    if (mode != "auto" && mode != "manual") {
      sendError(request, 400, "mode must be 'auto' or 'manual'");
      return;
    }
    hasMode = true;
    manualMode = (mode == "manual");
  }

  if (!hasLed && !hasFan && !hasMode) {
    sendError(request, 400, "provide at least one of: led, fan, mode");
    return;
  }

  const AriaActuators state = automationSetActuators(
      hasLed, body["led"].as<bool>(), hasFan, body["fan"].as<bool>(), hasMode, manualMode);

  JsonDocument response;
  fillActuators(response, state);
  sendJson(request, 200, response);
}

// --- POST /config ----------------------------------------------------------
void handleSetConfig(AsyncWebServerRequest *request, uint8_t *data, size_t len) {
  JsonDocument doc;
  String error;
  if (!parseBody(data, len, doc, error)) {
    sendError(request, 400, error);
    return;
  }

  static const char *KEYS[SETTING_COUNT] = {
      "gas_threshold_pct", "dark_threshold_pct", "temp_fan_threshold_c",
      "motion_light_hold_s", "warmup_s"};

  JsonObject body = doc.as<JsonObject>();
  for (JsonPair kv : body) {
    bool known = false;
    for (int i = 0; i < SETTING_COUNT; i++) {
      if (strcmp(kv.key().c_str(), KEYS[i]) == 0) {
        known = true;
        break;
      }
    }
    if (!known) {
      sendError(request, 400, String("unknown field: ") + kv.key().c_str());
      return;
    }
  }

  bool present[SETTING_COUNT] = {false, false, false, false, false};
  float values[SETTING_COUNT] = {0, 0, 0, 0, 0};
  bool any = false;

  for (int i = 0; i < SETTING_COUNT; i++) {
    JsonVariant value = body[KEYS[i]];
    if (value.isNull()) continue;
    if (!value.is<float>() && !value.is<int>()) {
      sendError(request, 400, String(KEYS[i]) + " must be a number");
      return;
    }
    present[i] = true;
    values[i] = value.as<float>();
    any = true;
  }

  if (!any) {
    sendError(request, 400, "provide at least one threshold to update");
    return;
  }

  if (!settingsApply(present, values, error)) {
    sendError(request, 400, error);
    return;
  }

  JsonDocument response;
  fillConfig(response);
  sendJson(request, 200, response);
}

}  // namespace

void apiRegisterRoutes(AsyncWebServer &server) {
  server.on("/health", HTTP_GET, handleHealth);
  server.on("/sensors", HTTP_GET, handleSensors);
  server.on("/config", HTTP_GET, handleGetConfig);

  // ESPAsyncWebServer delivers POST bodies in chunks; these handlers assume the small
  // single-chunk bodies this contract uses (all well under one MTU).
  server.on(
      "/actuators", HTTP_POST, [](AsyncWebServerRequest *request) {},
      nullptr,
      [](AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index,
         size_t total) { handleSetActuators(request, data, len); });

  server.on(
      "/config", HTTP_POST, [](AsyncWebServerRequest *request) {},
      nullptr,
      [](AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index,
         size_t total) { handleSetConfig(request, data, len); });

  server.onNotFound([](AsyncWebServerRequest *request) {
    sendError(request, 404, "unknown path");
  });
}
