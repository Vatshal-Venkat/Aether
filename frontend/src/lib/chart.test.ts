import { describe, expect, it } from "vitest";
import type { QueryResult } from "../api/types";
import { chartSpec, niceTicks } from "./chart";

const t = (columns: string[], rows: unknown[][]): QueryResult => ({ columns, rows, total_rows: rows.length, truncated: false });

describe("chartSpec", () => {
  it("names + a number -> bars, in the result's order", () => {
    const spec = chartSpec(t(["name", "customers"], [["Medicare", 40], ["Aetna", 25], ["Humana", 9]]));
    expect(spec?.kind).toBe("bar");
    expect(spec?.label).toBe("name");
    expect(spec?.measures).toEqual(["customers"]);
    expect(spec?.points.map((p) => [p.label, p.values[0]])).toEqual([["Medicare", 40], ["Aetna", 25], ["Humana", 9]]);
  });

  it("dates or years + a number -> a line, sorted by time", () => {
    const spec = chartSpec(t(["year", "visits"], [[2021, 30], [2019, 10], [2020, 20]]));
    expect(spec?.kind).toBe("line");
    expect(spec?.points.map((p) => p.label)).toEqual(["2019", "2020", "2021"]);
    const months = chartSpec(t(["month", "n"], [["2020-03", 3], ["2020-01", 1], ["2020-02", 2]]));
    expect(months?.kind).toBe("line");
    expect(months?.points.map((p) => p.values[0])).toEqual([1, 2, 3]);
  });

  it("several numbers -> one measure at a time to choose from; ids, codes and rank columns are not measures", () => {
    const spec = chartSpec(t(["patient_id", "first", "ranking", "code", "rows", "medicines"],
      [["a1", "Ann1", 1, 111, 50, 9], ["b2", "Bob2", 2, 222, 40, 7]]));
    expect(spec?.label).toBe("first");
    expect(spec?.measures).toEqual(["rows", "medicines"]);
    expect(spec?.points[0]).toMatchObject({ label: "Ann", values: [50, 9] });
  });

  it("number-like text (lab values stored as text) counts as a number", () => {
    expect(chartSpec(t(["test", "avg"], [["HbA1c", "5.9"], ["LDL", "101.5"]]))?.points[1].values).toEqual([101.5]);
  });

  it("no chart for a single number, no numbers, repeated labels, or ids only", () => {
    expect(chartSpec(t(["n"], [[8]]))).toBeNull();
    expect(chartSpec(t(["name", "n"], [["Aetna", 3]]))).toBeNull();
    expect(chartSpec(t(["first", "last"], [["Ann", "Lee"], ["Bob", "Ray"]]))).toBeNull();
    expect(chartSpec(t(["patient", "n"], [["Ann", 1], ["Ann", 2]]))).toBeNull();
    expect(chartSpec(t(["id", "n"], [["5f0e2c1a-9b7d-4c1e-8f3a-2b6d9e0a1c4f", 1], ["7a1b3c5d-2e4f-4a6b-8c0d-1e2f3a4b5c6d", 2]]))).toBeNull();
  });

  it("a line needs at least 3 points in time", () => {
    expect(chartSpec(t(["year", "n"], [[2020, 1], [2021, 2]]))?.kind).toBe("bar");
  });

  it("long results: bars for the first 20 rows, saying so", () => {
    const rows = Array.from({ length: 30 }, (_, i) => [`Drug ${i}`, 30 - i]);
    const spec = chartSpec({ ...t(["drug", "n"], rows), total_rows: 30 });
    expect(spec?.points).toHaveLength(20);
    expect(spec?.total).toBe(30);
  });
});

describe("niceTicks", () => {
  it("round numbers covering the data", () => {
    expect(niceTicks(0, 87)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceTicks(-30, 40)).toEqual([-40, -20, 0, 20, 40]);
  });
});
