#!/usr/bin/env python3
"""Fake ARIA node — a software stand-in for the ESP32.

Implements ``docs/CONTRACT.md`` exactly, including the edge automation rules and the
MQ-135 warm-up period, using plausible drifting sensor values.

Why this exists: it decouples the whole software stack from hardware availability. The
dashboard, the poller, the retention job and the auth flow can all be built and demoed
before a single wire is stripped — and if a sensor dies the night before the review,
this is the fallback that keeps the demo alive.

Run it:

    python tools/fake_node.py --port 8080

Then point the backend at it:

    ARIA_NODE_HOSTS=127.0.0.1 ARIA_NODE_PORT=8080 python -m aria

Stdlib only, no dependencies, so it runs anywhere Python does.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

logger = logging.getLogger("fake_node")

FIRMWARE = "1.0.0-sim"
ADC_MAX = 4095

DEFAULT_CONFIG: dict[str, Any] = {
    "gas_threshold_pct": 60.0,
    "dark_threshold_pct": 25.0,
    "temp_fan_threshold_c": 30.0,
    "motion_light_hold_s": 30,
    "warmup_s": 20,  # shortened vs. real hardware so demos are not spent waiting
}

# Validation ranges, mirroring CONTRACT.md. The simulator enforces them so that a bug in
# the backend's validation gets caught here rather than silently accepted.
CONFIG_RANGES: dict[str, tuple[type, float, float]] = {
    "gas_threshold_pct": (float, 0.0, 100.0),
    "dark_threshold_pct": (float, 0.0, 100.0),
    "temp_fan_threshold_c": (float, 0.0, 60.0),
    "motion_light_hold_s": (int, 5, 3600),
    "warmup_s": (int, 0, 600),
}


class FakeNode:
    """Sensor simulation plus the same edge automation the firmware runs."""

    def __init__(self, *, node_id: str, seed: int | None, gas_spike: bool) -> None:
        self.node_id = node_id
        self._rng = random.Random(seed)
        self._boot = time.monotonic()
        self._lock = threading.Lock()
        self._config = dict(DEFAULT_CONFIG)
        self._mode = "auto"
        self._led = False
        self._fan = False
        self._last_motion_at = 0.0
        self._alarm_active = False
        self._gas_spike = gas_spike
        # Random walk state so consecutive samples look correlated, not like noise.
        self._temp = 27.0
        self._humidity = 58.0
        self._gas_base = 22.0

    # --- simulation --------------------------------------------------------- #

    def _uptime_s(self) -> float:
        return time.monotonic() - self._boot

    def _drift(self, value: float, *, step: float, low: float, high: float) -> float:
        return max(low, min(high, value + self._rng.uniform(-step, step)))

    def _simulate(self) -> dict[str, Any]:
        """Advance the simulation one sample and return the raw sensor values."""
        uptime = self._uptime_s()
        self._temp = self._drift(self._temp, step=0.15, low=18.0, high=42.0)
        self._humidity = self._drift(self._humidity, step=0.4, low=25.0, high=95.0)
        self._gas_base = self._drift(self._gas_base, step=0.8, low=8.0, high=45.0)

        # A slow sine makes the light chart look like a room rather than static noise.
        light_pct = 50.0 + 35.0 * math.sin(uptime / 120.0) + self._rng.uniform(-3, 3)
        light_pct = max(0.0, min(100.0, light_pct))

        gas_pct = self._gas_base
        if self._gas_spike:
            # Push past the threshold for ~15s every 2 minutes so the alarm path,
            # the event log and the dashboard banner can all be exercised on demand.
            if (uptime % 120.0) < 15.0:
                gas_pct = min(100.0, self._config["gas_threshold_pct"] + 12.0)

        motion = self._rng.random() < 0.25

        # DHT22 reads genuinely fail now and then; emit nulls ~2% of the time so the
        # whole stack is forced to handle a missing value instead of assuming one.
        dht_failed = self._rng.random() < 0.02

        return {
            "temperature_c": None if dht_failed else round(self._temp, 1),
            "humidity_pct": None if dht_failed else round(self._humidity, 1),
            "gas_pct": round(gas_pct, 1),
            "light_pct": round(light_pct, 1),
            "motion": motion,
            "uptime_s": uptime,
        }

    # --- edge automation (mirrors the firmware) ------------------------------ #

    def _apply_edge_rules(self, sample: dict[str, Any], *, warmed_up: bool) -> bool:
        """Update actuators per the contract's rule priority. Returns ``gas_alarm``."""
        gas_alarm = warmed_up and sample["gas_pct"] >= self._config["gas_threshold_pct"]
        self._alarm_active = gas_alarm

        if sample["motion"]:
            self._last_motion_at = sample["uptime_s"]

        # 1. Gas alarm wins over everything, including manual mode.
        if gas_alarm:
            self._fan = True
            self._led = True
            return True

        # 2. Manual mode: hold the last commanded state, evaluate nothing else.
        if self._mode == "manual":
            return False

        # 3. Motion in the dark -> light on, held after the last motion.
        hold = self._config["motion_light_hold_s"]
        recently_active = (sample["uptime_s"] - self._last_motion_at) <= hold
        dark = sample["light_pct"] < self._config["dark_threshold_pct"]
        self._led = bool(recently_active and dark)

        # 4. Heat -> fan on.
        temp = sample["temperature_c"]
        self._fan = temp is not None and temp >= self._config["temp_fan_threshold_c"]
        return False

    # --- contract endpoints -------------------------------------------------- #

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "node_id": self.node_id,
            "firmware": FIRMWARE,
            "uptime_ms": int(self._uptime_s() * 1000),
        }

    def sensors(self) -> dict[str, Any]:
        with self._lock:
            sample = self._simulate()
            warmed_up = sample["uptime_s"] >= self._config["warmup_s"]
            gas_alarm = self._apply_edge_rules(sample, warmed_up=warmed_up)
            gas_pct = sample["gas_pct"]
            light_pct = sample["light_pct"]
            return {
                "node_id": self.node_id,
                "uptime_ms": int(sample["uptime_s"] * 1000),
                "temperature_c": sample["temperature_c"],
                "humidity_pct": sample["humidity_pct"],
                "gas_raw": int(gas_pct / 100.0 * ADC_MAX),
                "gas_pct": gas_pct,
                "light_raw": int(light_pct / 100.0 * ADC_MAX),
                "light_pct": light_pct,
                "motion": sample["motion"],
                "actuators": {"led": self._led, "fan": self._fan},
                "edge": {
                    "gas_alarm": gas_alarm,
                    "warmed_up": warmed_up,
                    "mode": self._mode,
                },
            }

    def set_actuators(self, body: dict[str, Any]) -> dict[str, Any]:
        allowed = {"led", "fan", "mode"}
        unknown = set(body) - allowed
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}")

        for key in ("led", "fan"):
            if key in body and not isinstance(body[key], bool):
                raise ValueError(f"{key} must be a boolean")
        if "mode" in body and body["mode"] not in ("auto", "manual"):
            raise ValueError("mode must be 'auto' or 'manual'")

        with self._lock:
            if "mode" in body:
                self._mode = body["mode"]
            if "led" in body:
                self._led = body["led"]
            if "fan" in body:
                self._fan = body["fan"]

            # Re-assert the alarm response before replying, so the caller is told the
            # state that is actually in effect rather than one that will be reverted a
            # moment later. Safety rules are not overridable from the network.
            if self._alarm_active:
                self._led = True
                self._fan = True

            return {"led": self._led, "fan": self._fan, "mode": self._mode}

    def get_config(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._config)

    def set_config(self, body: dict[str, Any]) -> dict[str, Any]:
        unknown = set(body) - set(CONFIG_RANGES)
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}")

        # Validate everything before applying anything — a partly-valid body must not
        # leave the node half-configured.
        validated: dict[str, Any] = {}
        for key, value in body.items():
            expected, low, high = CONFIG_RANGES[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a number")
            if expected is int and not float(value).is_integer():
                raise ValueError(f"{key} must be an integer")
            if not (low <= float(value) <= high):
                raise ValueError(f"{key} must be between {low} and {high}")
            validated[key] = expected(value)

        with self._lock:
            self._config = {**self._config, **validated}  # new dict, no in-place mutation
            return dict(self._config)


def make_handler(node: FakeNode) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"aria-fake-node/{FIRMWARE}"

        def log_message(self, fmt: str, *args: Any) -> None:
            logger.debug("%s - %s", self.address_string(), fmt % args)

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                raise ValueError("empty request body")
            if length > 8192:
                raise ValueError("request body too large")
            parsed = json.loads(self.rfile.read(length))
            if not isinstance(parsed, dict):
                raise ValueError("body must be a JSON object")
            return parsed

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            routes = {
                "/health": node.health,
                "/sensors": node.sensors,
                "/config": node.get_config,
            }
            handler = routes.get(self.path)
            if handler is None:
                self._send(404, {"error": f"unknown path {self.path}"})
                return
            self._send(200, handler())

        def do_POST(self) -> None:  # noqa: N802
            routes = {"/actuators": node.set_actuators, "/config": node.set_config}
            handler = routes.get(self.path)
            if handler is None:
                self._send(404, {"error": f"unknown path {self.path}"})
                return
            try:
                self._send(200, handler(self._read_json()))
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
            except json.JSONDecodeError:
                self._send(400, {"error": "malformed JSON"})

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Fake ARIA node (ESP32 stand-in)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--node-id", default="aria-node-sim")
    parser.add_argument("--seed", type=int, default=None, help="fix the RNG for repeatable runs")
    parser.add_argument(
        "--no-gas-spike",
        action="store_true",
        help="disable the periodic gas spike that exercises the alarm path",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    node = FakeNode(node_id=args.node_id, seed=args.seed, gas_spike=not args.no_gas_spike)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(node))
    logger.info("fake node %r listening on http://%s:%d", node.node_id, args.host, args.port)
    logger.info(
        "point the backend at it:  ARIA_NODE_HOSTS=%s ARIA_NODE_PORT=%d python -m aria",
        args.host,
        args.port,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
