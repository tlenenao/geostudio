import { test, expect, type Page } from "@playwright/test";
import { getSeed } from "./seed";
import { loginOidc } from "../_fixtures/env";
import { seedNotifications } from "./helpers";

test.setTimeout(90_000);

async function openBell(page: Page) {
  await page.getByRole("button", { name: "Notifications" }).first().click();
  await page.waitForTimeout(800);
}

test.describe("j02 lecteur — notifications in-app", () => {
  test("liste : pastille = non lues, succès/échec distingués, message d'erreur rendu comme texte", async ({
    page,
  }) => {
    const s = await getSeed();
    seedNotifications(s.readerId, s.sharedDataset, s.sharedApp, s.tag);
    await loginOidc(page, "reader");
    await page.waitForTimeout(1500);
    expect((await s.reader.get("/v1/notifications/unread-count")).body.count).toBe(2);
    await expect(page.getByRole("button", { name: "Notifications" }).first()).toContainText("2");
    await openBell(page);
    await expect(page.getByText(`${s.tag}-notif-ok`)).toBeVisible();
    await expect(page.getByText(`${s.tag}-notif-ko`)).toBeVisible();
    await expect(page.getByText("boom <b>html</b>")).toBeVisible();
    expect(await page.locator("b", { hasText: "html" }).count()).toBe(0);
  });

  test("un clic sur une notification la marque lue et ouvre l'élément", async ({ page }) => {
    const s = await getSeed();
    seedNotifications(s.readerId, s.sharedDataset, s.sharedApp, s.tag);
    await loginOidc(page, "reader");
    await page.waitForTimeout(1500);
    await openBell(page);
    await page.getByText(`${s.tag}-notif-ok`).click();
    await page.waitForTimeout(2500);
    expect((await s.reader.get("/v1/notifications/unread-count")).body.count).toBe(1);
    expect(page.url()).toContain(`/datasets/${s.sharedDataset}/edit`);
  });

  // j02-013 : le déclencheur et le sélecteur de préférence portent le même nom accessible.
  test.fixme("j02-013 : la cloche et le sélecteur de préférence ont des noms accessibles distincts", async ({
    page,
  }) => {
    await loginOidc(page, "reader");
    await page.waitForTimeout(1500);
    await openBell(page);
    await expect(page.getByLabel("Notifications", { exact: true })).toHaveCount(1);
  });

  // j02-014 : aucune distinction visuelle/sémantique entre notification lue et non lue.
  test.fixme("j02-014 : une notification lue se distingue d'une non lue dans la liste", async ({
    page,
  }) => {
    const s = await getSeed();
    seedNotifications(s.readerId, s.sharedDataset, s.sharedApp, s.tag);
    const list = await s.reader.get("/v1/notifications");
    const ok = list.body.notifications.find(
      (n: { itemTitle: string }) => n.itemTitle === `${s.tag}-notif-ok`,
    );
    await s.reader.send("POST", `/v1/notifications/${ok.id}/read`);
    await loginOidc(page, "reader");
    await page.waitForTimeout(1500);
    await openBell(page);
    const attrs = async (title: string) =>
      page
        .getByRole("button", { name: new RegExp(title) })
        .evaluate(
          (el) =>
            [...el.attributes].map((a) => `${a.name}=${a.value}`).join(";") +
            "|" +
            el.querySelector("span.text-sm")?.className,
        );
    expect(await attrs(`${s.tag}-notif-ok`)).not.toEqual(await attrs(`${s.tag}-notif-ko`));
  });
});
