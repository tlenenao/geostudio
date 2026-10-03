import { bug } from "../_fixtures/verify";
import { expect, test } from "@playwright/test";
import { loginOidc } from "../_fixtures/env";
import { spaGo } from "../j04/helpers";
import { getSeed, type Seed } from "./seed";

let seed: Seed;

test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
});

test.describe("j05 requête visuelle — UI", () => {
  test("Créateur : l'assistant charge le schéma, filtre/jointure/résumé s'ajoutent, Créer reste inactif (ETL désactivé)", async ({
    page,
  }) => {
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    await spaGo(page, "/datasets/visual-query/new", 2500);
    await expect(page.getByRole("heading", { name: "Nouvelle requête visuelle" })).toBeVisible();
    await page.getByLabel("Collection de base").selectOption(seed.ventes);
    await page.getByRole("button", { name: "Ajouter un filtre" }).click();
    await expect(page.getByLabel("Colonne du filtre 1")).toBeVisible();
    await page.getByLabel("Colonne du filtre 1").selectOption("montant");
    await page.getByLabel("Opérateur du filtre 1").selectOption("gte");
    await page.getByLabel("Valeur du filtre 1").fill("100");
    await page.getByRole("button", { name: "Ajouter une jointure" }).click();
    await page.getByRole("button", { name: "Ajouter un résumé" }).click();
    await page.getByRole("button", { name: "Ajouter une métrique" }).click();
    await page.getByLabel("Titre", { exact: true }).fill("aud-j05 requête");
    const create = page.getByRole("button", { name: "Créer", exact: true });
    await expect(create).toBeDisabled();
    await expect(page.getByText(/Fonction indisponible sur cette instance/)).toBeVisible();
    // Changer de collection de base réinitialise filtres, jointure et résumé.
    await page.getByLabel("Collection de base").selectOption(seed.zonesRef);
    await expect(page.getByLabel("Colonne du filtre 1")).toHaveCount(0);
  });

  // Finding j05-022 : la route n'a aucun RequirePrivilege, seul le bouton final est gardé.
  bug(
    "j05-022 : un Lecteur ne peut pas ouvrir l'assistant de requête visuelle par URL",
    async ({ page }) => {
      await loginOidc(page, "reader");
      await page.waitForTimeout(800);
      await spaGo(page, "/datasets/visual-query/new", 2500);
      await expect(page.getByLabel("Collection de base")).toHaveCount(0);
    },
  );
});
