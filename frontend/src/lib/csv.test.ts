import { describe, expect, it } from "vitest";
import { csvFilename, toCsv } from "./csv";

describe("toCsv", () => {
  it("writes a header row and one line per row, Windows line endings", () => {
    expect(toCsv(["name", "n"], [["Aetna", 12], ["Medicare", 7]])).toBe("name,n\r\nAetna,12\r\nMedicare,7\r\n");
  });

  it("quotes commas, quotes and line breaks", () => {
    expect(toCsv(["a"], [['say "hi", ok'], ["two\nlines"]])).toBe('a\r\n"say ""hi"", ok"\r\n"two\nlines"\r\n');
  });

  it("empty cells for missing values; full precision for numbers", () => {
    expect(toCsv(["a", "b"], [[null, 2.123456]])).toBe("a,b\r\n,2.123456\r\n");
  });

  it("drops Synthea's random digits from names, like the table does", () => {
    expect(toCsv(["patient"], [["Abe604 Bode78"]])).toBe("patient\r\nAbe Bode\r\n");
  });

  it("text that a spreadsheet would run as a formula is made harmless", () => {
    expect(toCsv(["x"], [["=HYPERLINK(\"http://evil\")"], ["+1"], ["@SUM(A1)"]])).toBe(
      "x\r\n\"'=HYPERLINK(\"\"http://evil\"\")\"\r\n'+1\r\n'@SUM(A1)\r\n",
    );
    expect(toCsv(["x"], [[-5]])).toBe("x\r\n-5\r\n"); // a real negative number stays a number
  });
});

describe("csvFilename", () => {
  it("names the file after the date", () => {
    expect(csvFilename(new Date(2026, 10, 20, 9, 5))).toBe("aether-result-2026-11-20-0905.csv");
  });
});
