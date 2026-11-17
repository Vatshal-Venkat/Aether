import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as client from "./api/client";
import type { ChatResult } from "./api/types";

vi.mock("./api/client", async (importOriginal) => {
  const real = await importOriginal<typeof import("./api/client")>();
  return { ...real, askChat: vi.fn(), getPatients: vi.fn(), getHealth: vi.fn() };
});

const askChat = vi.mocked(client.askChat);
const getPatients = vi.mocked(client.getPatients);
const getHealth = vi.mocked(client.getHealth);

const answer = (text: string): ChatResult => ({
  answer: text, kind: "answer", sql: [], sources: ["clinical_db.conditions"], table: null,
  unverified_numbers: [], documents: [], timings: { route: 0.5 },
});

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

const PATIENTS = [
  { id: "p1", name: "Angelyn934 Harris789", birthdate: "1970-01-01", gender: "F" },
  { id: "p2", name: "Miranda712 Jacobs452", birthdate: "1980-01-01", gender: "F" },
];

beforeEach(() => {
  askChat.mockReset();
  getPatients.mockReset().mockResolvedValue(PATIENTS);
  getHealth.mockReset().mockResolvedValue({ status: "ok", clinical: "ok", billing: "ok", drug_labels: "ok: 1 chunks", llm_provider: "groq" });
  try { localStorage.clear(); } catch { /* ignore */ }
  document.documentElement.dataset.theme = "dark";
});

const box = () => screen.getByRole("textbox", { name: "Message" });

async function ask(text: string) {
  await userEvent.type(box(), `${text}{Enter}`);
}

describe("App", () => {
  it("sends a question and shows the answer", async () => {
    askChat.mockResolvedValue(answer("There are **8** patients."));
    render(<App />);
    await ask("How many patients have diabetes?");
    expect(await screen.findByText("8")).toBeInTheDocument();
    expect(screen.getByText("How many patients have diabetes?")).toBeInTheDocument();
    expect(askChat.mock.calls[0][0]).toMatchObject({ message: "How many patients have diabetes?", role: "clinician" });
  });

  it("shows thinking orbs while the backend works", async () => {
    askChat.mockReturnValue(new Promise(() => {}));
    render(<App />);
    await ask("Hello?");
    expect(await screen.findByRole("status", { name: "Aether is thinking" })).toBeInTheDocument();
  });

  it("no double submit and no empty submit", async () => {
    askChat.mockReturnValue(new Promise(() => {}));
    render(<App />);
    await userEvent.type(box(), "{Enter}");
    expect(askChat).not.toHaveBeenCalled();
    await ask("First");
    await ask("Second");
    expect(askChat).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("patient mode requires a patient", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Patient" }));
    expect(box()).toBeDisabled();
    expect(screen.getByText(/Choose a patient/)).toBeInTheDocument();
  });

  it("patient picker filters and selects", async () => {
    askChat.mockResolvedValue(answer("Your medications..."));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Patient" }));
    await userEvent.type(await screen.findByRole("searchbox", { name: "Search patients" }), "mir");
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
    await userEvent.click(options[0]);
    expect(box()).toBeEnabled();
    await ask("What medications am I taking?");
    expect(askChat.mock.calls[0][0]).toMatchObject({ role: "patient", patient_id: "p2" });
  });

  it("switching role clears the conversation and starts a new session", async () => {
    askChat.mockResolvedValue(answer("Answer one."));
    render(<App />);
    await ask("Q1");
    await screen.findByText("Answer one.");
    const firstSession = askChat.mock.calls[0][0].session_id;
    await userEvent.click(screen.getByRole("button", { name: "Patient" }));
    expect(screen.queryByText("Answer one.")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Clinician" }));
    await ask("Q2");
    expect(askChat.mock.calls[1][0].session_id).not.toBe(firstSession);
  });

  it("discards a late answer after a role switch", async () => {
    const late = deferred<ChatResult>();
    askChat.mockReturnValueOnce(late.promise);
    render(<App />);
    await ask("Slow clinician question");
    await userEvent.click(screen.getByRole("button", { name: "Patient" }));
    await act(async () => late.resolve(answer("Clinician-only answer")));
    expect(screen.queryByText("Clinician-only answer")).toBeNull();
  });

  it("shows a network error and re-enables the composer", async () => {
    askChat.mockRejectedValue(new client.ApiError(0, "Can't reach the Aether backend. Is it running on port 8000?"));
    render(<App />);
    await ask("Anything");
    expect(await screen.findByText(/Can't reach the Aether backend/)).toBeInTheDocument();
    expect(box()).toBeEnabled();
  });

  it("an example chip sends its question", async () => {
    askChat.mockResolvedValue(answer("8."));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "How many patients have diabetes?" }));
    expect(askChat.mock.calls[0][0].message).toBe("How many patients have diabetes?");
  });

  it("the theme toggle switches and remembers", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /light theme/i }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("aether.theme")).toBe("light");
  });

  it("the status orb reflects backend health", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("status-orb")).toHaveAttribute("data-state", "up"));
  });
});

describe("final review fixes", () => {
  it("Enter while composing (Japanese/Chinese input) does not send", async () => {
    const { fireEvent } = await import("@testing-library/react");
    render(<App />);
    await userEvent.type(box(), "にほん");
    fireEvent.keyDown(box(), { key: "Enter", isComposing: true });
    fireEvent.keyDown(box(), { key: "Enter", keyCode: 229 });
    expect(askChat).not.toHaveBeenCalled();
  });

  it("limits a question to 1,000 characters", () => {
    render(<App />);
    expect(box()).toHaveAttribute("maxLength", "1000");
  });

  it("scrolls without smooth animation when reduced motion is requested", async () => {
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((q: string) => ({
      matches: q.includes("reduce"), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    const spy = vi.spyOn(Element.prototype, "scrollIntoView");
    spy.mockClear(); // count only this test's scrolls
    askChat.mockReturnValue(new Promise(() => {}));
    render(<App />);
    await ask("Q");
    expect(spy).toHaveBeenCalled();
    expect(spy.mock.calls.every(([opts]) => (opts as ScrollIntoViewOptions)?.behavior === "auto")).toBe(true);
    window.matchMedia = original;
    spy.mockRestore();
  });
});
