/**
 * Typed API client.
 *
 * Every backend response uses the same envelope, so unwrapping happens in exactly one
 * place here and callers deal in plain data or a thrown ApiError.
 */

import type {
  ActuatorMode,
  ActuatorState,
  ApiResponse,
  LiveSnapshot,
  NodeConfig,
  NodeEvent,
  Reading,
  SessionInfo,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
      ...init,
    });
  } catch {
    // Network-level failure: the backend process is down or unreachable.
    throw new ApiError("Cannot reach the ARIA server.", 0);
  }

  let envelope: ApiResponse<T>;
  try {
    envelope = (await response.json()) as ApiResponse<T>;
  } catch {
    throw new ApiError(`Unexpected non-JSON response (HTTP ${response.status}).`, response.status);
  }

  if (!response.ok || !envelope.success) {
    throw new ApiError(envelope.error ?? `Request failed (HTTP ${response.status}).`, response.status);
  }
  return envelope.data as T;
}

export const api = {
  session: () => request<SessionInfo>("/api/auth/session"),

  login: (username: string, password: string) =>
    request<{ username: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  logout: () => request<{ logged_out: boolean }>("/api/auth/logout", { method: "POST" }),

  status: () => request<LiveSnapshot>("/api/status"),

  history: (hours: number) =>
    request<Reading[]>(`/api/readings/history?hours=${encodeURIComponent(hours)}`),

  events: (limit = 40) => request<NodeEvent[]>(`/api/events?limit=${limit}`),

  actuators: () => request<ActuatorState>("/api/actuators"),

  setActuators: (patch: { led?: boolean; fan?: boolean; mode?: ActuatorMode }) =>
    request<ActuatorState>("/api/actuators", {
      method: "POST",
      body: JSON.stringify(patch),
    }),

  config: () => request<NodeConfig>("/api/config"),

  setConfig: (patch: Partial<NodeConfig>) =>
    request<NodeConfig>("/api/config", {
      method: "POST",
      body: JSON.stringify(patch),
    }),
};

/** WebSocket URL for the live feed, derived from the current origin. */
export function liveSocketUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/live`;
}
