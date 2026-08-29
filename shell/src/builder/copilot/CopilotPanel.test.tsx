// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { AppConfig, ItemClient } from "../../api/types";
import { applyClientOp } from "./applyClientOp";
import { CopilotPanel } from "./CopilotPanel";

// Implémentation réelle conservée, simplement espionnée : le test de page
// active ci-dessous a besoin de l'argument `activePageId` réellement reçu.
vi.mock("./applyClientOp", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./applyClientOp")>();
  return { ...actual, applyClientOp: vi.fn(actual.applyClientOp) };
});

enableMockAuth();

function emptyConfig(): AppConfig {
  return {
    kind: "app",
    theme: {} as AppConfig["theme"],
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
}

function renderPanel(
  client: Partial<ItemClient>,
  setDraft: (update: (prev: AppConfig | null) => AppConfig | null) => void,
) {
  return render(
    <ItemClientProvider client={client as ItemClient}>
      <CopilotPanel itemId="1" config={emptyConfig()} activePageId="page-1" setDraft={setDraft} />
    </ItemClientProvider>,
  );
}

describe("CopilotPanel", () => {
  it("sends a message and shows the reply, without changing the draft when there are no clientOps", async () => {
    const setDraft = vi.fn();
    const copilotTurn = vi
      .fn()
      .mockResolvedValue({ reply: "Ce dataset contient des incidents.", clientOps: [] });
    renderPanel({ copilotTurn }, setDraft);

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Explique ce dataset");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() =>
      expect(screen.getByText("Ce dataset contient des incidents.")).toBeInTheDocument(),
    );
    expect(setDraft).not.toHaveBeenCalled();
  });

  it("applies clientOps via a single setDraft call when present", async () => {
    const setDraft = vi.fn();
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "J'ai ajouté un indicateur.",
      clientOps: [{ op: "addWidget", args: { type: "text" } }],
    });
    renderPanel({ copilotTurn }, setDraft);

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Ajoute un widget texte");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(setDraft).toHaveBeenCalledTimes(1));
  });

  it("applies clientOps against the page active when the reply lands, not the one active at send time", async () => {
    const setDraft = vi.fn();
    let resolveTurn: (value: unknown) => void = () => {};
    const copilotTurn = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveTurn = resolve;
        }),
    );
    const client = { copilotTurn } as unknown as ItemClient;
    const panel = (activePageId: string) => (
      <ItemClientProvider client={client}>
        <CopilotPanel
          itemId="1"
          config={emptyConfig()}
          activePageId={activePageId}
          setDraft={setDraft}
        />
      </ItemClientProvider>
    );
    const { rerender } = render(panel("page-1"));

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Ajoute un widget texte");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    await waitFor(() => expect(copilotTurn).toHaveBeenCalledTimes(1));

    // L'utilisateur change de page pendant que le tour est encore en vol.
    rerender(panel("page-2"));

    vi.mocked(applyClientOp).mockClear();
    resolveTurn({
      reply: "J'ai ajouté un indicateur.",
      clientOps: [{ op: "addWidget", args: { type: "text" } }],
    });
    await waitFor(() => expect(setDraft).toHaveBeenCalledTimes(1));

    setDraft.mock.calls[0][0](emptyConfig());
    expect(vi.mocked(applyClientOp)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(applyClientOp).mock.calls[0][2]).toBe("page-2");
  });

  it("shows an error and does not crash when the request fails", async () => {
    const setDraft = vi.fn();
    const copilotTurn = vi.fn().mockRejectedValue(new Error("network"));
    renderPanel({ copilotTurn }, setDraft);

    await userEvent.type(screen.getByLabelText("Message au copilote"), "Explique ce dataset");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
