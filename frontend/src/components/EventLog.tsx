import { useEffect, useState } from "react";

import { api, ApiError } from "../api";
import type { NodeEvent } from "../types";

const LABELS: Record<string, string> = {
  gas_alarm: "Gas alarm",
  gas_alarm_cleared: "Alarm cleared",
  node_online: "Node online",
  node_offline: "Node offline",
  command: "Command",
  config: "Config change",
};

interface Props {
  refreshKey: number;
}

export function EventLog({ refreshKey }: Props) {
  const [events, setEvents] = useState<NodeEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .events()
      .then((data) => {
        if (cancelled) return;
        setEvents(data);
        setError(null);
      })
      .catch((exc) => {
        if (!cancelled) setError(exc instanceof ApiError ? exc.message : "Could not load events.");
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return (
    <div className="panel">
      <h2>Event log</h2>
      {error && <p className="error">{error}</p>}
      {events.length === 0 && !error ? (
        <p className="empty">No events recorded yet.</p>
      ) : (
        <ul className="events">
          {events.map((event) => (
            <li key={event.id}>
              <time dateTime={event.occurred_at}>
                {new Date(event.occurred_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </time>
              <div>
                <div className={`kind ${event.kind}`}>{LABELS[event.kind] ?? event.kind}</div>
                {event.detail && <div className="detail">{event.detail}</div>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
