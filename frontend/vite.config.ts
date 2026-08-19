import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * During development the dashboard runs on Vite's server (5173) while the API runs on
 * 8000, so /api is proxied. In production there is no proxy and no CORS: FastAPI serves
 * the built bundle from the same origin.
 */
const API_TARGET = process.env.ARIA_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        ws: true, // the live feed is a WebSocket upgrade on /api/live
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
});
