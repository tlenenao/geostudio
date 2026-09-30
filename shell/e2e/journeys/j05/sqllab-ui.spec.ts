import { bug } from "../_fixtures/verify";
import { expect, test, type Page } from "@playwright/test";
import { loginOidc } from "../_fixtures/env";
import { spaGo } from "../j04/helpers";
import { apiFor } from "./helpers";
import { getSeed, type Seed } from "./seed";

let seed: Seed;

test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
});

const editor = (page: Page) => page.getByRole("textbox", { name: "Requête SQL" });

async function typeSql(page: Page, sql: string) {
  await editor(page).click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(sql);
  // Referme l'éventuelle liste d'autocomplétion pour ne pas capter le clic suivant.
  await page.keyboard.press("Escape");
}

test.describe("j05 SQL Lab — UI", () => {
  test("Analyste : SQL Lab atteignable par « Analytique », exécution, résultat, historique, erreur DuckDB lisible", async ({
    page,
  }) => {
    await loginOidc(page, "analyst");
    await page.waitForTimeout(800);
    await page.getByRole("link", { name: "Analytique" }).click();
    await page.getByRole("link", { name: /SQL Lab/ }).click();
    await expect(page.getByRole("heading", { name: "SQL Lab" })).toBeVisible();
    await typeSql(page, `select zone, count(*) n from ${seed.ventes} group by zone order by zone`);
    await page.getByRole("button", { name: "Exécuter" }).click();
    const table = page.locator("table");
    await expect(table.locator("th")).toHaveText(["zone", "n"]);
    await expect(table.locator("tbody tr")).toHaveCount(3);
    await expect(table.locator("tbody tr").first()).toContainText("z1");
    // Historique : entrée ✓ cliquable qui recharge la requête.
    const entry = page.getByRole("button", { name: /Recharger la requête/ }).first();
    await expect(entry).toContainText(`from ${seed.ventes}`);
    await typeSql(page, "select 1");
    await entry.click();
    await expect(editor(page)).toContainText(`from ${seed.ventes}`);
    // Erreur : colonne inconnue → catégorie + ligne, table de résultat effacée.
    await typeSql(page, `select colonne_absente from ${seed.ventes}`);
    await page.getByRole("button", { name: "Exécuter" }).click();
    const alert = page.getByText("Binder Error");
    await expect(alert).toBeVisible();
    await expect(page.getByText(/Ligne 1 :/)).toBeVisible();
    await expect(page.locator("table")).toHaveCount(0);
  });

  test("Lecteur : /analytics/sql affiche le refus et aucun éditeur", async ({ page }) => {
    await loginOidc(page, "reader");
    await page.waitForTimeout(800);
    await spaGo(page, "/analytics/sql", 1500);
    await expect(page.getByText("Accès réservé aux analystes.")).toBeVisible();
    await expect(editor(page)).toHaveCount(0);
  });

  // Finding j05-013 : ni liste de tables, ni complétion de leurs noms (ids opaques type ingest_xxx).
  bug(
    "j05-013 : SQL Lab propose les collections interrogeables (noms de table) à la saisie",
    async ({ page }) => {
      await loginOidc(page, "analyst");
      await page.waitForTimeout(800);
      await spaGo(page, "/analytics/sql", 2000);
      await editor(page).click();
      await page.keyboard.type(`select * from ${seed.ventes.slice(0, 8)}`);
      const list = page.locator(".cm-tooltip-autocomplete");
      await expect(list).toContainText(seed.ventes);
    },
  );

  // Finding j05-015 : NULL et chaîne vide sont tous deux rendus en cellule vide.
  bug(
    "j05-015 : une valeur NULL se distingue d'une chaîne vide dans le résultat",
    async ({ page }) => {
      await loginOidc(page, "analyst");
      await page.waitForTimeout(800);
      await spaGo(page, "/analytics/sql", 2000);
      await typeSql(page, "select cast(null as varchar) a, '' b");
      await page.getByRole("button", { name: "Exécuter" }).click();
      const cells = page.locator("table tbody tr td");
      await expect(cells).toHaveCount(2);
      const [a, b] = await cells.allInnerTexts();
      expect(a).not.toBe(b);
    },
  );

  // Finding j05-016 : clé localStorage unique « geostudio.sqlLab.history », partagée entre comptes.
  bug("j05-016 : l'historique SQL est cloisonné par utilisateur", async ({ page }) => {
    const me = (await (await apiFor("analyst")).get("/v1/me")).body;
    await loginOidc(page, "analyst");
    await page.waitForTimeout(800);
    await spaGo(page, "/analytics/sql", 2000);
    await typeSql(page, "select 42 as secret_de_l_analyste");
    await page.getByRole("button", { name: "Exécuter" }).click();
    await expect(page.locator("table")).toBeVisible();
    const keys = await page.evaluate(() =>
      Object.keys(localStorage).filter((k) => k.toLowerCase().includes("sqllab")),
    );
    expect(keys.length).toBeGreaterThan(0);
    expect(keys.some((k) => k.includes(me.id) || k.includes(me.username))).toBe(true);
  });

  // Finding j05-027 : dialecte SQLite + Entrée qui valide la complétion au lieu de passer à la ligne.
  bug(
    "j05-027 : Entrée après « select cat » ne remplace pas la saisie par le mot-clé « catalog »",
    async ({ page }) => {
      await loginOidc(page, "analyst");
      await page.waitForTimeout(800);
      await spaGo(page, "/analytics/sql", 2000);
      await editor(page).click();
      await page.keyboard.type("select cat");
      await page.waitForTimeout(400);
      await page.keyboard.press("Enter");
      await expect(editor(page)).not.toContainText("catalog");
    },
  );
});
