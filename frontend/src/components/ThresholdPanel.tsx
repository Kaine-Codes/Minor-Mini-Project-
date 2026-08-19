import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import type { NodeConfig } from "../types";

/** Field metadata mirroring the ranges in docs/CONTRACT.md. */
const FIELDS = [
  {
    key: "gas_threshold_pct",
    label: "Gas alarm threshold",
    unit: "%",
    min: 0,
    max: 100,
    step: 1,
    hint: "Relative index, not ppm. Above this the node acts on its own.",
  },
  {
    key: "dark_threshold_pct",
    label: "Darkness threshold",
    unit: "%",
    min: 0,
    max: 100,
    step: 1,
    hint: "Below this, motion turns the light on.",
  },
  {
    key: "temp_fan_threshold_c",
    label: "Fan temperature",
    unit: "°C",
    min: 0,
    max: 60,
    step: 0.5,
    hint: "At or above this, the fan runs.",
  },
  {
    key: "motion_light_hold_s",
    label: "Light hold after motion",
    unit: "s",
    min: 5,
    max: 3600,
    step: 5,
    hint: "How long the light stays on after the last motion.",
  },
] as const satisfies ReadonlyArray<{
  key: keyof NodeConfig;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  hint: string;
}>;

interface Props {
  disabled: boolean;
  onSaved: () => void;
}

export function ThresholdPanel({ disabled, onSaved }: Props) {
  const [config, setConfig] = useState<NodeConfig | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .config()
      .then((data) => {
        setConfig(data);
        setDraft(Object.fromEntries(FIELDS.map((f) => [f.key, String(data[f.key])])));
        setError(null);
      })
      .catch((exc) => setError(exc instanceof ApiError ? exc.message : "Could not load config."));
  }, []);

  function validate(): Partial<NodeConfig> | string {
    const patch: Record<string, number> = {};
    for (const field of FIELDS) {
      const raw = draft[field.key];
      const value = Number(raw);
      if (raw === undefined || raw.trim() === "" || Number.isNaN(value)) {
        return `${field.label} must be a number.`;
      }
      if (value < field.min || value > field.max) {
        return `${field.label} must be between ${field.min} and ${field.max}.`;
      }
      // Only send what actually changed, so the node's NVS is not rewritten needlessly.
      if (config && value !== config[field.key]) patch[field.key] = value;
    }
    return patch as Partial<NodeConfig>;
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);

    const result = validate();
    if (typeof result === "string") {
      setError(result);
      return;
    }
    if (Object.keys(result).length === 0) {
      setError("No changes to save.");
      return;
    }

    setBusy(true);
    try {
      const updated = await api.setConfig(result);
      setConfig(updated);
      setDraft(Object.fromEntries(FIELDS.map((f) => [f.key, String(updated[f.key])])));
      setSaved(true);
      onSaved();
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "Could not save config.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h2>Edge thresholds</h2>
      <p className="empty" style={{ marginTop: -6, marginBottom: 14 }}>
        Stored on the node in NVS. These rules keep running with this server switched off.
      </p>

      <form onSubmit={save}>
        {FIELDS.map((field) => (
          <div className="field" key={field.key}>
            <label htmlFor={field.key}>
              {field.label} ({field.unit})
            </label>
            <input
              id={field.key}
              type="number"
              inputMode="decimal"
              min={field.min}
              max={field.max}
              step={field.step}
              value={draft[field.key] ?? ""}
              disabled={disabled || config === null}
              onChange={(e) => setDraft({ ...draft, [field.key]: e.target.value })}
            />
            <div className="range">{field.hint}</div>
          </div>
        ))}

        <div className="form-actions">
          <button className="primary" type="submit" disabled={disabled || busy || config === null}>
            {busy ? "Saving…" : "Save to node"}
          </button>
          {config && (
            <button
              type="button"
              className="ghost"
              disabled={busy}
              onClick={() =>
                setDraft(Object.fromEntries(FIELDS.map((f) => [f.key, String(config[f.key])])))
              }
            >
              Reset
            </button>
          )}
        </div>

        {error && <p className="error">{error}</p>}
        {saved && <p className="success">Saved and persisted to the node.</p>}
      </form>
    </div>
  );
}
