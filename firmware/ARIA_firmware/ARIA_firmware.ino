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
// #include <WiFiManager.h>  // not needed — using hardcoded hotspot credentials
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
const char* WIFI_SSID         = "THESHINEMACHINE 3140";
const char* WIFI_PASSWORD     = "1P3697{q";

// Fallback IP — used only when mDNS resolution of "aria" fails.
// 192.168.137.1 is the default gateway for Windows Mobile Hotspot.
const char* FALLBACK_SERVER_IP = "192.168.137.1";
const int   SERVER_PORT        = 5000;

const unsigned long POST_INTERVAL_MS   = 5000;   // send readings every 5s
const unsigned long COMMAND_POLL_MS    = 3000;   // check for overrides every 3s
const float GAS_SAFETY_THRESHOLD       = 1800.0; // raw ADC value - CALIBRATE THIS

DHT dht(DHTPIN, DHTTYPE);

// Resolved server IP — filled once during setup via mDNS or fallback
String resolvedServerIP = "";

unsigned long lastPostTime = 0;
unsigned long lastCommandPoll = 0;
unsigned long lastDhtTime = 0;
float lastTemp = -1;
float lastHum = -1;
bool latchedVibration = false;
bool latchedMotion = false;
bool localGasOverrideActive = false;

// ---------------- mDNS SERVER DISCOVERY ----------------
// Tries to resolve "aria.local" so the ESP32 can find the backend
// on ANY network without a hardcoded IP. Falls back to the known
// Windows Mobile Hotspot gateway if mDNS doesn't work (some mobile
// hotspots block multicast traffic).
void resolveServer() {
  Serial.println("Resolving backend via mDNS (aria.local)...");
  IPAddress serverIP = MDNS.queryHost("aria", 5000);  // 5-second timeout

  if (serverIP != IPAddress(0, 0, 0, 0)) {
    resolvedServerIP = serverIP.toString();
    Serial.print("mDNS resolved aria.local -> ");
    Serial.println(resolvedServerIP);
  } else {
    resolvedServerIP = String(FALLBACK_SERVER_IP);
    Serial.print("mDNS failed, using fallback IP -> ");
    Serial.println(resolvedServerIP);
  }
}

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

  // ---- Connect to WiFi ----
  Serial.print("Connecting to ");
  Serial.println(WIFI_SSID);
  
  // LOWER WIFI POWER TO PREVENT BROWNOUT REBOOTS ON EXTERNAL POWER
  WiFi.setTxPower(WIFI_POWER_8_5dBm); 
  
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 40) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nFailed to connect to WiFi, restarting...");
    delay(3000);
    ESP.restart();
  }
  Serial.println();

  Serial.print("Connected to WiFi. IP: ");
  Serial.println(WiFi.localIP());

  // ---- mDNS: register this node and discover the backend ----
  if (!MDNS.begin("aria-node")) {
    Serial.println("mDNS responder failed to start (non-fatal)");
  }

  resolveServer();

  Serial.println("MQ-135 warming up (~60s recommended before trusting readings)");
}

// ---------------- MAIN LOOP ----------------
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost, attempting reconnect...");
    WiFi.reconnect();
    delay(2000);
    if (WiFi.status() == WL_CONNECTED) {
      resolveServer();  // re-discover backend after reconnect
    }
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
  int gasRaw = analogRead(MQ135_PIN);
  
  // The user's LDR circuit is pulling the voltage down when exposed to light.
  // We invert the 12-bit ADC value (0-4095) in software so that:
  // Dark = 0, Bright = 4095.
  int lightRaw = 4095 - analogRead(LDR_PIN);

  // ---------------------------------------------------------
  // EDGE-FIRST SAFETY LOGIC
  // This does NOT wait for the server. If gas exceeds a safe
  // threshold, the fan is triggered locally and immediately.
  // ---------------------------------------------------------
  // Important: MQ-135 reads artificially HIGH during its first 60 seconds
  // of heating up. We MUST ignore it during this time, otherwise the motor
  // turns on instantly at boot, draws huge stall current, and restarts the ESP32!
  if (millis() > 60000 && gasRaw > GAS_SAFETY_THRESHOLD) {
    if (!localGasOverrideActive) {
      Serial.println("!! GAS THRESHOLD EXCEEDED - local override: fan ON !!");
      motorForward();
      localGasOverrideActive = true;
    }
  } else if (localGasOverrideActive && gasRaw <= GAS_SAFETY_THRESHOLD) {
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
  return "http://" + resolvedServerIP + ":" + String(SERVER_PORT);
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
