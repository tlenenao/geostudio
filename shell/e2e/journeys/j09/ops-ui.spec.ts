import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { openAs, spaGoto } from "./helpers";

// Pages Infrastructure et Tâches (shell + cœur réels).
test.setTimeout(90_000);

test.describe("j09 pages d'exploitation", () => {
  test("l'administrateur voit l'infrastructure sans boutons de lancement quand la passerelle est éteinte", async ({
    page,
  }) => {
    await openAs(page, "admin");
    await spaGoto(page, "/admin/infrastructure");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("Non activé sur cette instance")).toBeVisible();
    for (const tool of ["Martin", "Titiler", "Grafana"]) {
      await expect(page.getByRole("button", { name: tool, exact: true })).toHaveCount(0);
    }
    await expect(page.getByRole("link", { name: /MinIO/i })).toBeVisible();
  });

  // Bug confirmé : voir docs/revue/audit-2026-09-29/j09/findings.jsonl
  bug(
    "j09-009 : l'infrastructure affiche l'état des services (santé, files, jobs en attente)",
    async ({ page }) => {
      await openAs(page, "admin");
      await spaGoto(page, "/admin/infrastructure");
      await expect(
        page.getByText(/santé|healthy|file d'attente|jobs en attente/i).first(),
      ).toBeVisible();
    },
  );
});
