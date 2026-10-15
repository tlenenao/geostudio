// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { describe, expect, test, vi } from "vitest";

import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient, ReportSchedulePayload } from "../../api/types";
import { ReportScheduleEditor } from "./ReportScheduleEditor";

const BASE: ReportSchedulePayload = {
  bookmarkItemId: "bm-1",
  refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
  channels: [{ kind: "webhook", url: "" }],
};

// ReportScheduleEditor embarque PipelineScheduleEditor, qui appelle
// usePipelineNextRun (Tâche 22) inconditionnellement — un ItemClientProvider/
// QueryClientProvider ancêtre est désormais requis pour tout rendu, même
// quand la planification est déjà activée par défaut comme dans BASE.
function renderEditor(
  value: ReportSchedulePayload,
  onChange: (next: ReportSchedulePayload) => void,
  bookmarkTitle: string,
) {
  const bookmarks = [{ pk: "bm-1", title: bookmarkTitle }];
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    getPipelineNextRun: vi.fn().mockResolvedValue({ nextRun: "2026-08-07T02:00:00.000Z" }),
  };
  const wrap = (element: ReactElement) => (
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>{element}</ItemClientProvider>
    </QueryClientProvider>
  );
  const view = render(
    wrap(<ReportScheduleEditor value={value} onChange={onChange} bookmarks={bookmarks} />),
  );
  return {
    ...view,
    rerenderEditor: (nextValue: ReportSchedulePayload, nextOnChange = onChange) =>
      view.rerender(
        wrap(
          <ReportScheduleEditor value={nextValue} onChange={nextOnChange} bookmarks={bookmarks} />,
        ),
      ),
  };
}

describe("ReportScheduleEditor", () => {
  test("REV-362 : le sélecteur de bookmark propose les bookmarks et remonte le choix", async () => {
    const onChange = vi.fn();
    renderEditor({ ...BASE, bookmarkItemId: "" }, onChange, "Weekly view");
    const select = screen.getByLabelText("Vue ciblée");
    expect(select).toBeRequired();
    await userEvent.selectOptions(select, "bm-1");
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ bookmarkItemId: "bm-1" });
  });

  test("edits the webhook url when the channel is a webhook", async () => {
    const onChange = vi.fn();
    renderEditor(BASE, onChange, "v");
    await userEvent.type(screen.getByLabelText("URL du webhook"), "h");
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      channels: [{ kind: "webhook", url: "h" }],
    });
  });

  test("switching the channel to email shows recipient and smtp secret fields", async () => {
    const onChange = vi.fn();
    const { rerenderEditor } = renderEditor(BASE, onChange, "v");
    await userEvent.selectOptions(screen.getByLabelText("Canal"), "email");
    expect(onChange).toHaveBeenLastCalledWith({
      ...BASE,
      channels: [{ kind: "email", to: "", smtpSecretName: "" }],
    });

    const emailValue: ReportSchedulePayload = {
      ...BASE,
      channels: [{ kind: "email", to: "", smtpSecretName: "" }],
    };
    rerenderEditor(emailValue);
    await userEvent.type(screen.getByLabelText("Destinataire"), "a");
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      channels: [{ kind: "email", to: "a", smtpSecretName: "" }],
    });

    await userEvent.type(screen.getByLabelText("Secret SMTP"), "s");
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      channels: [{ kind: "email", to: "", smtpSecretName: "s" }],
    });
  });

  test("switching back to webhook resets the channel to an empty url", async () => {
    const onChange = vi.fn();
    const emailValue: ReportSchedulePayload = {
      ...BASE,
      channels: [{ kind: "email", to: "a", smtpSecretName: "s" }],
    };
    renderEditor(emailValue, onChange, "v");
    await userEvent.selectOptions(screen.getByLabelText("Canal"), "webhook");
    expect(onChange).toHaveBeenLastCalledWith({
      ...emailValue,
      channels: [{ kind: "webhook", url: "" }],
    });
  });

  test("forwards the refresh policy through the embedded PipelineScheduleEditor", async () => {
    const onChange = vi.fn();
    renderEditor(BASE, onChange, "v");
    await userEvent.click(screen.getByLabelText("Planification automatique"));
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      refreshPolicy: { enabled: false, cron: "0 8 * * MON" },
    });
  });
});
