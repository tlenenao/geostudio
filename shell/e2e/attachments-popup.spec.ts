// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const TILE = readFileSync(fileURLToPath(new URL("./fixtures/world-tile.mvt", import.meta.url)));

// Second et dernier test E2E du chantier 4.12 (SP-40) : cliquer une entité
// dont la couche déclare popup.attachmentField révèle sa pièce jointe dans le
// popup de la carte. Reprend le patron de navigation/clic de
// map-popup.spec.ts (Task 16, SP-24) — même carte publiée "map-1", même
// couche tuilée "communes", même fixture MVT (tuile 0/0/0) — et surcharge
// uniquement la config de la carte (route enregistrée après mockCore(),
// donc prioritaire) pour ajouter `attachmentField: "photos"` au popup de la
// couche.
//
// pkColumn: "id" (comme map-popup.spec.ts, PAS "population" comme au
// commit initial de la Tâche 17) : ce champ est justement le cas courant
// que la Tâche 20 corrige. Décodée directement (`@mapbox/vector-tile`,
// SP-40 Task 20), `world-tile.mvt` encode sa colonne "id" comme feature-id
// MVT — `ST_AsMVT(..., 'id')`, même mécanisme que
// core/app/features/tiles.py::mvt_feature_id_column pour une PK entière — :
// un seul feature, `f.id === 1`, `properties === { nom: "Tulle", population:
// 14000 }` (pas de clé "id"). Avant la Tâche 20, `handlePopup` ne résolvait
// `fid` que depuis `properties[layer.pkColumn]`, jamais depuis `f.id` — la
// Tâche 17 avait donc dû contourner avec `pkColumn: "population"` (un
// attribut MVT ordinaire, jamais choisi comme feature-id par la fixture) pour
// faire passer son scénario, ce qui prouvait un cas réel (PK non entière)
// mais pas le plus courant. Avec le correctif de la Tâche 20, `f.id` (1)
// prime sur `properties[pkColumn]` : ce spec cible maintenant
// `items/1/attachments`, pas `items/14000/…` (14000 est `population`, une
// valeur d'attribut ordinaire, jamais l'identité de l'entité pour cette
// couche).
test("cliquer une entité avec un champ attachment configuré révèle sa pièce jointe dans le popup", async ({
  page,
}) => {
  await mockCore(page);

  await page.route("**/configs/by-item/map-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-map-1",
        itemId: "map-1",
        kind: "map",
        config: {
          kind: "map",
          map: {
            basemap: { style: "https://demotiles.maplibre.org/style.json" },
            view: { center: [0, 0], zoom: 0 },
            layers: [
              {
                id: "communes",
                title: "Communes",
                visible: true,
                kind: "vector",
                tilesUrl: "https://core.test/v1/collections/communes/tiles/{z}/{x}/{y}.mvt",
                sourceLayer: "communes",
                collectionId: "communes",
                geometryKind: "polygon",
                pkColumn: "id",
                popup: {
                  titleField: "nom",
                  fields: [{ name: "population", label: "Habitants" }],
                  attachmentField: "photos",
                },
              },
            ],
          },
        },
      },
    });
  });

  await page.route("**/collections/communes/tiles/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: TILE,
    }),
  );

  await page.route("**/collections/communes/items/1/attachments*", async (route) => {
    await route.fulfill({
      json: {
        attachments: [
          {
            id: "att1",
            fieldKey: "photos",
            filename: "releve.jpg",
            contentType: "image/jpeg",
            byteSize: 10,
            createdAt: "2026-01-01T00:00:00Z",
          },
        ],
      },
    });
  });
  // Preuve de sortie de C1 (revue finale de branche) : le fichier n'est plus
  // servi par un `<a href>` nu (jamais authentifié) mais par un fetch réel —
  // ce mock permet de vérifier que la requête déclenchée par le clic aboutit
  // bien en 200, pas seulement que le bouton est visible. Le glob
  // `attachments*` ci-dessus ne matche jamais ce chemin (un `/` suit
  // "attachments"), donc une route dédiée est nécessaire.
  await page.route("**/collections/communes/items/1/attachments/att1/file", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/jpeg",
      body: Buffer.from("x"),
      headers: { "Content-Disposition": 'attachment; filename="releve.jpg"' },
    });
  });

  await page.goto("/maps/map-1");
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("map canvas has no bounding box");

  // Même écart que map-popup.spec.ts vis-à-vis d'un clic naïf au centre : à
  // ce zoom/viewport MapLibre demande plusieurs sous-tuiles z=1 couvrant la
  // vue, chacune recevant une copie de la même fixture — un clic au quart du
  // canevas atterrit de façon fiable dans le remplissage d'une sous-tuile.
  // Le clic est aussi rejoué (`toPass`) : il peut légitimement survenir avant
  // que la tuile ait fini de charger/rendre.
  const cx = box.x + box.width / 4;
  const cy = box.y + box.height / 4;
  const popup = page.getByRole("dialog", { name: "Attributs de l'entité" });
  await expect(async () => {
    await page.mouse.click(cx, cy);
    await expect(popup).toBeVisible({ timeout: 300 });
  }).toPass({ timeout: 10000 });

  await expect(popup.getByText("Pièces jointes")).toBeVisible();
  await expect(popup.getByRole("button", { name: "releve.jpg" })).toBeVisible();

  // Le clic déclenche un fetch authentifié réel (plus un `<a href>` nu) —
  // vérifié via la réponse effective, pas seulement la visibilité du bouton.
  const [fileResponse] = await Promise.all([
    page.waitForResponse((res) => res.url().includes("/attachments/att1/file")),
    popup.getByRole("button", { name: "releve.jpg" }).click(),
  ]);
  expect(fileResponse.status()).toBe(200);
});
