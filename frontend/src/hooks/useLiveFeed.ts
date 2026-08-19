/**
 * WebSocket subscription to the backend's live feed.
 *
 * The dashboard is push-driven: the backend polls the node once per interval and fans
 * the result out here. Reconnects with backoff so a laptop waking from sleep, or the
 * backend restarting, recovers without a page reload.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { liveSocketUrl } from "../api";
import type { LiveSnapshot } from "../types";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 15_000;

export type FeedState = "connecting" | "open" | "closed";

interface UseLiveFeed {
  snapshot: LiveSnapshot | null;
  feedState: FeedState;
}

export function useLiveFeed(enabled: boolean): UseLiveFeed {
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [feedState, setFeedState] = useState<FeedState>("closed");

  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<number | null>(null);
  const attemptsRef = useRef(0);
  const disposedRef = useRef(false);

  const connect = useCallback(() => {
    if (disposedRef.current) return;
    setFeedState("connecting");

    const socket = new WebSocket(liveSocketUrl());
    socketRef.current = socket;

    socket.onopen = () => {
      attemptsRef.current = 0;
      setFeedState("open");
    };

    socket.onmessage = (event) => {
      try {
        setSnapshot(JSON.parse(event.data as string) as LiveSnapshot);
      } catch {
        // A malformed frame must not tear down a working feed; drop it and continue.
      }
    };

    socket.onclose = () => {
      setFeedState("closed");
      if (disposedRef.current) return;
      // Exponential backoff, capped, so a long outage does not hammer the server.
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** attemptsRef.current, RECONNECT_MAX_MS);
      attemptsRef.current += 1;
      timerRef.current = window.setTimeout(connect, delay);
    };

    socket.onerror = () => socket.close();
  }, []);

  useEffect(() => {
    if (!enabled) return;
    disposedRef.current = false;
    connect();

    return () => {
      disposedRef.current = true;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [enabled, connect]);

  return { snapshot, feedState };
}
