/// <reference types="vitest/config" />
// Vite = the dev server and bundler. The proxy forwards /api and /health to the FastAPI backend
// on port 8000, so the browser only ever talks to one address (no CORS setup needed).
import { tmpdir } from "node:os";
import { join } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = "http://localhost:8000";

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
