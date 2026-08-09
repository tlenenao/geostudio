## Task 19: E2E — `report-schedule.spec.ts`

**Files:**
- Create: `shell/e2e/report-schedule.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (existing, `shell/e2e/mocks.ts`) — this codebase's E2E convention mocks every core route via `page.route(...)` rather than triggering a real procrastinate sweep (confirmed by reading `alert-rule.spec.ts`/`bookmarks.spec.ts`); this spec follows the same convention rather than the design doc's more literal "déclencher le sweep" phrasing.

- [ ] **Step 1: Write the E2E spec**

```ts
// shell/e2e/report-schedule.spec.ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// SP-17b — depuis "Mes vues", programmer un rapport PDF hebdomadaire sur un
// signet existant, avec un webhook comme canal ; l'historique des
// exécutions affiche un run "Terminé" avec un lien de téléchargement.
test("programmer un rapport sur un signet, voir son historique d'exécutions", async ({ page }) => {
  await mockCore(page);

  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "bookmark") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          { pk: "bookmark-1", resourceType: "bookmark", title: "Récents 2026", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-bookmark", isPublished: false },
        ],
        total: 1, page: 1, pageSize: 12,
      },
    });
  });

  let createdReportConfig: unknown = null;
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON();
    if (body?.config?.kind === "report") {
      createdReportConfig = body;
      await route.fulfill({ status: 201, json: { id: "cfg-report", kind: "report", itemId: "report-1" } });
      return;
    }
    return route.fallback();
  });
  await page.route("**/configs/by-item/report-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-report", itemId: "report-1", kind: "report",
        config: (createdReportConfig as { config: unknown })?.config ?? {
          kind: "report",
          report: { bookmarkItemId: "bookmark-1", refreshPolicy: { enabled: true, cron: "0 8 * * MON" }, channels: [{ kind: "webhook", url: "https://example.test/hook" }] },
        },
      },
    });
  });
  await page.route("**/reports/report-1/runs", async (route) => {
    await route.fulfill({
      json: [{
        id: "run-1", status: "done", resultUrl: "https://s3.test/renders/run-1.pdf",
        error: null, notifiedAt: "2026-08-09T08:00:05Z", createdAt: "2026-08-09T08:00:00Z",
      }],
    });
  });

  await page.goto("/bookmarks");
  await expect(page.getByText("Récents 2026")).toBeVisible();

  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Programmer un rapport" }).click();
  await expect(page).toHaveURL(/\/reports\/new$/);

  await page.getByLabel("URL du webhook").fill("https://example.test/hook");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page).toHaveURL(/\/reports\/report-1\/edit$/);

  expect(createdReportConfig).not.toBeNull();
  expect(createdReportConfig).toMatchObject({
    config: {
      kind: "report",
      report: {
        bookmarkItemId: "bookmark-1",
        channels: [{ kind: "webhook", url: "https://example.test/hook" }],
      },
    },
  });

  await expect(page.getByText("Terminé")).toBeVisible();
  await expect(page.getByRole("link", { name: "Télécharger" })).toHaveAttribute("href", "https://s3.test/renders/run-1.pdf");
});
```

Before finalizing, read `shell/e2e/mocks.ts` to confirm `mockCore`'s exact default fixtures (auth identity, base `**/items*` handler, etc.) match what this spec assumes — adjust route order/specificity if `mockCore` already registers a `**/items*` handler that would intercept before this spec's own override (Playwright matches routes in reverse registration order, most-recently-registered first, same as every other spec in this directory already relies on).

- [ ] **Step 2: Run the E2E spec**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test report-schedule.spec.ts`
Expected: PASS.

- [ ] **Step 3: Run the full E2E suite to confirm no regression**

Run: `cd shell && npm run e2e`
Expected: PASS (previous 18 specs + this new one = 19), no regressions.

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/e2e/report-schedule.spec.ts
git commit -m "test(shell): E2E — programmer un rapport sur un signet (SP-17b)"
```

---

## Final Verification

- [ ] **Full core suite**: `cd core && uv run pytest -q` — expect all green (SQLite-backed tests only; `postgis`-marked skip without `CORE_TEST_DATABASE_URL`).
- [ ] **Import-linter**: `cd core && uv run lint-imports` — no violations.
- [ ] **Core typecheck/lint** (if configured): `cd core && uv run ruff check .` — no new issues in touched files.
- [ ] **Shell build**: `cd shell && npm run build` — `tsc --noEmit` + `vite build` both succeed.
- [ ] **Shell unit tests**: `cd shell && npm run test` — all green, no regressions against the pre-existing 61 files / 398 tests.
- [ ] **Shell E2E**: `cd shell && npm run e2e` — all 19 specs green.
- [ ] **Real-Postgres migration check** (Tasks 3 & 6, if not already done inline): `cd core && DATABASE_URL=<real postgres> uv run alembic upgrade head` reaches `0023 (head)` cleanly.
- [ ] Re-read `docs/superpowers/specs/2026-08-09-sp17b-report-schedule-design.md`'s "Critères d'acceptation" section and confirm each one is now demonstrably true against the code (not just "a task claims to implement it").
