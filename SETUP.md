# ARIA — Setup Guide

This project has three parts. Set them up in this order: **backend → frontend →
firmware**, so the ESP32 has somewhere to send data to as soon as it comes online.

```
ARIA_project/
├── backend/       Flask + SQLite server (the "hub")
├── frontend/      React dashboard (Vite + Chart.js)
├── firmware/      ESP32 Arduino sketch
└── SETUP.md       this file
```

---

## 1. Backend (Flask) — run this on your laptop

**Where it goes:** any laptop/PC that will stay on during your demo (this is your
"hub" — see project context doc for why this stands in for a Pi/mini-PC).

**Setup:**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Before running, change these two things in `app.py`:**
- `DEFAULT_PASSWORD = "aria123"` — change to your own password before any real demo.
- `app.secret_key = ...` — set a real random string (or set env var `ARIA_SECRET_KEY`).

**Run it:**

```bash
python app.py
```

You should see something like:
```
mDNS registered: aria.local -> 192.168.1.42
 * Running on http://0.0.0.0:5000
```

**Verify it's working:** open `http://localhost:5000/api/status` in a browser — you
should see `{"logged_in": false}`.

**mDNS note:** the backend tries to register `aria.local` automatically via the
`zeroconf` Python package (already in requirements.txt), so the ESP32 can find it
by name instead of a hardcoded IP. If mDNS registration fails silently (some
networks/firewalls block it), you can fall back to hardcoding your laptop's local
IP address in the firmware instead (see firmware section below).

**Default login:** username `admin`, password `aria123` (change this — see above).

---

## 2. Frontend (React dashboard)

**Where it goes:** same laptop as the backend is easiest for a demo, but it can run
on any machine (even your phone's browser) as long as it can reach the backend.

**Setup:**

```bash
cd frontend
npm install
cp .env.example .env
```

Open `.env` and check `VITE_API_BASE` — for a local demo the default
(`http://localhost:5000`) is correct. If you're accessing the dashboard from a
different device on the same LAN, change it to your laptop's local IP, e.g.
`http://192.168.1.42:5000`. If you're accessing remotely via Tailscale, use the
backend machine's **Tailscale IP** there instead (see §4 below).

**Run it:**

```bash
npm run dev
```

Open the URL it prints (usually `http://localhost:5173`). Log in with the backend
credentials above.

---

## 3. Firmware (ESP32)

**Where it goes:** flashed onto the physical ESP32 board.

**Arduino IDE setup (one-time):**
1. Install the ESP32 board package: `File → Preferences → Additional Board
   Manager URLs` → add `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`,
   then `Tools → Board → Boards Manager` → search "esp32" → install.
2. Install libraries via `Tools → Manage Libraries`:
   - **WiFiManager** by tzapu
   - **DHT sensor library** by Adafruit (it will prompt to also install
     "Adafruit Unified Sensor" — accept that)
   - **ArduinoJson** by Benoit Blanchon
   - (ESPmDNS and HTTPClient come bundled with the ESP32 board package — no
     separate install needed)

**Wiring (matches the pin definitions at the top of the .ino file):**

| Component | ESP32 Pin |
|---|---|
| DHT22 data | GPIO 4 |
| MQ-135 analog out | GPIO 34 |
| LDR (via voltage divider) | GPIO 35 |
| PIR/IR digital out | GPIO 27 |
| LED (+ resistor) | GPIO 26 |
| L298N IN1 | GPIO 25 |
| L298N IN2 | GPIO 33 |
| L298N ENA | GPIO 32 |

Power the L298N and sensors from the ESP32's 5V pin (fed from the USB
adapter), and share a common ground between the ESP32 and the L298N module.

**Before flashing, open `ARIA_firmware.ino` and check:**
- `GAS_SAFETY_THRESHOLD` — this is a placeholder value (1800). You **must**
  calibrate this against your actual MQ-135 unit and room air — read the raw
  values via Serial Monitor first, in normal air vs. near a gas source (e.g. a
  lighter, briefly and safely), then set a sensible threshold in between.
- `SERVER_HOSTNAME` — leave as `"aria.local"` if mDNS is working (see backend
  section). If mDNS isn't resolving reliably on your network, replace this with
  your laptop's local IP address as a string, e.g. `"192.168.1.42"`.

**Flash it:**
1. Connect the ESP32 via USB, select the correct board (`Tools → Board`) and port
   (`Tools → Port`).
2. Click Upload.
3. Open Serial Monitor (115200 baud) to watch the boot log.

**First-time WiFi setup:**
1. On first boot, the ESP32 creates its own WiFi access point called
   `ARIA-Setup`.
2. On your phone, connect to that WiFi network — a setup page should pop up
   automatically (if not, open a browser and go to `192.168.4.1`).
3. Choose your home WiFi network and enter its password.
4. The ESP32 will reboot and join your home WiFi. It remembers this — you won't
   need to repeat this step unless you reset it or change networks.

**Note:** let the MQ-135 warm up for roughly a minute after power-on before
trusting its readings — this is a physical characteristic of the sensor, not a
bug.

---

## 4. Remote Access via Tailscale (optional, for "control from work" demo)

1. Install Tailscale on the laptop running the Flask backend, and on your
   phone: [tailscale.com/download](https://tailscale.com/download)
2. Sign in with the same account on both devices (Google/GitHub/Microsoft login
   works fine, free tier).
3. On the laptop, note its Tailscale IP (shown in the Tailscale app, looks like
   `100.x.x.x`).
4. On your phone, open a browser and go to `http://100.x.x.x:5173` (if running
   the dev dashboard on the phone's browser directly) — or better, build the
   frontend (`npm run build` in `frontend/`) and serve the static build from
   Flask/a simple static server so you only need one URL to remember.
5. As long as both devices have Tailscale running and are signed into the same
   account, this works from anywhere — the laptop doesn't need to be on the
   same WiFi as your phone.

**Reminder:** the laptop must be powered on and both `app.py` and `npm run dev`
(or the built frontend being served) must be running for remote access to work.
This is a known limitation of the current demo setup — see the project context
doc's Future Scope section for the production fix (always-on Pi/mini-PC).

---

## 5. Quick Start Checklist (demo day order of operations)

1. [ ] On laptop: `cd backend && source venv/bin/activate && python app.py`
2. [ ] On laptop (new terminal): `cd frontend && npm run dev`
3. [ ] Power on the ESP32 — wait ~60s for MQ-135 warm-up
4. [ ] Check Serial Monitor: confirm WiFi connected + readings being posted
5. [ ] Open dashboard in browser, log in, confirm live readings are updating
6. [ ] Test LED/fan toggle from the dashboard
7. [ ] (Optional) Test remote access via Tailscale from a phone off the home WiFi

---

## Troubleshooting

- **ESP32 can't reach `aria.local`:** replace `SERVER_HOSTNAME` in the firmware
  with your laptop's raw local IP address instead, and re-flash.
- **Dashboard shows "Waiting for sensor data":** check the Serial Monitor —
  confirm the ESP32 successfully POSTed (look for no error after
  `postReadings`). Also confirm the backend terminal isn't showing 404/500
  errors on `/api/readings`.
- **Login fails:** confirm you're using the username/password set in
  `backend/app.py` (`DEFAULT_USERNAME` / `DEFAULT_PASSWORD`), and that you
  haven't changed them without restarting the backend (which reseeds only if no
  user row exists yet — delete `backend/aria.db` to reset if needed).
- **CORS errors in browser console:** confirm `VITE_API_BASE` in
  `frontend/.env` matches the actual address the backend is reachable at.
