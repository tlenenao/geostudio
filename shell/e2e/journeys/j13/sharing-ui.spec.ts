import { test, expect, type Page } from "@playwright/test";
import {
  apiFor,
  go,
  mapConfigOn,
  meId,
  mkCollection,
  mkGroup,
  mkItem,
  openAs,
  share,
  TAG,
  type Api,
} from "./helpers";

// Partage et permissions vus depuis le shell (OIDC réel).
test.setTimeout(120_000);

let creator: Api, reader: Api, analyst: Api;
let readerId: string;

test.beforeAll(async () => {
  [creator, reader, analyst] = await Promise.all([
    apiFor("creator"),
    apiFor("reader"),
    apiFor("analyst"),
  ]);
  readerId = await meId(reader);
});

async function openMenu(page: Page) {
  await page.getByRole("button", { name: "Actions" }).click();
}

test.describe("j13 panneau de partage (propriétaire)", () => {
  test("le Créateur partage son app à un groupe en Éditeur depuis la fiche ; le cœur l'enregistre", async ({
    page,
  }) => {
    const it = await mkItem(creator, `${TAG}-ui-share`);
    const gName = `${TAG}-ui-g`;
    const g = await mkGroup(creator, gName);
    await openAs(page, "creator");
    await go(page, `/items/${it.pk}?panel=share`, 2500);
    await expect(page.getByRole("heading", { name: "Partager l'élément" })).toBeVisible();
    await page.getByRole("checkbox", { name: `Groupe ${gName}` }).check();
    await page.getByRole("combobox", { name: `Rôle ${gName}` }).selectOption("editor");
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(page.getByRole("heading", { name: "Partager l'élément" })).toHaveCount(0);
    const sh = await creator.get(`/v1/items/${it.pk}/sharing`);
    expect(sh.body.groups).toEqual([{ groupId: g, role: "editor" }]);
  });

  test("le Créateur crée un groupe depuis le panneau ; il apparaît dans la liste", async ({
    page,
  }) => {
    const it = await mkItem(creator, `${TAG}-ui-newgroup`);
    const name = `${TAG}-ui-created`;
    await openAs(page, "creator");
    await go(page, `/items/${it.pk}?panel=share`, 2500);
    await page.getByRole("textbox", { name: "Nom du nouveau groupe" }).fill(name);
    await page.getByRole("button", { name: "Créer le groupe" }).click();
    await expect(page.getByRole("checkbox", { name: `Groupe ${name}` })).toBeVisible();
  });

  // Finding j13-001 : CORE_SHARE_LINK_TOKEN_SECRET vide → 500 → message générique.
  test.fixme("j13-001 : « Créer un lien » affiche un lien utilisable", async ({ page }) => {
    const it = await mkItem(creator, `${TAG}-ui-link`);
    await openAs(page, "creator");
    await go(page, `/items/${it.pk}?panel=share`, 2500);
    await page.getByRole("button", { name: "Créer un lien" }).click();
    await expect(page.getByText("Lien créé :")).toBeVisible();
  });

  test("constat j13-001 : « Créer un lien » échoue avec un message générique", async ({ page }) => {
    const it = await mkItem(creator, `${TAG}-ui-link-obs`);
    await openAs(page, "creator");
    await go(page, `/items/${it.pk}?panel=share`, 2500);
    const resp = page.waitForResponse(
      (r) => r.url().includes("/share-links") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Créer un lien" }).click();
    expect((await resp).status()).toBe(500);
    await expect(page.getByText("Échec de la création du lien.")).toBeVisible();
  });

  // Finding j13-007 : « Public (visible par tous) » ne vaut que pour le tenant.
  test.fixme("j13-007 : la case de partage public précise qu'elle ne publie pas hors de l'organisation", async ({
    page,
  }) => {
    const it = await mkItem(creator, `${TAG}-ui-publabel`);
    await openAs(page, "creator");
    await go(page, `/items/${it.pk}?panel=share`, 2500);
    await expect(page.getByText(/organisation|comptes|connectés/i)).toBeVisible();
  });
});

test.describe("j13 masquage UI selon le rôle de partage", () => {
  test("viewer : le menu Actions n'offre ni Partager ni Supprimer ; ?panel=share est verrouillé", async ({
    page,
  }) => {
    const it = await mkItem(creator, `${TAG}-ui-viewer`);
    const g = await mkGroup(creator, `${TAG}-ui-gv`, [readerId]);
    expect(await share(creator, it.pk, [{ groupId: g, role: "viewer" }])).toBe(204);
    await openAs(page, "reader");
    await go(page, `/items/${it.pk}`, 2500);
    await openMenu(page);
    await expect(page.getByRole("button", { name: "Partager", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Supprimer", exact: true })).toHaveCount(0);
    await go(page, `/items/${it.pk}?panel=share`, 2000);
    await expect(page.getByText("Partage réservé au propriétaire et aux éditeurs.")).toBeVisible();
  });

  // Finding j13-010 : permissions.delete ignore le privilège de kind.
  test.fixme("j13-010 : un Lecteur éditeur par groupe ne se voit pas proposer « Supprimer » (refusé en 403)", async ({
    page,
  }) => {
    const it = await mkItem(creator, `${TAG}-ui-editor`);
    const g = await mkGroup(creator, `${TAG}-ui-ge`, [readerId]);
    expect(await share(creator, it.pk, [{ groupId: g, role: "editor" }])).toBe(204);
    await openAs(page, "reader");
    await go(page, `/items/${it.pk}`, 2500);
    await openMenu(page);
    await expect(page.getByRole("button", { name: "Supprimer", exact: true })).toHaveCount(0);
  });

  test("constat j13-010 : le Lecteur éditeur voit « Supprimer », confirme, obtient 403 et « Échec de la suppression »", async ({
    page,
  }) => {
    const it = await mkItem(creator, `${TAG}-ui-editor-obs`);
    const g = await mkGroup(creator, `${TAG}-ui-geo`, [readerId]);
    expect(await share(creator, it.pk, [{ groupId: g, role: "editor" }])).toBe(204);
    await openAs(page, "reader");
    await go(page, `/items/${it.pk}`, 2500);
    await openMenu(page);
    await page.getByRole("button", { name: "Supprimer", exact: true }).click();
    const resp = page.waitForResponse(
      (r) => r.url().endsWith(`/v1/configs/by-item/${it.pk}`) && r.request().method() === "DELETE",
    );
    await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
    expect((await resp).status()).toBe(403);
    await expect(page.getByText("Échec de la suppression.")).toBeVisible();
    expect((await creator.get(`/v1/items/${it.pk}`)).status).toBe(200);
  });

  // Finding j13-006 : contrôles de groupe proposés à qui ne peut pas s'en servir.
  test.fixme("j13-006 : un Lecteur éditeur ne voit ni « Créer le groupe » ni « Ajouter un membre » sur les groupes d'autrui", async ({
    page,
  }) => {
    const it = await mkItem(creator, `${TAG}-ui-grpctl`);
    const g = await mkGroup(creator, `${TAG}-ui-gctl`, [readerId]);
    expect(await share(creator, it.pk, [{ groupId: g, role: "editor" }])).toBe(204);
    await openAs(page, "reader");
    await go(page, `/items/${it.pk}?panel=share`, 2500);
    await expect(page.getByRole("button", { name: "Créer le groupe" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Ajouter un membre/ })).toHaveCount(0);
  });

  test("constat j13-006 : le Lecteur éditeur crée un groupe (403) et ajoute un membre à un groupe d'autrui (404)", async ({
    page,
  }) => {
    const it = await mkItem(creator, `${TAG}-ui-grpctl-obs`);
    const gName = `${TAG}-ui-gctlo`;
    const g = await mkGroup(creator, gName, [readerId]);
    expect(await share(creator, it.pk, [{ groupId: g, role: "editor" }])).toBe(204);
    await openAs(page, "reader");
    await go(page, `/items/${it.pk}?panel=share`, 2500);
    await page.getByRole("textbox", { name: "Nom du nouveau groupe" }).fill(`${TAG}-nope`);
    const create = page.waitForResponse(
      (r) => r.url().endsWith("/v1/groups") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Créer le groupe" }).click();
    expect((await create).status()).toBe(403);
    await expect(page.getByText("Échec de la création du groupe.")).toBeVisible();
    await page.getByRole("textbox", { name: `Identifiant utilisateur (${gName})` }).fill(readerId);
    const add = page.waitForResponse((r) => r.url().includes(`/v1/groups/${g}/members`));
    await page.getByRole("button", { name: `Ajouter un membre (${gName})` }).click();
    expect((await add).status()).toBe(404);
    await expect(page.getByText("Ce groupe n'existe pas, ou", { exact: false })).toBeVisible();
  });
});

test.describe("j13 identifiants et accès direct par URL", () => {
  // Finding j13-005 : l'identifiant exigé par « Ajouter un membre » n'est affiché nulle part.
  test.fixme("j13-005 : la page Paramètres affiche l'identifiant de l'utilisateur (requis pour l'ajout à un groupe)", async ({
    page,
  }) => {
    await openAs(page, "analyst");
    await go(page, "/settings", 2500);
    await expect(page.getByText(await meId(analyst))).toBeVisible();
  });

  test("accès direct par URL à des objets privés d'autrui : messages « introuvable », aucune donnée", async ({
    page,
  }) => {
    const title = `${TAG}-ui-idor`;
    const app = await mkItem(creator, title);
    const col = await mkCollection(creator, `${TAG}-ui-idor-col`);
    const map = await mkItem(creator, `${TAG}-ui-idor-map`, mapConfigOn(col));
    const ds = await mkItem(creator, `${TAG}-ui-idor-ds`, {
      version: 1,
      kind: "dataset",
      dataset: { source: "collection", collectionId: col },
    });
    await openAs(page, "reader");
    for (const [path, msg] of [
      [`/items/${app.pk}`, "Élément introuvable."],
      [`/apps/${app.pk}/edit`, "Application introuvable."],
      [`/maps/${map.pk}`, "Carte introuvable."],
      [`/datasets/${ds.pk}/edit`, "Dataset partagé introuvable."],
    ] as const) {
      await go(page, path, 2500);
      await expect(page.getByText(msg)).toBeVisible();
      await expect(page.getByText(title, { exact: true })).toHaveCount(0);
    }
  });

  test("un Analyste propriétaire d'un bookmark peut le partager en viewer au groupe d'un Créateur (UI)", async ({
    page,
  }) => {
    const target = await mkItem(creator, `${TAG}-ui-bm-target`);
    expect(await share(creator, target.pk, [], true)).toBe(204);
    const bm = await analyst.send("POST", "/v1/configs", {
      title: `${TAG}-ui-bm`,
      config: { version: 1, kind: "bookmark", bookmark: { appId: target.pk, pageId: "p1" } },
    });
    expect(bm.status).toBe(201);
    const gName = `${TAG}-ui-gbm`;
    const g = await mkGroup(creator, gName, [readerId]);
    await openAs(page, "analyst");
    await go(page, `/items/${bm.body.itemId}?panel=share`, 2500);
    await page.getByRole("checkbox", { name: `Groupe ${gName}` }).check();
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(page.getByRole("heading", { name: "Partager l'élément" })).toHaveCount(0);
    expect((await reader.get(`/v1/items/${bm.body.itemId}`)).status).toBe(200);
    const sh = await analyst.get(`/v1/items/${bm.body.itemId}/sharing`);
    expect(sh.body.groups).toEqual([{ groupId: g, role: "viewer" }]);
  });
});
