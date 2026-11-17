import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

const show = (text: string) => render(<div data-testid="md">{renderMarkdown(text)}</div>);

describe("mini markdown", () => {
  it("paragraphs and bold", () => {
    show("There are **8** patients.\n\nSource: clinical_db.conditions");
    expect(screen.getByText("8").tagName).toBe("STRONG");
    expect(screen.getByTestId("md").querySelectorAll("p")).toHaveLength(2);
  });

  it("bullet and numbered lists", () => {
    show("- lisinopril\n- metformin\n\n1. first\n2. second");
    expect(screen.getByTestId("md").querySelectorAll("ul li")).toHaveLength(2);
    expect(screen.getByTestId("md").querySelectorAll("ol li")).toHaveLength(2);
  });

  it("pipe tables", () => {
    show("| Drug | Effect |\n|---|---|\n| **Lisinopril** | cough |\n| Metformin | nausea |");
    const table = screen.getByTestId("md").querySelector("table")!;
    expect(table.querySelectorAll("th")).toHaveLength(2);
    expect(table.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(screen.getByText("Lisinopril").tagName).toBe("STRONG");
  });

  it("inline code", () => {
    show("Use `encounters.provider` here");
    expect(screen.getByText("encounters.provider").tagName).toBe("CODE");
  });

  it("renders html as text", () => {
    show('<img src=x onerror="alert(1)"> and <script>alert(2)</script>');
    expect(screen.getByTestId("md").querySelector("img, script")).toBeNull();
    expect(screen.getByTestId("md").textContent).toContain("<img src=x");
  });
});
