import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
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
    expect(screen.getByText("8").tagName).toBe("STRONG");
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
    expect(screen.getByText("Lisinopril may cause cough.")).toBeInTheDocument();
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
