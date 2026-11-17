import { describe, expect, it } from "vitest";
import { moodFor, phaseLabel } from "./moods";

describe("what the backend is doing -> orb rhythm and caption", () => {
  it.each([
    [null, "calm", "Starting"],
    [{ step: "route" }, "calm", "Understanding the question"],
    [{ step: "generate_sql", db: "clinical", retry: false }, "write", "Writing SQL"],
    [{ step: "generate_sql", db: "clinical", retry: true }, "retry", "Fixing the SQL"],
    [{ step: "validate", db: "billing" }, "check", "Checking safety"],
    [{ step: "row_filter", db: "billing" }, "check", "Applying the privacy filter"],
    [{ step: "execute", db: "billing" }, "query", "Querying billing_db"],
    [{ step: "retrieve" }, "read", "Reading FDA labels"],
    [{ step: "synthesize" }, "flow", "Writing the answer"],
    [{ step: "verify_numbers" }, "verify", "Checking numbers"],
  ] as const)("%j", (progress, mood, label) => {
    expect(moodFor(progress)).toBe(mood);
    expect(phaseLabel(progress)).toBe(label);
  });
});
