import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import {
  alertConfig,
  deferEvaluation,
  getAlertSeed,
  openAs,
  spaGoto,
  waitEvaluation,
} from "./helpers";

// Éditeur de règles d'alerte dans la page d'édition d'un dataset.
test.setTimeout(150_000);

test.describe("j09 AlertRuleEditor", () => {
  // Bug confirmé : voir docs/revue/audit-2026-09-29/j09/findings.jsonl
  bug(
    "j09-011 : « Exécuter maintenant » signale l'échec au lieu de rester muet",
    async ({ page }) => {
      const s = await getAlertSeed();
      const r = await s.creator.send("POST", "/v1/configs", {
        title: `${s.tag}-ui-run`,
        config: alertConfig(s.datasetId),
      });
      expect(r.status).toBe(201);
      await openAs(page, "creator");
      await spaGoto(page, `/datasets/${s.datasetId}/edit`);
      await page.getByRole("button", { name: "Exécuter maintenant" }).first().click();
      await expect(page.getByRole("alert")).toBeVisible({ timeout: 5000 });
    },
  );

  // Bug confirmé : voir docs/revue/audit-2026-09-29/j09/findings.jsonl
  bug(
    "j09-012 : l'état d'une règle est affiché en français avec sa valeur mesurée",
    async ({ page }) => {
      const s = await getAlertSeed();
      const r = await s.creator.send("POST", "/v1/configs", {
        title: `${s.tag}-ui-state`,
        config: alertConfig(s.datasetId),
      });
      const id = r.body.itemId as string;
      await s.creator.send("POST", `/v1/alerts/${id}/evaluate`);
      const evalId = (await s.creator.get(`/v1/alerts/${id}/evaluations`)).body[0].id as string;
      deferEvaluation(evalId);
      await waitEvaluation(s.creator, id, evalId);
      await openAs(page, "creator");
      await spaGoto(page, `/datasets/${s.datasetId}/edit`);
      const row = page.locator("div.border-t", { hasText: `${s.tag}-ui-state` });
      await expect(row).toBeVisible();
      // L'état est chargé après le titre : on attend qu'il remplace le « — » avant de juger le libellé.
      await expect(row).not.toContainText("—");
      await expect(row).not.toContainText("firing");
    },
  );
});
