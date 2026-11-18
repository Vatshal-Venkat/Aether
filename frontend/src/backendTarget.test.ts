import { describe, expect, it } from "vitest";
import { backendTarget } from "../backendTarget";

describe("where the website forwards /api and /health", () => {
  it("defaults to port 8000", () => expect(backendTarget({})).toBe("http://127.0.0.1:8000"));
  it("uses AETHER_API_PORT", () => expect(backendTarget({ AETHER_API_PORT: "8001" })).toBe("http://127.0.0.1:8001"));
  it("rejects a non-port", () => expect(() => backendTarget({ AETHER_API_PORT: "eighty" })).toThrow(/AETHER_API_PORT/));
});
