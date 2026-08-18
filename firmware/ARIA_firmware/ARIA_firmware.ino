/*
 * ARIA - Adaptive Room Intelligence & Automation
 * ESP32 Firmware (Single Node)
 *
 * Responsibilities:
 *  - First-boot WiFi setup via captive portal (WiFiManager)
 *  - Read DHT22 (temp/humidity), MQ-135 (gas), LDR (light), PIR/IR (motion)
 *  - EDGE-FIRST SAFETY: if gas exceeds threshold, react locally and
 *    immediately (fan ON) without waiting on the backend server.
 *  - POST readings to backend every few seconds (mDNS: aria.local)
 *  - Poll backend for manual/remote override commands (LED, fan)
 *  - Drive LED directly via GPIO, drive DC motor via L298N module
 *
 * Libraries required (install via Arduino Library Manager):
 *  - WiFiManager by tzapu
 *  - DHT sensor library by Adafruit (+ Adafruit Unified Sensor dependency)
 *  - ArduinoJson by Benoit Blanchon
 *  - ESPmDNS (bundled with ESP32 board package)
 */

#include <WiFi.h>
#include <WiFiManager.h>
#include <ESPmDNS.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ---------------- PIN MAPPING ----------------
#define DHTPIN        4      // DHT22 data pin
#define DHTTYPE       DHT22
#define MQ135_PIN     34     // Analog (ADC1)
#define LDR_PIN       35     // Analog (ADC1)
#define PIR_PIN       27     // Digital input
#define VIBRATION_PIN 13     // SW-804 vibration sensor, digital input
#define LED_PIN       26     // Digital output (light actuator)
#define MOTOR_IN1     25     // L298N IN1  NMBBBBBV
#define MOTOR_IN2     33     // L298N IN2
#define MOTOR_ENA     32     // L298N ENA (PWM speed, tie HIGH or PWM)

// ---------------- CONFIG ----------------
// mDNS auto-discovery: the ESP32 finds the backend at "aria.local"
// If your router blocks mDNS, uncomment the hardcoded IP line instead:
// const char* SERVER_HOSTNAME = "192.168.1.60";  // your laptop's current Wi-Fi IP (may change)
const char* SERVER_HOSTNAME   = "aria.local";
const int   SERVER_PORT       = 5000;
const unsigned long POST_INTERVAL_MS   = 5000;   // send readings every 5s
const unsigned long COMMAND_POLL_MS    = 3000;   // check for overrides every 3s
const float GAS_SAFETY_THRESHOLD       = 1800.0; // raw ADC value - CALIBRATE THIS

DHT dht(DHTPIN, DHTTYPE);

unsigned long lastPostTime = 0;
unsigned long lastCommandPoll = 0;
unsigned long lastDhtTime = 0;
float lastTemp = -1;
float lastHum = -1;
bool latchedVibration = false;
bool latchedMotion = false;
bool localGasOverrideActive = false;

// ---------------- SETUP ----------------
void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(PIR_PIN, INPUT);
  pinMode(VIBRATION_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
  pinMode(MOTOR_IN1, OUTPUT);
  pinMode(MOTOR_IN2, OUTPUT);
  pinMode(MOTOR_ENA, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  motorStop();

  dht.begin();

  // ---- WiFi setup via captive portal ----
  // On first boot (or if saved WiFi fails), ESP32 hosts its own AP called
  // "ARIA-Setup". Connect to it from a phone, a captive portal page pops up
  // automatically -- enter your home WiFi name + password there.
  WiFiManager wm;
  wm.setConfigPortalTimeout(180); // 3 min timeout, then retries/reboots
  bool connected = wm.autoConnect("ARIA-Setup");

  if (!connected) {
    Serial.println("Failed to connect to WiFi, restarting...");
    delay(3000);
    ESP.restart();
  }

  Serial.print("Connected to WiFi. IP: ");
  Serial.println(WiFi.localIP());

  // ---- mDNS: so we can find the backend at aria.local ----
  if (!MDNS.begin("aria-node")) {
    Serial.println("mDNS responder failed to start (non-fatal)");
  }

  Serial.println("MQ-135 warming up (~60s recommended before trusting readings)");
}

// ---------------- MAIN LOOP ----------------
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost, attempting reconnect...");
    WiFi.reconnect();
    delay(2000);
    return;
  }

  // Fast poll for quick events (vibration pulses and IR triggers)
  if (digitalRead(VIBRATION_PIN) == HIGH) {
    latchedVibration = true;
  }
  // User noted they have an IR sensor (usually Active LOW) that was "always on"
  if (digitalRead(PIR_PIN) == LOW) {
    latchedMotion = true;
  }

  // DHT22 requires at least 2 seconds between readings, otherwise it returns NaN (flaky)
  if (millis() - lastDhtTime >= 2000 || lastDhtTime == 0) {
    lastDhtTime = millis();
    lastTemp = dht.readTemperature();
    lastHum = dht.readHumidity();
  }

  // Read analog sensors for safety loop
  int   gasRaw        = analogRead(MQ135_PIN);
  int   lightRaw       = analogRead(LDR_PIN);

  // ---------------------------------------------------------
  // EDGE-FIRST SAFETY LOGIC
  // This does NOT wait for the server. If gas exceeds a safe
  // threshold, the fan is triggered locally and immediately.
  // ---------------------------------------------------------
  if (gasRaw > GAS_SAFETY_THRESHOLD) {
    if (!localGasOverrideActive) {
      Serial.println("!! GAS THRESHOLD EXCEEDED - local override: fan ON !!");
      motorForward();
      localGasOverrideActive = true;
    }
  } else if (localGasOverrideActive) {
    // Only release the local override once levels drop back down.
    Serial.println("Gas levels normalized - releasing local override");
    motorStop();
    localGasOverrideActive = false;
  }

  // ---- POST readings to backend on interval ----
  if (millis() - lastPostTime >= POST_INTERVAL_MS) {
    lastPostTime = millis();
    postReadings(lastTemp, lastHum, gasRaw, lightRaw, latchedMotion, latchedVibration);
    
    // Clear latches after successfully attempting to post
    latchedVibration = false;
    latchedMotion = false;
  }

  // ---- Poll backend for manual/remote commands on interval ----
  // (skipped while a local safety override is active, so the
  // dashboard cannot accidentally switch the fan off during a
  // real gas event)
  if (!localGasOverrideActive && millis() - lastCommandPoll >= COMMAND_POLL_MS) {
    lastCommandPoll = millis();
    pollCommands();
  }

  // Remove large delay to allow fast polling of vibration/IR sensors
  delay(10);
}

// ---------------- ACTUATOR HELPERS ----------------
void motorForward() {
  digitalWrite(MOTOR_IN1, HIGH);
  digitalWrite(MOTOR_IN2, LOW);
  digitalWrite(MOTOR_ENA, HIGH);
}

void motorStop() {
  digitalWrite(MOTOR_IN1, LOW);
  digitalWrite(MOTOR_IN2, LOW);
  digitalWrite(MOTOR_ENA, LOW);
}

void setLED(bool on) {
  digitalWrite(LED_PIN, on ? HIGH : LOW);
}

// ---------------- NETWORKING ----------------
String serverBaseUrl() {
  return "http://" + String(SERVER_HOSTNAME) + ":" + String(SERVER_PORT);
}

void postReadings(float temperature, float humidity, int gasRaw, int lightRaw, bool motion, bool vibration) {
  HTTPClient http;
  String url = serverBaseUrl() + "/api/readings";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  doc["temperature"] = isnan(temperature) ? -1 : temperature;
  doc["humidity"]     = isnan(humidity) ? -1 : humidity;
  doc["gas_raw"]       = gasRaw;
  doc["light_raw"]     = lightRaw;
  doc["motion"]        = motion;
  doc["vibration"]     = vibration;
  doc["local_gas_override"] = localGasOverrideActive;

  String payload;
  serializeJson(doc, payload);

  int code = http.POST(payload);
  if (code <= 0) {
    Serial.print("POST /api/readings failed: ");
    Serial.println(http.errorToString(code));
  }
  http.end();
}

void pollCommands() {
  HTTPClient http;
  String url = serverBaseUrl() + "/api/commands";
  http.begin(url);
  int code = http.GET();

  if (code == 200) {
    String response = http.getString();
    StaticJsonDocument<128> doc;
    DeserializationError err = deserializeJson(doc, response);
    if (!err) {
      if (doc.containsKey("led")) {
        setLED(doc["led"].as<bool>());
      }
      if (doc.containsKey("fan")) {
        bool fanOn = doc["fan"].as<bool>();
        fanOn ? motorForward() : motorStop();
      }
    }
  }
  http.end();
}
