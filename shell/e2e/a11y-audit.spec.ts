// SPDX-License-Identifier: Apache-2.0
//
// Audit d'accessibilité automatisé (axe-core), SP-57a volet 5.2 (GAP-14).
// Échantillon élargi (REV-178) : les 9 pages d'origine, une par famille de
// layout du triptyque (SP-30) + une page publique, complétées par 8 pages
// jusqu'ici hors échantillon — l'édition d'item par type non encore
// couverte (Dataset + Alertes, Rapport, Requête visuelle — Pipeline l'était
// déjà via PipelineBuilderPage) et les familles Administration restées
// hors échantillon (Extensions, Infrastructure, Rôles, Utilisateurs,
// Moissonnage — seule CollectionsAdminPage l'était). Reste un choix de
// portée assumé, pas l'exhaustivité du catalogue de routes (spec §3.2,
// REV-178) : ~17 pages sur >100 routes. Chaque violation critical/serious
// non exclue explicitement ci-dessous doit être corrigée, jamais
// silencieusement ignorée.
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { ADMIN_ME, ANALYST_ME, mockCollection, mockCore, mockItemDetail, mockMe } from "./mocks";

// Violations `moderate`/`minor`, ou `critical`/`serious` dont la correction
// dépasserait le budget de cette tâche (spec §3.3) — chaque entrée nomme la
// règle axe-core, un extrait de sélecteur cible (sous-chaîne, pas un match
// exact — axe-core émet des sélecteurs CSS complets), et la raison. Jamais
// une désactivation globale de la règle : seules ces occurrences précises
// sont filtrées.
interface Exclusion {
  // Page où l'exclusion s'applique — omis (undefined) pour une exclusion
  // valable sur toutes les pages de l'échantillon (ex. le chrome partagé
  // StatusBar/TriptychLayout, rendu identique partout).
  page?: string;
  rule: string;
  // Sous-chaîne cherchée dans failureSummary/html du nœud (axe-core) — pas
  // un sélecteur CSS : le même token de couleur ressort sous des sélecteurs
  // différents selon la page (StatusBar, LayersPanel, …), le identifier par
  // sa valeur de couleur plutôt que par un chemin DOM particulier.
  nodeIncludes: string;
  reason: string;
}

const EXCLUSIONS: Exclusion[] = [
  {
    rule: "color-contrast",
    nodeIncludes: "foreground color: #6e8087",
    reason:
      "Token --gs-ink-3 (le plus atténué de l'ambiance) : 3.65:1 sur fond " +
      "--gs-background, sous le seuil AA de 4.5:1 pour du texte normal. " +
      'Ressort sur plusieurs pages (StatusBar "v0.1.0 · demo", compteur ' +
      '"N entités" de LayersPanel, …) car c\'est le même token de couleur, ' +
      "réutilisé par ~20 fichiers (Combobox, Chip, Toast, Breadcrumb, …). " +
      "Retoucher sa valeur corrigerait ces occurrences mais changerait " +
      "l'ambiance visuelle de tout le shell, hors budget de ce SP (spec " +
      "SP-57a §3.3). Suivi : REV-176 (docs/revue/2026-09-04-backlog.md).",
  },
];

async function runAxeAudit(page: Page, pageName: string) {
  const results = await new AxeBuilder({ page }).analyze();
  const relevant = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  const unexcluded = relevant.filter((v) => {
    const excludedForThisPage = EXCLUSIONS.filter(
      (e) => (e.page === undefined || e.page === pageName) && e.rule === v.id,
    );
    if (excludedForThisPage.length === 0) return true;
    const remainingNodes = v.nodes.filter((n) => {
      const haystack = `${n.failureSummary ?? ""} ${n.html}`;
      return !excludedForThisPage.some((e) => haystack.includes(e.nodeIncludes));
    });
    if (remainingNodes.length > 0) {
      v.nodes = remainingNodes;
      return true;
    }
    return false;
  });

  expect(
    unexcluded,
    unexcluded
      .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.map((n) => n.target).join(" | ")}`)
      .join("\n"),
  ).toEqual([]);
}

test.describe("audit d'accessibilité (axe-core)", () => {
  test("CatalogPage (liste/recherche, layout triptyque standard)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
    await runAxeAudit(page, "CatalogPage");
  });

  test("ItemDetailPage (fiche détail)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/items/1");
    await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
    await runAxeAudit(page, "ItemDetailPage");
  });

  test("MapEditorPage (éditeur carte — widgets carte, panneaux de symbologie)", async ({
    page,
  }) => {
    await mockCore(page);
    await page.goto("/maps/map-1");
    await expect(page.locator("canvas.maplibregl-canvas").first()).toBeVisible();
    await runAxeAudit(page, "MapEditorPage");
  });

  test("AppBuilderPage (canvas builder — la surface la plus dense en contrôles interactifs)", async ({
    page,
  }) => {
    await mockCore(page);
    await page.goto("/apps/1/edit");
    await expect(page.getByText("Titre version 2")).toBeVisible();
    await runAxeAudit(page, "AppBuilderPage");
  });

  test("PipelineBuilderPage (canvas DAG, un autre type de canvas interactif)", async ({ page }) => {
    await mockCore(page);
    await page.route("https://core.test/v1/instance", async (route) => {
      await route.fulfill({ json: { readOnly: false, etlEnabled: true } });
    });
    await page.route("https://core.test/v1/pipelines/ops", async (route) => {
      await route.fulfill({
        json: {
          "reader.collection": {
            kind: "reader",
            paramsSchema: {
              properties: { collectionId: { type: "string", format: "collection-id" } },
              required: ["collectionId"],
            },
          },
          "writer.collection": {
            kind: "writer",
            paramsSchema: {
              properties: { collectionId: { type: "string", format: "collection-id" } },
              required: ["collectionId"],
            },
          },
        },
      });
    });
    await page.route("https://core.test/v1/collections*", async (route) => {
      await route.fulfill({
        json: {
          collections: [mockCollection({ id: "villes", title: "Villes", tableName: "villes" })],
        },
      });
    });
    await page.route("https://core.test/v1/configs/by-item/pipe-1", async (route) => {
      await route.fulfill({
        json: {
          id: "cfg-pipe1",
          itemId: "pipe-1",
          kind: "pipeline",
          config: {
            kind: "pipeline",
            pipeline: {
              nodes: [
                {
                  id: "r1",
                  kind: "reader",
                  op: "reader.collection",
                  x: 0,
                  y: 0,
                  params: { collectionId: "villes" },
                  title: "reader.collection",
                },
                {
                  id: "w1",
                  kind: "writer",
                  op: "writer.collection",
                  x: 300,
                  y: 0,
                  params: { collectionId: "villes" },
                  title: "writer.collection",
                },
              ],
              edges: [{ id: "e1", from: "r1", to: "w1" }],
            },
          },
        },
      });
    });
    await page.goto("/pipelines/pipe-1/edit");
    await expect(page.locator(".react-flow__node").first()).toBeVisible();
    await runAxeAudit(page, "PipelineBuilderPage");
  });

  test("CollectionsAdminPage (famille Administration)", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, ADMIN_ME);
    await page.route("https://core.test/v1/collections/candidates", async (route) => {
      await route.fulfill({ json: { candidates: [] } });
    });
    await page.route("https://core.test/v1/collections*", async (route) => {
      await route.fulfill({ json: { collections: [mockCollection()] } });
    });
    await page.goto("/admin/collections");
    await expect(page.getByText("Points d'intérêt")).toBeVisible();
    await runAxeAudit(page, "CollectionsAdminPage");
  });

  test("SqlLabPage (famille Analytique)", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, ANALYST_ME);
    await page.goto("/analytics/sql");
    await expect(page.getByRole("heading", { name: "SQL Lab" })).toBeVisible();
    await runAxeAudit(page, "SqlLabPage");
  });

  test("SitePublicPage (page publique, hors authentification)", async ({ page }) => {
    await mockCore(page);
    // Consultation publique directe — pas de flux création+publication
    // (cf. sites-portal-shell.spec.ts) : ces deux routes, enregistrées
    // après mockCore(page), gagnent sur son propre gestionnaire par défaut
    // (non publié) pour ce seul test.
    await page.route("https://core.test/v1/public/sites/*", async (route) => {
      await route.fulfill({
        json: {
          pk: "site-1",
          resourceType: "site",
          slug: "mon-portail",
          title: "Mon Portail",
          abstract: "",
          owner: "mockuser",
          thumbnailUrl: null,
          date: "2026-01-01",
          configId: null,
          isPublished: true,
        },
      });
    });
    await page.route("https://core.test/v1/public/configs/by-item/site-1", async (route) => {
      await route.fulfill({
        json: {
          id: "cfg-site",
          itemId: "site-1",
          kind: "site",
          version: 1,
          config: {
            version: 1,
            kind: "site",
            theme: {},
            dataSources: [],
            layout: {
              type: "grid",
              breakpoints: {},
              items: [
                {
                  id: "t1",
                  widget: "text",
                  x: 0,
                  y: 0,
                  w: 4,
                  h: 2,
                  props: { text: "Bienvenue sur le portail" },
                },
              ],
            },
            messages: [],
            pages: [],
          },
        },
      });
    });
    await page.goto("/sites/mon-portail");
    await expect(page.getByText("Bienvenue sur le portail")).toBeVisible();
    await runAxeAudit(page, "SitePublicPage");
  });

  test("UsagePage (tableaux/listes denses)", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, ADMIN_ME);
    await page.route("https://core.test/v1/usage/tasks**", async (route) => {
      await route.fulfill({
        json: {
          tasks: [
            {
              id: 1,
              actorId: "u-mock",
              action: "pipeline.run",
              objectType: "pipeline",
              objectId: "p1",
              createdAt: "2026-09-01T00:00:00Z",
            },
          ],
          total: 1,
          page: 1,
          pageSize: 50,
        },
      });
    });
    await page.route("https://core.test/v1/usage/summary**", async (route) => {
      await route.fulfill({
        json: { byActor: [{ actorId: "u-mock", count: 1 }], byResource: [] },
      });
    });
    await page.goto("/tasks");
    await expect(page.getByText("Mes tâches récentes")).toBeVisible();
    await runAxeAudit(page, "UsagePage");
  });

  // --- Échantillon élargi (REV-178) ------------------------------------

  test("DatasetEditPage (édition d'un dataset partagé, alertes incluses)", async ({ page }) => {
    await mockCore(page);
    // Host-scoped (jamais "**/items*") : le shell a lui-même une route
    // client "/items/dataset-a11y" via ItemDetailPage — même rationale que
    // "/items/1"/"/items/9" documentée dans mocks.ts.
    await page.route("https://core.test/v1/items/dataset-a11y", async (route) => {
      await route.fulfill({
        json: {
          pk: "dataset-a11y",
          resourceType: "dataset",
          title: "Points d'intérêt (partagé)",
          abstract: "",
          owner: "mockuser",
          thumbnailUrl: null,
          date: "2026-01-01",
          configId: "cfg-dataset-a11y",
          isPublished: false,
          keywords: [],
          permissions: { read: true, write: true, delete: true, share: true },
        },
      });
    });
    await page.route("https://core.test/v1/configs/by-item/dataset-a11y", async (route) => {
      await route.fulfill({
        json: {
          id: "cfg-dataset-a11y",
          itemId: "dataset-a11y",
          kind: "dataset",
          config: {
            kind: "dataset",
            // "incidents" : collection dont le schéma est déjà mocké par
            // défaut dans mockCore() (mocks.ts) — pas besoin d'un mock de
            // schéma dédié.
            dataset: { source: "collection", collectionId: "incidents", columns: {} },
          },
        },
      });
    });
    // AlertRuleEditor (section « Alertes » de ce panneau, SP-16b) — liste
    // vide, pas de règle existante à afficher.
    await page.route("https://core.test/v1/datasets/dataset-a11y/alerts", async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.route("https://core.test/v1/metadata-catalog", async (route) => {
      await route.fulfill({ json: { licenses: [], languages: [] } });
    });
    await page.goto("/datasets/dataset-a11y/edit");
    await expect(
      page.getByRole("heading", { name: "Dataset partagé — Points d'intérêt (partagé)" }),
    ).toBeVisible();
    await runAxeAudit(page, "DatasetEditPage");
  });

  test("ReportEditPage (édition d'un rapport planifié)", async ({ page }) => {
    await mockCore(page);
    await mockItemDetail(page, "report-a11y", {
      resourceType: "report",
      title: "Rapport hebdomadaire",
    });
    await page.route("https://core.test/v1/configs/by-item/report-a11y", async (route) => {
      await route.fulfill({
        json: {
          id: "cfg-report-a11y",
          itemId: "report-a11y",
          kind: "report",
          config: {
            kind: "report",
            report: {
              bookmarkItemId: "bookmark-1",
              refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
              channels: [{ kind: "webhook", url: "https://example.test/hook" }],
            },
          },
        },
      });
    });
    await page.route("https://core.test/v1/reports/report-a11y/runs*", async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.goto("/reports/report-a11y/edit");
    await expect(page.getByRole("heading", { name: "Modifier le rapport planifié" })).toBeVisible();
    await runAxeAudit(page, "ReportEditPage");
  });

  test("VisualQueryWizardPage (assistant Filtrer→Joindre→Résumer, brouillon)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/datasets/visual-query/new");
    await expect(page.getByRole("heading", { name: "Nouvelle requête visuelle" })).toBeVisible();
    await runAxeAudit(page, "VisualQueryWizardPage");
  });

  test("AdminExtensionsPage (famille Administration — extensions)", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, ADMIN_ME);
    // Host-scoped — même rationale que admin-extensions.spec.ts : la route
    // client "/admin/extensions" collisionnerait avec un glob non scopé.
    await page.route("https://core.test/v1/extensions**", async (route) => {
      if (route.request().method() === "PATCH") {
        await route.fulfill({ json: { id: "acme.gauge", enabled: false } });
        return;
      }
      await route.fulfill({
        json: {
          extensions: [
            {
              id: "acme.gauge",
              tag: "gauge-extension-widget",
              label: "Jauge (extension)",
              moduleUrl: "https://example.com/gauge.js",
              props: [],
              events: [],
              actions: [],
              defaultSize: { w: 2, h: 2 },
              permissions: { collections: "all" },
              enabled: true,
            },
          ],
        },
      });
    });
    await page.goto("/admin/extensions");
    await expect(page.getByRole("heading", { name: "Extensions" })).toBeVisible();
    await runAxeAudit(page, "AdminExtensionsPage");
  });

  test("AdminInfrastructurePage (famille Administration — outils protégés)", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, ADMIN_ME);
    await page.route("https://core.test/v1/instance", async (route) => {
      await route.fulfill({ json: { readOnly: false, adminToolsEnabled: true } });
    });
    await page.goto("/admin/infrastructure");
    await expect(page.getByRole("heading", { name: "Outils d'infrastructure" })).toBeVisible();
    await runAxeAudit(page, "AdminInfrastructurePage");
  });

  test("RolesAdminPage (famille Administration — rôles à privilèges)", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, ADMIN_ME);
    await page.route("https://core.test/v1/roles", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({
        json: [
          {
            id: "role-admin",
            name: "Administrateur",
            slug: "admin",
            isBuiltIn: true,
            privileges: ["admin.roles.manage"],
          },
          {
            id: "role-1",
            name: "Support",
            slug: "support",
            isBuiltIn: false,
            privileges: ["data.view"],
          },
        ],
      });
    });
    await page.goto("/admin/roles");
    await expect(page.getByRole("heading", { name: "Rôles" })).toBeVisible();
    await runAxeAudit(page, "RolesAdminPage");
  });

  test("UsersAdminPage (famille Administration — utilisateurs)", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, ADMIN_ME);
    await page.route("https://core.test/v1/roles", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({
        json: [
          { id: "role-admin", name: "Administrateur", slug: "admin", isBuiltIn: true },
          { id: "role-reader", name: "Lecteur", slug: "reader", isBuiltIn: true },
        ],
      });
    });
    await page.route("https://core.test/v1/users**", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({
        json: {
          users: [
            { id: "u1", username: "alice", roleSlug: "admin" },
            { id: "u2", username: "bob", roleSlug: "reader" },
          ],
          total: 2,
        },
      });
    });
    await page.goto("/admin/users");
    await expect(page.getByRole("heading", { name: "Utilisateurs" })).toBeVisible();
    await runAxeAudit(page, "UsersAdminPage");
  });

  test("HarvestSourcesAdminPage (famille Administration — moissonnage)", async ({ page }) => {
    await mockCore(page);
    await mockMe(page, ADMIN_ME);
    await page.route("https://core.test/v1/harvest/sources", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({ json: { sources: [] } });
    });
    await page.goto("/admin/harvest");
    await expect(page.getByRole("heading", { name: "Moissonnage" })).toBeVisible();
    await runAxeAudit(page, "HarvestSourcesAdminPage");
  });
});
