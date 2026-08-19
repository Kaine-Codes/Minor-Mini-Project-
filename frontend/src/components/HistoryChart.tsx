import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  type ChartOptions,
} from "chart.js";
import { useEffect, useMemo, useState } from "react";
import { Line } from "react-chartjs-2";

import { api, ApiError } from "../api";
import type { Reading } from "../types";

ChartJS.register(
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Filler,
  Legend,
  Tooltip,
);

const WINDOWS = [
  { label: "1h", hours: 1 },
  { label: "6h", hours: 6 },
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
] as const;

const SERIES = [
  { key: "temperature_c", label: "Temp (°C)", color: "#ff8a3d", axis: "y" },
  { key: "humidity_pct", label: "Humidity (%)", color: "#4da3ff", axis: "y1" },
  { key: "gas_pct", label: "Gas (%)", color: "#ff4d6d", axis: "y1" },
  { key: "light_pct", label: "Light (%)", color: "#ffd23d", axis: "y1" },
] as const;

interface Props {
  /** Bumped by the parent on each live sample so the chart refreshes in step. */
  refreshKey: number;
}

export function HistoryChart({ refreshKey }: Props) {
  const [hours, setHours] = useState<number>(6);
  const [rows, setRows] = useState<Reading[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .history(hours)
      .then((data) => {
        if (cancelled) return;
        setRows(data);
        setError(null);
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof ApiError ? exc.message : "Could not load history.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [hours, refreshKey]);

  const data = useMemo(
    () => ({
      labels: rows.map((row) =>
        new Date(row.recorded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      ),
      datasets: SERIES.map((series) => ({
        label: series.label,
        // Nulls are preserved rather than zero-filled, so a failed DHT22 read shows as
        // a gap in the line instead of a fake drop to 0.
        data: rows.map((row) => row[series.key]),
        borderColor: series.color,
        backgroundColor: `${series.color}1f`,
        yAxisID: series.axis,
        borderWidth: 1.75,
        pointRadius: 0,
        pointHitRadius: 8,
        tension: 0.3,
        spanGaps: false,
      })),
    }),
    [rows],
  );

  const options = useMemo<ChartOptions<"line">>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: {
            color: "#8e9094",
            boxWidth: 10,
            boxHeight: 10,
            usePointStyle: true,
            font: { family: "Space Grotesk", size: 11 },
          },
        },
        tooltip: {
          backgroundColor: "#17181a",
          borderColor: "#33353a",
          borderWidth: 1,
          titleColor: "#f2f2f0",
          bodyColor: "#c9cacd",
          titleFont: { family: "Space Grotesk" },
          bodyFont: { family: "Space Grotesk" },
          padding: 10,
        },
      },
      scales: {
        x: {
          grid: { color: "#1b1c1f" },
          ticks: {
            color: "#5c5e63",
            maxTicksLimit: 8,
            font: { family: "Space Grotesk", size: 10 },
          },
        },
        y: {
          position: "left",
          grid: { color: "#1b1c1f" },
          ticks: { color: "#ff8a3d", font: { family: "Space Grotesk", size: 10 } },
          title: {
            display: true,
            text: "°C",
            color: "#8e9094",
            font: { family: "Space Grotesk", size: 10 },
          },
        },
        y1: {
          position: "right",
          min: 0,
          max: 100,
          grid: { drawOnChartArea: false },
          ticks: { color: "#8e9094", font: { family: "Space Grotesk", size: 10 } },
          title: {
            display: true,
            text: "%",
            color: "#8e9094",
            font: { family: "Space Grotesk", size: 10 },
          },
        },
      },
    }),
    [],
  );

  return (
    <div className="panel wide">
      <div className="chart-head">
        <h2 style={{ margin: 0 }}>History</h2>
        <div className="segmented">
          {WINDOWS.map((window) => (
            <button
              key={window.label}
              className={hours === window.hours ? "on" : ""}
              onClick={() => setHours(window.hours)}
            >
              {window.label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="chart-box">
        {rows.length === 0 && !loading ? (
          <p className="empty">
            No readings in this window yet. Samples appear as the backend polls the node.
          </p>
        ) : (
          <Line data={data} options={options} />
        )}
      </div>

      <p className="empty" style={{ marginTop: 8 }}>
        {rows.length} sample{rows.length === 1 ? "" : "s"} · gas is a relative index, not
        calibrated ppm
      </p>
    </div>
  );
}
