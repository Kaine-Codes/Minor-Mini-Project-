import type { Reading } from "../types";

interface TileProps {
  label: string;
  value: string;
  unit?: string;
  meta?: string;
  accent: string;
  /** 0–100, drives the little progress bar. Omit for non-scalar tiles. */
  fill?: number;
  stale?: boolean;
}

function Tile({ label, value, unit, meta, accent, fill, stale }: TileProps) {
  return (
    <div className="tile" style={{ ["--tile-accent" as string]: accent }}>
      <div className="label">{label}</div>
      <div className={`value${stale ? " stale" : ""}`}>
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {meta && <div className="meta">{meta}</div>}
      {fill !== undefined && (
        <div className="bar">
          <i style={{ width: `${Math.max(0, Math.min(100, fill))}%` }} />
        </div>
      )}
    </div>
  );
}

interface Props {
  reading: Reading | null;
  gasThreshold: number | null;
}

export function SensorTiles({ reading, gasThreshold }: Props) {
  if (!reading) {
    return (
      <div className="grid tiles">
        {["Temperature", "Humidity", "Air quality", "Ambient light", "Motion"].map((label) => (
          <Tile key={label} label={label} value="—" accent="var(--border-bright)" />
        ))}
      </div>
    );
  }

  // A null temperature/humidity means the DHT22 read failed on this sample, which is
  // normal and intermittent — show it as unavailable rather than as zero.
  const temp = reading.temperature_c;
  const humidity = reading.humidity_pct;

  return (
    <div className="grid tiles">
      <Tile
        label="Temperature"
        value={temp === null ? "—" : temp.toFixed(1)}
        unit={temp === null ? undefined : "°C"}
        meta={temp === null ? "sensor read failed" : undefined}
        accent="var(--temp)"
        fill={temp === null ? undefined : ((temp - 10) / 40) * 100}
        stale={temp === null}
      />
      <Tile
        label="Humidity"
        value={humidity === null ? "—" : humidity.toFixed(0)}
        unit={humidity === null ? undefined : "%"}
        meta={humidity === null ? "sensor read failed" : undefined}
        accent="var(--humidity)"
        fill={humidity ?? undefined}
        stale={humidity === null}
      />
      <Tile
        label="Air quality"
        value={reading.gas_pct.toFixed(0)}
        unit="%"
        meta={
          gasThreshold === null
            ? "relative, not calibrated ppm"
            : `threshold ${gasThreshold.toFixed(0)}% · relative`
        }
        accent={reading.gas_alarm ? "var(--alarm)" : "var(--gas)"}
        fill={reading.gas_pct}
      />
      <Tile
        label="Ambient light"
        value={reading.light_pct.toFixed(0)}
        unit="%"
        accent="var(--light)"
        fill={reading.light_pct}
      />
      <Tile
        label="Motion"
        value={reading.motion ? "Detected" : "Clear"}
        meta={new Date(reading.recorded_at).toLocaleTimeString()}
        accent="var(--motion)"
      />
    </div>
  );
}
