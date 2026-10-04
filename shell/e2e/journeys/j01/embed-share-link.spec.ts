import { test, expect, type Page } from "@playwright/test";
import { CORE_URL } from "../_fixtures/env";
import { apiFor, type Api } from "../j03/api";
import { appConfig, mkItem, TAG } from "../j13/helpers";
import { psql } from "../j02/helpers";

// P14.14 (j01-010) : un Créateur crée un lien de partage à échéance, un
// visiteur ANONYME le rejoue sur /embed/:token — nominal, expiré, révoqué.
// Visiteur anonyme = page sans login (aucun persona), comme j01/anonymous.
const TEXT = "Contenu embed j01-010";
const EXPIRED_OR_REVOKED = "Ce lien de partage est expiré ou révoqué.";

let creator: Api;
test.beforeAll(async () => {
  creator = await apiFor("creator");
});

async function embeddableApp(title: string) {
  const config = {
    ...appConfig(),
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: TEXT } }],
    },
  };
  return mkItem(creator, title, config);
}

async function createLink(pk: string): Promise<{ token: string; id: string }> {
  const r = await creator.send("POST", `/v1/items/${pk}/share-links`, { ttlDays: 1 });
  expect(r.status).toBe(201);
  const list = await creator.get(`/v1/items/${pk}/share-links`);
  expect(list.status).toBe(200);
  expect(list.body).toHaveLength(1);
  return { token: r.body.token as string, id: list.body[0].id as string };
}

async function resolveAnon(token: string): Promise<number> {
  const doFetch = () => fetch(`${CORE_URL}/v1/share-links/${encodeURIComponent(token)}`);
  const r = await doFetch().catch(() => doFetch());
  await r.text();
  return r.status;
}

function trackAuthorization(page: Page) {
  const withAuth: string[] = [];
  page.on("request", (req) => {
    if (req.url().startsWith(CORE_URL) && "authorization" in req.headers()) {
      withAuth.push(req.url());
    }
  });
  return withAuth;
}

test.describe("j01-010 lien de partage à échéance rejoué en anonyme", () => {
  test("nominal : l'embed rend l'app sans jamais envoyer Authorization", async ({ page }) => {
    const it = await embeddableApp(`${TAG}-embed-ok`);
    const { token } = await createLink(it.pk);
    expect(await resolveAnon(token)).toBe(200);
    const withAuth = trackAuthorization(page);
    await page.goto(`/embed/${token}`);
    await expect(page.getByText(TEXT)).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    expect(withAuth).toEqual([]);
  });

  test("expiré : la ligne expirée prime sur le TTL encore valide du jeton → 401 et message", async ({
    page,
  }) => {
    const it = await embeddableApp(`${TAG}-embed-exp`);
    const { token, id } = await createLink(it.pk);
    expect(await resolveAnon(token)).toBe(200);
    psql(
      `UPDATE share_link SET expires_at = (now() at time zone 'utc') - interval '1 hour' WHERE id = '${id}'`,
    );
    expect(await resolveAnon(token)).toBe(401);
    const withAuth = trackAuthorization(page);
    await page.goto(`/embed/${token}`);
    await expect(page.getByRole("alert")).toHaveText(EXPIRED_OR_REVOKED);
    await expect(page.getByText(TEXT)).toHaveCount(0);
    expect(withAuth).toEqual([]);
  });

  test("révoqué : un lien qui fonctionnait cesse de résoudre dès la révocation", async ({
    page,
  }) => {
    const it = await embeddableApp(`${TAG}-embed-rev`);
    const { token, id } = await createLink(it.pk);
    expect(await resolveAnon(token)).toBe(200);
    expect((await creator.send("DELETE", `/v1/items/${it.pk}/share-links/${id}`)).status).toBe(204);
    expect(await resolveAnon(token)).toBe(401);
    const withAuth = trackAuthorization(page);
    await page.goto(`/embed/${token}`);
    await expect(page.getByRole("alert")).toHaveText(EXPIRED_OR_REVOKED);
    await expect(page.getByText(TEXT)).toHaveCount(0);
    expect(withAuth).toEqual([]);
  });
});
