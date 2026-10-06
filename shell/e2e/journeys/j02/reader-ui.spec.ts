import { bug } from "../_fixtures/verify";
import { test, expect, type Page } from "@playwright/test";
import { getSeed } from "./seed";
import { loginOidc, SHELL_URL } from "../_fixtures/env";
import { spaGo } from "./helpers";

test.setTimeout(90_000);

async function asReader(page: Page) {
  await loginOidc(page, "reader");
  await page.waitForTimeout(1000);
}

// Bouton « Ouvrir » de la carte dont le titre est exactement `title` (la
// recherche par sous-chaîne renvoie aussi les titres qui la préfixent).
async function openCard(page: Page, title: string) {
  const heading = page.getByRole("heading", { name: title, exact: true });
  await heading
    .locator("xpath=ancestor::*[.//button[normalize-space()='Ouvrir']][1]")
    .getByRole("button", { name: "Ouvrir" })
    .click();
}

async function searchCatalog(page: Page, text: string) {
  await page.getByRole("textbox", { name: "Rechercher" }).first().fill(text);
  await page.waitForTimeout(1500);
}

test.describe("j02 lecteur — catalogue, fiches, éditeurs", () => {
  test("le lecteur arrive sur le catalogue sans entrée d'administration ni bouton de création", async ({
    page,
  }) => {
    await asReader(page);
    const nav = await page.locator("body").innerText();
    expect(nav).toContain("Catalogue");
    for (const forbidden of ["Utilisateurs", "Rôles", "Extensions", "Moissonnage", "Conformité"]) {
      expect(nav, forbidden).not.toContain(forbidden);
    }
    await expect(page.getByRole("button", { name: /Nouveau|Importer|Nouvelle/ })).toHaveCount(0);
  });

  test("catalogue : recherche par titre, le partagé apparaît, le privé jamais", async ({
    page,
  }) => {
    const s = await getSeed();
    await asReader(page);
    await searchCatalog(page, `${s.tag}-carte`);
    await expect(page.getByRole("heading", { name: `${s.tag}-carte`, exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: `${s.tag}-carte-privee` })).toHaveCount(0);
  });

  test("catalogue : « Mes éléments » d'un lecteur (rien créé) affiche un état vide explicite", async ({
    page,
  }) => {
    await asReader(page);
    await page.getByLabel("Portée").selectOption("mine");
    await page.waitForTimeout(1500);
    await expect(page.getByRole("button", { name: "Ouvrir" })).toHaveCount(0);
    await expect(page.getByText(/Aucun (résultat|élément)/).first()).toBeVisible();
  });

  // j02-012 : une requête absurde ne renvoie rien (sans « j02 » : ce jeton ressemble par trigrammes
  // aux titres « aud-j02-… » du semis, ce qui est un vrai résultat).
  test("j02-012 : une requête sans aucun rapport avec le catalogue ne renvoie aucun résultat", async ({
    page,
  }) => {
    await asReader(page);
    await searchCatalog(page, "zzz-introuvable-xyz");
    await expect(page.getByRole("button", { name: "Ouvrir" })).toHaveCount(0);
    await expect(page.getByText("Aucun résultat").first()).toBeVisible();
  });

  test("un item privé ouvert par URL affiche « Élément introuvable » (aucune fuite)", async ({
    page,
  }) => {
    const s = await getSeed();
    await asReader(page);
    await spaGo(page, `/items/${s.privateMap}`);
    await expect(page.getByText("Élément introuvable.")).toBeVisible();
  });

  test("les écrans d'administration sont refusés au lecteur avec un message", async ({ page }) => {
    await asReader(page);
    for (const path of [
      "/admin/users",
      "/admin/roles",
      "/admin/collections",
      "/analytics/sql",
      "/admin/compliance",
    ]) {
      await spaGo(page, path);
      await expect(page.getByText(/réservé|Accès|droits|autorisé/i).first(), path).toBeVisible();
    }
  });

  // j02-007 : la fiche dataset ne montre ni licence, ni mots-clés, ni colonnes, ni volume.
  test("j02-007 : la fiche dataset expose licence, mots-clés et colonnes au lecteur", async ({
    page,
  }) => {
    const s = await getSeed();
    await asReader(page);
    await spaGo(page, `/items/${s.sharedDataset}`);
    const body = page.locator("body");
    await expect(body).toContainText("cadastre");
    await expect(body).toContainText(/Creative Commons Attribution 4.0|CC-BY/);
    await expect(body).toContainText("surface");
  });

  // j02-008 : ouvrir une app depuis le catalogue envoie le lecteur dans le builder.
  test("j02-008 : « Ouvrir » sur une app mène un lecteur à la vue d'usage, pas au builder", async ({
    page,
  }) => {
    const s = await getSeed();
    await asReader(page);
    await searchCatalog(page, `${s.tag}-app-auto`);
    await openCard(page, `${s.tag}-app-auto`);
    await page.waitForTimeout(2500);
    expect(page.url()).not.toMatch(/\/edit(\?|$)/);
  });

  test("éditeur de carte en lecture seule : Enregistrer est désactivé et expliqué", async ({
    page,
  }) => {
    const s = await getSeed();
    await asReader(page);
    await spaGo(page, `/maps/${s.sharedMap}`, 3000);
    const save = page.getByRole("button", { name: /Enregistrer/ }).first();
    await expect(save).toBeDisabled();
    await expect(
      page.getByText("Modification réservée aux éditeurs de cet élément."),
    ).toBeVisible();
  });

  // j02-009 : le canevas de la carte prend la hauteur du panneau de gauche, pas celle de l'écran.
  test("j02-009 : le canevas de la carte tient dans la fenêtre", async ({ page }) => {
    const s = await getSeed();
    await page.setViewportSize({ width: 1280, height: 720 });
    await asReader(page);
    await spaGo(page, `/maps/${s.sharedMap}`, 3000);
    const box = await page.locator("canvas.maplibregl-canvas").first().boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeLessThanOrEqual(720);
  });
});

test.describe("j02 lecteur — liens directs, runtime, bookmarks", () => {
  // j02-004 : un rechargement (ou un lien) perd la destination après le retour Keycloak.
  bug("j02-004 : un lien direct vers une fiche survit à la reconnexion OIDC", async ({ page }) => {
    const s = await getSeed();
    await asReader(page);
    await page.goto(`/items/${s.sharedMap}`);
    await expect(page).toHaveURL(new RegExp(`/items/${s.sharedMap}`), { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: `${s.tag}-carte` })).toBeVisible();
  });

  // j02-010 : /apps/:pk est hors RequireAuth, un rechargement part sans jeton → 401 « Accès refusé ».
  bug(
    "j02-010 : recharger (ou ouvrir sans session) une app en mode usage affiche l'app ou la connexion, pas « Accès refusé »",
    async ({ page, browser }) => {
      const s = await getSeed();
      await asReader(page);
      await spaGo(page, `/apps/${s.sharedApp}/p1`, 3000);
      await expect(page.getByText("Bonjour lecteur")).toBeVisible();
      await page.reload();
      await expect(page.getByText("Bonjour lecteur")).toBeVisible({ timeout: 15_000 });
      // 2e volet : sans aucune session, le lien ne renvoie pas vers la connexion.
      const ctx = await browser.newContext({ baseURL: SHELL_URL });
      const cold = await ctx.newPage();
      await cold.goto(`/apps/${s.sharedApp}/p1`);
      await cold.waitForTimeout(4000);
      const onLogin = /openid-connect\/auth/.test(cold.url());
      await ctx.close();
      expect(onLogin, "lien d'app sans session : redirection vers Keycloak attendue").toBe(true);
    },
  );

  test("bookmark : « Ouvrir » rejoue l'app, la page et le contexte (?ctx=)", async ({ page }) => {
    const s = await getSeed();
    await asReader(page);
    await searchCatalog(page, `${s.tag}-signet`);
    await openCard(page, `${s.tag}-signet`);
    await expect(page).toHaveURL(new RegExp(`/apps/${s.sharedApp}/p1\\?ctx=`));
    await expect(page.getByText("Bonjour lecteur")).toBeVisible();
    await expect(page.getByText("Alpha")).toBeVisible();
  });

  test("bookmark sur une app privée : l'ouverture ne montre pas de contenu et reste compréhensible", async ({
    page,
  }) => {
    const s = await getSeed();
    await asReader(page);
    await searchCatalog(page, `${s.tag}-signet-app-privee`);
    await openCard(page, `${s.tag}-signet-app-privee`);
    await page.waitForTimeout(3000);
    // Aucune donnée de l'app privée ne doit s'afficher.
    await expect(page.getByText("Bonjour lecteur")).toHaveCount(0);
    await expect(page.getByText("Alpha")).toHaveCount(0);
  });

  // j02-011 : le bouton « Enregistrer la vue » est proposé au lecteur alors que le cœur refuse (analytics.view).
  test("j02-011 : un lecteur ne se voit pas proposer « Enregistrer la vue » qui échouera", async ({
    page,
  }) => {
    const s = await getSeed();
    await asReader(page);
    await spaGo(page, `/apps/${s.autoApp}/p1`, 3000);
    await expect(page.getByText("Bonjour lecteur")).toBeVisible();
    await expect(page.getByRole("button", { name: /Enregistrer la vue/ })).toHaveCount(0);
  });
});
