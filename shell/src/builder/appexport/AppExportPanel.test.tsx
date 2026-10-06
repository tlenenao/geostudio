// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppExportPanel } from "./AppExportPanel";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { AppConfig, ItemClient } from "../../api/types";

function config(withForm = false): AppConfig {
  return {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    navigationMode: "tabs",
    variables: [],
    pages: [
      {
        id: "p1",
        name: "P1",
        onEnter: [],
        layout: {
          type: "grid",
          breakpoints: {},
          items: withForm ? [{ id: "w1", widget: "form", x: 0, y: 0, w: 4, h: 2, props: {} }] : [],
        },
      },
    ],
  } as unknown as AppConfig;
}

function makeClient(overrides: Partial<ItemClient>): ItemClient {
  return overrides as ItemClient;
}

describe("AppExportPanel", () => {
  it("triggers export and shows a download link once done", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({
        id: "job1",
        status: "done",
        resultUrl: "https://x.test/bundle.zip",
        error: null,
      }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /statique/i }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument(),
    );
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "static");
  });

  it("returns focus to the trigger once a mode is chosen (t01b-013)", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "running", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    const trigger = screen.getByRole("button", { name: /exporter/i });
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("button", { name: /statique/i }));
    expect(trigger).toHaveFocus();
  });

  it("shows the warning of a job done with truncation", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({
        id: "job1",
        status: "done",
        resultUrl: "https://x.test/bundle.zip",
        error: "source 's1' tronquée à 50000 enregistrements",
      }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /statique/i }));
    expect(await screen.findByText(/tronquée/)).toBeInTheDocument();
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
      getAppExportJob: vi.fn().mockResolvedValue({
        id: "job1",
        status: "done",
        resultUrl: "https://x.test/bundle.zip",
        error: null,
      }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /connect/i }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument(),
    );
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "connected");
  });

  it("confirms the write warning with the mode that actually triggered it", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({
        id: "job1",
        status: "done",
        resultUrl: "https://x.test/bundle.zip",
        error: null,
      }),
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
      getAppExportJob: vi.fn().mockResolvedValue({
        id: "job1",
        status: "done",
        resultUrl: "https://x.test/bundle.zip",
        error: null,
      }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /autoport/i }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument(),
    );
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "standalone");
  });
});

it("polls again while the job is still pending, then shows the download link", async () => {
  let call = 0;
  const getAppExportJob = vi.fn().mockImplementation(() => {
    call += 1;
    const status = call < 2 ? "pending" : "done";
    return Promise.resolve({
      id: "job1",
      status,
      resultUrl: status === "done" ? "https://x.test/bundle.zip" : null,
      error: null,
    });
  });
  const client = makeClient({
    createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
    getAppExportJob,
  });
  render(
    <ItemClientProvider client={client}>
      <AppExportPanel itemId="item1" config={config()} />
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
  await userEvent.click(screen.getByRole("button", { name: /statique/i }));
  await waitFor(
    () => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument(),
    { timeout: 5000 },
  );
  expect(call).toBeGreaterThanOrEqual(2);
});

it("surfaces a failure to even create the job", async () => {
  const client = makeClient({
    createAppExport: vi.fn().mockRejectedValue(new Error("Request failed: 500")),
    getAppExportJob: vi.fn(),
  });
  render(
    <ItemClientProvider client={client}>
      <AppExportPanel itemId="item1" config={config()} />
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
  await userEvent.click(screen.getByRole("button", { name: /statique/i }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/échec/i));
});

it("closes the mode picker without exporting", async () => {
  const createAppExport = vi.fn();
  const client = makeClient({ createAppExport, getAppExportJob: vi.fn() });
  render(
    <ItemClientProvider client={client}>
      <AppExportPanel itemId="item1" config={config()} />
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
  expect(screen.getByText(/mode d.export/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /fermer/i }));
  expect(screen.queryByText(/mode d.export/i)).not.toBeInTheDocument();
  expect(createAppExport).not.toHaveBeenCalled();
});

it("dismisses the write-widget warning without exporting", async () => {
  const createAppExport = vi.fn();
  const client = makeClient({ createAppExport, getAppExportJob: vi.fn() });
  render(
    <ItemClientProvider client={client}>
      <AppExportPanel itemId="item1" config={config(true)} />
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
  await userEvent.click(screen.getByRole("button", { name: /statique/i }));
  expect(screen.getByText(/écriture.*désactivée/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /ne pas exporter/i }));
  expect(screen.queryByText(/écriture.*désactivée/i)).not.toBeInTheDocument();
  expect(createAppExport).not.toHaveBeenCalled();
});

describe("AppExportPanel — plafond de poll", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("stops polling after the max attempt budget and surfaces a clear error instead of polling forever", async () => {
    const createAppExport = vi.fn().mockResolvedValue({ jobId: "job1" });
    const getAppExportJob = vi
      .fn()
      .mockResolvedValue({ id: "job1", status: "running", resultUrl: null, error: null });
    const client = makeClient({ createAppExport, getAppExportJob });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /exporter/i }));
    fireEvent.click(screen.getByRole("button", { name: /statique/i }));

    // 200 tentatives x 1500ms (MAX_POLL_ATTEMPTS x POLL_INTERVAL_MS) — même
    // patron que ExportPanel.test.tsx (« plafond de poll », finding I7).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500 * 200);
    });

    expect(screen.getByRole("alert")).toHaveTextContent(/toujours en cours/i);
    const callsAtCap = getAppExportJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500 * 10);
    });
    expect(getAppExportJob.mock.calls.length).toBe(callsAtCap);
  });
});

describe("AppExportPanel : accessibilité (P33.23, P33.24)", () => {
  it("le déclencheur expose aria-expanded et aria-controls vers le panneau de choix", async () => {
    render(
      <ItemClientProvider client={makeClient({})}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    const trigger = screen.getByRole("button", { name: /exporter/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(trigger.getAttribute("aria-controls") as string);
    expect(panel).not.toBeNull();
    expect(panel).toContainElement(screen.getByRole("button", { name: /statique/i }));
  });

  it("pendant l'export : aria-disabled (le focus reste), progression annoncée en role=status", async () => {
    let finish: (v: { jobId: string }) => void = () => {};
    const client = makeClient({
      createAppExport: vi.fn().mockReturnValue(new Promise((r) => (finish = r))),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "j", status: "done", resultUrl: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    const trigger = screen.getByRole("button", { name: /exporter/i });
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("button", { name: /statique/i }));
    expect(trigger).toHaveAttribute("aria-disabled", "true");
    expect(trigger).not.toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Export en cours");
    // un clic pendant l'export n'ouvre pas le panneau
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await act(async () => finish({ jobId: "j" }));
    await waitFor(() => expect(trigger).toHaveAttribute("aria-disabled", "false"));
  });

  it("REV-216 : annonce l'état du job (En cours puis Échoué) avec le vocabulaire partagé", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "j" }),
      getAppExportJob: vi
        .fn()
        .mockResolvedValueOnce({ id: "j", status: "running", resultUrl: null })
        .mockResolvedValue({ id: "j", status: "error", resultUrl: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /statique/i }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("État de l'export : En cours"),
    );
    await waitFor(
      () => expect(screen.getByRole("status")).toHaveTextContent("État de l'export : Échoué"),
      { timeout: 5000 },
    );
  });
});
