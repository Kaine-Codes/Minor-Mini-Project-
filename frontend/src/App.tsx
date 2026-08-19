import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "./api";
import { ActuatorPanel } from "./components/ActuatorPanel";
import { EventLog } from "./components/EventLog";
import { HistoryChart } from "./components/HistoryChart";
import { Login } from "./components/Login";
import { SensorTiles } from "./components/SensorTiles";
import { StatusBar } from "./components/StatusBar";
import { ThresholdPanel } from "./components/ThresholdPanel";
import { useLiveFeed } from "./hooks/useLiveFeed";
import type { NodeConfig } from "./types";

/** Refresh the history chart and event log every Nth live sample, not on every one. */
const REFRESH_EVERY_N_SAMPLES = 6;

type AuthState = "checking" | "signed-out" | "signed-in";

export default function App() {
  const [auth, setAuth] = useState<AuthState>("checking");
  const [config, setConfig] = useState<NodeConfig | null>(null);
  const [sampleCount, setSampleCount] = useState(0);
  const [manualRefresh, setManualRefresh] = useState(0);

  useEffect(() => {
    api
      .session()
      .then((info) => setAuth(info.authenticated ? "signed-in" : "signed-out"))
      .catch(() => setAuth("signed-out"));
  }, []);

  const { snapshot, feedState } = useLiveFeed(auth === "signed-in");

  useEffect(() => {
    if (snapshot?.reading) setSampleCount((n) => n + 1);
  }, [snapshot?.reading?.id]);

  // Fetch thresholds once signed in, so the gas tile can show the active threshold.
  const loadConfig = useCallback(() => {
    api
      .config()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  useEffect(() => {
    if (auth === "signed-in") loadConfig();
  }, [auth, loadConfig]);

  const refreshKey = useMemo(
    () => Math.floor(sampleCount / REFRESH_EVERY_N_SAMPLES) + manualRefresh,
    [sampleCount, manualRefresh],
  );

  if (auth === "checking") {
    return (
      <div className="login-wrap">
        <p className="empty">Loading…</p>
      </div>
    );
  }

  if (auth === "signed-out") {
    return <Login onAuthenticated={() => setAuth("signed-in")} />;
  }

  const reading = snapshot?.reading ?? null;
  const status = snapshot?.status ?? null;
  const nodeOffline = status?.online !== true;

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <h1>
            AR<span>IA</span>
          </h1>
          <p className="subtitle">Adaptive Room Intelligence &amp; Automation</p>
        </div>
      </header>

      <StatusBar status={status} feedState={feedState} onLoggedOut={() => setAuth("signed-out")} />

      {reading?.gas_alarm && (
        <div className="banner alarm" role="alert">
          <i className="dot bad live" />
          <div>
            Gas threshold exceeded — the node has triggered its local response.
            <div className="note">
              This ran on the ESP32 itself, without waiting for this server.
            </div>
          </div>
        </div>
      )}

      {reading && !reading.gas_alarm && snapshot?.status.online && config === null && (
        <div className="banner warn">
          <i className="dot warn" />
          <div>
            Could not read thresholds from the node.
            <div className="note">Live readings still work; threshold editing is unavailable.</div>
          </div>
        </div>
      )}

      {nodeOffline && (
        <div className="banner warn" role="status">
          <i className="dot bad" />
          <div>
            Node unreachable{status?.last_error ? ` — ${status.last_error}` : ""}.
            <div className="note">
              Showing the last known reading. The node's own safety automation continues
              regardless of this server.
            </div>
          </div>
        </div>
      )}

      <SensorTiles reading={reading} gasThreshold={config?.gas_threshold_pct ?? null} />

      <div className="grid panels">
        <HistoryChart refreshKey={refreshKey} />

        <ActuatorPanel reading={reading} disabled={nodeOffline} />

        <ThresholdPanel
          disabled={nodeOffline}
          onSaved={() => {
            loadConfig();
            setManualRefresh((n) => n + 1);
          }}
        />

        <EventLog refreshKey={refreshKey} />
      </div>

      <footer className="footnote">
        <div>
          ARIA · local-first room automation · no third-party server ever sees this data.
          Built by Shine Daniel, Roshan VN and Ryyan Safar — Dept. of Electronics &amp;
          Communication Engineering, RSET.
        </div>
        <div className="links">
          <a href="https://ryyansafar.site" target="_blank" rel="noreferrer noopener">
            Portfolio
          </a>
          <a href="https://github.com/ryyansafar" target="_blank" rel="noreferrer noopener">
            GitHub
          </a>
          <a href="https://buymeacoffee.com/ryyansafar" target="_blank" rel="noreferrer noopener">
            Buy me a coffee
          </a>
          <a
            href="https://www.paypal.com/paypalme/ryyansafar"
            target="_blank"
            rel="noreferrer noopener"
          >
            PayPal
          </a>
          <a href="https://razorpay.me/@ryyansafar" target="_blank" rel="noreferrer noopener">
            Razorpay
          </a>
        </div>
      </footer>
    </div>
  );
}
