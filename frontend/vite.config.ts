/// <reference types="vitest/config" />
// Vite = the dev server and bundler. The proxy forwards /api and /health to the FastAPI backend
// on port 8000, so the browser only ever talks to one address (no CORS setup needed).
import { tmpdir } from "node:os";
import { join } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 (::1) first; uvicorn listens on IPv4 only,
// so every request waited ~2.3 s for the fallback (measured: 2.98 s vs 0.68 s for /health).
const backend = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  // Keep Vite's cache outside OneDrive: OneDrive syncing locks the files Vite rewrites
  // (that caused "EPERM: operation not permitted, rmdir ...node_modules/.vite/deps").
  cacheDir: join(tmpdir(), "aether-vite-cache"),
  server: {
    port: 5173,
    proxy: { "/api": backend, "/health": backend },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
