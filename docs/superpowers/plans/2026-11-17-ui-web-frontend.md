# UI — Web Front End Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sleek black-and-white React web app for Aether: role switch (clinician / view-as patient), chat with thinking orbs, and full transparency of every answer (SQL, table, labels, timings).

**Architecture:** Vite + React + TypeScript single-page app in `frontend/`. A typed API client talks to the FastAPI backend through the Vite dev proxy. State lives in one `useChat` hook (messages, pending, role, session). Presentational components: TopBar (RolePill, PatientPicker, ThemeToggle, StatusOrb), Conversation (EmptyState, UserMessage, AnswerCard with Disclosures), ThinkingOrbs, Composer. Plain CSS with design tokens; `motion` for animation; orbs are SVG with a goo filter.

**Tech Stack:** Node 20.19, Vite 8, React 19.3, TypeScript ~5.9, motion 14, @fontsource-variable/inter + jetbrains-mono; tests: Vitest 4.1, jsdom 27.4, @testing-library/react 16 + user-event 14 + jest-dom.

**Spec:** `docs/superpowers/specs/2026-11-17-frontend-ui-design.md`

## Global Constraints

- Colours: only black, white and grays (tokens `--ink`, `--paper`, `--gray-1..5`). No other hue anywhere, including focus rings and selection.
- Lines are 1 px (`--hairline: 1px solid var(--line)`). No box-shadows. Corner radius ≤ 999px pills / 0–2px elsewhere.
- Dark theme default; light via toggle stored in localStorage key `aether.theme` (read/write wrapped in try/catch).
- All animation goes through `motion` or CSS keyframes, and respects `prefers-reduced-motion` (orbs static, transitions → opacity only).
- API base paths: `/api/chat`, `/api/patients`, `/health`; dev proxy to `http://localhost:8000`.
- No external network requests at runtime (fonts self-hosted). No secrets.
- Every component file starts with a one-paragraph plain-English comment (the owner is learning from the code).
- Commands run from `frontend/`. Tests: `npm test` (vitest run). Type check: `npm run typecheck` (tsc --noEmit). Build: `npm run build`.

## Review Focus

1. **Switching role mid-conversation** — the conversation clears, a new session id is used, and an in-flight answer from the old role is discarded, never shown under the new role. → Task 4 `discards a late answer after role switch`.
2. **Backend errors** — 422 (unknown patient), 503 (database down), network failure, and `kind:"error"` answers each show a clear message and leave the composer usable. → Task 1 `api error mapping`, Task 4 `shows network error and re-enables composer`.
3. **Large results** — a 1,000-row table renders inside a scroll area without freezing the page; `truncated` shows "partial". → Task 3 `table caps and shows partial`.
4. **Hostile text in answers or labels** — HTML/script in an answer or excerpt is shown as text, never injected. → Task 3 `renders html as text`.
5. **Double submit / empty input** — Enter on empty input does nothing; while pending, submit is disabled. → Task 4 `no double submit`.

---

### Task 1: Scaffold, design tokens, API client

**Files:** Create `frontend/` (package.json, vite.config.ts with proxy + vitest config, tsconfig.json, index.html, src/main.tsx, src/styles/tokens.css, src/styles/global.css, src/api/types.ts, src/api/client.ts, src/test/setup.ts); modify root `.gitignore` (`frontend/node_modules/`, `frontend/dist/`).
Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- `types.ts`: `Role = "clinician" | "patient"`; `AnswerKind = "answer" | "refusal" | "out_of_scope" | "error"`; `SqlRecord {db: "clinical"|"billing"; query: string; error: string|null}`; `QueryResult {columns: string[]; rows: unknown[][]; total_rows: number; truncated: boolean}`; `DocumentRef {label; source_url; excerpt}`; `ChatResult {answer; kind; sql: SqlRecord[]; sources: string[]; table: QueryResult|null; unverified_numbers: string[]; documents: DocumentRef[]; timings: Record<string, number>}`; `Patient {id; name; birthdate; gender}`; `Health {status; clinical; billing; drug_labels; llm_provider}`.
- `client.ts`: `class ApiError extends Error {status: number; userMessage: string}`; `askChat(req: {message; role; patient_id?; session_id}, signal?: AbortSignal): Promise<ChatResult>`; `getPatients(): Promise<Patient[]>`; `getHealth(): Promise<Health>`. Error mapping: 422 → "That patient wasn't found."; 503 → body.detail or "The database is unavailable right now."; network failure → "Can't reach the Aether backend. Is it running on port 8000?"; other → "Something went wrong (HTTP <status>)."

- [ ] Step 1: Scaffold with pinned deps; write failing tests: `posts the chat request body`, `api error mapping` (422/503/500/network via mocked fetch), `getPatients parses list`.
- [ ] Step 2: `npm test` → FAIL. Step 3: implement. Step 4: `npm test` and `npm run typecheck` → PASS.

### Task 2: Orbs — ThinkingOrbs, StatusOrb, AnswerOrb

**Files:** Create `src/components/orbs/ThinkingOrbs.tsx`, `StatusOrb.tsx`, `orbs.css`, `src/hooks/useReducedMotion.ts`, `src/hooks/usePhases.ts`.
Test: `src/components/orbs/orbs.test.tsx`

**Interfaces:** `ThinkingOrbs({size?: "large"|"small", active: boolean, caption?: string})` — SVG with goo filter and 5 orbs animated with motion (drift paths, scale breathing); `aria-label="Aether is thinking"` + `role="status"` when active. `usePhases(active: boolean): string` cycles PHASES = ["Routing", "Writing SQL", "Checking safety", "Querying", "Writing the answer", "Checking numbers"] every 1.4 s, holding the last one. `StatusOrb({health: Health|null, error: boolean})` — filled breathing orb (title "Backend running…") or hollow still orb (title "Backend not reachable"). `AnswerOrb({kind})` — small orb, filled for answer, outlined for refusal/out_of_scope, dashed for error.

- [ ] Step 1: failing tests: `thinking orbs announce status`, `phases advance and hold last` (fake timers), `status orb running vs down` (title + data-state), `reduced motion renders static` (matchMedia mock).
- [ ] Step 2–4: FAIL → implement → PASS + typecheck.

### Task 3: Answer rendering — AnswerCard, Disclosures, ResultTable, mini markdown

**Files:** Create `src/components/answer/AnswerCard.tsx`, `Disclosure.tsx`, `SqlList.tsx`, `ResultTable.tsx`, `LabelList.tsx`, `Timeline.tsx`, `answer.css`, `src/lib/markdown.tsx`.
Test: `src/components/answer/answer.test.tsx`, `src/lib/markdown.test.tsx`

**Interfaces:** `AnswerCard({result: ChatResult, question: string})`; `Disclosure({title, count?, children})` (button with aria-expanded; motion height animation); `renderMarkdown(text: string): ReactNode` — paragraphs, `-`/`1.` lists, `**bold**`, `` `code` ``, pipe tables; never uses dangerouslySetInnerHTML. SqlList shows db label (`clinical_db`/`billing_db`), failed tries struck through with their error. ResultTable shows at most 200 rows rendered + "Showing 200 of N" and "partial" badge when truncated. LabelList: label, excerpt, "Open label ↗" link (`rel="noreferrer noopener"`, `target="_blank"`). Timeline: one hairline bar per step proportional to time, total.

- [ ] Step 1: failing tests: `renders answer text and meta (sources, total time)`, `disclosures expand with aria-expanded`, `sql failed attempt struck through`, `table caps and shows partial`, `labels link out safely`, `unverified numbers note`, `renders html as text` (answer `<img src=x onerror=alert(1)>` appears as text, no img element), markdown cases (list, bold, table, code).
- [ ] Step 2–4: FAIL → implement → PASS + typecheck.

### Task 4: App shell — TopBar, RolePill, PatientPicker, Composer, useChat, health polling

**Files:** Create `src/App.tsx`, `src/hooks/useChat.ts`, `src/hooks/useHealth.ts`, `src/hooks/useTheme.ts`, `src/components/TopBar.tsx`, `RolePill.tsx`, `PatientPicker.tsx`, `ThemeToggle.tsx`, `Composer.tsx`, `Conversation.tsx`, `EmptyState.tsx`, `app.css`.
Test: `src/App.test.tsx`, `src/hooks/useChat.test.ts`

**Interfaces:** `useChat(): {messages: Message[]; pending: boolean; role; patient: Patient|null; setRole(role, patient?); send(text): Promise<void>; reset()}` where `Message = {id; type: "user"|"assistant"|"error"; text?; result?; question?}`; session id = `crypto.randomUUID()` regenerated on role/patient change; an AbortController + generation counter discards late answers. `useHealth(intervalMs = 15000)`. `useTheme()` with localStorage `aether.theme`. Composer: textarea auto-grow, Enter sends, Shift+Enter newline, disabled while pending or when patient mode has no patient chosen. EmptyState chips (clinician: "How many patients have diabetes?", "Which doctor has seen the most patients?", "Which insurance company has the most customers?", "What are the side effects of metformin?"; patient: "What medications am I taking?", "When was my last visit?", "How much do I still owe?", "What are the side effects of my medications?").

- [ ] Step 1: failing tests: `sends question and shows answer` (mock api), `shows thinking orbs while pending`, `no double submit`, `patient mode requires a patient` (composer disabled + hint), `patient picker filters and selects`, `switching role clears conversation and session`, `discards a late answer after role switch`, `shows network error and re-enables composer`, `example chip sends its question`, `theme toggle persists`.
- [ ] Step 2–4: FAIL → implement → PASS + typecheck + `npm run build`.

### Task 5: Real-browser check, polish, docs

**Files:** Modify `docs/how-it-works.md` (a "The website" section for non-technical readers), `docs/setup-windows.md` (install Node deps, run backend + frontend), `frontend/README.md` (short run instructions).

- [ ] Step 1: Run backend (`uvicorn app.main:app --port 8000`) and `npm run dev`; drive the app in Chrome (DevTools MCP): empty state, a clinician question, a patient question, a drug question, role switch, light/dark, reduced motion, narrow width. Take screenshots; check console for errors/warnings; fix issues (each behavioural fix test-first).
- [ ] Step 2: Docs. Step 3: `npm test`, `npm run typecheck`, `npm run build`, backend `pytest -q` → all PASS.
