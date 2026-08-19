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
| SW-804 vibration sensor | Vibration detection | Added after initial hardware lock-in (see §10.3) — digital output, wired like the PIR sensor, no voltage divider needed |

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

## 10. Implementation Status — What Has Actually Been Built

This section reflects real, working progress as of the current stage, on top of
the design decisions in §1–9. All items below are implemented, not just planned.

### 10.1 Codebase delivered

A complete, working three-part codebase was generated to match the architecture
in §8:

- **`firmware/ARIA_firmware/ARIA_firmware.ino`** — ESP32 sketch implementing:
  WiFiManager-based first-boot captive portal setup, mDNS registration,
  sensor reads for DHT22 / MQ-135 / PIR / LDR / SW-804, edge-first gas-safety
  override logic (fan triggers locally, independent of the backend), periodic
  `POST` of readings to the backend, and periodic polling of `/api/commands`
  for manual/remote LED and fan overrides.
- **`backend/app.py` + `backend/database.py`** — Flask REST API backed by
  SQLite: session-based login, endpoints for posting/reading sensor data,
  endpoints for reading/setting actuator commands, a background
  APScheduler job that deletes readings older than `RETENTION_DAYS` (see §6),
  and mDNS self-registration as `aria.local` via the `zeroconf` package.
- **`frontend/`** — React (Vite) dashboard: login screen, live-readings grid,
  manual LED/fan controls, and a Chart.js history view, talking to the backend
  over a small `api.js` fetch wrapper.

### 10.2 Simplified single-server deployment model

The original design assumed two running processes (Flask API + a separate
Vite dev server for the dashboard). This was simplified for ease of setup:

- The frontend is now **built once** (`npm run build`), producing static files
  in `frontend/dist`.
- Flask (`app.py`) serves those static files directly, with a catch-all route
  that returns `index.html` for any non-API path (so client-side routing and
  a browser refresh both work correctly).
- Net effect: the whole system now runs as **one process, one port**
  (`python app.py`, dashboard at `http://localhost:5000`) instead of two
  processes on two ports. This was done specifically to reduce setup
  complexity for a team newer to running this kind of stack, without changing
  the underlying architecture — the two-process/dev-server workflow is kept
  as a documented fallback (`frontend/.env.example`) for active frontend
  development.

### 10.3 Vibration sensing added

An **SW-804 vibration sensor** was added to the hardware and software stack
after the initial design was locked in:

- Wired to **GPIO 13** on the ESP32 (digital input, same wiring pattern as the
  PIR sensor — no voltage divider needed).
- Added to the firmware (`vibration` reading, included in the JSON payload
  posted to the backend).
- Added to the database schema (`readings.vibration` column) and to
  `insert_reading()`.
- Displayed on the dashboard's live-readings grid alongside the other sensors.

### 10.4 Real bugs found and fixed during setup

These were genuine issues hit while actually running the system for the first
time on the team's Windows machine — documented here since they're the kind of
thing likely to resurface (e.g. if the code is redeployed on a new machine) and
are useful to know about rather than relearn:

- **Frontend routing 404 on Windows.** The Flask `static_folder` path was
  originally built from a plain `os.path.dirname(__file__)`. On Windows, when
  a script is launched as `python app.py` directly, `__file__` is not always
  guaranteed to be an absolute path, which could throw off the relative path
  built from it. Fixed by wrapping it in `os.path.abspath(...)`, which
  resolves the ambiguity regardless of how the script is invoked.
- **Server appearing to "do nothing" (exit code 0, no output, no error).**
  Root cause turned out to be a copy-paste of `app.py` that silently dropped
  the last ~30 lines of the file — including the entire
  `if __name__ == "__main__":` block. With that block missing, Python simply
  defines all the routes/functions and exits cleanly at end-of-file, with no
  error and no server ever starting. This was diagnosed by adding explicit
  `print()` checkpoints through the startup sequence and by directly
  inspecting the file's tail — a useful diagnostic pattern if a similar
  "silently does nothing" symptom shows up again.
- **Dashboard showing the wrong (browser-local) time for readings.** The
  backend was storing timestamps as `datetime.utcnow().isoformat()` — UTC time,
  but without any marker saying so. Browsers interpret an unmarked ISO
  timestamp as already being in the *local* timezone, so the dashboard's
  `toLocaleTimeString()` conversion was silently wrong. Fixed by appending
  `"Z"` to every stored timestamp (`datetime.utcnow().isoformat() + "Z"`),
  which explicitly marks it as UTC — the browser then correctly converts it to
  the viewer's local time with no frontend code changes needed.

### 10.5 Two versions of the backend now exist, deliberately

For presentation purposes, the team wanted to be able to show an earlier,
simpler milestone ("V1") distinct from the current fully-integrated system,
without misrepresenting the current state of the project as less complete than
it actually is. Two real files now exist:

- **`app.py` (current)** — the single-server version described in §10.2:
  Flask serves the built dashboard directly at `http://localhost:5000`.
- **`app_v1.py`** — the original, pre-simplification version: a pure JSON API
  with no UI-serving code at all. To see a working dashboard against this
  version, the React dev server must be run separately (`npm run dev` in
  `frontend/`, with `VITE_API_BASE=http://localhost:5000` set in a `.env`
  file), and the dashboard is then reached at `http://localhost:5173`
  instead of `5000`. This is a genuine, functioning earlier state of the
  project, not a fabricated one — useful for showing incremental progress
  honestly in a presentation without altering what's currently built.

### 10.6 Presentation deck produced

A 12-slide progress presentation (`ARIA_progress_presentation.pptx`) was
created covering: title, introduction, problem statement, objectives, system
overview, system architecture (layered diagram), module design (sensing/edge
and backend/data-flow, including the real DB schema and API endpoint list),
UI wireframes (login + live-monitoring screens), tools & technologies,
challenges & mitigation, and conclusion.

**Framing note:** the "Challenges & Mitigation" slide presents the three real
architectural questions the team worked through — Pi vs. ESP32 for the hub,
secure remote access without opening ports, and edge-vs-cloud automation — each
paired with the actual chosen solution, honestly described as the team's
approach rather than as an unresolved problem. This was a deliberate choice:
the team wanted to show measured, believable progress (not the fully-polished
end state) for an early review, but without asserting that things which are
actually working are still broken.

---

## 11. What's Left To Do

Concrete, unfinished work — as distinct from the "Future Scope" wishlist in
§12, which is explicitly out of scope for this project's timeline.

### Hardware
- [ ] Physical breadboard assembly of all sensors + actuators per the pin map
      in `SETUP.md` (some components were still being sourced as of the last
      check-in).
- [ ] Calibrate `GAS_SAFETY_THRESHOLD` against the team's actual MQ-135 unit
      (currently a placeholder value in the firmware) — requires taking real
      readings in normal air vs. near a controlled gas source.
- [ ] Confirm SW-804 sensitivity trim-pot is adjusted appropriately for the
      demo environment (avoid false triggers from ambient vibration).

### Firmware
- [ ] End-to-end test of the WiFiManager captive-portal flow on the actual
      board (confirmed working in principle; needs a live run-through).
- [ ] Verify edge-first gas override actually cuts power to the fan
      correctly through the L298N under real load, not just in code review.

### Backend / Frontend
- [ ] Full end-to-end test with live ESP32 data flowing into the dashboard
      (has been tested with the dashboard's UI itself, but full sensor-to-chart
      integration on real hardware is the next milestone).
- [ ] Change `DEFAULT_PASSWORD` and `app.secret_key` away from placeholder
      values before any real demo (currently still using development
      placeholders on the team's working copy).
- [ ] Decide finally whether the demo will run the single-server setup
      (§10.2) or intentionally show the two-process V1 setup (§10.5) for the
      presentation, and rehearse whichever is chosen so it isn't the first
      time it's been run live.

### Remote Access
- [ ] Install and pair Tailscale on both the laptop (hub) and a phone.
- [ ] Do a live test of dashboard control from **outside** the home network
      (e.g. from a phone on mobile data, not the home WiFi) — this has been
      designed and documented but not yet demonstrated end-to-end.

### Documentation / Presentation
- [ ] Finalize which milestone (V1 vs. current) is shown at the next review,
      per the team's own pacing preference (see §10.5 framing note).
- [ ] Prepare the full working demo (all objectives from §4) for the final
      review, once the above items are complete.

---

## 12. Future Scope (Consolidated)

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

*This document reflects team decisions and progress as of the current stage and
is intended as a working reference for report writing, slide updates, and
anticipated panel Q&A preparation. Last major update: full codebase delivered,
vibration sensor integrated, Windows setup issues resolved, and progress
presentation produced.*
