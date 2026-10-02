import { test, expect } from "@playwright/test";
import { getSeed, baseApp, grid } from "./seed";
import { openBuilder, openRuntime, spaGo } from "./helpers";

test.setTimeout(90_000);

const filter = (id: string, field: string) => ({
  id,
  widget: "filter",
  x: 0,
  y: 0,
  w: 6,
  h: 2,
  props: { field },
});
const text = (id: string, t: string, y = 2) => ({
  id,
  widget: "text",
  x: 0,
  y,
  w: 6,
  h: 2,
  props: { text: t },
});

async function wire(page: import("@playwright/test").Page, target: string) {
  await page.getByLabel("Widget émetteur").selectOption({ label: "Filtre" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: target });
  await page.getByLabel("Action", { exact: true }).selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();
}

test.describe("j04 câblage, variables, actions", () => {
  test("j04-001 : après enregistrement et rechargement, deux actions restent indépendantes (id conservé)", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "msg-ids",
      baseApp({
        layout: grid([filter("f", "message")]),
        variables: [
          { id: "v1", name: "un", type: "string", initialValue: "" },
          { id: "v2", name: "deux", type: "string", initialValue: "" },
        ],
      }),
    );
    await openBuilder(page, id);
    await wire(page, "Variable : un");
    await wire(page, "Variable : deux");
    await expect(page.getByRole("button", { name: /^Retirer l'action/ })).toHaveCount(2);
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await page.waitForTimeout(1500);
    // Message n'a pas de champ `id` côté cœur : les ids sont perdus à l'enregistrement.
    const saved = await s.creator.get(`/v1/configs/by-item/${id}`);
    await spaGo(page, `/`, 1500);
    await spaGo(page, `/apps/${id}/edit`, 2500);
    await expect(page.getByRole("button", { name: /^Retirer l'action/ })).toHaveCount(2);
    await page
      .getByRole("button", { name: /^Retirer l'action/ })
      .first()
      .click();
    const remaining = await page.getByRole("button", { name: /^Retirer l'action/ }).count();
    const ids = saved.body.config.messages.map((m: { id?: string }) => m.id);
    console.log(
      "j04-001 ids reçus du cœur:",
      JSON.stringify(ids),
      "actions restantes après 1 retrait:",
      remaining,
    );
    expect(remaining).toBe(1);
    expect(ids.every((x: unknown) => typeof x === "string" && x.length > 0)).toBe(true);
  });

  test("le câblage Filtre → variable met à jour un Texte au runtime", async ({ page }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "wire-runtime",
      baseApp({
        layout: grid([filter("f", "message"), text("t", "Valeur : {{var:message}}")]),
        variables: [{ id: "v1", name: "message", type: "string", initialValue: "" }],
        messages: [{ id: "m1", from: "f", event: "changed", to: "var:v1", action: "set" }],
      }),
    );
    await openRuntime(page, `/apps/${id}`);
    await page.getByLabel("Valeur du filtre").fill("hello");
    await expect(page.getByText("Valeur : hello")).toBeVisible();
  });

  test("visibleWhen : widget masqué au runtime tant que la condition est fausse, visible ensuite", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "visible-when",
      baseApp({
        layout: grid(
          [filter("f", "message"), text("t", "Secret visible", 2)].map((w) =>
            w.id === "t" ? { ...w, visibleWhen: "vars.message == 'ok'" } : w,
          ),
        ),
        variables: [{ id: "v1", name: "message", type: "string", initialValue: "" }],
        messages: [{ id: "m1", from: "f", event: "changed", to: "var:v1", action: "set" }],
      }),
    );
    await openRuntime(page, `/apps/${id}`);
    await expect(page.getByText("Secret visible")).toHaveCount(0);
    await page.getByLabel("Valeur du filtre").fill("ok");
    await expect(page.getByText("Secret visible")).toBeVisible();
  });

  test("visibleWhen : en mode Édition le widget masqué reste manipulable, en Aperçu il disparaît", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "visible-edit",
      baseApp({
        layout: grid([{ ...text("t", "Caché", 0), visibleWhen: "false" }]),
      }),
    );
    await openBuilder(page, id);
    const editVisible = await page.getByText("Caché").count();
    await page.getByRole("button", { name: "Aperçu" }).click();
    await page.waitForTimeout(500);
    const previewVisible = await page.getByText("Caché").count();
    // Édition : le créateur doit pouvoir retrouver le widget ; Aperçu : masqué comme au runtime.
    expect({ editVisible: editVisible > 0, previewVisible: previewVisible > 0 }).toEqual({
      editVisible: true,
      previewVisible: false,
    });
  });

  test("variables : deux variables de même nom sont refusées avec un avertissement (j04-014)", async ({
    page,
  }) => {
    const s = await getSeed();
    await openBuilder(page, s.emptyApp);
    await page.getByRole("button", { name: "Ajouter une variable" }).click();
    await page.getByRole("button", { name: "Ajouter une variable" }).click();
    const inputs = page.getByLabel(/^Renommer la variable/);
    await inputs.nth(0).fill("x");
    await inputs.nth(1).fill("x");
    await expect(page.getByRole("alert")).toHaveCount(1);
  });

  test("j04-005 : Annuler (undo) d'un renommage de variable met à jour le champ de nom affiché", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "var-undo",
      baseApp({
        variables: [{ id: "v1", name: "origine", type: "string", initialValue: "" }],
      }),
    );
    await openBuilder(page, id);
    const input = page.getByLabel(/^Renommer la variable/);
    await input.fill("modifie");
    await page.waitForTimeout(600);
    await page.getByRole("button", { name: "Annuler", exact: true }).click();
    await expect(input).toHaveValue("origine");
  });

  test("j04-004 : supprimer une page purge les actions câblées vers ses widgets", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "page-del",
      baseApp({
        layout: grid([text("a", "A", 0)]),
        pages: [
          { id: "p1", name: "P1", layout: grid([text("a", "A", 0)]), onEnter: [] },
          {
            id: "p2",
            name: "P2",
            layout: grid([filter("f2", "x"), text("t2", "T2")]),
            onEnter: [],
          },
        ],
        variables: [{ id: "v1", name: "v", type: "string", initialValue: "" }],
        messages: [{ id: "m1", from: "f2", event: "changed", to: "var:v1", action: "set" }],
      }),
    );
    await openBuilder(page, id);
    await page.getByRole("button", { name: /^Retirer la page p2/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await page.waitForTimeout(1500);
    const saved = await s.creator.get(`/v1/configs/by-item/${id}`);
    expect(saved.body.config.messages).toHaveLength(0);
  });

  test("pages : ajouter, renommer, monter, retirer ; la dernière page ne peut pas être retirée", async ({
    page,
  }) => {
    const s = await getSeed();
    await openBuilder(page, s.emptyApp);
    await expect(page.getByRole("button", { name: /^Retirer la page/ })).toBeDisabled();
    await page.getByRole("button", { name: "Ajouter une page" }).click();
    await expect(page.getByRole("button", { name: /^Ouvrir la page/ })).toHaveCount(2);
    await page
      .getByLabel(/^Renommer la page/)
      .nth(1)
      .fill("Deuxième");
    await page
      .getByRole("button", { name: /^Monter la page/ })
      .nth(1)
      .click();
    await expect(page.getByRole("button", { name: /^Ouvrir la page/ }).first()).toHaveText(
      "Deuxième",
    );
    await page
      .getByRole("button", { name: /^Retirer la page/ })
      .first()
      .click();
    await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
    await expect(page.getByRole("button", { name: /^Ouvrir la page/ })).toHaveCount(1);
  });

  test("runtime : un identifiant de page inconnu affiche silencieusement la première page", async ({
    page,
  }) => {
    const s = await getSeed();
    const id = await s.mkApp(
      "page-inconnue",
      baseApp({
        layout: grid([text("a", "Page un", 0)]),
        pages: [
          { id: "p1", name: "P1", layout: grid([text("a", "Page un", 0)]), onEnter: [] },
          { id: "p2", name: "P2", layout: grid([text("b", "Page deux", 0)]), onEnter: [] },
        ],
      }),
    );
    await openRuntime(page, `/apps/${id}/inexistante`);
    const body = await page.locator("body").innerText();
    // Attendu raisonnable : message « page introuvable » ; observé : contenu de la 1re page.
    expect(body).toContain("Page un");
    expect(body).not.toMatch(/introuvable/i);
  });
});
