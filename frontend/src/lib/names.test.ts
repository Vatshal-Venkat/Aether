import { describe, expect, it } from "vitest";
import { cleanNames } from "./names";

describe("cleanNames", () => {
  it("drops Synthea's random digits from a name", () => {
    expect(cleanNames("Lyndon118 Bechtelar572")).toBe("Lyndon Bechtelar");
  });

  it("cleans names inside a sentence and keeps real numbers", () => {
    expect(cleanNames("Abe604 Bode78 had 3 visits in 2020; Dr. Rufus943 Bosco882 saw him.")).toBe(
      "Abe Bode had 3 visits in 2020; Dr. Rufus Bosco saw him.",
    );
  });

  it("handles accented names", () => {
    // Live: "Raúl937 Quintana711" kept its digits ("ú" is not an A-Z letter).
    expect(cleanNames("Mr. Raúl937 Claudio123 Quintana711")).toBe("Mr. Raúl Claudio Quintana");
    expect(cleanNames("Zoë42 Müller7 and Ángel3 Peña88")).toBe("Zoë Müller and Ángel Peña");
  });

  it("handles apostrophes and hyphens in names", () => {
    expect(cleanNames("Mary12 O'Keefe54 and Ann3 Ward-Smith55")).toBe("Mary O'Keefe and Ann Ward-Smith");
  });

  it("leaves medical codes, doses and ids alone", () => {
    const untouched = [
      "Hemoglobin A1c", "COVID-19", "Type 2 diabetes", "Vitamin B12", "E11.9", "metformin 500 mg",
      "SNOMED 44054006", "id 3f2a9c1e-77b0-4c1d", "NO_INSURANCE", "H2O", "Medicaid",
    ];
    for (const text of untouched) expect(cleanNames(text)).toBe(text);
  });
});
