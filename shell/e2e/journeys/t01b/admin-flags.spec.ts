import { expect, test } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { apiFor, makeUser, openAsUser, psql } from "../j08/helpers";
import { focusDesc, go, seriousViolations, session } from "./helpers";

test.setTimeout(150_000);
const tag = stamp("t01b");
let seq = 0;

// Conformité (RGPD) : exige compliance.manage, absent du rôle Administrateur. Un rôle jetable
// + un compte Keycloak jetable (comme j08) ; la purge n'est JAMAIS cliquée.
async function dpoPage(browser: import("@playwright/test").Browser, scheme: "light" | "dark") {
  const admin = await apiFor("admin");
  const n = ++seq;
  const role = (
    await admin.send("POST", "/v1/roles", {
      name: `${tag}-${n}-rgpd`,
      privileges: ["admin.users.manage"],
    })
  ).body;
  const officer = await makeUser(`${tag}-${n}-dpo`);
  await admin.send("PATCH", `/v1/users/${officer.id}`, { roleId: role.id });
  // Plafond « ≤ mes privilèges » (P12) : l'Administrateur ne détient pas compliance.manage et ne peut
  // donc pas l'accorder par l'API (ni attribuer un rôle qui le porte) ; le DPO d'une instance réelle est désigné hors bande (SQL).
  psql(
    `UPDATE roles SET privileges='["compliance.manage","admin.users.manage"]' WHERE id='${role.id}'`,
  );
  const ctx = await browser.newContext({ colorScheme: scheme });
  const page = await ctx.newPage();
  page.setDefaultTimeout(8000);
  await openAsUser(page, officer.username);
  return { ctx, page };
}

test.describe("t01b administration : conformité, infrastructure, usage", () => {
  test("/admin/compliance : axe propre en clair et en sombre pour un titulaire de compliance.manage", async ({
    browser,
  }) => {
    for (const scheme of ["light", "dark"] as const) {
      const { ctx, page } = await dpoPage(browser, scheme);
      await go(page, "/admin/compliance", 2500);
      await expect(page.getByRole("heading", { name: "Conformité (RGPD)" })).toBeVisible();
      expect(await seriousViolations(page), scheme).toEqual([]);
      await ctx.close();
    }
  });

  test("/admin/compliance : anonymisation au clavier, erreur annoncée (role=alert), bouton de purge verrouillé", async ({
    browser,
  }) => {
    const { ctx, page } = await dpoPage(browser, "light");
    await go(page, "/admin/compliance", 2500);
    const id = page.getByLabel(/^Identifiant de l'utilisateur/);
    await id.focus();
    await page.keyboard.type("identifiant-inconnu");
    await page.keyboard.press("Tab");
    expect(await focusDesc(page)).toContain("Anonymiser ce compte");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("alert")).toContainText(/Échec de l'anonymisation|introuvable/);
    await expect(
      page.getByRole("button", { name: "Purger définitivement ce tenant" }),
    ).toBeDisabled();
    await ctx.close();
  });

  // t01b-010 : finding. aria-label remplace le libellé visible (WCAG 2.5.3 Label in Name).
  test("t01b-010 : le nom accessible des champs de conformité contient leur libellé visible", async ({
    browser,
  }) => {
    const { ctx, page } = await dpoPage(browser, "light");
    await go(page, "/admin/compliance", 2500);
    const rows = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLInputElement>("label input")].map((i) => ({
        // Sans aria-label, le nom accessible est le libellé visible lui-même (correct).
        name: i.getAttribute("aria-label") ?? (i.closest("label")?.textContent ?? "").trim(),
        visible: (i.closest("label")?.textContent ?? "").trim(),
      })),
    );
    expect(rows.length).toBe(2);
    for (const r of rows) expect(r.name, r.visible).toContain(r.visible);
    await ctx.close();
  });

  test("/admin/infrastructure (outils admin allumés) : axe propre et un bouton par outil", async ({
    browser,
  }) => {
    const { ctx, page } = await session(browser, "admin");
    await go(page, "/admin/infrastructure", 2500);
    for (const name of ["Martin", "Titiler", "Grafana"])
      await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
    await expect(page.getByText(/Stockage : /)).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
    await ctx.close();
  });

  // t01b-011 : finding. Liens/boutons qui ouvrent un nouvel onglet sans le dire.
  test("t01b-011 : la console MinIO (target=_blank) annonce l'ouverture dans un nouvel onglet", async ({
    browser,
  }) => {
    const { ctx, page } = await session(browser, "admin");
    await go(page, "/admin/infrastructure", 2500);
    const link = page.getByRole("link", { name: /Console MinIO/ });
    await expect(link).toHaveAttribute("target", "_blank");
    const name = await link.evaluate(
      (a) =>
        `${a.getAttribute("aria-label") ?? ""} ${a.textContent ?? ""} ${a.getAttribute("title") ?? ""}`,
    );
    expect(name).toMatch(/nouvel onglet|nouvelle fen/i);
    await ctx.close();
  });

  test("/tasks (usage) : axe propre, tri au clavier sur l'en-tête (aria-sort) et synthèse de la plateforme", async ({
    browser,
  }) => {
    const { ctx, page } = await session(browser, "admin");
    await go(page, "/tasks", 2500);
    expect(await seriousViolations(page)).toEqual([]);
    await expect(page.getByRole("heading", { name: "Usage de la plateforme" })).toBeVisible();
    const th = page.getByRole("columnheader", { name: "Action" });
    await th.focus();
    await page.keyboard.press("Enter");
    await expect(th).toHaveAttribute("aria-sort", "ascending");
    await page.keyboard.press("Enter");
    await expect(th).toHaveAttribute("aria-sort", "descending");
    await ctx.close();
  });
});
