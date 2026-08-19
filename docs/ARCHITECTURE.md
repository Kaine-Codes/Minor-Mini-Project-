# ARIA — Architecture & Design Decisions

Companion to [`CONTRACT.md`](CONTRACT.md). This records *why* the system is shaped the way
it is, including the options that were rejected — the material a project review or viva
tends to probe.

---

## 1. Layers

| Layer | Runs on | Responsibility |
|---|---|---|
| Sensing + edge automation | ESP32 | Read sensors; enforce safety-critical rules locally |
| Transport | LAN (HTTP/JSON) | Backend polls the node; pushes commands to it |
| Storage + logic | Hub (laptop / Pi) | Persist history, log events, non-critical automation, auth |
| Presentation | Browser | Live tiles, charts, controls, threshold editing |

One process serves both the API and the dashboard. That is deliberate: a single thing to
start on demo day, no CORS in production, and no second port to explain.

---

## 2. Decision: the node is the server, the backend is the client

**Rejected:** the node POSTs readings to the backend.

That direction leaves the **command path undefined**. If the node is an HTTP client, the
backend has no stable address to reach it on — which is exactly the problem mDNS was
introduced to solve, only in the opposite direction. Any fix (the node self-registering its
IP, long-polling, a broker) adds moving parts.

**Chosen:** the node runs an HTTP server, advertises itself as `aria.local`, and the
backend polls it.

| | Node pushes | Node serves (chosen) |
|---|---|---|
| Discovery burden | ESP32 must *resolve* `aria.local` — unreliable on ESP32 | Laptop resolves it — native Bonjour/Avahi |
| Firmware complexity | HTTP client, retry queue, knows server address | Serves four endpoints, knows nothing about the server |
| Command path | Undefined | Free — same server |
| DHCP lease change | Breaks until re-registration | mDNS handles it |

**Trade-offs, honestly:** sampling is bounded by the poll interval, and nothing is logged
while the hub is off. Both were already accepted constraints. Polling a device at a
resolvable name is standard practice at single-node scale.

**Redundant discovery.** `ARIA_NODE_HOSTS` is an ordered list (`aria.local`, then a static
IP). The first host answering `GET /health` is cached and preferred thereafter. A single
request failure triggers one rediscovery-and-retry before anything is reported as down, so
a reboot onto a new address self-heals. Demo day does not hinge on mDNS alone.

### Why not MQTT?

A fair question, and the expected IoT answer — worth having ready.

MQTT with a **local** Mosquitto broker would fit the privacy pitch perfectly (no cloud
involved) and solves addressing cleanly in both directions. It was not chosen because at
**single-node scale** it adds a third always-on service to keep alive for no capability
this design lacks: HTTP already gives request/response commands, and the node's safety rule
does not use the network at all.

MQTT becomes the right call as soon as there are several nodes — which is precisely why
multi-node scaling and MQTT are listed together in future scope. A **cloud** MQTT relay
(HiveMQ and similar) was rejected outright: it puts a third party back in the data path.

---

## 3. Decision: edge-first automation, cloud-optional intelligence

**Problem:** if automation requires a server round trip (sensor → server → threshold check
→ command → actuator), then a sleeping laptop or a WiFi hiccup disables automation. For a
gas response that is unacceptable.

**Chosen:** safety-critical logic lives on the node.

- The ESP32 evaluates its rules every 250 ms with no network involvement.
- Thresholds persist to **NVS**, so they survive a reboot and stay enforced with the hub
  off. Without persistence, "edge-first" would only be half-implemented — a power cycle
  would silently disarm the safety rule.
- An active gas alarm **overrides everything**, including manual mode and any API command.
  The node re-asserts the alarm state before answering a command, so the dashboard is never
  shown a state that is about to be reverted.
- The server still receives every reading for logging, history and display, and owns the
  non-critical logic: manual overrides, remote commands, cross-sensor rules.

Rule priority is specified in [`CONTRACT.md`](CONTRACT.md) and implemented identically in
`firmware/aria_node/aria_automation.cpp` and in the simulator, so the two cannot drift
without a test noticing.

---

## 4. Decision: contract-first, with a simulator

`docs/CONTRACT.md` was written before either side was implemented. `backend/tools/fake_node.py`
implements it exactly — same endpoints, same validation, same automation rules, same
MQ-135 warm-up, plausible drifting values, and a periodic gas spike to exercise the alarm
path on demand.

Three things this buys:

1. **Decoupling from hardware.** The dashboard, poller, retention job and auth flow were
   all built and tested before any wiring existed.
2. **A demo-day fallback.** If a sensor dies the night before the review, the simulator
   keeps the demo alive.
3. **A deterministic test suite.** 153 tests run offline with no hardware.

The simulator also enforces the contract's validation ranges, so a gap in the backend's
validation surfaces there instead of being silently accepted.

---

## 5. Remote access

| Option | Verdict |
|---|---|
| Port forwarding + DDNS | **Rejected** — opens a real public attack surface, contradicting the project's core claim |
| Cloud MQTT relay | **Rejected** — puts a third party back in the data path |
| **Tailscale (WireGuard)** | **Chosen** |

Tailscale builds an encrypted tunnel between the user's own devices. No ports opened,
nothing publicly discoverable, and the dashboard is reached from a phone at work exactly as
if on the home LAN.

**Two caveats to state rather than gloss over:**

- Tailscale's coordination servers assist the initial handshake. Sensor data and commands
  do not route through them. The defensible claim is therefore *"no third-party server ever
  sees your data"* — **not** *"zero internet dependency"*, which stops being strictly true
  once remote access is in scope.
- The hub must be powered on. On a laptop that is a demo-stage constraint with a known
  production fix (Pi / mini-PC).

---

## 6. Storage and retention

- **SQLite** in WAL mode, so the dashboard can read history while the poller writes.
- **Index on `recorded_at DESC`** — every query is either "recent readings" or "purge older
  than X", both time-ordered. Without it the retention sweep becomes a full table scan.
- **History queries are always bounded** by a row limit as well as a time window, and the
  limit keeps the *newest* rows. An unbounded query would happily return a fortnight of
  5-second samples and stall the chart.
- **Nulls are preserved.** A failed DHT22 read stores `NULL`, never `0.0`, and the chart
  draws a gap rather than a phantom drop to freezing.
- **Retention:** a periodic sweep deletes rows older than `ARIA_RETENTION_DAYS` (default
  14). At a 5-second sample rate that is roughly 17k rows/day, so a cap is not optional.
  Downsampling older data to hourly averages is the better long-term answer and is listed
  as future scope; a time-based delete is sufficient here.
- **Events are logged on transitions only** — one `gas_alarm` row per incident, not one per
  sample taken during it.

---

## 7. Real-time delivery

The backend polls the node **once** per interval and fans the result out over a WebSocket,
so N open browser tabs still cost one request to the hardware. Clients reconnect with
exponential backoff (capped at 15 s), so a laptop waking from sleep recovers without a page
reload, and a newly-opened tab is sent the last snapshot immediately instead of sitting
blank until the next tick.

The WebSocket authenticates with the same session cookie as the REST routes — the browser
sends it on the upgrade handshake, so an unauthenticated socket is refused before `accept()`.

---

## 8. Security posture

| Concern | Approach |
|---|---|
| Dashboard auth | Salted **scrypt** hash from env; constant-time compare; signed HTTP-only cookie with TTL |
| Default credentials | None. Startup **fails** without `ARIA_PASSWORD_HASH` / `ARIA_SESSION_SECRET` |
| Untrusted input | Pydantic models with explicit ranges on every payload, from the node *and* the browser |
| Error leakage | Unhandled exceptions log server-side, return a generic message; validation errors name the field but never echo the value |
| Static file serving | Resolved paths confined to the bundle directory — traversal attempts fall through to `index.html` |
| Login guessing | Identical error message and cost for a wrong username and a wrong password, plus a fixed delay |
| Public exposure | No open ports; remote access only through the WireGuard tunnel |
| Safety override | An active gas alarm cannot be cleared by any network command |

The node itself is unauthenticated by design: it is LAN-only and holds no secrets. An
attacker would already need to be on the home WiFi — the same position from which they
could unplug the device.

---

## 9. What the ESP32 constrains

- **Analog sensors must use ADC1 (GPIO 32–39).** ADC2 shares hardware with the WiFi radio
  and returns garbage once WiFi is up — the classic "worked until I connected to WiFi" bug.
- **GPIO 34–39 are input-only**, with no internal pull-ups.
- **The DHT22 cannot be read faster than ~2 s.** The firmware rate-limits it internally and
  serves the last good value between reads, so `GET /sensors` can be polled freely.
- **A DC motor cannot be driven from a GPIO** (current and back-EMF). Hence the L298N.
- **The default flash partition leaves ~10% headroom** with WiFiManager + AsyncWebServer +
  ArduinoJson. Build with `PartitionScheme=huge_app` (37% used).
- **`millis()` rolls over** after ~49 days; all timing uses unsigned subtraction, which
  handles it correctly.

---

## 10. Claims to use carefully

- ✅ "No third-party server ever sees your data."
- ❌ "Zero internet dependency" — not strictly true once Tailscale remote access is included.
- ✅ "Local-network-only design significantly reduces attack surface versus cloud-connected
  commercial systems."
- ✅ "Edge-first automation ensures safety-relevant responses do not depend on server or
  network availability."
- ✅ "Air quality is reported as a relative index against a user-set threshold, not a
  calibrated ppm figure." — say this before being asked.
- State the laptop-as-hub limitation openly, with the Pi/mini-PC fix already identified.
