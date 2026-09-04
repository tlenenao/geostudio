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
// pkColumn: "population" plutôt que "id" (utilisé par map-popup.spec.ts) :
// vérifié empiriquement (cf. rapport Task 17) que world-tile.mvt encode sa
// colonne "id" comme feature-id MVT (ST_AsMVT(..., 'id') — même mécanisme
// que core/app/features/tiles.py::mvt_feature_id_column pour un pk entier),
// ce qui la retire des attributs décodés par MapLibre — seul `f.id` la
// porte, jamais `properties.id`. `handlePopup` (MapView.tsx) ne résout `fid`
// que depuis `properties[layer.pkColumn]`, jamais depuis `f.id` : un vrai
// défaut shipped (Task 14), hors périmètre de cette tâche E2E-only (limitée
// à ce seul fichier), documenté dans le rapport. "population" reste un
// attribut MVT ordinaire (jamais choisi comme feature-id par la fixture),
// donc un choix de pkColumn réaliste pour une collection dont la PK réelle
// n'est pas de type entier (cf. `mvt_feature_id_column`, qui rend alors
// `fid=NULL` côté SQL et laisse la colonne dans les attributs).
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
                tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
                sourceLayer: "communes",
                collectionId: "communes",
                geometryKind: "polygon",
                pkColumn: "population",
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

  await page.route("**/collections/communes/items/14000/attachments*", async (route) => {
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
  await expect(popup.getByRole("link", { name: "releve.jpg" })).toBeVisible();
});
