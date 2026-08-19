# ARIA — Adaptive Room Intelligence & Automation

Local-first IoT room monitoring and automation. An ESP32 sensor node reports temperature,
humidity, air quality, motion and ambient light; a self-hosted dashboard shows live and
historical data and controls the actuators.

**No third-party server ever sees your data.** Unlike Google Home, Alexa or SmartThings,
every part of ARIA — sensing, storage, automation logic and the dashboard — runs on
infrastructure you own.

**CS Minor Project, 2026–27** · Dept. of Electronics & Communication Engineering, RSET, Kochi
**Team:** Shine Daniel · Roshan VN · Ryyan Safar · **Guide:** Ms. Seema Safar

---

## Architecture

```
   ESP32 node (HTTP server, aria.local)          Hub (laptop / Pi / mini-PC)
  ┌─────────────────────────────────────┐       ┌──────────────────────────────────┐
  │  MQ-135 · DHT22 · LDR · PIR         │       │  FastAPI                         │
  │  LED · DC motor (via L298N)         │◀──────│   ├── poller  (GET /sensors)     │
  │                                     │ poll  │   ├── SQLite  (history)          │
  │  edge automation ── runs locally,   │──────▶│   ├── WebSocket (live push)      │
  │  no server required                 │ push  │   └── serves the React dashboard │
  └─────────────────────────────────────┘ cmds  └──────────────────────────────────┘
                                                                │
                             Browser (LAN, or anywhere via Tailscale/WireGuard)
```

Two decisions carry most of the design:

**1. The node is the HTTP server; the backend polls it.** The node advertises itself over
mDNS as `aria.local` and never needs to know the server's address. This makes the firmware
much simpler, keeps mDNS resolution on the laptop (where it is reliable) rather than on the
ESP32 (where it is not), and gives the command path a working address for free.

**2. Automation runs on the node, not on the server.** The gas threshold is evaluated on
the ESP32 every 250 ms and persisted to NVS. Switch the laptop off and ARIA still senses
and still responds — you lose logging, history and remote control, not the safety
response. The server layer handles the non-critical intelligence: manual overrides,
remote access, cross-sensor rules.

Full detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
The node's HTTP interface: [`docs/CONTRACT.md`](docs/CONTRACT.md).

---

## Quick start (no hardware needed)

A simulator implements the node's contract exactly, so the whole stack runs before any
wiring exists — and doubles as a demo-day fallback if a sensor fails.

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or: uv venv .venv
pip install -e ".[dev]"                             # or: uv pip install -e ".[dev]"

# Generate credentials — ARIA refuses to start without them (no default password)
python -m aria.hashpw
cp .env.example .env      # paste the two generated values into .env
```

For simulator mode, also set in `.env`:

```ini
ARIA_NODE_HOSTS=127.0.0.1
ARIA_NODE_PORT=8080
```

### 2. Frontend

```bash
cd frontend
npm install
npm run build          # FastAPI serves the built bundle — one process, no CORS
```

### 3. Run

```bash
# Terminal 1 — the fake node
cd backend && python tools/fake_node.py --port 8080

# Terminal 2 — the backend + dashboard
cd backend && python -m aria
```

Open <http://localhost:8000> and sign in.

**Frontend development** (hot reload) — run `npm run dev` in `frontend/` and use
<http://localhost:5173>; `/api` is proxied to port 8000.

---

## Hardware

| Component | Purpose | Notes |
|---|---|---|
| ESP32 DevKit | Edge node | Single node; multi-node is future scope |
| DHT22 | Temperature + humidity | Covers both — no separate humidity sensor needed |
| MQ-135 | Air quality | Needs warm-up; **relative index, not calibrated ppm** |
| LDR + fixed resistor | Ambient light | Voltage divider — the ADC reads voltage, not resistance |
| PIR / IR proximity | Motion | Digital GPIO |
| LED + resistor | "Light" actuator | Straight off a GPIO |
| Small DC motor | "Fan" actuator | **Cannot** be driven from a GPIO directly |
| L298N module | Motor driver | Handles the motor's current and back-EMF |

Pin map and wiring notes: [`firmware/aria_node/aria_config.h`](firmware/aria_node/aria_config.h).

> **Two hardware gotchas worth knowing before you wire anything.**
>
> **Analog sensors must use ADC1 pins (GPIO 32–39).** ADC2 shares hardware with the WiFi
> radio; reads return garbage once WiFi is up. This is the usual cause of "it worked until
> I connected to WiFi". Both analog sensors are on ADC1 in the pin map.
>
> **The MQ-135 gives no ppm figure.** It is a broad-spectrum VOC sensor, and absolute ppm
> needs a reference-gas calibration this project does not perform. Everything — API,
> dashboard, this README — calls it a relative index deliberately.

Only low-voltage loads are driven. Mains-rated relay control is listed as future scope
rather than built, to keep a classroom demo free of mains-wiring risk.

---

## Firmware

Open `firmware/aria_node/` in the Arduino IDE, or build from the CLI:

```bash
arduino-cli core install esp32:esp32
arduino-cli lib install "ArduinoJson" "DHT sensor library" "Adafruit Unified Sensor" \
                        "WiFiManager" "ESP Async WebServer" "Async TCP"

# The huge_app partition is required: the default leaves only ~10% flash headroom.
arduino-cli compile --fqbn "esp32:esp32:esp32:PartitionScheme=huge_app" firmware/aria_node
arduino-cli upload  --fqbn "esp32:esp32:esp32:PartitionScheme=huge_app" -p /dev/cu.usbserial-XXXX firmware/aria_node
```

Verified: compiles clean with `--warnings all`; 37% flash and 15% RAM on `huge_app`
(90% flash on the default partition, which is why the setting matters).

**First-time WiFi setup** — no credentials are hardcoded. On first boot the node raises a
temporary access point, `ARIA-Setup`. Connect a phone to it, enter the home WiFi details
once, and the node joins the LAN from then on — the same flow commercial smart bulbs use.

---

## Remote access

Use **Tailscale** (WireGuard) on the hub and your phone. This creates a private encrypted
tunnel between your own devices with **no ports opened** on the router and nothing publicly
reachable. Port forwarding was rejected precisely because it creates the public attack
surface ARIA exists to avoid.

Two things to state honestly rather than gloss over:

- Tailscale's coordination servers help your devices *find* each other. Sensor data and
  commands do not pass through them. So the accurate claim is **"no third-party server
  ever sees your data"**, not "zero internet dependency".
- The hub must be powered on for remote access to work. On a laptop that is a demo-stage
  constraint; the production answer is an always-on Pi or mini-PC.

---

## Security

- **Auth required** on every route and on the WebSocket. Password stored as a salted
  **scrypt** hash, never plaintext; comparison is constant-time.
- **No default credentials.** The app refuses to start without `ARIA_PASSWORD_HASH` and
  `ARIA_SESSION_SECRET` rather than falling back to something guessable.
- **Signed, HTTP-only session cookies** with an explicit TTL.
- **Validated at the boundary.** Every payload from the node and from the browser passes
  through a Pydantic model with explicit ranges before it reaches storage or hardware.
- **No open ports** to the internet; remote access is via the WireGuard tunnel.
- **Safety rules are not network-overridable.** An active gas alarm cannot be switched off
  by any API call.

WebAuthn/biometric login is deliberately future scope: it protects the *device* unlock
rather than the app, and adds a hardware dependency that could fail on demo day.

---

## Tests

```bash
cd backend
python -m pytest -q --cov=aria --cov-report=term-missing
```

153 tests, **90% coverage** (target: 80%). Covers the automation/alarm logic, host
discovery and retry, the retention policy, auth, and every API route — all against the
fake node, so the suite needs no hardware and runs offline.

```bash
cd frontend && npx tsc --noEmit    # type check
```

---

## Project layout

```
backend/
  aria/
    config.py        settings (env-driven, nothing hardcoded)
    models.py        Pydantic schemas — the validation boundary
    db.py            SQLite: WAL, schema, timestamp index
    repository.py    data access (repository pattern)
    node_client.py   HTTP client + redundant host discovery
    poller.py        poll loop and retention sweeper
    hub.py           WebSocket fan-out
    auth.py          scrypt hashing + signed sessions
    routes/          auth · readings · control · config
  tools/fake_node.py ESP32 simulator (stdlib only)
  tests/
frontend/
  src/components/    tiles · chart · controls · thresholds · event log
  src/hooks/         WebSocket feed with reconnect backoff
firmware/aria_node/
  aria_node.ino      setup/loop, WiFi provisioning, mDNS
  aria_automation.*  the edge rules
  aria_sensors.*     sensor reads with DHT22 rate limiting
  aria_settings.*    NVS-persisted thresholds
  aria_api.*         the HTTP contract
docs/
  CONTRACT.md        the node's HTTP interface
  ARCHITECTURE.md    design decisions and rationale
```

---

## Future scope

Mains-rated relay integration · WebAuthn/biometric login · data downsampling to hourly
averages instead of time-based deletion · multi-node mesh across rooms · MQTT via a local
Mosquitto broker (the right answer once there are several nodes) · mobile companion app ·
offline voice control · solar/battery nodes · on-device predictive automation.

---

## Notes

- Node 20.19+ is recommended; Vite warns on older versions (the build still works).
- Vite is pinned to 7.x deliberately — 8.x pulls a platform-specific native binary that
  is awkward across a team on mixed machines.

---

## Author & support

- **Portfolio** — <https://ryyansafar.site>
- **GitHub** — <https://github.com/ryyansafar>
- **Buy me a coffee** — <https://buymeacoffee.com/ryyansafar>
- **PayPal** — <https://www.paypal.com/paypalme/ryyansafar>
- **Razorpay** — <https://razorpay.me/@ryyansafar>
