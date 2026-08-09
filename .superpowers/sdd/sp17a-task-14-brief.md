### Task 14: E2E — export depuis la visionneuse de carte

**Files:**
- Create: `shell/e2e/export.spec.ts`

**Interfaces:**
- Consumes: toute la chaîne des tâches 1-13, via interception réseau Playwright (pas de vrai cœur/worker démarré — cohérent avec les 13+ specs E2E existantes qui tournent contre `VITE_AUTH_MODE=mock` + interception de routes).

- [ ] **Step 1: Écrire la spec**

Inspecter d'abord `shell/e2e/pipeline-builder.spec.ts` ou `shell/e2e/alert-rule.spec.ts` (cités dans le design comme référence de profondeur d'assertion) pour le patron exact d'authentification mock + navigation + `page.route(...)` déjà en place dans ce dépôt, puis écrire :

```typescript
// shell/e2e/export.spec.ts
import { test, expect } from "@playwright/test";

test("exporter une carte en PDF depuis la visionneuse : le job atteint 'done' et expose un lien de téléchargement", async ({ page }) => {
  let createdExportBody: unknown = null;
  let pollCount = 0;

  await page.route("**/instance", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ readOnly: false, etlEnabled: false, exportEnabled: true }) }),
  );

  await page.route("**/configs/by-item/*", (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ config: { kind: "map", map: { basemap: { style: "https://demotiles.maplibre.org/style.json" }, view: { center: [0, 0], zoom: 2 }, layers: [] } } }),
    });
  });

  await page.route("**/export", async (route) => {
    createdExportBody = route.request().postDataJSON();
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ jobId: "job-e2e-1" }) });
  });

  await page.route("**/export/jobs/job-e2e-1", async (route) => {
    pollCount += 1;
    const status = pollCount < 2 ? "running" : "done";
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ id: "job-e2e-1", status, resultUrl: status === "done" ? "https://minio.example.test/exports/job-e2e-1.pdf" : null, error: null }),
    });
  });

  await page.goto("/maps/map-1");
  await page.getByRole("button", { name: "Exporter" }).click();
  await page.getByRole("button", { name: "PDF" }).click();

  await expect.poll(() => createdExportBody).not.toBeNull();
  // Vérifie le CONTENU du POST, pas seulement qu'un POST a eu lieu (piège
  // documenté CLAUDE.md/SP-16b : une assertion finale qui ne prouve qu'une
  // occurrence sans vérifier le corps).
  expect(createdExportBody).toEqual({ itemId: "map-1", format: "pdf" });

  const downloadLink = page.getByRole("link", { name: /télécharger/i });
  await expect(downloadLink).toHaveAttribute("href", "https://minio.example.test/exports/job-e2e-1.pdf", { timeout: 10_000 });
  expect(pollCount).toBeGreaterThanOrEqual(2);
});

test("le bouton Exporter est absent quand la capacité est désactivée", async ({ page }) => {
  await page.route("**/instance", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ readOnly: false, etlEnabled: false, exportEnabled: false }) }),
  );
  await page.route("**/configs/by-item/*", (route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ config: { kind: "map", map: { basemap: { style: "https://demotiles.maplibre.org/style.json" }, view: { center: [0, 0], zoom: 2 }, layers: [] } } }),
    }),
  );

  await page.goto("/maps/map-1");
  await expect(page.getByRole("button", { name: "Exporter" })).toHaveCount(0);
});
```

Adapter l'URL de navigation initiale (`/maps/map-1`) et le mécanisme d'authentification mock au patron réel déjà utilisé par les autres specs E2E de ce dépôt (probablement une étape de login/bypass en amont dans un `beforeEach` partagé — inspecter `shell/e2e/pipeline-builder.spec.ts` pour le reproduire à l'identique).

- [ ] **Step 2: Lancer la spec**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/export.spec.ts`
Expected: PASS (2 tests). Si le premier test échoue sur le sélecteur du bouton PDF (texte exact différent de celui posé Tâche 11), ajuster la spec pour matcher le texte réel du bouton — ne jamais assouplir l'assertion sur le corps du POST pour faire passer le test.

- [ ] **Step 3: Suite E2E complète (non-régression)**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e`
Expected: PASS — les 13+ specs existantes restent vertes en plus de `export.spec.ts`.

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/export.spec.ts
git commit -m "test(e2e): SP-17a — exporter une carte en PDF, capacité désactivée cache le bouton"
```

---

## Après l'exécution

Une fois les 14 tâches livrées et review passée : mettre à jour `CLAUDE.md` (nouvelle entrée SP-17a dans « Fait », déplacer la ligne SP-17 de « À venir » vers son état réel — 3D et `ReportSchedule` restent à faire) et la mémoire de session, en documentant explicitement l'état réel des deux vérifications best-effort non bloquantes (test `@pytest.mark.playwright` de la Tâche 6, build Docker de la Tâche 13) — jamais une affirmation de succès non vérifiée, cf. le précédent SP-15d.
