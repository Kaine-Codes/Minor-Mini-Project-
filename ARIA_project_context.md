# ARIA — Adaptive Room Intelligence & Automation
### Project Context & Decisions Log

**Team:** Shine Daniel, Roshan VN, Ryyan Safar
**Faculty Guide:** Ms. Seema Safar
**Department:** Electronics & Communication Engineering, RSET, Kochi
**Program:** CS Minor Project, 2026–27

---

## 1. Project Summary

ARIA is a full-stack IoT home/room automation system. It monitors environmental
conditions (temperature, humidity, air quality, motion, light) via an ESP32-based
sensor node, and allows automation + remote control of actuators (LED, fan) through
a locally-hosted web dashboard.

**Core positioning:** unlike commercial smart-home ecosystems (Google Home, Alexa,
SmartThings), ARIA does not rely on a third-party cloud server. All sensor data,
processing, and control logic stay on infrastructure the user owns — the trade-off
being some setup effort in exchange for privacy and no subscription cost.

**Project emphasis (explicit team decision):** the **software/dashboard side is the
primary focus** of this project. Hardware is intentionally kept simple — a single
ESP32 node wired up quickly on a breadboard — since the team's background is EC and
the differentiator they want to demonstrate is the full-stack system design (edge
firmware → backend → real-time dashboard), not sensor exotica.

---

## 2. Key Q&A That Shaped the Architecture

These are the questions raised during an internal presentation review, and the
reasoning that resolved them. Useful context for anticipating panel questions.

### Q: Where does the sensor data actually go? How is this different from Alexa?
A local "hub" (server) is still required to store data and serve the dashboard —
this isn't optional if you want live charts and history. The differentiator isn't
*absence* of a server, but **whose network it lives on**: Alexa/Google Home ship
data to the vendor's cloud and require an internet connection to function at all.
ARIA's server lives on the user's own network/device; no third party ever sees the
data, and the core sensing/automation loop does not depend on internet connectivity.

### Q: Do we need a Raspberry Pi as the edge/hub device?
No — a Pi is not required for this project's scope. Two options were considered:
- Drop the Flask/SQLite/React stack and have the ESP32 serve its own lightweight
  dashboard directly (e.g. `ESPAsyncWebServer`) — simpler, but limits dashboard
  quality, which conflicts with the team's goal of prioritizing the dashboard.
- **[Chosen]** Keep the full Flask/Node + SQLite + React stack, but run it on a
  laptop for development/demo purposes. Frame the "hub" conceptually in the report
  as *any always-on local device* (Pi, mini PC, spare laptop) — the laptop is a
  stand-in, not a limitation of the architecture. Pi/mini-PC deployment is noted as
  a future-scope / productionization step.

### Q: What would a real consumer need to set this up?
- The ESP32 sensor node (plug and power).
- An always-on hub device on the same home network (Pi/mini-PC/laptop in practice).
- First-time WiFi setup via the ESP32's own captive-portal access point (same UX
  pattern as smart bulbs) — connect phone to ESP32's temporary AP, enter home WiFi
  credentials, ESP32 joins the home LAN from then on.
- Browser access to the dashboard via a local address (no app, no account, no
  cloud sign-up required).

### Q: Does using an ESP32 (vs. wired internet) create a security problem?
No — this was identified as actually the opposite of a problem. The ESP32 only
needs a **local network** (LAN), not an internet connection — a home WiFi router
creates a LAN regardless of whether it's connected to an ISP. No ports are opened
to the public internet, so there's no remote attack surface from the open internet.
The only realistic attacker would need to already be on the home WiFi — this
reinforces the privacy pitch rather than undermining it. WiFi security (WPA2/3,
decent router password) and basic dashboard auth are still relevant, and were
addressed separately (see §4 and §6).

---

## 3. Remote Access Design (Work → Home Control)

**Requirement:** user wants to control the system remotely (e.g. turn off home
lights from their workplace), not just on the home LAN.

**Problem identified:** a device on a home network has a private IP address (e.g.
`192.168.1.5`) that is meaningless from any other network (e.g. office WiFi).
"Hosted on my laptop" and "controllable from work" are in direct tension without
an additional bridging mechanism.

**Options considered:**

| Option | Mechanism | Verdict |
|---|---|---|
| A. Port forwarding + DDNS | Open router port, point a dynamic DNS name at home IP | Rejected — opens a real public attack surface, undercuts the "no internet exposure" pitch, needs HTTPS/auth hardening |
| B. VPN mesh (Tailscale) | Private encrypted tunnel directly between the user's own devices, built on WireGuard | **Chosen** |
| C. Cloud MQTT relay | ESP32 + dashboard both connect out to a hosted broker (e.g. HiveMQ free tier) | Rejected — reintroduces "the cloud" into the data path, weakens the anti-Alexa pitch |

**Decision: Option B — Tailscale.**

- Built on **WireGuard** (peer-reviewed, in the Linux kernel) — not a proprietary
  black box; free tier supports far more devices than needed for this project.
- Creates a private tunnel *only* between the user's own devices (laptop + phone).
  No ports opened on the home router; nothing publicly reachable or discoverable
  by outside parties.
- From the phone (at work), the dashboard is reached exactly as if still on the
  home network.
- **Honest caveat for the report:** Tailscale's coordination servers assist devices
  in *finding* each other (handshake only) — actual data/commands do not route
  through Tailscale's infrastructure. Because of this nuance, the project's claim
  should be phrased as **"no third-party server ever sees your data"** rather than
  an absolute "zero internet dependency," which is no longer strictly true once
  remote access is in scope.
- **Demo constraint to state explicitly:** the laptop hosting Flask must be powered
  on and running for remote access to work in the current setup. This is flagged
  as a limitation of the demo, with an always-on Pi/mini-PC noted as the
  production fix.

---

## 4. Automation Architecture: Edge-First, Cloud-Optional

**Problem identified:** if automation logic requires a round trip through the
server (sensor → server → threshold check → command back to ESP32), any server
downtime (laptop off/asleep/WiFi hiccup) disables automation — a serious issue for
anything safety-related (e.g. gas threshold response).

**Decision:** critical automation logic runs **locally on the ESP32**, with no
server round-trip required:
- Example: if MQ-135 gas reading exceeds a threshold, the ESP32 triggers its
  relay/actuator response immediately and independently.
- The server still receives the same sensor readings for logging, dashboard
  display, and history.
- The server layer handles the "smarter" or non-critical automation: manual
  overrides, remote commands, schedules, combined/cross-sensor conditions.

This is described in the report as an **"edge-first automation, cloud-optional
intelligence"** pattern — a legitimate, citable IoT design principle, and a
stronger architectural story than pure server-dependent automation.

---

## 5. Security & Access Control

- **Remote access security:** handled by Tailscale (see §3) — private encrypted
  tunnel, no open ports, no public attack surface.
- **Dashboard authentication:** a simple username/password login (e.g.
  Flask-Login, single hardcoded user is acceptable for this project's scope) will
  be implemented, since the dashboard becomes reachable from Tailscale-connected
  devices, not just the physical home LAN.
- **Biometric/WebAuthn login was considered and explicitly deferred.** Reasoning:
  phone/laptop fingerprint or face unlock (Face ID, Windows Hello) protects
  *unlocking the device*, not the web app itself — a browser-level biometric login
  requires implementing WebAuthn (public-key crypto, browser APIs, credential
  storage), which is disproportionate engineering effort for this project's scope,
  and adds a hardware dependency (fingerprint sensor/camera) that risks failing
  on demo day if unavailable. **Decision:** ship simple password auth for the
  working demo; list WebAuthn/biometric login as a **Future Scope** bullet to show
  awareness of the stronger approach without taking on unnecessary build risk.

---

## 6. Data Retention

**Problem identified:** logging sensor readings every few seconds to SQLite will
cause unbounded row growth over time.

**Decision:** implement a simple **delete-after-N-days** policy — a scheduled job
(e.g. Flask-APScheduler, or a check on each new insert) runs a
`DELETE FROM readings WHERE timestamp < now - X days` style query to purge old
raw readings.

**Considered but deferred (noted as future scope only):** downsampling instead of
deleting — keep raw readings for the most recent 24–48 hours, then collapse older
data into hourly averages, preserving long-term trend visibility without unbounded
storage growth. Not required for current scope; simple delete is sufficient and
was chosen to avoid unnecessary build complexity.

---

## 7. Hardware — Final Parts List

**Design principle:** hardware is deliberately simple and quick to wire up
(breadboard + jumper wires, single afternoon), since the dashboard/backend is the
project's centerpiece. All components below are standard, well-documented parts.

| Component | Purpose | Notes |
|---|---|---|
| ESP32 (×1) | Core MCU / edge node | Single node — multi-node scaling explicitly deferred to future scope |
| MQ-135 | Gas / air quality sensing | Requires a warm-up period (~20s to a few minutes) after power-on; mention this in report/demo timing |
| IR proximity sensor / PIR | Motion / presence detection | Digital output, simple GPIO wiring |
| LDR | Ambient light sensing | Analog — needs a voltage-divider circuit (LDR + fixed resistor) since ESP32 ADC reads voltage, not resistance directly |
| DHT22 | Temperature + humidity | Single sensor covers both readings — a separate moisture/humidity sensor was considered and dropped as redundant |
| LED | "Light" automation demo actuator | Straight off a GPIO pin through a current-limiting resistor — no driver circuit needed |
| Small DC motor | "Fan" automation demo actuator | **Cannot** be driven directly from a GPIO pin (current/back-EMF) |
| L298N motor driver module | Drives the DC motor safely from GPIO logic | Chosen over discrete transistor + flyback diode circuit for reliability and a cleaner parts list; ESP32 GPIO controls the driver's input pins |

**Explicitly dropped from scope:**
- **Mains-voltage relay control of real appliances** — considered too much
  additional engineering/safety overhead (proper relay ratings, mains wiring
  safety) relative to the project's timeframe and the software-first priority.
  **Decision:** demo uses only low-voltage loads (LED, small DC motor). Mains
  relay integration is mentioned in the presentation as a **Future Scope** item
  ("designed to extend to mains-rated relays for real appliances") to show the
  concept generalizes, without taking on physical safety risk for a classroom demo.
- **Soil moisture sensor** — initially considered as a separate "moisture" sensor,
  clarified to be redundant with DHT22 (which already provides humidity), and
  dropped from the final parts list.

**Power plan:**
- ESP32 powered via USB cable from a standard 5V adapter.
- Sensors and the L298N module powered off the ESP32's available 5V rail (from
  the same USB/adapter supply) — no separate power supply required for this
  scope.
- Note for wiring: ESP32 logic level is 3.3V; peripheral modules (sensors,
  L298N control inputs) are commonly 5V-tolerant/powered — standard, non-blocking
  consideration to keep in mind when wiring, not a redesign issue.

---

## 8. Updated System Architecture (Single Node)

```
Sensor Layer                Edge Layer              Backend Layer            Frontend Layer
MQ-135 · IR/PIR             ESP32                    Flask / Node.js          React Dashboard
LDR · DHT22        ─────▶   Firmware        ─────▶   SQLite DB        ─────▶  Chart.js
                             (single node,             (mDNS: aria.local)
                             edge-first automation)

Actuators: LED, DC Motor (via L298N) — driven directly by ESP32 for
threshold-critical automation; can also receive commands relayed from
the backend for manual/remote overrides.

Remote access path: Phone/Laptop (anywhere) ── Tailscale (WireGuard tunnel) ──▶ Laptop (Flask server, home network)
```

**Key architectural notes:**
- **mDNS (`aria.local`)** is used instead of a hardcoded IP address for the ESP32
  to locate the backend server — prevents demo-day breakage if the server's local
  IP address changes (routers often reassign DHCP leases).
- Single ESP32 node — multi-node/mesh scaling explicitly deferred to Future Scope.
- Data flow: sensors → ESP32 → backend (via mDNS-resolved address) → SQLite →
  dashboard (polls/fetches for live + historical display).
- Control flow: dashboard (local or via Tailscale) → backend → ESP32 → actuator;
  **plus** a parallel local-only path where ESP32 acts on critical thresholds
  (e.g. gas level) without waiting on the backend at all.

---

## 9. Claims to Use Carefully in the Report/Presentation

To stay accurate and defensible under panel questioning:

- ✅ Say: *"No third-party server ever sees your data."*
- ❌ Avoid: *"Zero internet dependency"* (no longer strictly true once Tailscale-based
  remote access is included — Tailscale's coordination service assists the initial
  handshake, though it does not touch actual sensor/control data).
- ✅ Say: *"Local-network-only design significantly reduces attack surface compared
  to cloud-connected commercial systems."*
- ✅ Say: *"Edge-first automation ensures safety-relevant responses do not depend
  on server/network availability."*
- State the laptop-as-hub limitation openly, framed as a demo-stage constraint
  with a clear production fix (Pi/mini-PC) already identified.

---

## 10. Future Scope (Consolidated)

Items intentionally deferred from the current build, to be listed as future work:

- Mains-rated relay integration for real household appliances
- WebAuthn / biometric authentication for the dashboard login
- Data downsampling (hourly aggregation) instead of simple time-based deletion
- Multi-node / mesh scaling across multiple rooms
- Mobile companion app
- Offline voice control integration
- Solar-powered / battery ESP32 nodes for off-grid use
- On-device predictive automation (ML-based)
- Smart-plug integration with off-the-shelf hardware

---

*This document reflects team decisions as of the current planning stage and is
intended as a working reference for report writing, slide updates, and
anticipated panel Q&A preparation.*
