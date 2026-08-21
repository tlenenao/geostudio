// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockVisualQueryFlow(page: Page) {
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, etlEnabled: true } });
  });

  // Liste des collections pour le sélecteur "Collection de base" — réutilise
  // le schéma "incidents" déjà mocké par mockCore() (titre: string, gravite: enum).
  await page.route("https://core.test/collections*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          {
            id: "incidents",
            title: "Incidents",
            description: "",
            tableName: "incidents",
            isPublic: true,
            editable: true,
            geometryType: null,
            srid: null,
            pkColumn: "id",
            canWrite: true,
            featureCount: 3,
            owner: "mockuser",
          },
        ],
      },
    });
  });

  await page.route("https://core.test/collections/empty", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ status: 201, json: { id: "query_out" } });
  });

  await page.route("https://core.test/collections/query_out/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "query_out",
        pk: "id",
        geometry: null,
        fields: [{ name: "titre", type: "string", required: false }],
      },
    });
  });

  // Stockage mutable du pipeline créé, pour la réouverture (GET /configs/by-item/pipeline-vq1).
  let storedPipeline: unknown = null;
  // Stockage mutable de la config dataset, pour refléter le sourcePipelineId posé par saveDatasetConfig.
  let storedDatasetConfig: {
    source: string;
    collectionId: string;
    columns: Record<string, unknown>;
    sourcePipelineId?: string;
  } = {
    source: "collection",
    collectionId: "query_out",
    columns: {},
  };

  await page.route("https://core.test/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON();
    if (body?.config?.kind === "pipeline") {
      storedPipeline = body.config.pipeline;
      await route.fulfill({
        status: 201,
        json: { id: "cfg-pipeline-vq", kind: "pipeline", itemId: "pipeline-vq1" },
      });
      return;
    }
    return route.fallback(); // laisse mockCore() gérer "dataset" (renvoie toujours itemId "dataset-1") et les autres kinds
  });

  await page.route("https://core.test/configs/by-item/dataset-1", async (route) => {
    const method = route.request().method();
    if (method === "PUT") {
      const body = route.request().postDataJSON();
      storedDatasetConfig = body.dataset;
      await route.fulfill({
        json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", config: body },
      });
    } else if (method === "GET") {
      await route.fulfill({
        json: {
          id: "cfg-dataset",
          itemId: "dataset-1",
          kind: "dataset",
          config: { kind: "dataset", dataset: storedDatasetConfig },
        },
      });
    } else {
      await route.fallback();
    }
  });

  await page.route("https://core.test/configs/by-item/pipeline-vq1", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        id: "cfg-pipeline-vq",
        itemId: "pipeline-vq1",
        kind: "pipeline",
        config: { kind: "pipeline", pipeline: storedPipeline },
      },
    });
  });

  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        pk: "dataset-1",
        resourceType: "dataset",
        title: "E2E requête visuelle",
        abstract: "",
        owner: "mockuser",
        thumbnailUrl: null,
        date: "2026-01-01",
        configId: "cfg-dataset",
        isPublished: false,
        keywords: [],
      },
    });
  });

  await page.route("https://core.test/datasets/dataset-1/alerts", async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.route("https://core.test/pipelines/pipeline-vq1/run", async (route) => {
    await route.fulfill({ status: 202, json: { runId: "run-1" } });
  });

  let runPolls = 0;
  await page.route("https://core.test/pipelines/pipeline-vq1/runs", async (route) => {
    runPolls += 1;
    const status = runPolls < 2 ? "running" : "succeeded";
    await route.fulfill({
      json: [
        {
          id: "run-1",
          status,
          startedAt: "2026-08-13T10:00:00Z",
          finishedAt: status === "succeeded" ? "2026-08-13T10:00:02Z" : null,
          error: null,
          nodeStats: {},
        },
      ],
    });
  });
}

test("crée un dataset par requête visuelle avec filtre, puis le rouvre pour vérifier la requête", async ({
  page,
}) => {
  await mockCore(page);
  await mockVisualQueryFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("visual-query");
  await dialog.getByLabel("Titre").fill("E2E requête visuelle");
  await dialog.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/datasets\/visual-query\/new/);
  await page.getByLabel("Collection de base").selectOption("incidents");
  await page.getByRole("button", { name: "Ajouter un filtre" }).click();
  await page.getByLabel("Valeur du filtre 1").fill("1");
  await page.getByRole("button", { name: "Créer" }).click();

  // Le wizard poll désormais lui-même (indépendamment de `PipelineRunPanel`,
  // qui reste affiché pour l'historique/relance manuelle mais ne pilote plus
  // la redirection) : aucun clic manuel n'est nécessaire pour avancer, même
  // si le premier statut lu est "running" (mock `runPolls < 2`). L'écran
  // transitoire "Exécution de la requête…" n'est pas asserté ici : le poll
  // est maintenant assez rapide (mock local, latence réseau nulle) pour que
  // la redirection ait déjà eu lieu avant que Playwright ne l'observe.
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit/, { timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Modifier la requête" })).toBeVisible();

  await page.getByRole("button", { name: "Modifier la requête" }).click();
  await expect(page).toHaveURL(/\/datasets\/visual-query\/pipeline-vq1\/edit/);
  await expect(page.getByLabel("Valeur du filtre 1")).toHaveValue("1");
});
