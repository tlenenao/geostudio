// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// Mêmes conventions que dataset-export.spec.ts / map-editor.spec.ts : la
// carte est créée via la vraie UI (dialogue "Nouveau"), pas injectée en JSON
// brut — mockCore() fait atterrir toute carte créée sur l'item "77"
// (cf. mocks.ts, route POST /configs → { itemId: "77" }).
async function createMap(page: import("@playwright/test").Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill(title);
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
}

test("exporter une carte en PDF depuis la visionneuse : le job atteint 'done' et expose un lien de téléchargement", async ({
  page,
}) => {
  await mockCore(page);

  // Surcharge la route /instance de mockCore (qui répond exportEnabled
  // absent → false) — ajoutée après mockCore(), donc prioritaire (Playwright
  // exécute le gestionnaire le plus récemment enregistré en premier), même
  // patron que les surcharges "site portal" en fin de mocks.ts.
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, etlEnabled: false, exportEnabled: true } });
  });

  let createdExportBody: unknown = null;
  let pollCount = 0;

  await page.route("**/export", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    createdExportBody = route.request().postDataJSON();
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ jobId: "job-e2e-1" }),
    });
  });

  await page.route("**/export/jobs/job-e2e-1", async (route) => {
    pollCount += 1;
    const status = pollCount < 2 ? "running" : "done";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "job-e2e-1",
        status,
        resultUrl: status === "done" ? "https://minio.example.test/exports/job-e2e-1.pdf" : null,
        error: null,
      }),
    });
  });

  await createMap(page, "Carte à exporter");

  await page.getByRole("button", { name: "Exporter", exact: true }).click();
  const formatDialog = page.getByRole("dialog", { name: "Choisir le format d'export" });
  await expect(formatDialog).toBeVisible();
  await formatDialog.getByRole("button", { name: "PDF", exact: true }).click();

  await expect.poll(() => createdExportBody).not.toBeNull();
  // Vérifie le CONTENU du POST /export, pas seulement qu'un POST a eu lieu
  // (piège documenté CLAUDE.md/SP-16b, Tâche 15 : une assertion finale qui ne
  // prouve qu'une occurrence sans vérifier le corps). itemId doit être celui
  // de la carte réellement ouverte ("77"), format celui du bouton réellement
  // cliqué ("pdf", pas "png").
  expect(createdExportBody).toEqual({ itemId: "77", format: "pdf" });

  // Le lien de téléchargement ne doit apparaître qu'une fois le job "done" —
  // en attendant, ni erreur ni lien prématuré.
  await expect(page.getByRole("alert")).toHaveCount(0);

  const downloadLink = page.getByRole("link", { name: /Télécharger l.export/i });
  await expect(downloadLink).toHaveAttribute(
    "href",
    "https://minio.example.test/exports/job-e2e-1.pdf",
    { timeout: 10_000 },
  );
  // Le job a bien transité pending/running → done (au moins deux réponses de
  // poll), pas seulement une réponse "done" immédiate qui masquerait un
  // court-circuit de la boucle de poll.
  expect(pollCount).toBeGreaterThanOrEqual(2);
});

test("le rendu ?exportRender=1 a une hauteur non nulle (régression C1 — chaîne de hauteur cassée)", async ({
  page,
}) => {
  // Régression pour la revue finale SP-17a (C1) : le rendu export sans chrome
  // (AppLayout court-circuité) doit tout de même établir une hauteur de
  // viewport explicite, sinon le conteneur MapLibre (h-full w-full) résout
  // sa hauteur en pourcentage contre un ancêtre body/#root sans hauteur
  // explicite et s'effondre à zéro — chaque capture serait alors blanche.
  // jsdom (Vitest) n'a pas de moteur de mise en page et ne peut pas détecter
  // cette classe de régression ; seul un vrai navigateur Playwright le peut.
  await mockCore(page);
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, etlEnabled: false, exportEnabled: true } });
  });

  await createMap(page, "Carte pour vérif hauteur export");

  await page.goto("/maps/77?exportRender=1");
  const mapContainer = page.getByTestId("map-container");
  await expect(mapContainer).toBeVisible();
  const box = await mapContainer.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height).toBeGreaterThan(0);
  expect(box!.width).toBeGreaterThan(0);
});

test("le bouton Exporter est absent quand la capacité est désactivée", async ({ page }) => {
  await mockCore(page);

  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, etlEnabled: false, exportEnabled: false } });
  });

  await createMap(page, "Carte sans export");

  await expect(page.getByRole("button", { name: "Exporter", exact: true })).toHaveCount(0);
});
