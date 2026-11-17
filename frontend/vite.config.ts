/// <reference types="vitest/config" />
// Vite = the dev server and bundler. The proxy forwards /api and /health to the FastAPI backend
// on port 8000, so the browser only ever talks to one address (no CORS setup needed).
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
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
