# ARIA Node Contract (v1)

The **single interface** between the ESP32 sensor node and the ARIA backend.

The ESP32 is an **HTTP server**. The backend is the **client** — it polls readings and
pushes commands. The node never needs to know the backend's address.

- Node advertises itself over mDNS as **`aria.local`** (service `_aria._tcp`, port 80).
- All request/response bodies are JSON, `Content-Type: application/json`.
- All endpoints must respond in under 2 s; the backend's timeout is configurable
  (`ARIA_NODE_TIMEOUT_S`, default 3 s).
- No authentication on the node. It is LAN-only and holds no secrets. Dashboard auth
  sits at the backend layer (see `docs/ARCHITECTURE.md` §Security).

---

## `GET /health`

Cheap liveness probe used by discovery to pick a working host candidate.

```json
{ "ok": true, "node_id": "aria-node-1", "firmware": "1.0.0", "uptime_ms": 128400 }
```

---

## `GET /sensors`

The hot path. Polled by the backend every `ARIA_POLL_INTERVAL_S` seconds (default 5).

```json
{
  "node_id": "aria-node-1",
  "uptime_ms": 128400,
  "temperature_c": 28.4,
  "humidity_pct": 61.2,
  "gas_raw": 1430,
  "gas_pct": 34.9,
  "light_raw": 2210,
  "light_pct": 53.9,
  "motion": true,
  "actuators": { "led": true, "fan": false },
  "edge": { "gas_alarm": false, "warmed_up": true, "mode": "auto" }
}
```

### Field semantics

| Field | Type | Range / units | Notes |
|---|---|---|---|
| `node_id` | string | — | Stable per-device id. |
| `uptime_ms` | int | ms | Since boot. Used to detect node reboots. |
| `temperature_c` | float \| null | °C | `null` when the DHT22 read fails (it does, intermittently). |
| `humidity_pct` | float \| null | 0–100 | `null` on DHT22 read failure. |
| `gas_raw` | int | 0–4095 | Raw ESP32 ADC counts from the MQ-135. |
| `gas_pct` | float | 0–100 | `gas_raw` normalised. **Relative, not calibrated ppm** — see caveat below. |
| `light_raw` | int | 0–4095 | Raw ADC from the LDR voltage divider. |
| `light_pct` | float | 0–100 | 0 = dark, 100 = bright. |
| `motion` | bool | — | PIR/IR digital output. |
| `actuators.led` | bool | — | Current LED state, whoever set it. |
| `actuators.fan` | bool | — | Current DC motor state (via L298N). |
| `edge.gas_alarm` | bool | — | True while the node's **local** gas threshold is exceeded. |
| `edge.warmed_up` | bool | — | False during MQ-135 warm-up; `gas_*` is unreliable until true. |
| `edge.mode` | `"auto"` \| `"manual"` | — | Whether local automation is currently arming actuators. |

> **MQ-135 calibration caveat.** The MQ-135 is a broad-spectrum VOC/gas sensor. Deriving
> absolute ppm requires a reference-gas calibration this project does not perform, so
> `gas_pct` is an explicitly **relative** indicator against a user-set threshold. The
> report and viva must state this rather than claim ppm.

---

## `POST /actuators`

Manual override from the dashboard. **Partial** body — omitted keys are left unchanged
(immutable-update semantics: the node returns the new full state, it does not mutate in
place conceptually).

Request:

```json
{ "led": true, "fan": false, "mode": "manual" }
```

| Field | Type | Notes |
|---|---|---|
| `led` | bool, optional | Set LED state. |
| `fan` | bool, optional | Set fan state. |
| `mode` | `"auto"` \| `"manual"`, optional | `manual` suspends local automation for the actuators. `auto` returns control to the edge rules. |

Response — the **new** full actuator state (same shape as `sensors.actuators` + `mode`):

```json
{ "led": true, "fan": false, "mode": "manual" }
```

Errors: `400` with `{"error": "..."}` on an unknown field or wrong type.

> **Safety exception.** A `gas_alarm` always wins. While the local gas threshold is
> exceeded the node drives its alarm response regardless of `mode` or any command
> received. This is the point of edge-first automation and must not be overridable
> from the network.
>
> The node must **re-assert the alarm state before responding**, so the returned body is
> the state actually in effect. Echoing back a command that the alarm will overturn a
> moment later would make the dashboard briefly show a lie.

---

## `GET /config`

Returns the thresholds the node is currently enforcing locally.

```json
{
  "gas_threshold_pct": 60.0,
  "dark_threshold_pct": 25.0,
  "temp_fan_threshold_c": 30.0,
  "motion_light_hold_s": 30,
  "warmup_s": 60
}
```

## `POST /config`

Partial update. Persisted to **NVS (ESP32 Preferences)** so thresholds survive reboot
and remain enforced with the backend switched off — without this, "edge-first
automation" would only be half-implemented.

Request (any subset):

```json
{ "gas_threshold_pct": 55.0, "temp_fan_threshold_c": 31.5 }
```

Response: the new full config (same shape as `GET /config`).

### Validation (enforced on the node **and** at the backend boundary)

| Field | Type | Valid range |
|---|---|---|
| `gas_threshold_pct` | float | 0–100 |
| `dark_threshold_pct` | float | 0–100 |
| `temp_fan_threshold_c` | float | 0–60 |
| `motion_light_hold_s` | int | 5–3600 |
| `warmup_s` | int | 0–600 |

Out-of-range or wrong-typed values → `400 {"error": "..."}`, and **no** field is applied
(all-or-nothing, so a partially valid body cannot leave the node in a half-configured
state).

---

## Edge automation rules (run on the node, no backend involved)

Evaluated every loop iteration, in this priority order:

1. **Gas alarm** — `warmed_up && gas_pct >= gas_threshold_pct` → fan ON, LED blink.
   Overrides everything, including `manual` mode.
2. **Manual mode** — if `mode == "manual"` and no alarm, hold whatever the last command
   set and evaluate nothing further.
3. **Motion + darkness** — `motion && light_pct < dark_threshold_pct` → LED ON, held for
   `motion_light_hold_s` after the last motion.
4. **Heat** — `temperature_c >= temp_fan_threshold_c` → fan ON.

Rules 3 and 4 are also mirrored in the backend for cross-sensor/scheduled automation,
but the node's copy is authoritative for the safety-relevant rule 1.

---

## Versioning

Breaking changes bump the path prefix (`/v2/sensors`). `GET /health` reports `firmware`
so the backend can warn on a contract mismatch.
