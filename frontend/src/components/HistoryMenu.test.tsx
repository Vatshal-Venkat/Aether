import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { Conversation } from "../api/types";
import { HistoryMenu } from "./HistoryMenu";

const CONVS: Conversation[] = [
  { session_id: "s2", title: "Show me Abe604 Bode78's medications", questions: 3,
    started_at: "2026-11-22T10:00:00Z", updated_at: "2026-11-22T10:05:00Z" },
  { session_id: "s1", title: "How many patients have diabetes?", questions: 1,
    started_at: "2026-11-21T09:00:00Z", updated_at: "2026-11-21T09:00:00Z" },
];

afterEach(() => vi.restoreAllMocks());

const open = () => userEvent.click(screen.getByRole("button", { name: "Past conversations" }));

describe("HistoryMenu", () => {
  it("lists this person's past conversations, newest first, with clean names", async () => {
    const get = vi.spyOn(client, "getConversations").mockResolvedValue(CONVS);
    render(<HistoryMenu role="patient" patientId="p1" current="s9" onOpen={vi.fn()} onNew={vi.fn()} />);
    await open();
    expect(get).toHaveBeenCalledWith("patient", "p1");
    const items = within(await screen.findByRole("list", { name: "Past conversations" })).getAllByRole("button");
    expect(items[0]).toHaveTextContent("Show me Abe Bode's medications");
    expect(items[0]).toHaveTextContent("3 questions");
    expect(items[1]).toHaveTextContent("1 question");
  });

  it("opening one hands its id over and closes the menu", async () => {
    vi.spyOn(client, "getConversations").mockResolvedValue(CONVS);
    const onOpen = vi.fn();
    render(<HistoryMenu role="clinician" patientId={null} current="s9" onOpen={onOpen} onNew={vi.fn()} />);
    await open();
    await userEvent.click(await screen.findByRole("button", { name: /How many patients have diabetes/ }));
    expect(onOpen).toHaveBeenCalledWith("s1");
    await waitFor(() => expect(screen.queryByRole("list", { name: "Past conversations" })).toBeNull());
  });

  it("marks the conversation already on screen", async () => {
    vi.spyOn(client, "getConversations").mockResolvedValue(CONVS);
    render(<HistoryMenu role="clinician" patientId={null} current="s1" onOpen={vi.fn()} onNew={vi.fn()} />);
    await open();
    expect(await screen.findByRole("button", { name: /How many patients have diabetes/ }))
      .toHaveAttribute("aria-current", "true");
  });

  it("starts a new conversation", async () => {
    vi.spyOn(client, "getConversations").mockResolvedValue([]);
    const onNew = vi.fn();
    render(<HistoryMenu role="clinician" patientId={null} current="s9" onOpen={vi.fn()} onNew={onNew} />);
    await open();
    expect(await screen.findByText("No past conversations yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New conversation" }));
    expect(onNew).toHaveBeenCalled();
  });

  it("in patient mode, asks for a patient first and fetches nothing", async () => {
    const get = vi.spyOn(client, "getConversations").mockResolvedValue(CONVS);
    render(<HistoryMenu role="patient" patientId={null} current="s9" onOpen={vi.fn()} onNew={vi.fn()} />);
    await open();
    expect(screen.getByText("Pick a patient to see their conversations.")).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });

  it("says so when the list can't be loaded", async () => {
    vi.spyOn(client, "getConversations").mockRejectedValue(new client.ApiError(0, "Can't reach the Aether backend."));
    render(<HistoryMenu role="clinician" patientId={null} current="s9" onOpen={vi.fn()} onNew={vi.fn()} />);
    await open();
    expect(await screen.findByText("Can't reach the Aether backend.")).toBeInTheDocument();
  });
});
