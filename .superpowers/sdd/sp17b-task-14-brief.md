## Task 14: Shell — types, `ItemClient`, hooks

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Test: none new (these are thin wiring layers, exercised transitively by Tasks 15-19's component tests and E2E).

**Interfaces:**
- Produces: `ReportSchedulePayload`, `ReportRunStatus` types; `createReportScheduleItem`, `getReportScheduleConfig`, `saveReportScheduleConfig`, `getReportRuns` on `ItemClient`; `useCreateReportSchedule`, `useReportScheduleConfig`, `useSaveReportSchedule` hooks — consumed by Tasks 15-17.

- [ ] **Step 1: Add `"report"` to `ResourceType` and the two new types**

In `shell/src/api/types.ts`, change:
```ts
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark" | "pipeline" | "alert";
```
to:
```ts
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark" | "pipeline" | "alert" | "report";
```

Add, right after `AlertRuleSummary`/`AlertEvaluation` (they're the closest sibling shapes):
```ts
export interface ReportSchedulePayload {
  bookmarkItemId: string;
  refreshPolicy: PipelineRefreshPolicy; // reused verbatim, same shape as pipeline/alert scheduling
  channels: AlertChannel[]; // reused verbatim from AlertRule (SP-16b)
}

export interface ReportRunStatus {
  id: string;
  status: "pending" | "running" | "done" | "error" | "unknown";
  resultUrl: string | null;
  error: string | null;
  notifiedAt: string | null;
  createdAt: string;
}
```

- [ ] **Step 2: Add `ItemClient` methods**

In the `ItemClient` interface block (`shell/src/api/types.ts`), add near the alert methods:
```ts
  createReportScheduleItem(input: { title: string; owner: string; report: ReportSchedulePayload }): Promise<Item>;
  getReportScheduleConfig(pk: string): Promise<ReportSchedulePayload>;
  saveReportScheduleConfig(pk: string, payload: ReportSchedulePayload): Promise<void>;
  getReportRuns(pk: string): Promise<ReportRunStatus[]>;
```

In `shell/src/api/itemClient.ts`, add right after the existing `getAlertEvaluations` method:
```ts
    async createReportScheduleItem(input: { title: string; owner: string; report: ReportSchedulePayload }): Promise<Item> {
      const config = { version: 1, kind: "report", report: input.report };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createReportScheduleItem: core returned no itemId");
      return {
        pk: String(data.itemId), resourceType: "report", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },

    async getReportScheduleConfig(pk: string): Promise<ReportSchedulePayload> {
      const data = await request<{ config?: { report?: ReportSchedulePayload } }>(
        "GET", `/configs/by-item/${pk}`,
      );
      if (!data.config?.report) throw new Error("getReportScheduleConfig: config has no report payload");
      return data.config.report;
    },

    async saveReportScheduleConfig(pk: string, payload: ReportSchedulePayload): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "report", report: payload });
    },

    async getReportRuns(pk: string): Promise<ReportRunStatus[]> {
      return request<ReportRunStatus[]>("GET", `/reports/${pk}/runs`);
    },
```

- [ ] **Step 3: Add hooks**

In `shell/src/api/hooks.ts`, add right after `useCreateAlertRule`:
```ts
export function useCreateReportSchedule() {
  const client = useItemClientInternal();
  return useMutation({
    mutationFn: (input: { title: string; owner: string; report: ReportSchedulePayload }) =>
      client.createReportScheduleItem(input),
  });
}

export function useReportScheduleConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["report-schedule", pk],
    queryFn: () => client.getReportScheduleConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useSaveReportSchedule(pk: string) {
  const client = useItemClientInternal();
  return useMutation({
    mutationFn: (payload: ReportSchedulePayload) => client.saveReportScheduleConfig(pk, payload),
  });
}
```

Add `ReportSchedulePayload` to this file's existing type import from `./types` (do not add a second import statement — extend the existing one, matching how `AlertRulePayload`/`PipelineRefreshPolicy` are already imported there).

- [ ] **Step 4: Typecheck**

Run: `cd shell && npm run build`
Expected: `tsc --noEmit` passes — no unresolved references, no unused-import errors.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts
git commit -m "feat(shell): ReportSchedule types, ItemClient methods, hooks (SP-17b)"
```

---

