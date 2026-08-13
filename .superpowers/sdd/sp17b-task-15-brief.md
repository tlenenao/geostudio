## Task 15: `ReportScheduleEditor.tsx`

**Files:**
- Create: `shell/src/builder/report/ReportScheduleEditor.tsx`
- Test: exercised via Task 17's `ReportEditPage` and Task 19's E2E spec (this component has no data fetching of its own — it's a controlled form, same as `PipelineScheduleEditor`).

**Interfaces:**
- Consumes: `PipelineScheduleEditor` (existing, `shell/src/builder/pipeline/PipelineScheduleEditor.tsx`), `PipelineRefreshPolicy`/`AlertChannel`/`ReportSchedulePayload` types.
- Produces: `ReportScheduleEditor({ value, onChange, bookmarkLabel }: { value: ReportSchedulePayload; onChange: (next: ReportSchedulePayload) => void; bookmarkLabel: string })` — a controlled form, no internal save logic (the parent `ReportEditPage`, Task 17, owns saving — mirrors `PipelineScheduleEditor`'s controlled-component shape, NOT `AlertRuleEditor`'s self-contained-create shape, since a `ReportSchedule` needs a full edit lifecycle with a run panel, unlike an alert rule which is create-only from `DatasetEditPage`). `bookmarkLabel` is display-only (Task 17 passes `draft.bookmarkItemId` — the raw id, since no bookmark-title lookup is in scope for this plan).

- [ ] **Step 1: Write the component**

```tsx
// shell/src/builder/report/ReportScheduleEditor.tsx
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
```

- [ ] **Step 2: Typecheck**

Run: `cd shell && npm run build`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/builder/report/ReportScheduleEditor.tsx
git commit -m "feat(shell): ReportScheduleEditor — controlled form for channel + cron (SP-17b)"
```

---

