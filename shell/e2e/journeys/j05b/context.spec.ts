import { bug } from "../_fixtures/verify";
import { expect, test } from "@playwright/test";
import { loginOidc, stamp } from "../_fixtures/env";
import { spaGo } from "../j04/helpers";
import { apiFor, getSeed, type Seed } from "./helpers";

let seed: Seed;
let appId: string;

function enc(state: unknown): string {
  return Buffer.from(JSON.stringify(state), "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

test.beforeAll(async () => {
  test.setTimeout(300_000);
  seed = await getSeed();
  const creator = await apiFor("creator");
  const ds = await creator.send("POST", "/v1/configs", {
    title: `${stamp("j05b")}-ds`,
    config: {
      version: 1,
      kind: "dataset",
      dataset: {
        source: "collection",
        collectionId: seed.ventes,
        columns: {},
        timeField: "d",
        reactsToExtent: false,
      },
    },
  });
  if (ds.status !== 201) throw new Error(`dataset ${ds.status} ${JSON.stringify(ds.body)}`);
  const app = await creator.send("POST", "/v1/configs", {
    title: `${stamp("j05b")}-ctx-app`,
    config: {
      version: 1,
      kind: "app",
      theme: {},
      interactions: "auto",
      dataSources: [
        {
          id: "s1",
          type: "features",
          service: "core",
          layer: seed.ventes,
          datasetId: ds.body.itemId,
          query: {},
        },
      ],
      messages: [],
      layout: {
        type: "grid",
        breakpoints: {},
        items: [
          { id: "tbl", widget: "table", x: 0, y: 0, w: 12, h: 8, props: { dataSourceId: "s1" } },
        ],
      },
    },
  });
  if (app.status !== 201) throw new Error(`app ${app.status} ${JSON.stringify(app.body)}`);
  appId = app.body.itemId;
  await creator.send("PATCH", `/v1/items/${appId}`, { isPublished: true });
});

async function itemsRequests(
  page: import("@playwright/test").Page,
  ctx: unknown,
): Promise<{ url: string; status: number; n: number | null }[]> {
  const seen: { url: string; status: number; n: number | null }[] = [];
  page.on("response", async (r) => {
    if (r.url().includes(`/collections/${seed.ventes}/items`) && r.request().method() === "GET") {
      let n: number | null = null;
      try {
        n = ((await r.json()) as { features?: unknown[] }).features?.length ?? null;
      } catch {
        /* corps non JSON */
      }
      seen.push({ url: r.url(), status: r.status(), n });
    }
  });
  await loginOidc(page, "creator");
  await page.waitForTimeout(800);
  await spaGo(page, `/apps/${appId}?ctx=${enc(ctx)}`, 5000);
  return seen;
}

test.describe("j05b contexte analytique global (temps × emprise) — exécution réelle", () => {
  test("plage temporelle ISO complète : la table est filtrée sur le champ temporel du dataset", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const seen = await itemsRequests(page, {
      timeRange: { from: "2026-01-01T00:00:00Z", to: "2026-12-31T23:59:59Z" },
      extent: null,
      crossFilter: {},
    });
    const filtered = seen.find((r) => r.url.includes("d__gte="));
    expect(filtered?.status).toBe(200);
    expect(filtered?.n).toBe(30);
    await expect(page.getByRole("cell", { name: "n30", exact: true })).toBeVisible();
  });

  // Finding j05b-007 : confirme j05-024 par exécution (même défaut que j05-003, sur /items).
  bug(
    "j05b-007 : plage temporelle à bornes « YYYY-MM-DD » identiques : retient les lignes du jour",
    async ({ page }) => {
      test.setTimeout(120_000);
      const seen = await itemsRequests(page, {
        timeRange: { from: "2026-03-15", to: "2026-03-15" },
        extent: null,
        crossFilter: {},
      });
      // Seed : date = <année>-<mois>-15T10:00:00Z ; 2026-03-15 -> i = 32 (un seul) ; attendu >= 1.
      const filtered = seen.find((r) => r.url.includes("d__gte="));
      expect(filtered?.n).toBeGreaterThan(0);
    },
  );

  test("contexte ?ctx= illisible : l'app s'affiche sans filtre (pas d'écran blanc)", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const seen: number[] = [];
    page.on("response", (r) => {
      if (r.url().includes(`/collections/${seed.ventes}/items`)) seen.push(r.status());
    });
    await loginOidc(page, "creator");
    await page.waitForTimeout(800);
    await spaGo(page, `/apps/${appId}?ctx=%%%not-base64`, 4000);
    await expect(page.locator("body")).not.toContainText("Application error");
    expect(seen.length).toBeGreaterThan(0);
    expect(seen[seen.length - 1]).toBe(200);
  });
});
