import { expect, test } from "@playwright/test";
import { focusDesc, getA11ySeed, go, seriousViolations, session } from "./helpers";

test.setTimeout(120_000);

test.describe("t01b export d'app (appexport allumé)", () => {
  test("panneau d'export : le déclencheur ouvre le choix de mode, Fermer le referme, axe propre", async ({
    browser,
  }) => {
    const s = await getA11ySeed();
    const { ctx, page } = await session(browser, "creator");
    await go(page, `/apps/${s.appId}/edit`, 3000);
    await page.getByRole("button", { name: "Exporter", exact: true }).click();
    await expect(page.getByRole("button", { name: /statique/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /connecté/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /autoporté/i })).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
    await page.getByRole("button", { name: "Fermer" }).click();
    await expect(page.getByRole("button", { name: /statique/i })).toHaveCount(0);
    await ctx.close();
  });

  // t01b-012 : finding. Bascule de panneau en ligne sans aria-expanded/aria-controls (REV-088).
  test("t01b-012 : le déclencheur « Exporter » porte aria-expanded et aria-controls", async ({
    browser,
  }) => {
    const s = await getA11ySeed();
    const { ctx, page } = await session(browser, "creator");
    await go(page, `/apps/${s.appId}/edit`, 3000);
    const trigger = page.getByRole("button", { name: "Exporter", exact: true });
    await trigger.click();
    expect(await trigger.getAttribute("aria-expanded")).toBe("true");
    expect(await trigger.getAttribute("aria-controls")).toBeTruthy();
    await ctx.close();
  });

  // t01b-013 : finding. Choisir un mode ferme le panneau, désactive le déclencheur : le focus
  // tombe sur <body> et le clavier repart du début de la page.
  test("t01b-013 : après le choix d'un mode d'export, le focus reste dans l'éditeur (pas sur body)", async ({
    browser,
  }) => {
    const s = await getA11ySeed();
    const { ctx, page } = await session(browser, "creator");
    await go(page, `/apps/${s.appId}/edit`, 3000);
    await page.getByRole("button", { name: "Exporter", exact: true }).click();
    await page.getByRole("button", { name: /statique/i }).focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(2500);
    expect(await focusDesc(page)).not.toBe("body");
    await ctx.close();
  });
});

test.describe("t01b tileset 3D (tileset3d allumé)", () => {
  test("le tiroir « Nouveau tileset 3D » : focus piégé, Échap referme et rend le focus, axe propre en clair et en sombre", async ({
    browser,
  }) => {
    for (const scheme of ["light", "dark"] as const) {
      const { ctx, page } = await session(browser, "creator", scheme);
      const trigger = page.getByRole("button", { name: "Nouveau tileset 3D" });
      await trigger.focus();
      await page.keyboard.press("Enter");
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      expect(await seriousViolations(page), scheme).toEqual([]);
      for (let i = 0; i < 6; i++) {
        await page.keyboard.press("Tab");
        expect(await page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"))).toBe(
          true,
        );
      }
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await ctx.close();
    }
  });

  // Envoi simulé (le multipart réel est cassé : j10b-012) : création/presign/PUT/complete sont
  // interceptés côté navigateur pour figer la phase « validation ».
  async function uploadWithMockedCore(page: import("@playwright/test").Page) {
    await page.route("**/v1/tileset3d/uploads", (r) =>
      r.fulfill({ status: 201, contentType: "application/json", body: '{"jobId":"job-t01b"}' }),
    );
    await page.route("**/v1/tileset3d/uploads/job-t01b/parts/*/presign", (r) =>
      r.fulfill({
        contentType: "application/json",
        body: '{"uploadUrl":"http://127.0.0.1:9/put-t01b"}',
      }),
    );
    await page.route("http://127.0.0.1:9/put-t01b", (r) =>
      r.fulfill({
        status: 200,
        headers: { ETag: '"abc"', "access-control-expose-headers": "ETag" },
        body: "",
      }),
    );
    await page.route(
      "**/v1/tileset3d/uploads/job-t01b/complete",
      () => new Promise(() => undefined),
    );
    await page.getByRole("button", { name: "Nouveau tileset 3D" }).click();
    await page.getByLabel("Archive du tileset (.zip)").setInputFiles({
      name: "t.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("PK\u0005\u0006" + "\u0000".repeat(18)),
    });
    await page.getByLabel("Titre", { exact: true }).fill("t01b-tileset");
    await page.getByRole("button", { name: /^Envoyer$|^Importer$|^Créer$/ }).click();
  }

  // t01b-014 : finding. Progression « x / y » et « Validation… » sont des <p> inertes.
  test("t01b-014 : la progression d'envoi et la phase de validation sont annoncées (role=status / aria-live)", async ({
    browser,
  }) => {
    const { ctx, page } = await session(browser, "creator");
    await uploadWithMockedCore(page);
    const validating = page.getByText(/Validation/i);
    await expect(validating).toBeVisible();
    const live = await validating.evaluate(
      (e) => !!e.closest("[role=status],[role=alert],[aria-live]"),
    );
    expect(live).toBe(true);
    await ctx.close();
  });

  // t01b-015 : finding. Le bouton est conditionné par la capacité, pas par le privilège.
  test("t01b-015 : un lecteur (sans droit d'écriture) ne voit pas « Nouveau tileset 3D »", async ({
    browser,
  }) => {
    const { ctx, page } = await session(browser, "reader");
    await expect(page.getByRole("button", { name: "Nouveau tileset 3D" })).toHaveCount(0);
    await ctx.close();
  });
});
