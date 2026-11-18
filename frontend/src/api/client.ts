// The website's phone line to the backend. Three calls: ask a question, list patients (for the
// "view as patient" picker), and check health. Every failure becomes an ApiError carrying a
// sentence a person can read ("Can't reach the Aether backend...") instead of a raw HTTP code.
// A cancelled request (we cancel when you switch role mid-question) is passed through untouched.

import type { ChatRequest, ChatResult, Health, Patient, Progress, ResultPage, Role } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public userMessage: string,
  ) {
    super(userMessage);
    this.name = "ApiError";
  }
}

const UNREACHABLE = `Can't reach the Aether backend. Is it running on port ${__AETHER_API_PORT__}?`;
const INTERRUPTED = "The connection to the backend was interrupted before the answer arrived. Please try again.";

async function messageFor(response: Response): Promise<string> {
  let detail: unknown;
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail;
  } catch {
    detail = undefined;
  }
  if (response.status === 422) {
    // 422 means "the request was refused as given": an unknown patient, a question over 1,000 characters
    // (FastAPI's checks send a list), or a plain explanation such as "page must be between 1 and 3".
    if (detail === "Unknown patient_id") return "That patient wasn't found.";
    if (typeof detail === "string") return detail;
    return "That question couldn't be sent — questions can be at most 1,000 characters.";
  }
  if (response.status === 404 && typeof detail === "string") {
    return detail; // e.g. "This table has expired or isn't yours — ask the question again."
  }
  if (response.status === 429) {
    return typeof detail === "string" ? detail : "Too many questions at once — please wait a moment.";
  }
  if (response.status === 503) {
    return typeof detail === "string" ? detail : "The database is unavailable right now.";
  }
  return `Something went wrong (HTTP ${response.status}).`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, UNREACHABLE);
  }
  if (!response.ok) throw new ApiError(response.status, await messageFor(response));
  return (await response.json()) as T;
}

export function askChat(req: ChatRequest, signal?: AbortSignal): Promise<ChatResult> {
  return request<ChatResult>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
}

/** Ask a question and hear the backend's progress as it works (Server-Sent Events):
 *  onProgress is called each time a step starts; the promise resolves with the final result. */
export async function askChatStream(
  req: ChatRequest,
  onProgress: (p: Progress) => void,
  signal?: AbortSignal,
): Promise<ChatResult> {
  let response: Response;
  try {
    response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(req),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, UNREACHABLE);
  }
  if (!response.ok) throw new ApiError(response.status, await messageFor(response));
  if (!response.body) throw new ApiError(0, INTERRUPTED);

  // An SSE stream is text: blocks separated by a blank line, each with "event: x" and "data: {...}".
  // Network chunks can cut a block anywhere, so we buffer until a full block has arrived.
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1]?.trim();
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || data === undefined) continue;
      const payload = JSON.parse(data);
      if (event === "progress") onProgress(payload as Progress);
      else if (event === "final") return payload as ChatResult;
      else if (event === "error") throw new ApiError(500, String(payload.message ?? "Something went wrong."));
    }
    if (done) throw new ApiError(0, INTERRUPTED);
  }
}

/** The next 100 rows of a big table; only works for the person who asked (same role and patient). */
export function getResultPage(resultId: string, page: number, role: Role, patientId: string | null): Promise<ResultPage> {
  const params = new URLSearchParams({ page: String(page), role });
  if (role === "patient" && patientId) params.set("patient_id", patientId);
  return request<ResultPage>(`/api/results/${encodeURIComponent(resultId)}?${params}`);
}

export function getPatients(): Promise<Patient[]> {
  return request<Patient[]>("/api/patients");
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}
