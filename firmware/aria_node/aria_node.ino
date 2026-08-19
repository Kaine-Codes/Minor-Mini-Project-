/**
 * ARIA node — ESP32 firmware
 *
 * The node is an HTTP *server*. It advertises itself over mDNS as `aria.local` and
 * serves the contract in docs/CONTRACT.md. The backend is the client: it polls
 * GET /sensors and pushes commands. The node never needs to know the server's address,
 * which is what keeps this firmware simple and removes any dependency on mDNS lookups
 * from the ESP32 side.
 *
 * Critically, the automation in aria_automation.cpp runs on a local timer and does not
 * involve the network at all. With the backend off, asleep, or unreachable, the node
 * still senses and still responds to a gas threshold. The server adds logging, history,
 * remote control and cross-sensor rules — not the safety response.
 *
 * Required libraries (Arduino Library Manager unless noted):
 *   - ESP32 board support (Espressif, board: "ESP32 Dev Module")
 *   - ESPAsyncWebServer  + AsyncTCP   (me-no-dev)
 *   - ArduinoJson v7                  (Benoit Blanchon)
 *   - DHT sensor library + Adafruit Unified Sensor (Adafruit)
 *   - WiFiManager                     (tzapu)
 *
 * Wiring and the ADC1 constraint are documented in aria_config.h — read it before
 * connecting the analog sensors.
 */

#include <ESPAsyncWebServer.h>
#include <ESPmDNS.h>
#include <WiFi.h>
#include <WiFiManager.h>

#include "aria_api.h"
#include "aria_automation.h"
#include "aria_config.h"
#include "aria_sensors.h"
#include "aria_settings.h"

AsyncWebServer server(HTTP_PORT);

static uint32_t lastAutomationMs = 0;

/**
 * Bring up WiFi.
 *
 * On first boot (or after the stored credentials stop working) WiFiManager raises a
 * temporary access point and a captive portal: connect a phone to "ARIA-Setup", enter
 * the home WiFi credentials once, and the node joins the LAN from then on. This is the
 * same provisioning flow commercial smart bulbs use, and it means no SSID or password
 * is ever hardcoded into this sketch.
 */
static void connectWifi() {
  WiFiManager manager;
  manager.setConfigPortalTimeout(SETUP_AP_TIMEOUT_S);
  manager.setHostname(MDNS_HOSTNAME);

  if (!manager.autoConnect(SETUP_AP_SSID)) {
    // Do not sit forever in the portal: reboot and retry, so a power blip during a
    // demo recovers on its own rather than needing a phone.
    Serial.println("[wifi] provisioning timed out, restarting");
    delay(1000);
    ESP.restart();
  }

  Serial.printf("[wifi] connected to %s as %s\n", WiFi.SSID().c_str(),
                WiFi.localIP().toString().c_str());
}

/**
 * Advertise the node as `aria.local`.
 *
 * This is the discovery half of the design: the backend resolves this name, so a DHCP
 * lease change never breaks the link and no IP address is hardcoded anywhere.
 */
static void startMdns() {
  if (!MDNS.begin(MDNS_HOSTNAME)) {
    Serial.println("[mdns] failed to start — backend must fall back to the IP address");
    return;
  }
  MDNS.addService("http", "tcp", HTTP_PORT);
  MDNS.addService("aria", "tcp", HTTP_PORT);
  Serial.printf("[mdns] advertising http://%s.local:%d/\n", MDNS_HOSTNAME, HTTP_PORT);
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("\nARIA node %s (%s) booting\n", NODE_ID, FIRMWARE_VERSION);

  // Order matters: actuators are driven to a known-off state and thresholds are loaded
  // before anything can evaluate a rule or serve a request.
  settingsBegin();
  sensorsBegin();
  automationBegin();

  connectWifi();
  startMdns();

  apiRegisterRoutes(server);
  server.begin();
  Serial.printf("[http] serving the ARIA contract on port %d\n", HTTP_PORT);

  const AriaSettings settings = settingsGet();
  Serial.printf("[mq135] warming up for %us — gas readings are unreliable until then\n",
                settings.warmupS);
}

void loop() {
  // ESPAsyncWebServer handles requests on its own task, so this loop only has to keep
  // the local automation running. It deliberately contains no network logic.
  const uint32_t now = millis();
  if ((now - lastAutomationMs) >= AUTOMATION_INTERVAL_MS) {
    lastAutomationMs = now;
    automationEvaluate(sensorsRead());
  }

  // If WiFi drops, automation keeps running. Reconnection is attempted quietly in the
  // background; losing the network must never stop the node sensing and reacting.
  if (WiFi.status() != WL_CONNECTED) {
    static uint32_t lastRetryMs = 0;
    if ((now - lastRetryMs) > 10000UL) {
      lastRetryMs = now;
      Serial.println("[wifi] disconnected — automation continues, retrying link");
      WiFi.reconnect();
    }
  }

  delay(10);
}
