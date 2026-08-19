import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import type { ActuatorState, Reading } from "../types";

interface Props {
  /** Live reading, so the panel reflects edge-driven changes it did not initiate. */
  reading: Reading | null;
  disabled: boolean;
}

export function ActuatorPanel({ reading, disabled }: Props) {
  const [state, setState] = useState<ActuatorState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Track the live feed: the node's own automation changes actuators without us asking,
  // so the buttons must follow the node rather than only local optimistic state.
  useEffect(() => {
    if (!reading) return;
    setState({ led: reading.led, fan: reading.fan, mode: reading.mode });
  }, [reading]);

  async function send(patch: Partial<ActuatorState>, key: string) {
    setBusy(key);
    setError(null);
    try {
      setState(await api.setActuators(patch));
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "Command failed.");
    } finally {
      setBusy(null);
    }
  }

  const alarm = reading?.gas_alarm === true;
  const isManual = state?.mode === "manual";

  return (
    <div className="panel">
      <h2>Manual control</h2>

      <div className="control-row">
        <div>
          <div className="name">Automation mode</div>
          <div className="hint">
            {isManual
              ? "Edge rules suspended — actuators hold your setting"
              : "Node's own rules are driving the actuators"}
          </div>
        </div>
        <div className="segmented">
          <button
            className={!isManual ? "on" : ""}
            disabled={disabled || busy !== null}
            onClick={() => send({ mode: "auto" }, "auto")}
          >
            Auto
          </button>
          <button
            className={isManual ? "on" : ""}
            disabled={disabled || busy !== null}
            onClick={() => send({ mode: "manual" }, "manual")}
          >
            Manual
          </button>
        </div>
      </div>

      <div className="control-row">
        <div>
          <div className="name">Light (LED)</div>
          <div className="hint">GPIO via current-limiting resistor</div>
        </div>
        <button
          className={state?.led ? "on" : ""}
          disabled={disabled || busy !== null}
          onClick={() => send({ led: !state?.led, mode: "manual" }, "led")}
        >
          {busy === "led" ? "…" : state?.led ? "On" : "Off"}
        </button>
      </div>

      <div className="control-row">
        <div>
          <div className="name">Fan (DC motor)</div>
          <div className="hint">Driven through the L298N module</div>
        </div>
        <button
          className={state?.fan ? "on" : ""}
          disabled={disabled || busy !== null}
          onClick={() => send({ fan: !state?.fan, mode: "manual" }, "fan")}
        >
          {busy === "fan" ? "…" : state?.fan ? "On" : "Off"}
        </button>
      </div>

      {alarm && (
        <p className="error">
          Gas alarm active — the node is enforcing its safety response and will ignore
          conflicting commands until the level clears.
        </p>
      )}
      {error && <p className="error">{error}</p>}
      {disabled && !error && <p className="empty">Node offline — controls unavailable.</p>}
    </div>
  );
}
