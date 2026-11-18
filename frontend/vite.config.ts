/// <reference types="vitest/config" />
// Vite = the dev server and bundler. The proxy forwards /api and /health to the FastAPI backend, so the
// browser only ever talks to one address (no CORS setup needed). The backend's port comes from
// AETHER_API_PORT (your environment, or the line in backend/.env — only AETHER_* lines are read there,
// never your secrets).
import { tmpdir } from "node:os";
import { join } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { backendPort, backendTarget } from "./backendTarget";

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, join(__dirname, "..", "backend"), "AETHER_"), ...process.env };
  const backend = backendTarget(env);
  return {
    plugins: [react()],
    // Keep Vite's cache outside OneDrive: OneDrive syncing locks the files Vite rewrites
    // (that caused "EPERM: operation not permitted, rmdir ...node_modules/.vite/deps").
    cacheDir: join(tmpdir(), "aether-vite-cache"),
    // Lets the website's "can't reach the backend" message name the right port.
    define: { __AETHER_API_PORT__: JSON.stringify(String(backendPort(env))) },
    server: {
      port: 5173,
      proxy: { "/api": backend, "/health": backend },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
