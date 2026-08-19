#pragma once

// ---------------------------------------------------------------------------
// ARIA node — pin map and constants
//
// IMPORTANT (ESP32 hardware constraint): analog sensors MUST use ADC1 pins
// (GPIO 32–39). ADC2 shares hardware with the WiFi radio and cannot be read
// while WiFi is active — reads silently return garbage. Both analog sensors
// below are therefore on ADC1. This is the single most common cause of
// "my sensor works until I connect to WiFi" on ESP32.
//
// GPIO 34–39 are input-only (no internal pull-up/pull-down, no output).
// ---------------------------------------------------------------------------

// --- Sensors ---------------------------------------------------------------
#define PIN_DHT           4    // DHT22 data (any GPIO)
#define PIN_MQ135        34    // MQ-135 analog out — ADC1, input-only
#define PIN_LDR          35    // LDR voltage divider midpoint — ADC1, input-only
#define PIN_PIR          27    // PIR / IR proximity digital out

// --- Actuators -------------------------------------------------------------
#define PIN_LED          16    // LED through a current-limiting resistor
#define PIN_MOTOR_IN1    26    // L298N IN1 — direction
#define PIN_MOTOR_IN2    25    // L298N IN2 — direction
#define PIN_MOTOR_ENA    33    // L298N ENA — PWM speed (ADC1 pin, used digitally)

// --- Identity --------------------------------------------------------------
#define NODE_ID          "aria-node-1"
#define FIRMWARE_VERSION "1.0.0"

// mDNS hostname. The backend discovers the node at http://aria.local/ — the node
// itself never needs to know the server's address.
#define MDNS_HOSTNAME    "aria"
#define HTTP_PORT        80

// SSID of the temporary access point used for first-time WiFi setup.
#define SETUP_AP_SSID    "ARIA-Setup"
#define SETUP_AP_TIMEOUT_S 180

// --- Sampling --------------------------------------------------------------
// The DHT22 cannot be read faster than about every 2 s; reading more often just
// returns the previous value or NaN.
#define DHT_MIN_INTERVAL_MS 2000
// How often the edge automation re-evaluates. Independent of how often the
// backend polls — automation must not depend on the backend at all.
#define AUTOMATION_INTERVAL_MS 250

#define ADC_MAX 4095

// --- Defaults (overridden by whatever is stored in NVS) --------------------
#define DEFAULT_GAS_THRESHOLD_PCT     60.0f
#define DEFAULT_DARK_THRESHOLD_PCT    25.0f
#define DEFAULT_TEMP_FAN_THRESHOLD_C  30.0f
#define DEFAULT_MOTION_LIGHT_HOLD_S   30
// MQ-135 needs a warm-up before its reading means anything. Real datasheets
// suggest minutes; 60 s is a practical compromise for a demo, and the node
// reports warmed_up so the dashboard can say so honestly.
#define DEFAULT_WARMUP_S              60

// --- Validation ranges (must match docs/CONTRACT.md) ----------------------
#define GAS_THRESHOLD_MIN      0.0f
#define GAS_THRESHOLD_MAX    100.0f
#define DARK_THRESHOLD_MIN     0.0f
#define DARK_THRESHOLD_MAX   100.0f
#define TEMP_FAN_MIN           0.0f
#define TEMP_FAN_MAX          60.0f
#define MOTION_HOLD_MIN          5
#define MOTION_HOLD_MAX       3600
#define WARMUP_MIN               0
#define WARMUP_MAX             600
