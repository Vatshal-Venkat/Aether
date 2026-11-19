import { describe, expect, it } from "vitest";
import { similarity } from "./trigram";

describe("trigram similarity", () => {
  it("is 1 for the same spelling, any case", () => {
    expect(similarity("Angelyn Harris", "angelyn harris")).toBe(1);
  });

  it("stays high for typos and low for different names", () => {
    expect(similarity("angelin haris", "Angelyn Harris")).toBeGreaterThan(0.3);
    expect(similarity("angelin haris", "Miranda Jacobs")).toBeLessThan(0.1);
  });

  it("is 0 for empty text", () => {
    expect(similarity("", "Angelyn Harris")).toBe(0);
  });
});
