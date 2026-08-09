// SPDX-License-Identifier: Apache-2.0
import type { AlertChannel, ReportSchedulePayload } from "../../api/types";
import { PipelineScheduleEditor } from "../pipeline/PipelineScheduleEditor";

// Controlled component (mirrors PipelineScheduleEditor's value/onChange
// shape, not AlertRuleEditor's self-contained create-and-reset shape):
// ReportEditPage (SP-17b) needs both a create AND an edit lifecycle plus a
// run-history panel alongside it, so the parent owns persistence — same
// reason PipelineBuilderPage owns PipelinePayload state instead of
// PipelineScheduleEditor owning it.
export function ReportScheduleEditor({
  value, onChange, bookmarkLabel,
}: {
  value: ReportSchedulePayload;
  onChange: (next: ReportSchedulePayload) => void;
  bookmarkLabel: string;
}) {
  function setChannel(channel: AlertChannel) {
    onChange({ ...value, channels: [channel] });
  }
  const channel: AlertChannel | undefined = value.channels[0];

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-600">
        Vue ciblée : <span className="font-medium">{bookmarkLabel}</span>
      </p>

      <label className="flex flex-col gap-1 text-sm">
        Canal
        <select
          className="rounded border border-slate-300 px-2 py-1"
          value={channel?.kind ?? "webhook"}
          onChange={(e) => {
            if (e.target.value === "webhook") setChannel({ kind: "webhook", url: "" });
            else setChannel({ kind: "email", to: "", smtpSecretName: "" });
          }}
        >
          <option value="webhook">Webhook</option>
          <option value="email">E-mail</option>
        </select>
      </label>

      {channel?.kind === "webhook" && (
        <label className="flex flex-col gap-1 text-sm">
          URL du webhook
          <input
            className="rounded border border-slate-300 px-2 py-1"
            value={channel.url}
            onChange={(e) => setChannel({ kind: "webhook", url: e.target.value })}
          />
        </label>
      )}

      {channel?.kind === "email" && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            Destinataire
            <input
              className="rounded border border-slate-300 px-2 py-1"
              value={channel.to}
              onChange={(e) => setChannel({ kind: "email", to: e.target.value, smtpSecretName: channel.smtpSecretName })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Secret SMTP
            <input
              className="rounded border border-slate-300 px-2 py-1"
              value={channel.smtpSecretName}
              onChange={(e) => setChannel({ kind: "email", to: channel.to, smtpSecretName: e.target.value })}
            />
          </label>
        </>
      )}

      <PipelineScheduleEditor
        value={value.refreshPolicy}
        onChange={(policy) => onChange({ ...value, refreshPolicy: policy ?? { enabled: false, cron: "0 8 * * MON" } })}
      />
    </div>
  );
}
