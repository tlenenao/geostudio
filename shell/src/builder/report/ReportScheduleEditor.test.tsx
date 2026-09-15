// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import type { ReportSchedulePayload } from "../../api/types";
import { ReportScheduleEditor } from "./ReportScheduleEditor";

const BASE: ReportSchedulePayload = {
  bookmarkItemId: "bm-1",
  refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
  channels: [{ kind: "webhook", url: "" }],
};

describe("ReportScheduleEditor", () => {
  test("shows the targeted view label", () => {
    render(<ReportScheduleEditor value={BASE} onChange={vi.fn()} bookmarkLabel="Weekly view" />);
    expect(screen.getByText("Weekly view")).toBeInTheDocument();
  });

  test("edits the webhook url when the channel is a webhook", async () => {
    const onChange = vi.fn();
    render(<ReportScheduleEditor value={BASE} onChange={onChange} bookmarkLabel="v" />);
    await userEvent.type(screen.getByLabelText("URL du webhook"), "h");
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      channels: [{ kind: "webhook", url: "h" }],
    });
  });

  test("switching the channel to email shows recipient and smtp secret fields", async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ReportScheduleEditor value={BASE} onChange={onChange} bookmarkLabel="v" />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Canal"), "email");
    expect(onChange).toHaveBeenLastCalledWith({
      ...BASE,
      channels: [{ kind: "email", to: "", smtpSecretName: "" }],
    });

    const emailValue: ReportSchedulePayload = {
      ...BASE,
      channels: [{ kind: "email", to: "", smtpSecretName: "" }],
    };
    rerender(<ReportScheduleEditor value={emailValue} onChange={onChange} bookmarkLabel="v" />);
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
    render(<ReportScheduleEditor value={emailValue} onChange={onChange} bookmarkLabel="v" />);
    await userEvent.selectOptions(screen.getByLabelText("Canal"), "webhook");
    expect(onChange).toHaveBeenLastCalledWith({
      ...emailValue,
      channels: [{ kind: "webhook", url: "" }],
    });
  });

  test("forwards the refresh policy through the embedded PipelineScheduleEditor", async () => {
    const onChange = vi.fn();
    render(<ReportScheduleEditor value={BASE} onChange={onChange} bookmarkLabel="v" />);
    await userEvent.click(screen.getByLabelText("Planification automatique"));
    expect(onChange.mock.calls.at(-1)![0]).toMatchObject({
      refreshPolicy: { enabled: false, cron: "0 8 * * MON" },
    });
  });
});
