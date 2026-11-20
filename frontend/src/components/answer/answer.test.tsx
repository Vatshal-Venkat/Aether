import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChatResult } from "../../api/types";
import { AnswerCard, cleanAnswer } from "./AnswerCard";

const base: ChatResult = {
  answer: "There are **8** patients with diabetes.",
  kind: "answer",
  sql: [
    { db: "clinical", query: "SELECT cnt FROM conditions", error: "column \"cnt\" does not exist" },
    { db: "clinical", query: "SELECT count(DISTINCT patient) AS n FROM conditions", error: null },
  ],
  sources: ["clinical_db.conditions"],
  table: { columns: ["n"], rows: [[8]], total_rows: 1, truncated: false },
  unverified_numbers: [],
  documents: [],
  timings: { route: 0.7, generate_sql: 0.9, execute: 0.05, synthesize: 1.1 },
};

describe("AnswerCard", () => {
  it("renders answer text and meta (sources, total time)", () => {
    render(<AnswerCard result={base} />);
    expect(screen.getByText("8").closest("strong")).not.toBeNull();  // words are revealed one by one, each in a span
    expect(screen.getByText("clinical_db.conditions")).toBeInTheDocument();
    expect(screen.getByText("2.8 s")).toBeInTheDocument();
  });

  it("disclosures expand with aria-expanded", async () => {
    render(<AnswerCard result={base} />);
    const sqlButton = screen.getByRole("button", { name: /SQL/ });
    expect(sqlButton).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(sqlButton);
    expect(sqlButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/count\(DISTINCT patient\)/)).toBeInTheDocument();
  });

  it("sql failed attempt struck through with its error and database", async () => {
    render(<AnswerCard result={base} />);
    await userEvent.click(screen.getByRole("button", { name: /SQL/ }));
    const failed = screen.getByText("SELECT cnt FROM conditions");
    expect(failed.closest("[data-failed='true']")).not.toBeNull();
    expect(screen.getByText(/column "cnt" does not exist/)).toBeInTheDocument();
    expect(screen.getAllByText("clinical_db").length).toBeGreaterThan(0);
  });

  it("table caps rendered rows and shows partial", async () => {
    const rows = Array.from({ length: 1000 }, (_, i) => [i, `name ${i}`]);
    render(<AnswerCard result={{ ...base, table: { columns: ["id", "name"], rows, total_rows: 1000, truncated: true } }} />);
    await userEvent.click(screen.getByRole("button", { name: /Table/ }));
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(201); // header + 200
    expect(screen.getByText(/Showing 200 of 1,000/)).toBeInTheDocument();
    expect(screen.getByText(/partial/i)).toBeInTheDocument();
  });

  it("labels link out safely", async () => {
    const result = { ...base, documents: [{ label: "openFDA label: Lisinopril — Side effects",
      source_url: "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=x", excerpt: "Cough may occur." }] };
    render(<AnswerCard result={result} />);
    await userEvent.click(screen.getByRole("button", { name: /Labels/ }));
    const link = screen.getByRole("link", { name: /Open label/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
    expect(screen.getByText("Cough may occur.")).toBeInTheDocument();
  });

  it("unverified numbers note", () => {
    render(<AnswerCard result={{ ...base, unverified_numbers: ["7.1%"] }} />);
    expect(screen.getByText(/could not be matched/i)).toBeInTheDocument();
    expect(screen.getByText("7.1%")).toBeInTheDocument();
  });

  it("timeline shows each step", async () => {
    render(<AnswerCard result={base} />);
    await userEvent.click(screen.getByRole("button", { name: /Timeline/ }));
    expect(screen.getByText("generate_sql")).toBeInTheDocument();
    expect(screen.getByText("0.90 s")).toBeInTheDocument();
  });

  it("refusal has no disclosures and an outlined orb", () => {
    render(<AnswerCard result={{ ...base, kind: "refusal", answer: "In patient mode I can only...", sql: [], table: null, timings: {} }} />);
    expect(screen.queryByRole("button", { name: /SQL/ })).toBeNull();
    expect(screen.getByTestId("answer-orb")).toHaveAttribute("data-kind", "refusal");
  });
});

describe("AnswerCard polish (found in the real browser)", () => {
  it("hides the AI's own Sources paragraph and citation markers", () => {
    const text = "Lisinopril may cause cough【2】.\n\nSources: clinical_db.medications; openFDA label: Lisinopril — Side effects.";
    render(<AnswerCard result={{ ...base, answer: text }} />);
    expect(screen.queryByText(/^Sources:/)).toBeNull();
    expect(document.querySelector(".answer__text")).toHaveTextContent("Lisinopril may cause cough.");
  });

  it("meta lists database tables and a label count, not every label", () => {
    const sources = ["clinical_db.medications", "openFDA label: Lisinopril — Side effects", "openFDA label: Insulin Human — Side effects"];
    render(<AnswerCard result={{ ...base, sources }} />);
    expect(screen.getByText("clinical_db.medications")).toBeInTheDocument();
    expect(screen.getByText("2 FDA labels")).toBeInTheDocument();
    expect(screen.queryByText("openFDA label: Lisinopril — Side effects")).toBeNull();
  });

  it("says 1 row, not 1 rows", () => {
    render(<AnswerCard result={base} />);
    expect(screen.getByRole("button", { name: /Table 1 row$/ })).toBeInTheDocument();
  });

  it("numbers queries across databases instead of calling them tries", async () => {
    render(<AnswerCard result={base} />);
    await userEvent.click(screen.getByRole("button", { name: /SQL/ }));
    expect(screen.getByText(/query 2/)).toBeInTheDocument();
  });
});

it("replaces the backend's warning line with the UI note (shown once)", () => {
  const text = "Diarrhea (10%).\n\nSource: openFDA label: Metformin Er 500 Mg — Side effects\n\n" +
    "⚠ Some numbers in this answer could not be matched to the query results: 500";
  render(<AnswerCard result={{ ...base, answer: text, unverified_numbers: ["500"] }} />);
  expect(screen.queryByText(/Some numbers in this answer/)).toBeNull();
  expect(screen.queryByText(/^Source:/)).toBeNull();
  expect(screen.getByText(/could not be matched to the data/)).toBeInTheDocument();
});

describe("cleanAnswer keeps real content (final review)", () => {
  it.each([
    ["You have 3 claims.\n\nSources of the balance: 2 unpaid claims ($120) and 1 copay ($30).", "Sources of the balance"],
    ["Effects:\n- nausea\nSourced from the FDA label, common effects include diarrhea.", "Sourced from the FDA label"],
    ["Iron intake is fine.\nSources of iron include spinach.", "Sources of iron include spinach."],
  ])("does not drop %#", (text, kept) => {
    expect(cleanAnswer(text, true)).toContain(kept);
  });

  it("still drops a real trailing Source(s): line", () => {
    expect(cleanAnswer("8 patients.\n\n**Sources:** clinical_db.conditions", true)).toBe("8 patients.");
    expect(cleanAnswer("8 patients.\nSource: clinical_db.conditions", true)).toBe("8 patients.");
  });
});

describe("backup model notice", () => {
  it("shows a small alert when a backup AI model wrote the answer", () => {
    render(<AnswerCard result={{ ...base, model_notice: "gpt-oss-120b has used up its free daily limit, so this answer came from the backup model gpt-oss-20b." }} />);
    const alert = screen.getByRole("status", { name: "Model notice" });
    expect(alert).toHaveTextContent("backup model gpt-oss-20b");
  });

  it("shows nothing when the main model answered", () => {
    render(<AnswerCard result={base} />);
    expect(screen.queryByRole("status", { name: "Model notice" })).toBeNull();
  });
});

describe("names without Synthea's random digits", () => {
  const named: ChatResult = {
    ...base,
    answer: "Abe604 Bode78 has 2 active conditions.",
    standalone_question: "What conditions does Abe604 Bode78 have?",
    table: { columns: ["first", "last", "n"], rows: [["Abe604", "Bode78", 2]], total_rows: 1, truncated: false },
  };

  it("the answer, the 'Understood as' line and the table show clean names", async () => {
    render(<AnswerCard result={named} />);
    expect(document.querySelector(".answer__text")).toHaveTextContent("Abe Bode has 2 active conditions.");
    expect(screen.getByText("What conditions does Abe Bode have?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Table/ }));
    const table = screen.getByRole("table");
    expect(within(table).getByText("Abe")).toBeInTheDocument();
    expect(within(table).queryByText("Abe604")).toBeNull();
  });

  it("the SQL panel still shows the query exactly as it ran", async () => {
    const sql = [{ db: "clinical" as const, query: "SELECT * FROM conditions WHERE first = 'Abe604'", error: null }];
    render(<AnswerCard result={{ ...named, sql }} />);
    await userEvent.click(screen.getByRole("button", { name: /SQL/ }));
    expect(screen.getByText(/first = 'Abe604'/)).toBeInTheDocument();
  });

  it("an option chip shows the clean name but sends the original", async () => {
    const picked: string[] = [];
    render(<AnswerCard result={{ ...base, kind: "clarification", answer: "Which patient?", options: ["Abe604 Bode78"],
      sql: [], table: null, timings: {} }} onOption={(o) => picked.push(o)} />);
    await userEvent.click(screen.getByRole("button", { name: "Abe Bode" }));
    expect(picked).toEqual(["Abe604 Bode78"]);
  });
});

describe("conversation (Plan 4)", () => {
  it("a clarifying question offers one-click options", async () => {
    const picked: string[] = [];
    render(<AnswerCard result={{ ...base, kind: "clarification", answer: "Revenue of what — a hospital or an insurer?",
      options: ["Hospitals", "Insurers"], sql: [], table: null, timings: {} }} onOption={(o) => picked.push(o)} />);
    expect(document.querySelector(".answer__text")).toHaveTextContent("Revenue of what");
    await userEvent.click(screen.getByRole("button", { name: "Insurers" }));
    expect(picked).toEqual(["Insurers"]);
  });

  it("'did you mean?' — Yes sends the corrected question", async () => {
    const sent: string[] = [];
    const result = { ...base, kind: "clarification" as const, answer: "Did you mean metformin?", options: ["Yes", "No"],
      option_questions: { Yes: "What are the side effects of metformin?", No: "" }, sql: [], table: null, timings: {} };
    render(<AnswerCard result={result} onOption={(o) => sent.push(o)} />);
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(sent).toEqual(["What are the side effects of metformin?"]);
  });

  it("'did you mean?' — No sends nothing and invites a new question", async () => {
    const sent: string[] = [];
    const result = { ...base, kind: "clarification" as const, answer: "Did you mean metformin?", options: ["Yes", "No"],
      option_questions: { Yes: "What are the side effects of metformin?", No: "" }, sql: [], table: null, timings: {} };
    render(<AnswerCard result={result} onOption={(o) => sent.push(o)} />);
    await userEvent.click(screen.getByRole("button", { name: "No" }));
    expect(sent).toEqual([]);
    expect(screen.getByText(/ask your question again/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yes" })).toBeDisabled();
  });

  it("shows how a follow-up was understood", () => {
    render(<AnswerCard result={{ ...base, standalone_question: "How many female patients have diabetes?" }} />);
    expect(screen.getByText("Understood as")).toBeInTheDocument();
    expect(screen.getByText("How many female patients have diabetes?")).toBeInTheDocument();
  });
});

it("reduced motion shows the answer at once (no word-by-word reveal)", () => {
  // Final review, Plan 4: the global reduced-motion rule shortened the animation but not its delay.
  const original = window.matchMedia;
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({
    matches: q.includes("reduce"), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
  const { container } = render(<AnswerCard result={base} />);
  expect(container.querySelectorAll(".answer__text span.w")).toHaveLength(0);
  expect(container.querySelector(".answer__text")).toHaveTextContent("There are 8 patients with diabetes.");
  window.matchMedia = original;
});

describe("Plan 5: pages and cache", () => {
  it("'Load more' fetches the next page of a big table", async () => {
    const client = await import("../../api/client");
    const spy = vi.spyOn(client, "getResultPage").mockResolvedValue({ columns: ["n"], rows: Array.from({ length: 100 }, (_, i) => [100 + i]),
      page: 2, pages: 3, total_rows: 250 });
    const table = { columns: ["n"], rows: Array.from({ length: 100 }, (_, i) => [i]), total_rows: 250, truncated: false, result_id: "abc" };
    render(<AnswerCard result={{ ...base, table }} owner={{ role: "clinician", patientId: null }} />);
    await userEvent.click(screen.getByRole("button", { name: /Table/ }));
    expect(screen.getByText(/100 of 250/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Load more/ }));
    expect(spy).toHaveBeenCalledWith("abc", 2, "clinician", null);
    expect(await screen.findByText(/200 of 250/)).toBeInTheDocument();
    spy.mockRestore();
  });

  it("a cached answer says so", () => {
    render(<AnswerCard result={{ ...base, cached: true }} />);
    expect(screen.getByText("from cache")).toBeInTheDocument();
  });
});

describe("charts, CSV export and one-click suggestions", () => {
  const insurers = { columns: ["name", "customers", "revenue"], rows: [["Medicare", 40, 900.5], ["Aetna", 25, 1200], ["Humana", 9, 300]],
    total_rows: 3, truncated: false };

  it("names + numbers get a Chart panel with one bar per row, values at the tips", async () => {
    render(<AnswerCard result={{ ...base, table: insurers }} />);
    await userEvent.click(screen.getByRole("button", { name: /Chart/ }));
    const chart = screen.getByRole("figure", { name: /customers by name/i });
    const bars = within(chart).getAllByRole("listitem");
    expect(bars).toHaveLength(3);
    expect(bars[0]).toHaveTextContent("Medicare");
    expect(bars[0]).toHaveTextContent("40");
  });

  it("several number columns: choose which one to chart", async () => {
    render(<AnswerCard result={{ ...base, table: insurers }} />);
    await userEvent.click(screen.getByRole("button", { name: /Chart/ }));
    await userEvent.click(screen.getByRole("button", { name: "revenue" }));
    expect(screen.getByRole("button", { name: "revenue" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("figure", { name: /revenue by name/i })).getAllByRole("listitem")[1]).toHaveTextContent("1,200");
  });

  it("dates + numbers get a line chart", async () => {
    const table = { columns: ["year", "visits"], rows: [[2019, 10], [2020, 20], [2021, 15]], total_rows: 3, truncated: false };
    render(<AnswerCard result={{ ...base, table }} />);
    await userEvent.click(screen.getByRole("button", { name: /Chart/ }));
    expect(screen.getByRole("img", { name: /visits by year, 2019 to 2021/i })).toBeInTheDocument();
  });

  it("a single number gets no chart", () => {
    render(<AnswerCard result={base} />);
    expect(screen.queryByRole("button", { name: /Chart/ })).toBeNull();
  });

  it("Export CSV downloads every row — fetching the pages not loaded yet", async () => {
    const client = await import("../../api/client");
    const csv = await import("../../lib/csv");
    const pages = vi.spyOn(client, "getResultPage").mockImplementation(async (_id, page) => ({
      columns: ["n"], rows: Array.from({ length: page === 3 ? 50 : 100 }, (_, i) => [page * 1000 + i]), page, pages: 3, total_rows: 250 }));
    const download = vi.spyOn(csv, "downloadCsv").mockImplementation(() => {});
    const table = { columns: ["n"], rows: Array.from({ length: 100 }, (_, i) => [i]), total_rows: 250, truncated: false, result_id: "abc" };
    render(<AnswerCard result={{ ...base, table }} owner={{ role: "patient", patientId: "p1" }} />);
    await userEvent.click(screen.getByRole("button", { name: /Table/ }));
    await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await vi.waitFor(() => expect(download).toHaveBeenCalled());
    expect(pages.mock.calls.map((c) => c[1])).toEqual([2, 3]);
    expect(pages).toHaveBeenCalledWith("abc", 2, "patient", "p1");
    const text = download.mock.calls[0][1];
    expect(text.split("\r\n").filter(Boolean)).toHaveLength(251); // header + 250 rows
    expect(download.mock.calls[0][0]).toMatch(/^aether-result-.*\.csv$/);
    pages.mockRestore();
    download.mockRestore();
  });

  it("out-of-scope replies offer example questions to click", async () => {
    const onOption = vi.fn();
    render(<AnswerCard result={{ ...base, kind: "out_of_scope", answer: "I can only answer... For example:", table: null, sql: [],
      options: ["How many patients are there?"], option_questions: { "How many patients are there?": "How many patients are there?" } }}
      onOption={onOption} />);
    await userEvent.click(screen.getByRole("button", { name: "How many patients are there?" }));
    expect(onOption).toHaveBeenCalledWith("How many patients are there?");
  });
});
