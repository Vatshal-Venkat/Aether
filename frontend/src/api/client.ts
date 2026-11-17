// The website's phone line to the backend. Three calls: ask a question, list patients (for the
// "view as patient" picker), and check health. Every failure becomes an ApiError carrying a
// sentence a person can read ("Can't reach the Aether backend...") instead of a raw HTTP code.
// A cancelled request (we cancel when you switch role mid-question) is passed through untouched.

import type { ChatRequest, ChatResult, Health, Patient } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public userMessage: string,
  ) {
    super(userMessage);
    this.name = "ApiError";
  }
}

const UNREACHABLE = "Can't reach the Aether backend. Is it running on port 8000?";

async function messageFor(response: Response): Promise<string> {
  let detail: unknown;
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail;
  } catch {
    detail = undefined;
  }
  if (response.status === 422) {
    // 422 also comes from input checks (e.g. a question over 1,000 characters), not only unknown patients.
    return detail === "Unknown patient_id"
      ? "That patient wasn't found."
      : "That question couldn't be sent — questions can be at most 1,000 characters.";
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

export function getPatients(): Promise<Patient[]> {
  return request<Patient[]>("/api/patients");
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}
