import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { labelLinks, mentionedFirst } from "../components/answer/AnswerCard";
import { renderMarkdown } from "./markdown";

const HCTZ = { name: "Hydrochlorothiazide", url: "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=h" };
const METO = { name: "Metoprolol Succinate", url: "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=m" };

const show = (text: string, reveal = false) =>
  render(<div data-testid="md">{renderMarkdown(text, { labels: [HCTZ, METO], reveal })}</div>);

describe("label links in answers", () => {
  it("adds one link after a bold drug name, outside the bold", () => {
    show("The top drug is **hydrochlorothiazide** (40 reactions). Hydrochlorothiazide again.");
    const links = screen.getAllByRole("link", { name: /FDA label for Hydrochlorothiazide/ });
    expect(links).toHaveLength(1); // only the first mention
    expect(links[0].getAttribute("href")).toBe(HCTZ.url);
    expect(links[0].closest("strong")).toBeNull();
    expect(links[0].previousSibling?.previousSibling?.textContent).toBe("hydrochlorothiazide");
  });

  it("matches a drug by its distinctive first word, in plain text and with word-by-word reveal", () => {
    show("Patients on metoprolol may feel tired.", true);
    expect(screen.getByRole("link", { name: /Metoprolol Succinate/ })).toBeTruthy();
    expect(screen.getByTestId("md").textContent).toContain("Patients on metoprolol label ↗ may feel tired.");
  });

  it("no links without a matching drug or inside code", () => {
    show("No medicine here. `hydrochlorothiazide`");
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("builds one link per drug and lists mentioned drugs first", () => {
    const doc = (drug: string, section: string) =>
      ({ label: `openFDA label: ${drug} — ${section}`, source_url: `u-${drug}`, excerpt: "" });
    const docs = [doc("Epoetin Alfa", "Side effects"), doc("Metoprolol Succinate", "Side effects"),
                  doc("Hydrochlorothiazide", "Side effects"), doc("Hydrochlorothiazide", "Warnings")];
    expect(labelLinks(docs).map((l) => l.name)).toEqual(["Epoetin Alfa", "Metoprolol Succinate", "Hydrochlorothiazide"]);
    expect(mentionedFirst(docs, "The answer is **hydrochlorothiazide**; metoprolol is second.").map((d) => d.label))
      .toEqual(["openFDA label: Hydrochlorothiazide — Side effects", "openFDA label: Hydrochlorothiazide — Warnings",
                "openFDA label: Metoprolol Succinate — Side effects", "openFDA label: Epoetin Alfa — Side effects"]);
  });
});
