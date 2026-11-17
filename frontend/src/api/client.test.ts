import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, askChat, getHealth, getPatients } from "./client";

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
