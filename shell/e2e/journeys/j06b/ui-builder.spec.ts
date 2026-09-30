import { test, expect } from "@playwright/test";
import { apiFor } from "./seeds";
import { stamp } from "../_fixtures/env";
import {
  createPipeline,
  edge,
  ensureExportsBucket,
  exportWriter,
  getPlainSeed,
  openAs,
  reader,
  spaGoto,
} from "./helpers";

const tag = stamp("j06b");

test.describe("j06b builder de pipeline (UI réelle)", () => {
  test("palette 57 op + recherche, construction glisser-déposer, connexion, annuler/rétablir, zone, enregistrement persistant", async ({
    page,
  }) => {
    const seed = await getPlainSeed();
    await openAs(page, "creator");
    await page.getByRole("button", { name: "Nouveau", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
    await dialog.getByLabel("Type").selectOption("pipeline");
    await dialog.getByLabel("Titre").fill(`${tag}-ui`);
    await dialog.getByRole("button", { name: "Créer" }).click();
    await expect(page).toHaveURL(/\/pipelines\/new$/);

    // Palette : 57 opérations (sections permanentes), la recherche filtre.
    const items = page.locator(".cursor-grab");
    await expect(items.first()).toBeVisible();
    expect(await items.count()).toBe(57);
    const search = page.getByRole("searchbox", { name: "Rechercher une opération" });
    await search.fill("buffer");
    await expect(items).toHaveCount(1);
    await search.fill("zzzz-rien");
    await search.fill("");
    await expect(items).toHaveCount(57);

    const canvas = page.locator(".react-flow__pane");
    const palette = (op: string) => page.locator(".cursor-grab", { hasText: op }).last();
    // La palette est longue et défile : on isole l'op par la recherche avant de la glisser.
    await search.fill("reader.collection");
    await palette("reader.collection").dragTo(canvas, { targetPosition: { x: 0, y: 50 } });
    await search.fill("writer.export");
    await palette("writer.export").dragTo(canvas, { targetPosition: { x: 0, y: 250 } });
    await search.fill("");
    const nodes = page.locator(".react-flow__node");
    await expect(nodes).toHaveCount(2);
    await nodes
      .nth(0)
      .locator(".react-flow__handle-right")
      .dragTo(nodes.nth(1).locator(".react-flow__handle-left"));
    await expect(page.locator(".react-flow__edge")).toHaveCount(1);

    // Annuler / Rétablir sur la connexion.
    await page.getByRole("button", { name: "Annuler" }).click();
    await expect(page.locator(".react-flow__edge")).toHaveCount(0);
    await page.getByRole("button", { name: "Rétablir" }).click();
    await expect(page.locator(".react-flow__edge")).toHaveCount(1);

    await nodes.nth(0).click();
    await page.getByLabel("collectionId").selectOption(seed.collection);
    await nodes.nth(1).click();
    await page.getByLabel("format").selectOption("csv");
    await page.getByLabel("key").fill(`j06b/${tag}-ui.csv`);

    await page.getByRole("button", { name: "Ajouter une zone" }).click();
    await expect(page.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(page).toHaveURL(/\/pipelines\/[0-9a-f]{32}\/edit$/);

    // Un rechargement complet perd le chemin après la reconnexion OIDC (j02-004) : on repasse par le routeur.
    const path = new URL(page.url()).pathname;
    await spaGoto(page, "/");
    await spaGoto(page, path);
    await expect(page.locator(".react-flow__node")).toHaveCount(3);
    await expect(page.locator(".react-flow__edge")).toHaveCount(1);
    await page.locator(".react-flow__node").nth(1).click(); // nth(0) = la zone annotée
    await expect(page.getByLabel("key")).toHaveValue(`j06b/${tag}-ui.csv`);
  });

  test("pipeline existant : aperçu tabulaire du nœud source, jeton de webhook montré une fois puis révoqué", async ({
    page,
  }) => {
    ensureExportsBucket();
    const seed = await getPlainSeed();
    const creator = await apiFor("creator");
    const r = { ...reader(seed.collection), x: 0, y: 0 };
    const w = { ...exportWriter(`j06b/${tag}-ui-tok.csv`), x: 300, y: 0 };
    const p = await createPipeline(creator, `${tag}-ui-tok`, [r, w], [edge("r", "w")]);
    await openAs(page, "creator");
    await spaGoto(page, `/pipelines/${p.itemId}/edit`);
    await page.locator(".react-flow__node").first().click();
    await expect(page.getByText("Lignes 1–6 sur 6")).toBeVisible();

    await page.getByRole("button", { name: "Générer un jeton" }).click();
    const status = page.getByRole("status").filter({ hasText: "ne sera plus jamais affiché" });
    await expect(status).toBeVisible();
    const token = (await status.locator("p").first().innerText()).trim();
    expect(token.length).toBeGreaterThanOrEqual(32);
    const listed = await creator.get(`/v1/pipelines/${p.itemId}/webhook-tokens`);
    expect(listed.body).toHaveLength(1);
    await page.getByRole("button", { name: /^Révoquer / }).click();
    await expect
      .poll(async () => (await creator.get(`/v1/pipelines/${p.itemId}/webhook-tokens`)).body.length)
      .toBe(0);
  });

  // Findings j06b-001 (run depuis l'UI), j06b-014 (recherche sans résultat), j06b-015 (format),
  // j06b-016 (commande webhook affichée) : assertions souples, un seul parcours.
  test.fixme("j06b-001 / j06b-014 / j06b-015 / j06b-016 : finitions du builder", async ({
    page,
  }) => {
    ensureExportsBucket();
    const seed = await getPlainSeed();
    const creator = await apiFor("creator");
    const r = { ...reader(seed.collection), x: 0, y: 0 };
    const w = { ...exportWriter(`j06b/${tag}-ui-fin.csv`), x: 300, y: 0 };
    const p = await createPipeline(creator, `${tag}-ui-fin`, [r, w], [edge("r", "w")]);
    await openAs(page, "creator");
    await spaGoto(page, `/pipelines/${p.itemId}/edit`);

    // j06b-014 : une recherche sans résultat affiche un état vide explicite.
    await page.getByRole("searchbox", { name: "Rechercher une opération" }).fill("zzzz-rien");
    await expect.soft(page.getByText(/aucun(e)? (résultat|opération)/i)).toBeVisible();
    await page.getByRole("searchbox", { name: "Rechercher une opération" }).fill("");

    // j06b-015 : un writer.export fraîchement déposé affiche « geojson » dans le select « format »
    // alors que la valeur n'est pas posée (« format est requis. » s'affiche sous le select).
    const search = page.getByRole("searchbox", { name: "Rechercher une opération" });
    await search.fill("writer.export");
    await page
      .locator(".cursor-grab", { hasText: "writer.export" })
      .last()
      .dragTo(page.locator(".react-flow__pane"), { targetPosition: { x: 0, y: 250 } });
    await search.fill("");
    await page.locator(".react-flow__node").last().click();
    await expect(page.getByLabel("format")).toBeVisible();
    await expect.soft(page.getByText("format est requis.")).toHaveCount(0);

    // j06b-016 : la commande d'appel webhook affichée est copiable (URL réelle, avec /v1).
    await page.getByRole("button", { name: "Générer un jeton" }).click();
    const cmd = page.getByRole("status").filter({ hasText: "ne sera plus jamais affiché" });
    await expect.soft(cmd).not.toContainText("{coreBaseUrl}");
    await expect.soft(cmd).toContainText("/v1/pipelines/");

    // j06b-001 : « Exécuter » mène à un statut terminal (le run est créé mais jamais déféré).
    await page.getByRole("button", { name: "Exécuter" }).click();
    await expect(page.getByText("Terminé")).toBeVisible({ timeout: 20_000 });
  });
});
