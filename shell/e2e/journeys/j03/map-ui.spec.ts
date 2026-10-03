import { bug } from "../_fixtures/verify";
import { test, expect, type Page } from "@playwright/test";
import { loginOidc } from "../_fixtures/env";
import { spaGo } from "../j02/helpers";
import { apiFor, FX, ingest, fixture, type Api } from "./api";
import { getSeed, mapConfig, type Seed } from "./seed";
import { join } from "node:path";

// Parcours créateur dans le shell (OIDC réel) : import par le tiroir, éditeur de carte,
// symbologie/popups, terrain, sauvegarde/historique, publication, lecteur en lecture seule.
// NB : le rendu canvas MapLibre n'est pas vérifiable ici (le style « demotiles » ne
// devient jamais « loaded » sous Chromium headless de l'audit) : on vérifie le DOM et l'API.
test.setTimeout(120_000);

let creator: Api;
let seed: Seed;
let pub: { itemId: string; collectionId: string };

test.beforeAll(async () => {
  creator = await apiFor("creator");
  seed = await getSeed();
  // Collection publique : sert de témoin pour j03-013 (la liste des champs y arrive).
  const res = await ingest(creator, "points.geojson", fixture("points.geojson"), {
    collectionTitle: `${seed.tag}-points-publics`,
  });
  expect(res.job.status).toBe("done");
  pub = { itemId: res.job.itemId, collectionId: res.job.collectionId };
  await creator.send("PATCH", `/v1/collections/${pub.collectionId}`, { isPublic: true });
});

async function asCreator(page: Page) {
  await loginOidc(page, "creator");
  await page.waitForTimeout(1000);
}

async function openMap(page: Page, pk: string) {
  await asCreator(page);
  await spaGo(page, `/maps/${pk}`, 3500);
}

const fieldOptions = (page: Page, label: string) =>
  page
    .getByLabel(label, { exact: true })
    .first()
    .evaluate((el) => {
      const list = el.getAttribute("list");
      return list ? [...document.querySelectorAll(`datalist[id="${list}"] option`)].length : -1;
    });

test.describe("j03 import par le tiroir « Importer un fichier »", () => {
  test("le tiroir s'ouvre, refuse un envoi sans titre et affiche une erreur explicite quand l'envoi échoue", async ({
    page,
  }) => {
    await asCreator(page);
    await page.getByRole("button", { name: "Importer un fichier" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Fichier à importer").setInputFiles(join(FX, "points.geojson"));
    // Sans titre : rien ne part (submit ignoré), le tiroir reste en phase « form ».
    await dialog.getByRole("button", { name: "Importer", exact: true }).click();
    await expect(dialog.getByRole("alert")).toHaveCount(0);
    await dialog.getByLabel("Titre de la collection").fill("aud-j03 import ui");
    await dialog.getByRole("button", { name: "Importer", exact: true }).click();
    // Chemin actuel : le présigné répond 500 (j03-002) → message générique, pas de boucle infinie.
    await expect(dialog.getByRole("alert")).toContainText("Échec de l'envoi du fichier.", {
      timeout: 20_000,
    });
  });

  bug(
    "j03-002 : importer un GeoJSON par l'UI aboutit à l'ouverture de la carte /maps/{id}",
    async ({ page }) => {
      // Bloqué par j03-002 (présigné 500) puis j03-001 (POST /uploads 500) ; sans CORS bucket MinIO le PUT
      // navigateur échouerait aussi. Attendu : navigation vers /maps/<id>.
      await asCreator(page);
      await page.getByRole("button", { name: "Importer un fichier" }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel("Fichier à importer").setInputFiles(join(FX, "points.geojson"));
      await dialog.getByLabel("Titre de la collection").fill("aud-j03 import ui ok");
      await dialog.getByRole("button", { name: "Importer", exact: true }).click();
      await expect(page).toHaveURL(/\/maps\/[0-9a-f]{32}/, { timeout: 60_000 });
    },
  );

  test("un CSV sans colonnes lat/lon reconnues propose le choix des colonnes avant l'envoi", async ({
    page,
  }) => {
    await asCreator(page);
    await page.getByRole("button", { name: "Importer un fichier" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Fichier à importer").setInputFiles(join(FX, "nogeom.csv"));
    await expect(dialog.getByLabel("Colonne latitude")).toBeVisible();
    await expect(dialog.getByLabel("Colonne longitude")).toBeVisible();
  });

  test("j03-005 : un CSV séparé par « ; » propose ses vraies colonnes (nom, lat, lon) au choix", async ({
    page,
  }) => {
    // Défaut j03-005 : l'en-tête est découpé sur « , » : une seule « colonne » « nom;lat;lon ».
    await asCreator(page);
    await page.getByRole("button", { name: "Importer un fichier" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Fichier à importer").setInputFiles(join(FX, "semi.csv"));
    const latOptions = await dialog
      .getByLabel("Colonne latitude")
      .locator("option")
      .allInnerTexts();
    expect(latOptions).toContain("lat");
  });
});

test.describe("j03 éditeur de carte — symbologie, popups, terrain", () => {
  test("la carte importée s'ouvre : couche listée, ajustement à l'emprise et terrain proposés", async ({
    page,
  }) => {
    await openMap(page, seed.pointsItem);
    await expect(page.getByText(`${seed.tag}-points`).first()).toBeVisible();
    await expect(page.getByLabel("Champ couleur")).toBeVisible();
    await expect(page.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
    await expect(page.getByLabel("Activer le terrain 3D")).toBeVisible();
  });

  bug(
    "j03-016 : l'éditeur de carte tient dans la fenêtre (pas de défilement de page)",
    async ({ page }) => {
      // Défaut j03-016 : à 1400x900 la page défile (scrollHeight ≈ 1619) — la colonne « Couches » (liste
      // de toutes les collections + formulaires d'ajout) étire tout l'éditeur, la carte fait ~1585 px de haut.
      await openMap(page, seed.pointsItem);
      const { scrollHeight, innerHeight } = await page.evaluate(() => ({
        scrollHeight: document.scrollingElement!.scrollHeight,
        innerHeight: window.innerHeight,
      }));
      expect(scrollHeight).toBeLessThanOrEqual(innerHeight + 2);
    },
  );

  bug(
    "j03-013 : sur une collection privée, « Champ couleur » propose les champs de la couche importée",
    async ({ page }) => {
      // Défaut j03-013 : geojsonIntrospect.fetchFeatureCollection fait un fetch() nu (sans jeton) :
      // 404 sur une collection privée → liste de champs vide, symbologie par champ inutilisable.
      await openMap(page, seed.pointsItem);
      expect(await fieldOptions(page, "Champ couleur")).toBeGreaterThanOrEqual(4);
    },
  );

  test("témoin j03-013 : sur une collection publique la même liste de champs se charge", async ({
    page,
  }) => {
    await openMap(page, pub.itemId);
    await expect
      .poll(() => fieldOptions(page, "Champ couleur"), { timeout: 15_000 })
      .toBeGreaterThanOrEqual(4);
  });

  test("popup : activer « Afficher les attributs au clic » révèle l'éditeur de champs, une expression non fermée est signalée", async ({
    page,
  }) => {
    await openMap(page, pub.itemId);
    await page.getByLabel("Afficher les attributs au clic").check();
    await expect(page.getByText("Sans sélection, tous les champs sont affichés.")).toBeVisible();
    await page.getByRole("button", { name: "Avancé (gabarit)" }).click();
    const tpl = page.getByLabel("Gabarit", { exact: true });
    await tpl.fill("Nom : ${record.nom");
    await expect(page.getByText("Expression non fermée")).toBeVisible();
  });

  test("terrain : cocher « Activer le terrain 3D » révèle URL de tuiles et exagération, pas de dépôt de DEM (capacité éteinte)", async ({
    page,
  }) => {
    await openMap(page, pub.itemId);
    await page.getByLabel("Activer le terrain 3D").check();
    await expect(page.getByLabel("URL de tuiles terrain")).toBeVisible();
    await expect(page.getByLabel("Exaggeration du terrain")).toBeVisible();
    await expect(page.getByText("DEM hébergé")).toHaveCount(0);
  });

  bug("j03-014 : le champ d'exagération du terrain est libellé en français", async ({ page }) => {
    // Défaut j03-014 : libellé « Exaggeration » en dur (TerrainPanel.tsx) et aria « Exaggeration du terrain ».
    await openMap(page, pub.itemId);
    await page.getByLabel("Activer le terrain 3D").check();
    await expect(page.getByText("Exaggeration", { exact: true })).toHaveCount(0);
  });
});

test.describe("j03 sauvegarde, historique, publication", () => {
  bug(
    "j03-015 : après Enregistrer, le panneau Historique liste aussitôt la nouvelle version comme courante",
    async ({ page }) => {
      // Défaut j03-015 : ConfigHistoryPanel ne charge qu'au montage et après restauration, jamais après
      // une sauvegarde : il affiche encore « Version N (courante) » alors que le serveur est en N+1.
      await openMap(page, pub.itemId);
      const before = await mapConfig(creator, pub.itemId);
      await page.getByRole("slider", { name: "Opacité" }).first().press("ArrowLeft");
      await page.getByRole("button", { name: "Enregistrer" }).click();
      await expect
        .poll(async () => (await mapConfig(creator, pub.itemId)).version, { timeout: 15_000 })
        .toBeGreaterThan(before.version);
      await expect(page.getByText(new RegExp(`Version ${before.version + 1} —`))).toBeVisible({
        timeout: 5_000,
      });
    },
  );

  test("modifier l'opacité, Enregistrer, recharger, « Restaurer » la version précédente réécrit la config", async ({
    page,
  }) => {
    await openMap(page, pub.itemId);
    const before = await mapConfig(creator, pub.itemId);
    await page.getByRole("slider", { name: "Opacité" }).first().press("ArrowLeft");
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect
      .poll(async () => (await mapConfig(creator, pub.itemId)).version, { timeout: 15_000 })
      .toBeGreaterThan(before.version);
    const saved = await mapConfig(creator, pub.itemId);
    expect(JSON.stringify(saved.config.map.layers[0])).not.toBe(
      JSON.stringify(before.config.map.layers[0]),
    );
    // Rechargement (navigation client : l'auth OIDC vit en mémoire) pour voir l'historique à jour.
    await spaGo(page, "/", 1500);
    await spaGo(page, `/maps/${pub.itemId}`, 3500);
    await page.getByRole("button", { name: "Restaurer" }).first().click();
    await page.getByRole("dialog").getByRole("button", { name: "Restaurer" }).click();
    await expect
      .poll(async () => (await mapConfig(creator, pub.itemId)).version, { timeout: 15_000 })
      .toBeGreaterThan(saved.version);
  });

  test("le menu ⋯ du catalogue publie la carte en un clic (aucune confirmation)", async ({
    page,
  }) => {
    await asCreator(page);
    await page
      .getByRole("textbox", { name: "Rechercher" })
      .first()
      .fill(`${seed.tag}-points-publics`);
    await page.waitForTimeout(1500);
    await page.getByRole("button", { name: "Actions" }).first().click();
    await page.getByRole("button", { name: "Publier", exact: true }).click();
    await expect
      .poll(async () => (await creator.get(`/v1/items/${pub.itemId}`)).body.isPublished, {
        timeout: 10_000,
      })
      .toBe(true);
    await creator.send("PATCH", `/v1/items/${pub.itemId}`, { isPublished: false });
  });

  test("un lecteur ouvre la carte publiée en lecture seule : Enregistrer désactivé et motif affiché", async ({
    page,
  }) => {
    await creator.send("PATCH", `/v1/items/${pub.itemId}`, { isPublished: true });
    await loginOidc(page, "reader");
    await page.waitForTimeout(1000);
    await spaGo(page, `/maps/${pub.itemId}`, 3500);
    await expect(page.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
    await expect(
      page.getByText("Modification réservée aux éditeurs de cet élément."),
    ).toBeVisible();
    await creator.send("PATCH", `/v1/items/${pub.itemId}`, { isPublished: false });
  });
});
