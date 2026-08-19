/** Shapes mirroring the backend's Pydantic models (see backend/aria/models.py). */

export type ActuatorMode = "auto" | "manual";

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta: Record<string, unknown> | null;
}

export interface NodeStatus {
  online: boolean;
  host: string | null;
  firmware: string | null;
  consecutive_failures: number;
  last_error: string | null;
  last_seen_at: string | null;
}

export interface Reading {
  id: number;
  recorded_at: string;
  node_id: string;
  temperature_c: number | null;
  humidity_pct: number | null;
  gas_pct: number;
  light_pct: number;
  motion: boolean;
  led: boolean;
  fan: boolean;
  gas_alarm: boolean;
  mode: ActuatorMode;
}

export interface LiveSnapshot {
  status: NodeStatus;
  reading: Reading | null;
}

export interface ActuatorState {
  led: boolean;
  fan: boolean;
  mode: ActuatorMode;
}

export interface NodeConfig {
  gas_threshold_pct: number;
  dark_threshold_pct: number;
  temp_fan_threshold_c: number;
  motion_light_hold_s: number;
  warmup_s: number;
}

export interface NodeEvent {
  id: number;
  occurred_at: string;
  kind: string;
  detail: string | null;
}

export interface SessionInfo {
  authenticated: boolean;
  username: string | null;
}
