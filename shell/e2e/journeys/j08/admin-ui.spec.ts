/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect, type Page } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { openAs } from "../j06/helpers";
import { apiFor, makeUser, openAsUser, psql, spaGoto, type Api } from "./helpers";

// SettingsNav, pages Utilisateurs / Rôles / Conformité / Tâches / Extensions (shell + cœur réels).
test.setTimeout(120_000);
const tag = stamp("j08");
let admin: Api;

test.beforeAll(async () => {
  admin = await apiFor("admin");
});

const navLinks = (page: Page) =>
  page
    .getByRole("navigation", { name: "Navigation des paramètres" })
    .getByRole("link")
    .allInnerTexts();

async function go(page: Page, path: string): Promise<void> {
  await spaGoto(page, path);
  await page.waitForTimeout(800);
}

test.describe("j08 SettingsNav et droits d'accès", () => {
  test("l'Administrateur prédéfini voit Général + 6 destinations ; l'infrastructure affiche l'usage sans limite", async ({
    page,
  }) => {
    await openAs(page, "admin");
    await go(page, "/settings");
    expect(await navLinks(page)).toEqual([
      "Général →",
      "Extensions →",
      "Outils d'infrastructure →",
      "Rôles et privilèges →",
      "Utilisateurs →",
      "Collections →",
      "Moissonnage →",
    ]);
    await page.getByRole("link", { name: "Outils d'infrastructure →" }).click();
    await expect(page.getByText("Utilisation", { exact: true })).toBeVisible();
    await expect(page.getByText(/Stockage : .*pas de limite configurée/)).toBeVisible();
    await expect(page.getByText("Non activé sur cette instance")).toBeVisible();
  });

  // Finding j08-002 : l'écran d'anonymisation exige compliance.manage, absent de l'Administrateur.
  bug(
    "j08-002 : l'Administrateur atteint l'anonymisation depuis la navigation",
    async ({ page }) => {
      await openAs(page, "admin");
      await go(page, "/settings");
      expect(await navLinks(page)).toContain("Conformité (RGPD) →");
    },
  );

  test("lecteur : navigation réduite à Général, pages d'administration et tâches refusées", async ({
    page,
  }) => {
    await openAs(page, "reader");
    await go(page, "/settings");
    expect(await navLinks(page)).toEqual(["Général →"]);
    const denied: Record<string, string> = {
      "/admin/users": "Accès réservé à la gestion des utilisateurs.",
      "/admin/roles": "Accès réservé à la gestion des rôles.",
      "/admin/compliance": "Accès réservé à la conformité (RGPD).",
      "/admin/extensions": "Accès réservé aux administrateurs.",
      "/tasks": "Accès réservé — privilège tasks.view requis.",
    };
    for (const [path, message] of Object.entries(denied)) {
      await go(page, path);
      await expect(page.getByText(message), path).toBeVisible();
    }
  });
});

test.describe("j08 utilisateurs — UI", () => {
  test("recherche et changement de rôle par ligne, persistés côté cœur", async ({ page }) => {
    const u = await makeUser(`${tag}-ui`);
    await openAs(page, "admin");
    await go(page, "/admin/users");
    await page.getByLabel("Rechercher").first().fill(u.username);
    await expect(page.getByRole("row").filter({ hasText: u.username })).toHaveCount(1);
    await expect(page.getByRole("row").filter({ hasText: "audit-reader" })).toHaveCount(0);
    await page.getByRole("combobox", { name: `Rôle de ${u.username}` }).selectOption({
      label: "Lecteur",
    });
    await expect
      .poll(async () => (await u.api.get("/v1/me")).body.role.slug, { timeout: 10_000 })
      .toBe("reader");
    await page.getByLabel("Rechercher").first().fill(`${tag}-zzz`);
    await expect(page.getByText("Aucun utilisateur ne correspond à cette recherche")).toBeVisible();
  });

  test("pagination : 60 comptes → Page 1 / 2, Suivant et Précédent", async ({ page }) => {
    const readerRole = psql(
      "SELECT id FROM roles WHERE slug='reader' AND tenant_id='default'",
    ).trim();
    psql(
      `INSERT INTO users (id, tenant_id, oidc_sub, username, email, first_name, last_name, created_at, updated_at, is_admin, role_id) ` +
        `SELECT md5('${tag}'||g), 'default', '${tag}-sub-'||g, '${tag}-bulk-'||lpad(g::text,3,'0'), NULL, '', '', now(), now(), false, '${readerRole}' FROM generate_series(1,60) g`,
    );
    await openAs(page, "admin");
    await go(page, "/admin/users");
    await expect(page.getByText(/Page 1 \/ [2-9]/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Précédent" })).toBeDisabled();
    await page.getByRole("button", { name: "Suivant" }).click();
    await expect(page.getByText(/Page 2 \/ /)).toBeVisible();
    await page.getByRole("button", { name: "Précédent" }).click();
    await expect(page.getByText(/Page 1 \/ /)).toBeVisible();
  });

  // Finding j08-006 : aucune action d'anonymisation depuis la liste des utilisateurs.
  bug("j08-006 : chaque ligne d'utilisateur propose d'anonymiser le compte", async ({ page }) => {
    const u = await makeUser(`${tag}-pick`);
    await openAs(page, "admin");
    await go(page, "/admin/users");
    await page.getByLabel("Rechercher").first().fill(u.username);
    const row = page.getByRole("row").filter({ hasText: u.username });
    await expect(row.getByRole("button", { name: /Anonymiser/ })).toBeVisible();
  });
});

test.describe("j08 rôles — UI", () => {
  test("création, édition et suppression d'un rôle sur mesure ; prédéfinis sans actions", async ({
    page,
  }) => {
    const name = `${tag}-ui-role`;
    await openAs(page, "admin");
    await go(page, "/admin/roles");
    const builtIn = page.getByRole("row").filter({ hasText: /Administrateur\s*\(Prédéfini\)/ });
    await expect(builtIn.getByText("Prédéfini")).toBeVisible();
    await expect(builtIn.getByRole("button")).toHaveCount(0);

    await page.getByRole("button", { name: "Ajouter un rôle" }).click();
    const panel = page.getByRole("region", { name: "Ajouter un rôle" });
    await panel.getByLabel("Nom").fill(name);
    await panel.getByLabel("Voir ses tâches").check();
    await panel.getByRole("button", { name: "Enregistrer" }).click();
    const row = page.getByRole("row").filter({ hasText: name });
    await expect(row).toBeVisible();
    const created = (await admin.get("/v1/roles")).body.find((r: any) => r.name === name);
    expect(created.privileges).toEqual(["tasks.view"]);

    await row.getByRole("button", { name: "Éditer" }).click();
    const edit = page.getByRole("region", { name: `Éditer ${name}` });
    await edit.getByLabel("Voir les tâches de tout le tenant").check();
    await edit.getByRole("button", { name: "Enregistrer" }).click();
    await expect(edit).toHaveCount(0);
    const updated = (await admin.get("/v1/roles")).body.find((r: any) => r.name === name);
    expect(updated.privileges.sort()).toEqual(["tasks.view", "tasks.view_all"]);

    await row.getByRole("button", { name: "Supprimer" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Supprimer" }).click();
    await expect(row).toHaveCount(0);
    expect((await admin.get("/v1/roles")).body.some((r: any) => r.name === name)).toBe(false);
  });

  // Finding j08-011 : le 409 « N utilisateur(s) ont ce rôle » est réduit à un échec générique.
  bug(
    "j08-011 : supprimer un rôle encore attribué explique combien d'utilisateurs le portent",
    async ({ page }) => {
      const name = `${tag}-held-ui`;
      const role = (await admin.send("POST", "/v1/roles", { name, privileges: [] })).body;
      const u = await makeUser(`${tag}-held-ui`);
      await admin.send("PATCH", `/v1/users/${u.id}`, { roleId: role.id });
      await openAs(page, "admin");
      await go(page, "/admin/roles");
      const row = page.getByRole("row").filter({ hasText: name });
      await row.getByRole("button", { name: "Supprimer" }).click();
      await page.getByRole("alertdialog").getByRole("button", { name: "Supprimer" }).click();
      await expect(page.getByText(/Encore attribué à 1 utilisateur/)).toBeVisible();
    },
  );
});

test.describe("j08 conformité — UI", () => {
  test("titulaire de compliance.manage : anonymise par identifiant, erreur sur id inconnu, purge verrouillée par le slug", async ({
    page,
  }) => {
    const role = (
      await admin.send("POST", "/v1/roles", {
        name: `${tag}-rgpd`,
        privileges: ["compliance.manage", "admin.users.manage"],
      })
    ).body;
    const officer = await makeUser(`${tag}-dpo`);
    await admin.send("PATCH", `/v1/users/${officer.id}`, { roleId: role.id });
    const victim = await makeUser(`${tag}-victim-ui`);

    await openAsUser(page, officer.username);
    await go(page, "/admin/compliance");
    await expect(page.getByRole("heading", { name: "Conformité (RGPD)" })).toBeVisible();
    const id = page.getByLabel("Identifiant de l'utilisateur à anonymiser");
    const erase = page.getByRole("button", { name: "Anonymiser ce compte" });
    await expect(erase).toBeDisabled();
    await id.fill("identifiant-inconnu");
    await erase.click();
    await expect(page.getByText("Échec de l'anonymisation.")).toBeVisible();
    await id.fill(victim.id);
    await erase.click();
    await expect(page.getByText("Compte anonymisé.")).toBeVisible();
    expect(psql(`SELECT username FROM users WHERE id='${victim.id}'`).trim()).toMatch(
      /^utilisateur-efface-/,
    );

    // Purge : le bouton reste désactivé tant que le slug n'est pas retapé exactement (jamais cliqué).
    const purge = page.getByRole("button", { name: "Purger définitivement ce tenant" });
    await expect(purge).toBeDisabled();
    const slug = page.getByLabel("Confirmer le slug du tenant");
    await slug.fill("defaul");
    await expect(purge).toBeDisabled();
    await slug.fill("default");
    await expect(purge).toBeEnabled();
    await slug.fill("");
  });
});

test.describe("j08 tâches et extensions — UI", () => {
  test("/tasks : l'analyste sans activité voit un état vide et pas l'usage de la plateforme", async ({
    page,
  }) => {
    await openAs(page, "analyst");
    await go(page, "/tasks");
    await expect(page.getByText("Aucune tâche récente.")).toBeVisible();
    await expect(page.getByText("Usage de la plateforme")).toHaveCount(0);
  });

  // Finding j08-012 : titre « Mes tâches » mais le tableau liste tout le tenant, sans colonne acteur.
  bug(
    "j08-012 : pour tasks.view_all, le journal indique l'utilisateur de chaque action",
    async ({ page }) => {
      const other = (await admin.get("/v1/users?q=audit-creator")).body.users[0].id;
      psql(
        `INSERT INTO audit_log (tenant_id, actor_id, actor_kind, action, object_type, object_id, payload, created_at) VALUES ('default','${other}','user','pipeline.run','item','${tag}-ui','{}',now())`,
      );
      await openAs(page, "admin");
      await go(page, "/tasks");
      await expect(page.getByText("Usage de la plateforme")).toBeVisible();
      await expect(page.getByRole("cell", { name: `item/${tag}-ui` })).toBeVisible();
      await expect(page.getByRole("columnheader", { name: "Utilisateur" })).toBeVisible();
    },
  );

  test("extensions : liste et bascule d'activation persistée côté cœur", async ({ page }) => {
    const id = `${tag}-ext`;
    const made = await admin.send("POST", "/v1/extensions", {
      id,
      tag: `${tag}-widget`,
      label: `Ext ${tag}`,
      moduleUrl: "https://example.org/never-loaded.js",
      defaultSize: { w: 4, h: 3 },
    });
    expect(made.status).toBe(201);
    await admin.send("PATCH", `/v1/extensions/${id}`, { enabled: false });
    await openAs(page, "admin");
    await go(page, "/admin/extensions");
    const box = page.getByRole("checkbox", { name: `Actif : Ext ${tag}` });
    await expect(box).not.toBeChecked();
    await box.click();
    await expect
      .poll(async () => {
        const list = await admin.get("/v1/extensions?all=true");
        return list.body.extensions.find((e: any) => e.id === id)?.enabled;
      })
      .toBe(true);
    await box.click();
    await expect
      .poll(async () => {
        const list = await admin.get("/v1/extensions?all=true");
        return list.body.extensions.find((e: any) => e.id === id)?.enabled;
      })
      .toBe(false);
  });

  // Finding j08-009 : impossible d'enregistrer ou de retirer une extension depuis l'admin.
  bug(
    "j08-009 : l'administration des extensions permet d'en enregistrer et d'en retirer",
    async ({ page }) => {
      await openAs(page, "admin");
      await go(page, "/admin/extensions");
      await expect(
        page.getByRole("button", { name: /Ajouter|Enregistrer une extension/ }),
      ).toBeVisible();
      await expect(page.getByRole("button", { name: /Supprimer|Retirer/ }).first()).toBeVisible();
    },
  );
});
