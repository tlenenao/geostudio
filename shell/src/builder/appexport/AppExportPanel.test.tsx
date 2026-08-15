// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppExportPanel } from "./AppExportPanel";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { AppConfig, ItemClient } from "../../api/types";

function config(withForm = false): AppConfig {
  return {
    kind: "app", theme: {}, dataSources: [], messages: [], navigationMode: "tabs", variables: [],
    pages: [{
      id: "p1", name: "P1", onEnter: [],
      layout: { type: "grid", breakpoints: {}, items: withForm ? [{ id: "w1", widget: "form", x: 0, y: 0, w: 4, h: 2, props: {} }] : [] },
    }],
  } as unknown as AppConfig;
}

function makeClient(overrides: Partial<ItemClient>): ItemClient {
  return overrides as ItemClient;
}

describe("AppExportPanel", () => {
  it("triggers export and shows a download link once done", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /statique/i }));
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument());
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "static");
  });

  it("warns before export when the config contains a form widget", async () => {
    const client = makeClient({ createAppExport: vi.fn(), getAppExportJob: vi.fn() });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config(true)} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /statique/i }));
    expect(screen.getByText(/écriture.*désactivée/i)).toBeInTheDocument();
    expect(client.createAppExport).not.toHaveBeenCalled();
  });

  it("triggers a connected export and shows a download link once done", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /connect/i }));
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument());
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "connected");
  });

  it("confirms the write warning with the mode that actually triggered it", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config(true)} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /connect/i }));
    expect(screen.getByText(/écriture.*désactivée/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /quand même/i }));
    await waitFor(() => expect(client.createAppExport).toHaveBeenCalledWith("item1", "connected"));
  });

  it("triggers a standalone export and shows a download link once done", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /autoport/i }));
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument());
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "standalone");
  });
});
