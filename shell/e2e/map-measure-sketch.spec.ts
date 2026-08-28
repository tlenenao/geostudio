// SPDX-License-Identifier: Apache-2.0
import { expect, test, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

// Crée une App vide et atterrit sur l'éditeur (/apps/9/edit). Recopié
// verbatim d'analytics-context.spec.ts:34-41 — helper local dupliqué par
// spec, convention établie de ce dépôt (aussi dans dataset-export.spec.ts).
async function createApp(page: Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill(title);
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
}

// Ajoute une source features et renseigne sa collection (dernière source
// ajoutée). Recopié verbatim d'analytics-context.spec.ts:44-50.
async function addFeaturesSource(page: Page, collection: string) {
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page
    .getByLabel(/Collection de la source/)
    .last()
    .fill(collection);
}

// Crée une app portant UN widget carte, l'enregistre, et retourne sur son
// runtime — la seule séquence de ce dépôt qui rende /apps/9 porteur d'un
// canvas MapLibre (constat B6 : DEFAULT_APP_CONFIG a `items: []`, donc
// /apps/9 n'a aucun widget par défaut). Réduite au strict nécessaire par
// rapport à analytics-context.spec.ts:280-300 (pas de dataset partagé, pas de
// source statistiques).
//
// La route "**/collections/geo/items*" est nécessaire (pas seulement une
// précaution) : mapWidget.tsx retourne `<p>Erreur de données</p>` — donc
// aucun canvas — dès que `ctx.data?.error` est vrai, et DataContext.tsx
// interroge réellement `client.queryDataSource` (un GET
// `/collections/{layer}/items`) pour toute source de type "features". Sans
// route pour "geo", cette requête échoue contre l'hôte fictif
// "https://core.test" et le widget affiche l'erreur au lieu de la carte.
async function appWithAMapWidget(page: Page) {
  await page.route("**/collections/geo/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [
          {
            id: 1,
            geometry: { type: "Point", coordinates: [2.4, 46.6] },
            properties: { nom: "P1" },
          },
        ],
      },
    });
  });
  await createApp(page, "Mesure");
  await addFeaturesSource(page, "geo");
  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await page.goto("/apps/9");
}

// L'assertion « aucune requête d'écriture » n'a AUCUN précédent dans les 57
// specs pré-existantes. L'outil, lui, en a : page.on("request") est utilisé
// par map-symbology.spec.ts:68 et analytics-context.spec.ts:1997 pour
// compter des requêtes, et c'est cet idiome qu'on reprend.
function recordWrites(page: Page): string[] {
  const writes: string[] = [];
  page.on("request", (req) => {
    if (!["POST", "PUT", "PATCH", "DELETE"].includes(req.method())) return;
    // /aggregate est le chemin de DONNÉES préexistant du widget carte (une
    // requête POST légitime, émise au chargement et au changement d'emprise),
    // sans rapport avec la barre d'outils. Tout le reste est une écriture.
    if (req.url().includes("/aggregate")) return;
    writes.push(`${req.method()} ${req.url()}`);
  });
  return writes;
}

// La preuve de sortie du chantier 4.5 du plan d'action : un lecteur mesure
// une distance / pose un croquis sur une app publiée, purement côté client —
// aucune requête d'écriture n'en résulte. Rien n'expose l'instance MapLibre
// au contexte de page (mesuré : aucun global de test dans le code de
// production), donc les assertions portent sur l'UI visible (texte de
// distance, compteur de formes) et sur le trafic réseau, jamais sur
// `map.getSource("__sketch__")`.
test("un lecteur mesure une distance sur une app publiée sans aucune écriture", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("**/map-icons", (route) => route.fulfill({ json: [] }));
  await appWithAMapWidget(page);

  // Attendre que la carte du widget existe AVANT de commencer à compter :
  // l'autorat de l'app écrit légitimement (PUT de la config), et ce qui doit
  // être prouvé porte sur la BARRE D'OUTILS.
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const writes = recordWrites(page);

  await page.getByRole("button", { name: "Mesurer" }).click();

  // Deux clics sur le canvas, bas de la carte : la barre d'outils
  // mesure/croquis est positionnée en overlay absolu en haut à gauche
  // (`MapMeasureSketchToolbar.tsx`, `absolute left-2 top-2`) et un clic à
  // ces coordonnées est un clic RÉEL au niveau du système, pas un
  // hit-test DOM — il atteint le premier élément sous le curseur, donc la
  // barre si le point choisi tombe dans son emprise. Mesuré : sur ce
  // canvas (~630×252 en résolution de test), la barre occupe jusqu'à
  // (x≈500, y≈134) ; les deux clics ci-dessous visent le tiers bas de la
  // carte, largement sous cette emprise. Retry parce qu'un clic arrivé
  // avant le premier rendu de la couche ne fait rien.
  const box = (await canvas.boundingBox())!;
  await expect(async () => {
    await page.mouse.click(box.x + box.width * 0.25, box.y + box.height * 0.75);
    await page.mouse.click(box.x + box.width * 0.55, box.y + box.height * 0.75);
    await expect(page.getByText(/\d+([.,]\d+)?\s*(m|km)$/)).toBeVisible({ timeout: 500 });
  }).toPass({ timeout: 10_000 });

  expect(writes).toEqual([]);
});

test("le croquis pose une forme comptabilisée dans la barre d'outils", async ({ page }) => {
  await mockCore(page);
  await page.route("**/map-icons", (route) => route.fulfill({ json: [] }));
  await appWithAMapWidget(page);

  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const writes = recordWrites(page);

  await page.getByRole("button", { name: "Croquis" }).click();
  await page.getByRole("button", { name: "Rectangle" }).click();

  // Même précaution que le test précédent : les deux coins visent le tiers
  // bas de la carte pour rester hors de l'emprise de la barre d'outils
  // (overlay absolu en haut à gauche).
  const box = (await canvas.boundingBox())!;
  await expect(async () => {
    await page.mouse.click(box.x + box.width * 0.25, box.y + box.height * 0.75);
    await page.mouse.click(box.x + box.width * 0.6, box.y + box.height * 0.9);
    await expect(page.getByText("1 rectangle")).toBeVisible({ timeout: 500 });
  }).toPass({ timeout: 10_000 });

  // La forme est aussi passée sur la carte (source __sketch__), mais rien
  // n'expose l'instance MapLibre au contexte de page et Global Constraints
  // interdit d'ajouter un global de test au code de production : la preuve
  // observable est le compteur de la barre d'outils, couvert côté source
  // GeoJSON par les tests unitaires de la tâche 18.
  expect(writes).toEqual([]);
});
