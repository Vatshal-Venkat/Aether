# Aether — Web UI — Design (approved 2026-11-17)

## Intent
A web front end for the Aether backend so the chatbot can be used (and shown) in a browser. Built now, before
Plan 4 (memory, clarification, streaming); it must work with today's API and be easy to extend for streaming later.

## Owner's requirements (verbatim intent)
- Black and white only. Sleek, minimal, stylish. Hairline (1 px) lines. Amazing animations.
- "Thinking orbs" — and orbs whenever the backend is working; the header status shows the backend is running.

## Goals
- Ask questions as a clinician, or as a chosen patient ("view as"), with no login (matches backend decision).
- Show everything the backend returns, nothing hidden: answer, kind, every SQL try (database, error, the filtered
  query that actually ran), sources, result table (with "partial" flag), FDA label passages with links, unverified
  numbers, per-step timings.
- Clear states: thinking, refusal, out of scope, error (AI rate-limited, DB down → backend messages), network down.

## Non-goals (now)
- Streaming / SSE, conversation memory, clarification (Plan 4). Login. Mobile-first polish beyond a sane narrow layout.
- Pagination of large results (Plan 5); the table shows the rows the API returns (≤1000) with a scroll.

## Approaches considered
1. **Vite + React + TypeScript, plain CSS tokens, `motion` for animation, SVG orbs** — chosen: smallest stack, easy to
   read, precise control of a monochrome hairline look; SVG blur/"goo" filter gives fluid orbs without images.
2. Tailwind CSS — rejected: another layer to learn; little benefit for a tiny, token-driven monochrome design.
3. Next.js — rejected: server rendering/routing not needed for a single-page chat on localhost.

## Design
- Layout: top bar (wordmark "AETHER", role pill Clinician | Patient with searchable patient picker, theme toggle,
  backend status orb), conversation column (max ~760 px), hairline composer pinned at the bottom.
- Empty state: one large slowly drifting orb cluster + 3–4 example question chips (hairline outline) that change with role.
- Thinking: a cluster of grayscale orbs that drift, merge and breathe (SVG gooey filter), with a caption cycling through
  pipeline phases ("Routing…", "Writing SQL…", "Checking safety…", "Querying…", "Writing the answer…", "Checking
  numbers…") — timed guesses until streaming exists; on completion the cluster collapses into the small orb beside the answer.
- Answer: text rises/fades in by line; minimal markdown (paragraphs, lists, tables, bold, code); meta line (kind,
  sources, total time); hairline disclosure rows — SQL (n), Table (rows), Labels (n), Timeline — that expand smoothly.
  Unverified numbers listed with a dotted underline note. Refusal/out-of-scope/error answers: muted static orb.
- Role switch clears the conversation (answers from one view never mix with the other) and starts a new session id.
- Status orb: polls `GET /health` every 15 s; breathing filled orb = backend up; hollow still orb = down (tooltip shows details).
- Theme: dark by default, light via toggle (remembered in localStorage, wrapped in try/catch). Colours: black, white, a
  small gray scale only. Fonts: Inter (UI), JetBrains Mono (SQL), self-hosted via @fontsource (no external requests).
- Motion respects `prefers-reduced-motion` (orbs freeze to a soft static state; transitions become fades).

## Constraints
- Free/open source only. Runs on Node 20.19 (pin Vitest 4.1 + jsdom 27, which support Node 20).
- Dev server proxies `/api` and `/health` to `http://localhost:8000` (no CORS needed; backend CORS also allows localhost).
- No secrets in the frontend. No analytics, no external CDNs at runtime.

## Left to the builder
Exact animation curves/durations, orb count and sizes, example questions, gray scale values.
