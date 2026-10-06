import { bug } from "../_fixtures/verify";
import { test, expect, type Page } from "@playwright/test";
import { openAs, spaGoto } from "../j06/helpers";
import { apiFor, startQuotaCore, stopQuotaCore, waitQuotaCore } from "./helpers";

// Les pages du shell sont jouées contre le cœur de test à quotas bas (:8201) : toute requête
// vers :8200 est réécrite vers :8201 (même base, mêmes utilisateurs, mêmes jetons).
test.setTimeout(120_000);
let usage: { itemCount: number; collectionCount: number; storageBytes: number };

test.beforeAll(async () => {
  const admin = await apiFor("admin");
  usage = (await admin.get("/v1/admin/usage")).body;
  startQuotaCore({
    items: usage.itemCount,
    collections: usage.collectionCount,
    storage: usage.storageBytes + 5000,
  });
  await waitQuotaCore();
});

test.afterAll(() => stopQuotaCore());

async function toQuotaCore(page: Page): Promise<void> {
  await page.route("http://localhost:8200/**", (route) =>
    route.continue({ url: route.request().url().replace("localhost:8200", "localhost:8201") }),
  );
}

test("Infrastructure : l'usage affiche éléments et collections avec leur limite", async ({
  page,
}) => {
  await openAs(page, "admin");
  await toQuotaCore(page);
  await spaGoto(page, "/settings");
  await page.getByRole("link", { name: "Outils d'infrastructure →" }).click();
  await expect(page.getByText("Utilisation", { exact: true })).toBeVisible();
  await expect(
    page.getByText(`Éléments : ${usage.itemCount} / ${usage.itemCount}`, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(`Collections : ${usage.collectionCount} / ${usage.collectionCount}`, {
      exact: true,
    }),
  ).toBeVisible();
});

// Finding j08b-007 : stockage affiché en Mo à une décimale, donc « 0,0 Mo / 0,0 Mo » tant que
// l'usage et la limite sont sous ~50 Ko : l'écran ne permet pas de voir qu'on approche du quota.
bug("j08b-007 : le stockage affiche une valeur lisible sous le méga-octet", async ({ page }) => {
  await openAs(page, "admin");
  await toQuotaCore(page);
  await spaGoto(page, "/settings");
  await page.getByRole("link", { name: "Outils d'infrastructure →" }).click();
  const line = page.getByText(/^Stockage : /);
  await expect(line).toBeVisible();
  expect(await line.innerText()).not.toMatch(/0\.0 Mo \/ 0\.0 Mo/);
});

// Finding j08b-008 : aucune alerte visuelle d'approche ou d'atteinte du quota (et le refus à la
// création n'indique pas quoi faire).
bug("j08b-008 : l'écran d'usage signale un quota atteint", async ({ page }) => {
  await openAs(page, "admin");
  await toQuotaCore(page);
  await spaGoto(page, "/settings");
  await page.getByRole("link", { name: "Outils d'infrastructure →" }).click();
  await expect(page.getByText(`Éléments : ${usage.itemCount} / ${usage.itemCount}`)).toBeVisible();
  await expect(page.getByText(/Seuil d'alerte atteint|quota atteint/i).first()).toBeVisible();
});

test("création d'une App au quota d'items : le dialogue reste ouvert et affiche le motif du refus", async ({
  page,
}) => {
  await openAs(page, "creator");
  await toQuotaCore(page);
  await page.getByRole("button", { name: "Nouveau", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Titre").fill("aud-j08b-quota-ui");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/Quota d'éléments atteint/)).toBeVisible();
});
