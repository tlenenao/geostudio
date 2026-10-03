/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { CORE_URL, SHELL_URL, stamp } from "../_fixtures/env";
import { openAs, spaGoto } from "../j06/helpers";
import {
  apiFor,
  createSite,
  getDatasetSeed,
  richItem,
  siteConfig,
  storyConfig,
  XSS_MARKDOWN,
  type Api,
} from "./seed";

test.setTimeout(90_000);
const tag = stamp("j10");
let creator: Api;

test.beforeAll(async () => {
  creator = await apiFor("creator");
});

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

async function uploadThumbnail(pk: string): Promise<void> {
  const { token } = await import("../j03/api");
  const tok = await token("creator");
  const form = new FormData();
  form.append("file", new Blob([PNG], { type: "image/png" }), "t.png");
  const r = await fetch(`${CORE_URL}/v1/items/${pk}/thumbnail`, {
    method: "POST",
    headers: { authorization: `Bearer ${tok}` },
    body: form,
  });
  expect(r.status).toBe(204);
}

test.describe("j10 sites publics : rendu anonyme", () => {
  test("le Markdown d'une section riche est assaini et le titre de l'onglet suit le site", async ({
    page,
  }) => {
    const s = await createSite(creator, `${tag}-md`, siteConfig([richItem("r", XSS_MARKDOWN)]), {
      publish: true,
    });
    await creator.send("PATCH", `/v1/items/${s.pk}`, { abstract: "Résumé du site" });
    let dialogs = 0;
    page.on("dialog", (d) => {
      dialogs += 1;
      void d.dismiss();
    });
    await page.goto(`/sites/${s.slug}`);
    await expect(page.getByRole("heading", { name: "Titre du site" })).toBeVisible();
    await expect(page.locator("strong", { hasText: "gras" })).toBeVisible();
    expect(
      await page.evaluate(() => (window as unknown as { __xss?: number }).__xss),
    ).toBeUndefined();
    expect(dialogs).toBe(0);
    expect(await page.locator(".prose script").count()).toBe(0);
    expect(await page.locator(".prose [onerror]").count()).toBe(0);
    expect(await page.locator('.prose a[href^="javascript"]').count()).toBe(0);
    await expect(page).toHaveTitle(`${tag}-md`);
    await expect(page.locator('meta[name="description"]')).toHaveAttribute(
      "content",
      "Résumé du site",
    );
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      `${SHELL_URL}/sites/${s.slug}`,
    );
  });

  test("un slug inconnu affiche « Page introuvable. » sans exposer de détail", async ({ page }) => {
    await page.goto(`/sites/${tag}-n-existe-pas`);
    await expect(page.getByRole("alert")).toHaveText("Page introuvable.");
  });

  test("un site non publié est introuvable, même pour son propriétaire connecté", async ({
    page,
  }) => {
    const s = await createSite(
      creator,
      `${tag}-brouillon`,
      siteConfig([richItem("r", "# secret")]),
    );
    await openAs(page, "creator");
    await spaGoto(page, `/sites/${s.slug}`);
    await expect(page.getByRole("alert")).toHaveText("Page introuvable.");
    await expect(page.getByRole("heading", { name: "secret" })).toHaveCount(0);
  });

  test("la fiche jeu de données d'un site affiche titre, compte et téléchargements, puis mène à la page publique", async ({
    page,
  }) => {
    const ds = await getDatasetSeed();
    const cfg = siteConfig(
      [{ id: "dc", widget: "datasetCard", x: 0, y: 0, w: 6, h: 6, props: { dataSourceId: "d1" } }],
      {
        dataSources: [
          { id: "d1", type: "features", service: "core", layer: ds.collectionId, query: {} },
        ],
      },
    );
    const s = await createSite(creator, `${tag}-card`, cfg, { publish: true });
    await page.goto(`/sites/${s.slug}`);
    await expect(page.getByRole("heading", { name: `${ds.tag}-col` })).toBeVisible();
    await expect(page.getByText("3 entités")).toBeVisible();
    await expect(page.getByRole("link", { name: /GeoJSON/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /CSV/ })).toBeEnabled();
    await page.getByRole("link", { name: "Voir le jeu de données" }).click();
    await expect(page).toHaveURL(new RegExp(`/public/datasets/${ds.collectionId}$`));
    await expect(page.getByRole("heading", { name: `${ds.tag}-col` })).toBeVisible();
    await expect(page.getByRole("cell", { name: "A", exact: true })).toBeVisible();
  });

  test("la page publique d'un jeu de données non public est introuvable pour un anonyme", async ({
    page,
  }) => {
    const c = await creator.send("POST", "/v1/collections/empty", {
      title: `${tag}-privee`,
      columns: [{ name: "nom", sqlType: "text" }],
      geometryType: "Point",
      srid: 4326,
    });
    expect(c.status).toBe(201);
    await page.goto(`/public/datasets/${c.body.id}`);
    await expect(page.getByRole("alert")).toBeVisible();
  });

  test("la galerie liste les items publiés et pas les brouillons", async ({ page }) => {
    const pub = await createSite(creator, `${tag}-gal-pub`, siteConfig(), { publish: true });
    const draft = await createSite(creator, `${tag}-gal-draft`, siteConfig());
    const cfg = siteConfig([
      { id: "g", widget: "gallery", x: 0, y: 0, w: 12, h: 6, props: { type: "site", limit: 100 } },
    ]);
    const host = await createSite(creator, `${tag}-gal`, cfg, { publish: true });
    await page.goto(`/sites/${host.slug}`);
    await expect(page.getByRole("heading", { name: `${tag}-gal-pub` })).toBeVisible();
    await expect(page.getByRole("heading", { name: `${tag}-gal-draft` })).toHaveCount(0);
    await page.getByRole("link", { name: new RegExp(`${tag}-gal-pub`) }).click();
    await expect(page).toHaveURL(new RegExp(`/public/items/${pub.pk}$`));
    void draft;
  });

  // FINDING j10-003 : les vignettes de la galerie pointent vers une route
  // authentifiée (et un chemin sans /v1) : image cassée pour un visiteur anonyme.
  test("j10-003 : la galerie publique affiche la vignette d'un item publié", async ({ page }) => {
    const pub = await createSite(creator, `${tag}-vign`, siteConfig(), { publish: true });
    await uploadThumbnail(pub.pk);
    const cfg = siteConfig([
      { id: "g", widget: "gallery", x: 0, y: 0, w: 12, h: 6, props: { type: "site", limit: 100 } },
    ]);
    const host = await createSite(creator, `${tag}-vign-host`, cfg, { publish: true });
    await page.goto(`/sites/${host.slug}`);
    const img = page.locator(`a[href="/public/items/${pub.pk}"] img`);
    await expect(img).toBeVisible();
    await expect
      .poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0))
      .toBe(true);
  });
});

test.describe("j10 sites : édition côté auteur", () => {
  test("créer un site depuis un modèle par l'UI, le publier, puis le voir en anonyme", async ({
    page,
    browser,
  }) => {
    await openAs(page, "creator");
    await page.getByRole("button", { name: "Nouveau" }).click();
    await page.locator("select").first().selectOption("site");
    await page.getByLabel("Modèle").selectOption({ label: "Portail de données" });
    await page.getByLabel("Titre").fill(`${tag} Portail UI`);
    await expect(page.getByLabel("Slug")).toHaveValue(new RegExp(`^${tag}-portail-ui$`));
    await page.getByRole("button", { name: "Créer" }).click();
    await page.waitForURL(/\/apps\/.*\/edit/);
    await expect(
      page.getByText("Explorez et téléchargez nos jeux de données ouverts."),
    ).toBeVisible();

    const pk = page.url().match(/\/apps\/([^/]+)\/edit/)![1];
    await creator.send("PATCH", `/v1/items/${pk}`, { isPublished: true });
    const slug = (await creator.get(`/v1/items/${pk}`)).body.slug as string;
    const anon = await browser.newPage({ baseURL: SHELL_URL });
    await anon.goto(`/sites/${slug}`);
    await expect(anon.getByRole("heading", { name: "Portail de données" })).toBeVisible();
    await anon.close();
  });

  // FINDING j10-005 : ni la fiche d'item, ni le builder n'affichent l'URL publique
  // /sites/{slug} ni ne permettent de modifier le slug après création.
  test("j10-005 : la fiche d'un site publié montre son URL publique", async ({ page }) => {
    const s = await createSite(creator, `${tag}-url`, siteConfig(), { publish: true });
    await openAs(page, "creator");
    await spaGoto(page, `/items/${s.pk}`);
    await expect(page.getByRole("heading", { name: `${tag}-url` })).toBeVisible();
    await expect(page.getByText(`/sites/${s.slug}`)).toBeVisible();
  });
});

test.describe("j10 sites publics : story et téléchargements", () => {
  test("un site publié en mode story offre la navigation par chapitre à un anonyme", async ({
    page,
  }) => {
    const cfg: any = { ...storyConfig(), kind: "site" };
    const s = await createSite(creator, `${tag}-site-story`, cfg, { publish: true });
    await page.goto(`/sites/${s.slug}`);
    await expect(page.getByText("Chapitre 1 / 3")).toBeVisible();
    await expect(page.getByText("Variable : etape-1")).toBeVisible();
    await page.getByRole("button", { name: /suivant/i }).click();
    await expect(page.getByRole("heading", { name: "Titre chapitre 2" })).toBeVisible();
    await expect(page.getByText("Variable : etape-2")).toBeVisible();
  });

  test("le lien de téléchargement GeoJSON d'une fiche publique fonctionne sans authentification", async ({
    page,
  }) => {
    const ds = await getDatasetSeed();
    const cfg = siteConfig(
      [{ id: "dc", widget: "datasetCard", x: 0, y: 0, w: 6, h: 6, props: { dataSourceId: "d1" } }],
      {
        dataSources: [
          { id: "d1", type: "features", service: "core", layer: ds.collectionId, query: {} },
        ],
      },
    );
    const s = await createSite(creator, `${tag}-dl`, cfg, { publish: true });
    await page.goto(`/sites/${s.slug}`);
    const href = await page.getByRole("link", { name: /GeoJSON/ }).getAttribute("href");
    expect(href).toBeTruthy();
    const res = await fetch(new URL(href!, CORE_URL).toString());
    expect(res.status).toBe(200);
    const body = (await res.json()) as { features: unknown[] };
    expect(body.features).toHaveLength(3);
  });
});
