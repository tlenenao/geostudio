## Task 17: `ReportEditPage.tsx` + routing

**Files:**
- Create: `shell/src/pages/ReportEditPage.tsx`
- Modify: `shell/src/shell/routes.tsx`

**Interfaces:**
- Consumes: `ReportScheduleEditor` (Task 15), `ReportRunPanel` (Task 16), `useCreateReportSchedule`/`useReportScheduleConfig`/`useSaveReportSchedule` (Task 14), `useAuth().username` (existing).
- Produces: `ReportEditPage({ pk, initialBookmarkItemId }: { pk: string | null; initialBookmarkItemId?: string })`; routes `/reports`, `/reports/new`, `/reports/:pk/edit`.

- [ ] **Step 1: Write `ReportEditPage.tsx`**

```tsx
// shell/src/pages/ReportEditPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateReportSchedule, useReportScheduleConfig, useSaveReportSchedule } from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import type { ReportSchedulePayload } from "../api/types";
import { Button } from "../ui/button";
import { ReportScheduleEditor } from "../builder/report/ReportScheduleEditor";
import { ReportRunPanel } from "../builder/report/ReportRunPanel";

function defaultPayload(bookmarkItemId: string): ReportSchedulePayload {
  return {
    bookmarkItemId,
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [{ kind: "webhook", url: "" }],
  };
}

// pk === null : brouillon local (/reports/new) — mirrors PipelineBuilderPage's
// pk-nullable create/edit split exactly (SP-15b §2.2's rationale applies
// verbatim here: nothing persisted before the first "Enregistrer").
export function ReportEditPage({ pk, initialBookmarkItemId }: { pk: string | null; initialBookmarkItemId?: string }) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const configQuery = useReportScheduleConfig(pk ?? "", { enabled: pk !== null });
  const createReport = useCreateReportSchedule();
  const saveReport = useSaveReportSchedule(pk ?? "");

  const [draft, setDraft] = useState<ReportSchedulePayload>(
    defaultPayload(initialBookmarkItemId ?? ""),
  );
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (pk !== null && configQuery.data) setDraft(configQuery.data);
  }, [pk, configQuery.data]);

  if (pk !== null && configQuery.isLoading) return <p role="status">Chargement…</p>;

  async function onSave() {
    setSaveError(null);
    try {
      if (pk === null) {
        const item = await createReport.mutateAsync({ title: "Rapport planifié", owner: username ?? "", report: draft });
        navigate(`/reports/${item.pk}/edit`, { replace: true });
        return;
      }
      await saveReport.mutateAsync(draft);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Échec de l'enregistrement.");
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-lg font-medium">{pk === null ? "Programmer un rapport" : "Modifier le rapport planifié"}</h1>
      <ReportScheduleEditor value={draft} onChange={setDraft} bookmarkLabel={draft.bookmarkItemId} />
      <Button onClick={onSave} disabled={createReport.isPending || saveReport.isPending}>
        Enregistrer
      </Button>
      {saveError && (
        <p role="alert" className="text-sm text-red-600">
          {saveError}
        </p>
      )}
      {pk !== null && <ReportRunPanel reportId={pk} />}
    </div>
  );
}
```

- [ ] **Step 2: Wire routes**

In `shell/src/shell/routes.tsx`, add the import:
```ts
import { ReportEditPage } from "../pages/ReportEditPage";
```

Add two route-wrapper functions, right after `PipelineEditRoute`:
```tsx
function ReportNewRoute() {
  const location = useLocation();
  const bookmarkItemId = (location.state as { bookmarkItemId?: string } | null)?.bookmarkItemId;
  return <ReportEditPage pk={null} initialBookmarkItemId={bookmarkItemId} />;
}

function ReportEditRoute() {
  const { pk } = useParams();
  return <ReportEditPage pk={pk!} />;
}

function ReportsRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <>
      {openError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de l'ouverture du rapport.
        </p>
      )}
      <CatalogPage onOpenItem={onOpenItem} fixedType="report" />
    </>
  );
}
```

Add the `"report"` branch to `useOpenItem`, right before the final catch-all `navigate(...)` line:
```tsx
    if (type === "pipeline") {
      navigate(`/pipelines/${pk}/edit`);
      return;
    }
    if (type === "report") {
      navigate(`/reports/${pk}/edit`);
      return;
    }
    navigate(type === "map" ? `/maps/${pk}` : type === "dataset" ? `/datasets/${pk}/edit` : `/apps/${pk}/edit`);
```

Register the three routes inside `<Route element={<ProtectedLayout />}>`, right after `/pipelines/:pk/edit`:
```tsx
        <Route path="/pipelines/:pk/edit" element={<PipelineEditRoute />} />
        <Route path="/reports" element={<ReportsRoute />} />
        <Route path="/reports/new" element={<ReportNewRoute />} />
        <Route path="/reports/:pk/edit" element={<ReportEditRoute />} />
```

- [ ] **Step 3: Typecheck**

Run: `cd shell && npm run build`
Expected: passes.

- [ ] **Step 4: Run existing shell unit tests**

Run: `cd shell && npm run test -- routes`
Expected: PASS, no regressions (if `routes.tsx` has no dedicated unit test file, this step is a no-op — confirm by checking `shell/src` for a `routes.test.tsx` before assuming).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/pages/ReportEditPage.tsx shell/src/shell/routes.tsx
git commit -m "feat(shell): ReportEditPage + /reports routes (SP-17b)"
```

---

