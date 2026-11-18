import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, askChat, askChatStream, getHealth, getPatients, getResultPage } from "./client";

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
const status = (code: number, body: unknown = {}) =>
  new Response(JSON.stringify(body), { status: code, headers: { "Content-Type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("posts the chat request body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ answer: "8", kind: "answer", sql: [], sources: [], table: null,
      unverified_numbers: [], documents: [], timings: {} }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await askChat({ message: "How many?", role: "patient", patient_id: "p1", session_id: "s1" });
    expect(result.answer).toBe("8");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ message: "How many?", role: "patient", patient_id: "p1", session_id: "s1" });
  });

  it.each([
    [422, { detail: "Unknown patient_id" }, "That patient wasn't found."],
    [503, { detail: "The database is unavailable right now. Please try again shortly." },
      "The database is unavailable right now. Please try again shortly."],
    [500, {}, "Something went wrong (HTTP 500)."],
  ])("api error mapping %i", async (code, body, message) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(status(code, body)));
    const err = await askChat({ message: "x", role: "clinician", session_id: "s" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(code);
    expect(err.userMessage).toBe(message);
  });

  it("maps a network failure to a friendly message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await getHealth().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.userMessage).toMatch(/Can't reach the Aether backend/);
  });

  it("passes an abort through untouched", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));
    const err = await askChat({ message: "x", role: "clinician", session_id: "s" }).catch((e) => e);
    expect(err.name).toBe("AbortError");
  });

  it("getPatients parses the list", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok([{ id: "p1", name: "Ann1 Lee2", birthdate: "1990-01-01", gender: "F" }])));
    expect((await getPatients())[0].name).toBe("Ann1 Lee2");
  });
});

describe("422 is not always an unknown patient (final review)", () => {
  it("validation errors get their own message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ msg: "String should have at most 1000 characters" }] }),
      { status: 422, headers: { "Content-Type": "application/json" } })));
    const err = await askChat({ message: "x".repeat(1200), role: "clinician", session_id: "s" }).catch((e) => e);
    expect(err.userMessage).toMatch(/at most 1,000 characters/);
  });
});

describe("askChatStream (live progress over Server-Sent Events)", () => {
  const sse = (...parts: string[]) => {
    const enc = new TextEncoder();
    return new Response(new ReadableStream({
      start(c) { parts.forEach((p) => c.enqueue(enc.encode(p))); c.close(); },
    }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
  };
  const FINAL = JSON.stringify({ answer: "Done.", kind: "answer", sql: [], sources: [], table: null,
    unverified_numbers: [], documents: [], timings: {} });

  it("reports progress in order and resolves with the final result, even when events are split", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sse(
      'event: progress\ndata: {"step": "route"}\n\nevent: prog', 'ress\ndata: {"step": "execute", "db": "billing"}\n\n',
      `event: final\ndata: ${FINAL}\n\n`)));
    const seen: unknown[] = [];
    const result = await askChatStream({ message: "q", role: "clinician", session_id: "s" }, (p) => seen.push(p));
    expect(seen).toEqual([{ step: "route" }, { step: "execute", db: "billing" }]);
    expect(result.answer).toBe("Done.");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/chat/stream");
  });

  it("an error event becomes an ApiError with the backend's message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sse('event: error\ndata: {"message": "The AI service is rate-limited."}\n\n')));
    const err = await askChatStream({ message: "q", role: "clinician", session_id: "s" }, () => {}).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.userMessage).toBe("The AI service is rate-limited.");
  });

  it("a stream that ends without a result is reported", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sse('event: progress\ndata: {"step": "route"}\n\n')));
    const err = await askChatStream({ message: "q", role: "clinician", session_id: "s" }, () => {}).catch((e) => e);
    expect(err.userMessage).toMatch(/interrupted/);
  });

  it("HTTP errors are mapped like the normal request", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(status(422, { detail: "Unknown patient_id" })));
    const err = await askChatStream({ message: "q", role: "patient", patient_id: "x", session_id: "s" }, () => {}).catch((e) => e);
    expect(err.userMessage).toBe("That patient wasn't found.");
  });
});

describe("Plan 5", () => {
  it("a rate limit (429) gets a friendly message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(status(429, { detail: "Too many questions at once — please wait a moment." })));
    const err = await askChat({ message: "q", role: "clinician", session_id: "s" }).catch((e) => e);
    expect(err.status).toBe(429);
    expect(err.userMessage).toBe("Too many questions at once — please wait a moment.");
  });

  it("fetches a page of a big table for the same person", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ columns: ["n"], rows: [[100]], page: 2, pages: 3, total_rows: 250 }));
    vi.stubGlobal("fetch", fetchMock);
    const page = await getResultPage("abc", 2, "patient", "p1");
    expect(page.rows).toEqual([[100]]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/results/abc?page=2&role=patient&patient_id=p1");
  });
});

describe("result pages: the backend's own explanation is shown (final review)", () => {
  it("404: expired or not yours", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(status(404, { detail: "This table has expired or isn't yours — ask the question again." })));
    const err = await getResultPage("abc", 2, "clinician", null).catch((e) => e);
    expect(err.userMessage).toBe("This table has expired or isn't yours — ask the question again.");
  });

  it("422 with a plain explanation (page out of range) is shown as is", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(status(422, { detail: "page must be between 1 and 3" })));
    const err = await getResultPage("abc", 9, "clinician", null).catch((e) => e);
    expect(err.userMessage).toBe("page must be between 1 and 3");
  });
});
