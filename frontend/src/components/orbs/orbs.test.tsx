import { act, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnswerOrb } from "./AnswerOrb";
import { StatusOrb } from "./StatusOrb";
import { ThinkingOrbs } from "./ThinkingOrbs";

const HEALTH = { status: "ok" as const, clinical: "ok", billing: "ok", drug_labels: "ok: 4140 chunks", llm_provider: "groq" };

afterEach(() => vi.useRealTimers());

describe("orbs", () => {
  it("thinking orbs announce status with a caption", () => {
    render(<ThinkingOrbs active caption="Writing SQL" />);
    const status = screen.getByRole("status", { name: "Aether is thinking" });
    expect(status).toBeInTheDocument();
    expect(screen.getByText("Writing SQL")).toBeInTheDocument();
  });

  it("idle orbs are decorative (no status role)", () => {
    render(<ThinkingOrbs active={false} />);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("status orb: running vs down", () => {
    const { rerender } = render(<StatusOrb health={HEALTH} error={false} />);
    let orb = screen.getByTestId("status-orb");
    expect(orb).toHaveAttribute("data-state", "up");
    expect(orb.getAttribute("title")).toMatch(/Backend running/);
    rerender(<StatusOrb health={null} error />);
    orb = screen.getByTestId("status-orb");
    expect(orb).toHaveAttribute("data-state", "down");
    expect(orb.getAttribute("title")).toMatch(/not reachable/);
  });

  it("status orb: degraded when a database is down", () => {
    render(<StatusOrb health={{ ...HEALTH, status: "degraded", billing: "error: refused" }} error={false} />);
    const orb = screen.getByTestId("status-orb");
    expect(orb).toHaveAttribute("data-state", "degraded");
    expect(orb.getAttribute("title")).toMatch(/billing: error: refused/);
  });

  it("answer orb styles follow the answer kind", () => {
    const { rerender } = render(<AnswerOrb kind="answer" />);
    expect(screen.getByTestId("answer-orb")).toHaveAttribute("data-kind", "answer");
    rerender(<AnswerOrb kind="error" />);
    expect(screen.getByTestId("answer-orb")).toHaveAttribute("data-kind", "error");
  });

  it("reduced motion renders static orbs", () => {
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((q: string) => ({
      matches: q.includes("reduce"), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    render(<ThinkingOrbs active />);
    expect(screen.getByTestId("thinking-orbs")).toHaveAttribute("data-motion", "reduced");
    window.matchMedia = original;
  });
});

describe("liquid orbs (owner: the merging look was good — make the motion more fluid)", () => {
  it("melts the orbs together with the goo filter", () => {
    const { container } = render(<ThinkingOrbs active />);
    expect(container.querySelector("feColorMatrix")).not.toBeNull();
    expect(container.querySelector("g.orbs__body")!.getAttribute("filter")).toMatch(/^url\(#goo-/);
  });

  it("has a core and five drifting droplets", () => {
    const { container } = render(<ThinkingOrbs active />);
    expect(container.querySelectorAll("circle.droplet")).toHaveLength(5);
    expect(container.querySelectorAll("circle.core")).toHaveLength(1);
  });

  it("reduced motion still draws every orb, standing still", () => {
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((q: string) => ({
      matches: q.includes("reduce"), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    const { container } = render(<ThinkingOrbs active />);
    expect(container.querySelectorAll("circle.droplet")).toHaveLength(5);
    window.matchMedia = original;
  });
});

describe("rhythm follows the backend", () => {
  it("shows the mood it was given", () => {
    render(<ThinkingOrbs active mood="query" />);
    expect(screen.getByTestId("thinking-orbs")).toHaveAttribute("data-mood", "query");
  });

  it("idle orbs use the idle mood", () => {
    render(<ThinkingOrbs active={false} />);
    expect(screen.getByTestId("thinking-orbs")).toHaveAttribute("data-mood", "idle");
  });
});
