# Aether — website

A black-and-white React page for the Aether chatbot.

```bash
npm install      # first time
npm run dev      # http://localhost:5173 (forwards to the backend on AETHER_API_PORT, default 8000)
npm test         # component tests (Vitest)
npm run build    # type check + production build into dist/
```

The dev server forwards `/api` and `/health` to `http://127.0.0.1:<AETHER_API_PORT>` — read from your environment or
the `AETHER_API_PORT` line in `backend/.env` (see `vite.config.ts`, `backendTarget.ts`).
Design tokens (the only colours, lines and timings used) live in `src/styles/tokens.css`.
