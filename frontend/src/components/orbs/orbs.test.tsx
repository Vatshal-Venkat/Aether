import { act, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PHASES, usePhases } from "../../hooks/usePhases";
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

  it("phases advance and hold the last one", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => usePhases(true));
    expect(result.current).toBe(PHASES[0]);
    act(() => vi.advanceTimersByTime(1400));
    expect(result.current).toBe(PHASES[1]);
    act(() => vi.advanceTimersByTime(60_000));
    expect(result.current).toBe(PHASES[PHASES.length - 1]);
  });

  it("phases restart when thinking starts again", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ on }) => usePhases(on), { initialProps: { on: true } });
    act(() => vi.advanceTimersByTime(5000));
    rerender({ on: false });
    rerender({ on: true });
    expect(result.current).toBe(PHASES[0]);
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

describe("glowing spheres (owner's choice: separate shaded spheres, never merging)", () => {
  it("draws a core and four orbiting spheres, each shaded with a radial gradient", () => {
    const { container } = render(<ThinkingOrbs active />);
    const spheres = container.querySelectorAll("circle.sphere");
    expect(spheres).toHaveLength(5);
    const gradientId = container.querySelector("radialGradient")!.id;
    spheres.forEach((s) => expect(s.getAttribute("fill")).toBe(`url(#${gradientId})`));
  });

  it("does not use the merging 'goo' filter any more", () => {
    const { container } = render(<ThinkingOrbs active />);
    expect(container.querySelector("feColorMatrix")).toBeNull();
  });

  it("reduced motion still shows all five spheres, standing still", () => {
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((q: string) => ({
      matches: q.includes("reduce"), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    const { container } = render(<ThinkingOrbs active />);
    expect(container.querySelectorAll("circle.sphere")).toHaveLength(5);
    window.matchMedia = original;
  });
});
