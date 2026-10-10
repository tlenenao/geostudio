/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { openAs, spaGoto } from "../j06/helpers";
import { apiFor, storyConfig, type Api } from "./seed";

test.setTimeout(90_000);
const tag = stamp("j10");
let creator: Api;

test.beforeAll(async () => {
  creator = await apiFor("creator");
});

// Story de 3 chapitres dont le premier porte deux actions à l'entrée.
async function twoActionStory(title: string): Promise<string> {
  const cfg: any = storyConfig();
  cfg.pages[0].onEnter.push({
    from: "ch1",
    event: "enter",
    to: "var:vv",
    action: "set",
    payload: { etape: "bis" },
  });
  const r = await creator.send("POST", "/v1/configs", { title, config: cfg });
  expect(r.status).toBe(201);
  return r.body.itemId as string;
}

test.describe("j10 builder : mode story et pages", () => {
  test("ajouter un chapitre, enregistrer et relire conserve le mode story et les pages", async ({
    page,
  }) => {
    const pk = await twoActionStory(`${tag}-b2`);
    await openAs(page, "creator");
    await spaGoto(page, `/apps/${pk}/edit`);
    await page.getByRole("button", { name: "Ajouter une page" }).click();
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect
      .poll(
        async () =>
          ((await creator.get(`/v1/configs/by-item/${pk}`)).body.config.pages ?? []).length,
      )
      .toBe(4);
    const cfg = (await creator.get(`/v1/configs/by-item/${pk}`)).body.config;
    expect(cfg.navigationMode).toBe("story");
    expect(cfg.pages[0].onEnter).toHaveLength(2);
    expect(cfg.variables).toHaveLength(1);
  });

  // FINDING j10-006 : Message n'a pas de champ `id` côté cœur, il est perdu à
  // l'enregistrement ; au rechargement toutes les actions ont id undefined, donc
  // retirer une action d'entrée de chapitre les retire toutes.
  bug(
    "j10-006 : retirer une action d'entrée de chapitre ne retire que celle-ci",
    async ({ page }) => {
      const pk = await twoActionStory(`${tag}-b3`);
      await openAs(page, "creator");
      await spaGoto(page, `/apps/${pk}/edit`);
      const removes = page.getByRole("button", { name: /Retirer l'action/ });
      await expect(removes).toHaveCount(2);
      await removes.first().click();
      await expect(page.getByRole("button", { name: /Retirer l'action/ })).toHaveCount(1);
    },
  );

  test("un lecteur qui ouvre le builder d'un site publié voit le bouton Enregistrer désactivé", async ({
    page,
  }) => {
    const r = await creator.send("POST", "/v1/configs", {
      title: `${tag}-b4`,
      config: { version: 1, kind: "site", layout: { type: "grid", items: [] } },
    });
    await creator.send("PATCH", `/v1/items/${r.body.itemId}`, { isPublished: true });
    await openAs(page, "reader");
    await spaGoto(page, `/apps/${r.body.itemId}/edit`);
    await page.waitForTimeout(2000);
    await page.getByRole("button", { name: "Ajouter une page" }).click();
    await expect(page.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
    const cfg = (await creator.get(`/v1/configs/by-item/${r.body.itemId}`)).body;
    expect(cfg.version).toBe(1);
  });

  test("l'export d'app n'est pas proposé dans le builder quand la capacité est éteinte", async ({
    page,
  }) => {
    const inst = await creator.get("/v1/instance");
    test.skip(
      inst.body.appExportEnabled === true,
      "capacité allumée sur cette stack (enable-flags.sh)",
    );
    const pk = await twoActionStory(`${tag}-b5`);
    await openAs(page, "creator");
    await spaGoto(page, `/apps/${pk}/edit`);
    await expect(page.getByLabel("Mode de navigation")).toBeVisible();
    await expect(page.getByText("Export standalone")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Exporter/ })).toHaveCount(0);
  });
});
