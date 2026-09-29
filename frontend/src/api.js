// Backend base URL.
// Default is "" (empty string) -- this means "same origin as the page itself".
// This works automatically for the simple setup where Flask serves the built
// frontend directly (one server, one URL, e.g. http://localhost:5000 or
// http://aria.local:5000 or the Tailscale address -- whatever you're viewing
// the dashboard from IS the backend).
//
// You only need to set VITE_API_BASE if you're running the Vite dev server
// (`npm run dev`) separately from Flask during frontend development.
export const API_BASE = import.meta.env.VITE_API_BASE || "";

// Retry wrapper — Tailscale over mobile networks can drop packets,
// so we retry up to MAX_RETRIES times with a small delay between each.
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1500;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function request(path, options = {}, retriesLeft = MAX_RETRIES) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      credentials: "include", // sends session cookie for auth
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Request failed: ${res.status}`);
    }
    return res.json();
  } catch (err) {
    // Only retry on network errors (failed to fetch), not on server errors (4xx/5xx)
    if (retriesLeft > 0 && err.message === "Failed to fetch") {
      console.warn(`[ARIA] Retrying ${path} (${retriesLeft} left)...`);
      await wait(RETRY_DELAY_MS);
      return request(path, options, retriesLeft - 1);
    }
    throw err;
  }
}

export const login = (username, password) =>
  request("/api/login", { method: "POST", body: JSON.stringify({ username, password }) });

export const logout = () => request("/api/logout", { method: "POST" });

export const getStatus = () => request("/api/status");

export const getLatest = () => request("/api/readings/latest");

export const getHistory = (limit = 200) => request(`/api/readings/history?limit=${limit}`);

// The ESP32 already polls this to know what the dashboard last commanded.
// The dashboard reads it too now, so a page refresh shows the real current
// LED/fan state instead of always starting from "OFF".
export const getCommands = () => request("/api/commands");

export const sendCommand = (led, fan) =>
  request("/api/commands", { method: "POST", body: JSON.stringify({ led, fan }) });
