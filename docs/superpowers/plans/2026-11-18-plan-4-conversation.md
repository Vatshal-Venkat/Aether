# Plan 4 — Conversation: Follow-ups, Clarification, Answer Streaming

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Aether remembers the conversation ("how many of *them* are female?" works), asks back when a question is genuinely unclear ("what's the revenue?" → "Of a hospital, or an insurer?" with one-click options), shows how it understood each follow-up, and reveals answers word by word.

**Architecture:** A small conversation store (SQLite, `backend/data/memory.sqlite`, git-ignored) keeps each turn keyed by **session + role + patient** — a session id reused under another patient sees no history (privacy). The graph gains `contextualize` (first step: with history, the AI rewrites the follow-up into a standalone question; without history, no AI call) and a `clarify` route kind (the router may return a short question and 2–4 options). Everything downstream uses the standalone question, unchanged. The runner loads history before and saves the turn after. The website shows "Understood as …", clarification option chips, and a word-by-word reveal of the (already fact-checked) answer.

**Spec:** `docs/superpowers/specs/2026-11-17-healthcare-multidb-chatbot-design.md` §9 (contextualize, clarify, memory), §10 (`kind: clarification`, `/api/chat/stream`, `GET /api/sessions/{id}`), §15 milestone 5.

## Global Constraints
- Memory is scoped to (session_id, role, patient_id); history window = last 3 turns; stored answer text truncated to 400 chars; result rows are never stored.
- No history → no extra AI call (contextualize is free for first questions).
- Clarification only for genuinely ambiguous questions; the router prompt must prefer answering when one reading is clearly most likely.
- Rulings vs spec, decided here: (1) a small SQLite table instead of a LangGraph checkpointer — the checkpointer would persist whole states including result rows (patient data), and a plain table makes the privacy scoping explicit and readable; (2) the answer text is revealed word by word on the website instead of server `answer_chunk` events — the answer is held back until fact-checked anyway, so server chunks would add requests without adding information.

## Review Focus
1. Session reused across patients/roles must not see the other's history. → `test_history_scoped_to_role_and_patient`.
2. A follow-up rewritten into a question about ANOTHER patient in patient mode must still be refused/filtered (the patient-name check and RLS run on the standalone question). → `test_followup_standalone_still_privacy_checked`.
3. First question costs no extra AI call. → `test_no_history_no_contextualize_call`.
4. Clarification options, when clicked, produce a normal answer using the clarification turn as context. → `test_clarification_then_choice`.
5. Errors/refusals are stored as turns but don't poison context (only answer/clarification turns are offered as context).

### Task 1: Conversation store
- `app/memory/store.py`: `Turn` (session_id, role, patient_id, question, standalone, answer, kind, created_at); `ConversationStore(path)` with `history(session_id, role, patient_id, limit=3) -> list[Turn]` (oldest first) and `add(turn)`; `turns(session_id) -> list[Turn]` for the API. Settings: `memory_path = data_dir / "memory.sqlite"`, `memory_turns = 3`.
- Tests: add/history order and limit; scoping by role and patient; answer truncation; survives reopen.

### Task 2: contextualize + clarify in the graph
- State: `history`, `original_question`; `RouteDecision` + `clarify_question: str = ""`, `options: list[str] = []`; RouteKind + `"clarify"`; AnswerKind + `"clarification"`.
- `contextualize(state, deps)`: no history → `{}` (no AI call). Else `ask_json` → `{"standalone": str}`; sets `question` = standalone, `original_question` = what the user typed.
- route prompt: describe `clarify` (only when truly ambiguous; give a short question + 2–4 short options).
- `clarify` node: `kind="clarification"`, answer = clarify_question.
- Runner: `run_chat`/`stream_chat` accept `store`; load history (answer/clarification kinds only), save the turn after; `ChatResult.standalone_question` (when it differs) and `options`.
- Tests: no-history no-call; follow-up rewritten and used downstream (SQL prompt contains the standalone question); clarification result with options; clarification then choice; patient-mode privacy on standalone; turn saved with kind; errors saved but not used as context.

### Task 3: API + website
- `GET /api/sessions/{id}` → turns (question, standalone, answer, kind).
- Progress step `contextualize` → caption "Recalling the conversation" (mood calm).
- Website: "Understood as: …" line under follow-up answers; clarification card with option chips that send the option; word-by-word reveal of answer text (respects reduced motion; the full text is in the DOM for screen readers).
- Tests: client/types; App: option chip sends; "Understood as" shown; reveal completes; moods mapping for contextualize.

### Task 4: Accuracy report + live check + docs
- Un-plan PL01/PL02 (category `conversation`), add 2 more conversation cases (follow-up on a billing answer; clarification reply). Run the conversation cases + a regression sample live. Update `docs/how-it-works.md`.
