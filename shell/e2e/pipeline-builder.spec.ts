// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

const OPS_CATALOG = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] } },
  "transform.join": {
    kind: "transform",
    paramsSchema: { properties: { withCollectionId: { type: "string", format: "collection-id" }, on: { type: "string" } }, required: ["on"] },
    acceptsSecondaryInput: true,
  },
  "writer.collection": { kind: "writer", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
};

async function mockPipelineFlow(page: Page) {
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, etlEnabled: true } });
  });
  await page.route("https://core.test/pipelines/ops", async (route) => {
    await route.fulfill({ json: OPS_CATALOG });
  });
  await page.route("https://core.test/collections*", async (route) => {
    await route.fulfill({
      json: { collections: [
        { id: "villes", title: "Villes", description: "", tableName: "villes", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 10, owner: "alice" },
        { id: "villes_propres", title: "Villes propres", description: "", tableName: "villes_propres", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 0, owner: "alice" },
      ] },
    });
  });
  await page.route("https://core.test/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind !== "pipeline") return route.fallback();
    await route.fulfill({ status: 201, json: { id: "cfg-pipe1", kind: "pipeline", itemId: "pipe-1" } });
  });
  let runPolls = 0;
  await page.route("https://core.test/pipelines/pipe-1/run", async (route) => {
    await route.fulfill({ status: 202, json: { runId: "run-1" } });
  });
  await page.route("https://core.test/pipelines/pipe-1/runs", async (route) => {
    runPolls += 1;
    const status = runPolls < 2 ? "running" : "succeeded";
    await route.fulfill({
      json: [{ id: "run-1", status, startedAt: "2026-08-06T10:00:00Z", finishedAt: status === "succeeded" ? "2026-08-06T10:00:02Z" : null, error: null, nodeStats: {} }],
    });
  });
}

test("un utilisateur non-technicien construit, enregistre puis exécute un pipeline visuellement", async ({ page }) => {
  await mockCore(page);
  await mockPipelineFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("pipeline");
  await dialog.getByLabel("Titre").fill("Nettoyer villes");
  await dialog.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/pipelines\/new$/);

  // Glisser un reader sur le canvas.
  const reader = page.getByText("reader.collection");
  const canvas = page.locator(".react-flow__pane");
  await reader.dragTo(canvas, { targetPosition: { x: 100, y: 100 } });

  // Glisser un writer sur le canvas.
  const writer = page.getByText("writer.collection");
  await writer.dragTo(canvas, { targetPosition: { x: 400, y: 100 } });

  // Relier reader -> writer (poignée droite du premier nœud vers la poignée
  // gauche du second — sélecteurs React Flow standard).
  const sourceHandle = page.locator(".react-flow__node").first().locator(".react-flow__handle-right");
  const targetHandle = page.locator(".react-flow__node").last().locator(".react-flow__handle-left");
  await sourceHandle.dragTo(targetHandle);

  // Renseigner les paramètres des deux nœuds.
  await page.locator(".react-flow__node").first().click();
  await page.getByLabel("collectionId").selectOption("villes");
  await page.locator(".react-flow__node").last().click();
  await page.getByLabel("collectionId").selectOption("villes_propres");

  await expect(page.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await expect(page).toHaveURL(/\/pipelines\/pipe-1\/edit$/);

  await page.getByRole("button", { name: "Exécuter" }).click();
  await expect(page.getByText("succeeded")).toBeVisible({ timeout: 10_000 });
});

test("un utilisateur relie une seconde source sur la poignée secondaire d'un transform.join", async ({ page }) => {
  await mockCore(page);
  await mockPipelineFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("pipeline");
  await dialog.getByLabel("Titre").fill("Joindre deux sources");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/pipelines\/new$/);

  const canvas = page.locator(".react-flow__pane");
  // Les libellés de la palette (`.cursor-grab`) sont ciblés explicitement :
  // une fois un nœud déposé, son op apparaît aussi dans le nœud (titre +
  // sous-titre), ce qui rendrait `getByText` ambigu (mode strict Playwright).
  const paletteItem = (op: string) => page.locator(".cursor-grab", { hasText: op });
  // Positions volontairement resserrées et étagées verticalement : l'app
  // place un nœud déposé à `event.clientX/Y` bruts (coordonnées page, non
  // relatives au pane React Flow ni compensées du pan/zoom) — au-delà d'un
  // petit décalage, le nœud atterrit hors de la zone du canvas (sous le
  // panneau d'inspection à droite), rendant ses poignées impossibles à
  // cibler. Cette disposition reste dans la zone sûre tout en gardant
  // chaque nœud vertical séparé des autres pour que les segments de
  // glisser-déposer entre poignées ne traversent pas un nœud tiers.
  await paletteItem("reader.collection").dragTo(canvas, { targetPosition: { x: 0, y: 210 } });
  await paletteItem("reader.collection").dragTo(canvas, { targetPosition: { x: 0, y: 50 } });
  await paletteItem("transform.join").dragTo(canvas, { targetPosition: { x: 70, y: 150 } });
  await paletteItem("writer.collection").dragTo(canvas, { targetPosition: { x: 100, y: 320 } });

  const nodes = page.locator(".react-flow__node");
  const primaryReader = nodes.nth(0);
  const secondaryReader = nodes.nth(1);
  const joinNode = nodes.nth(2);
  const writerNode = nodes.nth(3);

  // Primaire : premier reader -> entrée primaire (gauche) du join.
  await primaryReader.locator(".react-flow__handle-right").dragTo(joinNode.locator(".react-flow__handle-left"));
  // Secondaire : second reader -> entrée secondaire (haut) du join.
  await secondaryReader.locator(".react-flow__handle-right").dragTo(joinNode.locator(".react-flow__handle-top"));
  // join -> writer.
  await joinNode.locator(".react-flow__handle-right").dragTo(writerNode.locator(".react-flow__handle-left"));

  await primaryReader.click();
  await page.getByLabel("collectionId").selectOption("villes");
  await secondaryReader.click();
  await page.getByLabel("collectionId").selectOption("villes_propres");
  await joinNode.click();
  // Match exact : `getByLabel("on")` en sous-chaîne matcherait aussi
  // "withCollectionId" (contient "on") ainsi que les contrôles React Flow
  // ("Control Panel", "React Flow attribution", qui contiennent tous deux
  // "on" comme sous-chaîne) — mode strict Playwright sinon violé.
  await page.getByLabel("on", { exact: true }).fill("id");
  await writerNode.click();
  await page.getByLabel("collectionId").selectOption("villes_propres");

  await expect(page.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
});
