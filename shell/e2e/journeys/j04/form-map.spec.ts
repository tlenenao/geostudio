import { test, expect } from "@playwright/test";
import { getSeed, baseApp, grid } from "./seed";
import { openBuilder, openRuntime, fixme } from "./helpers";

test.setTimeout(90_000);

test.describe("j04 formulaire, carte, story", () => {
  test("formulaire : charger les champs depuis le schéma de la collection puis enregistrer la config", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp("form-schema", baseApp());
    await openBuilder(page, id);
    await page.getByRole("button", { name: "Formulaire", exact: true }).click();
    await page.getByRole("button", { name: "Ajouter une source" }).click();
    await page
      .getByLabel(/^Collection de la source/)
      .first()
      .fill(s.colId);
    await page.getByLabel("Source de données").first().selectOption({ index: 1 });
    await page.getByRole("button", { name: "Charger les champs du schéma" }).click();
    await page.waitForTimeout(1500);
    const labels = await page.getByText("Requis", { exact: true }).count();
    expect(labels).toBeGreaterThanOrEqual(3);
    await page.getByRole("complementary").getByRole("button", { name: "Enregistrer" }).click();
    await page.waitForTimeout(1500);
    const saved = await s.creator.get(`/v1/configs/by-item/${id}`);
    const form = saved.body.config.layout.items.find(
      (i: { widget: string }) => i.widget === "form",
    );
    expect(form.props.fields.map((f: { name: string }) => f.name)).toEqual(
      expect.arrayContaining(["nom", "surface", "statut"]),
    );
  });

  test("formulaire au runtime : champ requis vide est refusé côté client avec un message", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "form-required",
      baseApp({
        dataSources: [{ id: "s1", type: "features", service: "core", layer: s.colId, query: {} }],
        layout: grid([
          {
            id: "fm",
            widget: "form",
            x: 0,
            y: 0,
            w: 6,
            h: 8,
            props: {
              dataSourceId: "s1",
              submitLabel: "Envoyer",
              geometryType: null,
              fields: [{ name: "nom", label: "Nom", type: "string", required: true }],
            },
          },
        ]),
      }),
    );
    await openRuntime(page, `/apps/${id}`);
    await page.getByRole("button", { name: "Envoyer" }).click();
    await expect(page.getByText(/obligatoire|requis/i).first()).toBeVisible();
  });

  // À basculer en test() après rejeu sous --verify.
  // j04-010 : le refus serveur est simulé (sa cause réelle, j02-003, est corrigée) pour prouver
  // le retour utilisateur ; le formulaire affiche l'alerte générique (P10.02).
  fixme(
    "j04-010 : un refus serveur portant sur un champ absent du formulaire est signalé à l'utilisateur",
    async ({ page }) => {
      const s = await getSeed();
      const id = await s.mkApp(
        "form-submit",
        baseApp({
          dataSources: [{ id: "s1", type: "features", service: "core", layer: s.colId, query: {} }],
          layout: grid([
            {
              id: "fm",
              widget: "form",
              x: 0,
              y: 0,
              w: 6,
              h: 8,
              props: {
                dataSourceId: "s1",
                submitLabel: "Envoyer",
                geometryType: null,
                fields: [{ name: "nom", label: "Nom", type: "string" }],
              },
            },
          ]),
        }),
      );
      await page.route("**/collections/*/items", (route) =>
        route.request().method() === "POST"
          ? route.fulfill({
              status: 400,
              contentType: "application/json",
              body: JSON.stringify({
                errors: [{ field: "champ_cache", code: "missing_required", message: "requis" }],
              }),
            })
          : route.fallback(),
      );
      await openRuntime(page, `/apps/${id}`);
      await page.getByLabel("Nom").fill("Delta");
      await page.getByRole("button", { name: "Envoyer" }).click();
      await expect(
        page.getByRole("alert").filter({ hasText: "Échec de l'enregistrement." }),
      ).toBeVisible();
    },
  );

  test("carte multi-couches : le widget carte avec deux couches additionnelles se rend sans erreur de widget", async ({
    page,
  }) => {
    const s = await getSeed();
    const mk = (n: string) => ({
      id: n,
      title: n,
      kind: "vector",
      collectionId: s.colId,
      geometryKind: "point",
      pkColumn: "id",
      tilesUrl: `http://localhost:8200/v1/collections/${s.colId}/tiles/{z}/{x}/{y}.mvt`,
      sourceLayer: s.colId,
      renderAs: "circle",
      visible: true,
    });
    const id = await s.mkApp(
      "carte-multi",
      baseApp({
        dataSources: [{ id: "s1", type: "features", service: "core", layer: s.colId, query: {} }],
        layout: grid([
          {
            id: "m",
            widget: "map",
            x: 0,
            y: 0,
            w: 8,
            h: 8,
            props: { dataSourceId: "s1", layers: [mk("l1"), mk("l2")] },
          },
        ]),
      }),
    );
    await openRuntime(page, `/apps/${id}`);
    await page.waitForTimeout(3000);
    await expect(page.getByText("Erreur du widget")).toHaveCount(0);
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  });
});
