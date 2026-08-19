# Contributing to ARIA

Team notes for Shine, Roshan and Ryyan — and anyone picking this up later.

---

## Setup

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m aria.hashpw          # generates the two required secrets
cp .env.example .env           # paste them in

# Frontend
cd ../frontend
npm install
```

Node 20.19+ recommended. Vite is pinned to 7.x on purpose — 8.x pulls a platform-specific
native binary, which is awkward across three machines.

---

## Day-to-day loop

Nothing requires hardware. Run the simulator and work against it:

```bash
# Terminal 1
cd backend && python tools/fake_node.py --port 8080

# Terminal 2 — with ARIA_NODE_HOSTS=127.0.0.1 and ARIA_NODE_PORT=8080 in .env
cd backend && python -m aria

# Terminal 3 — hot-reloading dashboard at localhost:5173
cd frontend && npm run dev
```

Useful simulator flags:

| Flag | Effect |
|---|---|
| `--seed 42` | Repeatable sensor values, for debugging something specific |
| `--no-gas-spike` | Stops the periodic alarm, when it gets in the way |
| `--verbose` | Log every request |

---

## Changing the node's interface

`docs/CONTRACT.md` is the source of truth, and **three** places implement it:

1. `docs/CONTRACT.md` — the spec
2. `backend/tools/fake_node.py` — the simulator
3. `firmware/aria_node/aria_api.cpp` — the real node

Plus `backend/aria/models.py` (validation) and `frontend/src/types.ts` (the TS mirror).

**Change the spec first, then all of them together.** The models use `extra="forbid"`, so
if you update the firmware and forget the backend, a test fails immediately rather than a
renamed field being silently ignored.

The edge automation rules exist in two implementations — `aria_automation.cpp` and the
simulator's `_apply_edge_rules`. They must stay in step; the rule priority in `CONTRACT.md`
is what both follow.

---

## Before you commit

```bash
cd backend && python -m pytest -q --cov=aria --cov-report=term-missing
cd frontend && npx tsc --noEmit
```

- Coverage must stay at or above **80%** (currently 90%).
- Firmware must compile clean:
  ```bash
  arduino-cli compile --fqbn "esp32:esp32:esp32:PartitionScheme=huge_app" --warnings all firmware/aria_node
  ```

Commit format:

```
<type>: <description>

<optional body>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`.

---

## Code conventions

**Python** — PEP 8, type annotations on every signature, Pydantic models frozen
(`frozen=True`), repository pattern for all data access. Never construct SQL by
concatenation; the existing queries are all parameterised.

**TypeScript** — no `any`. API responses unwrap in exactly one place (`src/api.ts`); the
rest of the app deals in plain data or a thrown `ApiError`.

**C++ / firmware** — file-local state in an anonymous `namespace`, not global. Validate
before applying, and apply all-or-nothing so a bad request cannot leave the node
half-configured.

**Everywhere** — no hardcoded values (settings go in `config.py` / `aria_config.h`), handle
errors explicitly, prefer new objects to mutation, and keep files focused (200–400 lines).

---

## Things not to break

These are load-bearing, and each exists for a reason worth remembering:

1. **The gas alarm cannot be overridden from the network.** Not by manual mode, not by an
   API call. The node re-asserts it before answering a command.
2. **Thresholds persist to NVS.** Without that, a reboot silently disarms the safety rule.
3. **Automation never waits on the network.** Nothing in `aria_automation.cpp` should ever
   make a network call.
4. **History queries stay bounded.** Both a time window and a row cap, always.
5. **Nulls stay null.** A failed DHT22 read is `NULL`, never `0.0`.
6. **No default password.** Startup must keep failing when secrets are missing.
7. **Fonts stay bundled.** No CDN at runtime — the dashboard has to work with the internet
   unplugged, which is the entire point of the project.

---

## Adding a sensor

1. Add pins and thresholds to `aria_config.h` (**ADC1 only** — GPIO 32–39 — for anything
   analog; see the note in that file).
2. Extend `AriaSample` and `sensorsRead()` in `aria_sensors.*`.
3. Add the field to `GET /sensors` in `aria_api.cpp`, and to `CONTRACT.md`.
4. Add it to `SensorReading` in `models.py` with an explicit valid range.
5. Add the column in `db.py`, the insert/select in `repository.py`, and `StoredReading`.
6. Mirror it in the simulator so tests keep working without hardware.
7. Add it to `types.ts`, then a tile in `SensorTiles.tsx` and a series in `HistoryChart.tsx`.
8. Write the test, then update this list if you learned something worth passing on.

---

## Author & support

- **Portfolio** — <https://ryyansafar.site>
- **GitHub** — <https://github.com/ryyansafar>
- **Buy me a coffee** — <https://buymeacoffee.com/ryyansafar>
- **PayPal** — <https://www.paypal.com/paypalme/ryyansafar>
- **Razorpay** — <https://razorpay.me/@ryyansafar>
