import { test, expect } from "@playwright/test";
import { getSeed, baseApp, grid } from "./seed";
import { openBuilder, openRuntime } from "./helpers";

test.setTimeout(90_000);

const src = (id: string, layer: string) => ({
  id,
  type: "features",
  service: "core",
  layer,
  query: {},
});
const table = (ds: string, y = 0) => ({
  id: "tbl",
  widget: "table",
  x: 0,
  y,
  w: 8,
  h: 5,
  props: { dataSourceId: ds },
});

test.describe("j04 sources de données et widgets de données au runtime", () => {
  test("une Table liée à une collection affiche ses lignes au runtime", async ({ page }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "table-ok",
      baseApp({
        dataSources: [src("s1", s.colId)],
        layout: grid([table("s1")]),
      }),
    );
    await openRuntime(page, `/apps/${id}`);
    await expect(page.getByText("Alpha")).toBeVisible();
    await expect(page.getByText("Gamma")).toBeVisible();
  });

  test("source pointant vers une collection inexistante : message d'erreur de données, pas de blocage", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "table-ko",
      baseApp({
        dataSources: [src("s1", "collection-qui-n-existe-pas")],
        layout: grid([table("s1")]),
      }),
    );
    await openRuntime(page, `/apps/${id}`);
    await page.waitForTimeout(3000);
    await expect(page.getByText(/Chargement/)).toHaveCount(0);
  });

  test("j04-006 : un widget dont dataSourceId ne référence aucune source affiche un état explicite, pas « Chargement… » indéfiniment", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "table-dangling",
      baseApp({
        dataSources: [],
        layout: grid([table("s-supprimee")]),
      }),
    );
    await openRuntime(page, `/apps/${id}`);
    await page.waitForTimeout(4000);
    await expect(page.getByText(/Chargement/)).toHaveCount(0);
  });

  test("retirer une source de données signale ou délie les widgets qui l'utilisent (comportement conforme)", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "source-remove",
      baseApp({
        dataSources: [src("s1", s.colId)],
        layout: grid([table("s1")]),
      }),
    );
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Sélectionner widget-tbl" }).click();
    await page.getByRole("button", { name: `Retirer ${s.colId}` }).click();
    await page.waitForTimeout(800);
    // Attendu : la propriété du widget est remise à « Aucune » ou un avertissement apparaît.
    const hasWarning = (await page.getByRole("alert").count()) > 0;
    const bound = await page.getByLabel("Source de données").first().inputValue();
    expect(hasWarning || bound === "").toBe(true);
  });

  test("Filtre câblé sur une Table (setFilter) restreint les lignes au runtime", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "filter-table",
      baseApp({
        dataSources: [src("s1", s.colId)],
        layout: grid([
          { id: "f", widget: "filter", x: 0, y: 0, w: 6, h: 2, props: { field: "nom" } },
          table("s1", 2),
        ]),
        messages: [{ id: "m1", from: "f", event: "changed", to: "tbl", action: "setFilter" }],
      }),
    );
    await openRuntime(page, `/apps/${id}`);
    await expect(page.getByText("Beta")).toBeVisible();
    await page.getByLabel("Filtrer", { exact: true }).fill("Alpha");
    await page.waitForTimeout(2000);
    await expect(page.getByText("Beta")).toHaveCount(0);
    await expect(page.getByText("Alpha")).toBeVisible();
  });

  test("Filtre avec valeur sans correspondance : état vide explicite", async ({ page }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "filter-none",
      baseApp({
        dataSources: [src("s1", s.colId)],
        layout: grid([
          { id: "f", widget: "filter", x: 0, y: 0, w: 6, h: 2, props: { field: "nom" } },
          table("s1", 2),
        ]),
        messages: [{ id: "m1", from: "f", event: "changed", to: "tbl", action: "setFilter" }],
      }),
    );
    await openRuntime(page, `/apps/${id}`);
    await page.getByLabel("Filtrer", { exact: true }).fill("ZZZ-inexistant");
    await page.waitForTimeout(2000);
    await expect(page.getByText(/Aucune donnée|Aucun/i).first()).toBeVisible();
  });

  test("droits : app partagée au lecteur mais collection privée -> pas de fuite des lignes", async ({
    page,
  }) => {
    const s = await getSeed();
    const me = await s.reader.get("/v1/me");
    const g = await s.creator.send("POST", "/v1/groups", {
      name: `${s.tag}-g-${Date.now().toString(36)}`,
    });
    await s.creator.send("POST", `/v1/groups/${g.body.id}/members`, { userId: me.body.id });
    const id = await s.mkApp(
      "app-partagee-col-privee",
      baseApp({
        dataSources: [src("s1", s.colId)],
        layout: grid([table("s1")]),
      }),
    );
    const sh = await s.creator.send("PUT", `/v1/items/${id}/sharing`, {
      public: false,
      groups: [{ groupId: g.body.id, role: "viewer" }],
    });
    expect(sh.status).toBe(204);
    await openRuntime(page, `/apps/${id}`, "reader");
    await page.waitForTimeout(2500);
    await expect(page.getByText("Alpha")).toHaveCount(0);
  });
});
