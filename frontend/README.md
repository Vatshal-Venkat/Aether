# Aether — website

A black-and-white React page for the Aether chatbot.

```bash
npm install      # first time
npm run dev      # http://localhost:5173 (the backend must run on port 8000)
npm test         # component tests (Vitest)
npm run build    # type check + production build into dist/
```

The dev server forwards `/api` and `/health` to `http://localhost:8000` (see `vite.config.ts`).
Design tokens (the only colours, lines and timings used) live in `src/styles/tokens.css`.
