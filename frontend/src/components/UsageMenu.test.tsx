import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { ModelUsage } from "../api/types";
import { UsageMenu } from "./UsageMenu";

const SINCE = new Date(2026, 10, 19, 21, 40).getTime() / 1000;
const ROWS: ModelUsage[] = [
  { model: "openai/gpt-oss-120b", name: "gpt-oss-120b", role: "main", status: "available", back_in_s: null,
    daily_limit: 200000, used: 50000, remaining: 150000, exact: false, complete: true, counting_since: SINCE },
  { model: "openai/gpt-oss-20b", name: "gpt-oss-20b", role: "backup", status: "resting", back_in_s: 290,
    daily_limit: 200000, used: 199868, remaining: 132, exact: true, complete: true, counting_since: SINCE },
  { model: "gemini-2.5-flash", name: "gemini-2.5-flash", role: "last resort", status: "available", back_in_s: null,
    daily_limit: null, used: 1234, remaining: null, exact: false, complete: true, counting_since: SINCE },
];

describe("UsageMenu", () => {
  it("one button opens a small menu; its button shows every model's remaining limit", async () => {
    const getUsage = vi.spyOn(client, "getUsage").mockResolvedValue(ROWS);
    render(<UsageMenu />);
    await userEvent.click(screen.getByRole("button", { name: "AI model limits" }));
    expect(getUsage).not.toHaveBeenCalled();  // the menu first, nothing fetched yet
    await userEvent.click(screen.getByRole("button", { name: "Show model limits" }));

    const list = await screen.findByRole("list", { name: "AI models" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("gpt-oss-120b");
    expect(items[0]).toHaveTextContent("main");
    expect(items[0]).toHaveTextContent("150,000 of 200,000 tokens left");
    expect(items[0]).toHaveTextContent("estimated");
    expect(items[1]).toHaveTextContent("Limit reached — back in about 5 min");
    expect(items[1]).toHaveTextContent("exact");
    expect(items[2]).toHaveTextContent("1,234 tokens used today");
  });

  it("a count younger than 24 hours doesn't pretend to know what's left", async () => {
    vi.spyOn(client, "getUsage").mockResolvedValue([{ ...ROWS[0], used: 3200, remaining: 196800, complete: false }]);
    render(<UsageMenu />);
    await userEvent.click(screen.getByRole("button", { name: "AI model limits" }));
    await userEvent.click(screen.getByRole("button", { name: "Show model limits" }));
    const item = (await screen.findAllByRole("listitem"))[0];
    expect(item).toHaveTextContent("3,200 tokens used since 9:40 PM");
    expect(item).not.toHaveTextContent("196,800");
  });

  it("says so when the limits can't be loaded", async () => {
    vi.spyOn(client, "getUsage").mockRejectedValue(new client.ApiError(0, "Can't reach the Aether backend."));
    render(<UsageMenu />);
    await userEvent.click(screen.getByRole("button", { name: "AI model limits" }));
    await userEvent.click(screen.getByRole("button", { name: "Show model limits" }));
    expect(await screen.findByText("Can't reach the Aether backend.")).toBeInTheDocument();
  });

  it("Escape closes it", async () => {
    render(<UsageMenu />);
    await userEvent.click(screen.getByRole("button", { name: "AI model limits" }));
    expect(screen.getByRole("button", { name: "Show model limits" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Show model limits" })).toBeNull());  // after the fade
  });
});
