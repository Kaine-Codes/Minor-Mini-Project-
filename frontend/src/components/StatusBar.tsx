import { api } from "../api";
import type { FeedState } from "../hooks/useLiveFeed";
import type { NodeStatus } from "../types";

interface Props {
  status: NodeStatus | null;
  feedState: FeedState;
  onLoggedOut: () => void;
}

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

export function StatusBar({ status, feedState, onLoggedOut }: Props) {
  const nodeOnline = status?.online === true;

  return (
    <div className="statusbar">
      <span className="pill">
        <i className={`dot ${nodeOnline ? "ok live" : "bad"}`} />
        Node {nodeOnline ? "online" : "offline"}
        {status?.host && <span style={{ color: "var(--text-faint)" }}>· {status.host}</span>}
      </span>

      <span className="pill">
        <i className={`dot ${feedState === "open" ? "ok" : feedState === "connecting" ? "warn" : "bad"}`} />
        Feed {feedState}
      </span>

      <span className="pill">Last sample {relativeTime(status?.last_seen_at ?? null)}</span>

      {status?.firmware && <span className="pill">fw {status.firmware}</span>}

      <span className="spacer" />

      <button
        className="ghost"
        onClick={async () => {
          await api.logout().catch(() => undefined);
          onLoggedOut();
        }}
      >
        Sign out
      </button>
    </div>
  );
}
