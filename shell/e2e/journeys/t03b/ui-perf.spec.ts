/* eslint-disable @typescript-eslint/no-explicit-any -- sondes navigateur */
import { test, expect, type Page } from "@playwright/test";
import { loginOidc, SHELL_URL } from "../_fixtures/env";
import { installVitals, netLog, readVitals } from "../t03/helpers";
import {
  apiFor,
  token,
  createPipeline,
  edge,
  exportWriter,
  getBigSeed,
  getPlainBig,
  reader,
  stamp,
  type PNode,
} from "./helpers";

interface Nav {
  readyMs: number;
  shellKb: number;
  jsFiles: string[];
  clsDelta: number;
  longTaskMs: number;
}

// Navigation SPA (pushState) depuis la page courante : temps jusqu'au premier titre visible,
// octets du shell réellement transférés (chunks de route inclus), décalage de mise en page.
async function softNav(page: Page, path: string, ready = "h1"): Promise<Nav> {
  const log = await netLog(page);
  const before = await readVitals(page);
  const t0 = Date.now();
  await page.evaluate((p) => {
    window.history.pushState({}, "", p);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
  await page.locator(ready).first().waitFor({ state: "visible", timeout: 30_000 });
  const readyMs = Date.now() - t0;
  await page.waitForTimeout(2000);
  const n = await log.stop();
  const after = await readVitals(page);
  const shell = n.byUrl.filter((r) => r.url.startsWith(SHELL_URL));
  return {
    readyMs,
    shellKb: Math.round(shell.reduce((s, r) => s + r.kb, 0)),
    jsFiles: shell
      .filter((r) => /\.m?js$/.test(r.url))
      .map((r) => `${r.url.split("/").pop()}:${r.kb}`),
    clsDelta: after.cls - before.cls,
    longTaskMs: Math.round(after.longTaskMs - before.longTaskMs),
  };
}

let pipeline500k = "";
const tag = stamp("t03b");

test.beforeAll(async () => {
  test.setTimeout(300_000);
  const creator = await apiFor("creator");
  const plain = await getPlainBig(500_000);
  const nodes: PNode[] = [
    reader(plain.id),
    { id: "f", kind: "transform", op: "transform.filter", params: { expr: "val > 990" } },
    exportWriter(`t03b/${tag}-ui.csv`),
  ];
  const p = await createPipeline(creator, `${tag}-ui500k`, nodes, [edge("r", "f"), edge("f", "w")]);
  pipeline500k = p.itemId!;
});

test.describe("t03b bundle et écrans pipeline / admin (navigation SPA, cache chaud du shell)", () => {
  test.beforeEach(async ({ page }) => {
    await installVitals(page);
  });

  test("éditeur de pipeline (canevas) : prêt en moins de 4 s, CLS < 0,1, chunk de route mesuré", async ({
    page,
  }) => {
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    const r = await softNav(
      page,
      `/pipelines/${pipeline500k}/edit`,
      "[data-testid='pipeline-canvas'], .react-flow, h1",
    );
    console.log("T03B ui pipeline", JSON.stringify(r));
    expect(r.readyMs).toBeLessThan(4000);
    expect(r.clsDelta).toBeLessThan(0.1);
  });

  test("écrans d'administration (admin) : chacun prêt en moins de 3 s sans décalage de mise en page", async ({
    page,
  }) => {
    await loginOidc(page, "admin");
    await page.waitForTimeout(1500);
    const rows: string[] = [];
    const slow: string[] = [];
    const shifty: string[] = [];
    for (const path of [
      "/admin/users",
      "/admin/collections",
      "/admin/roles",
      "/admin/infrastructure",
      "/admin/harvest",
      "/admin/extensions",
      "/tasks",
      "/analytics/sql",
    ]) {
      const r = await softNav(page, path).catch((e) => {
        rows.push(`${path} ECHEC ${String(e).slice(0, 80)}`);
        return null;
      });
      if (!r) continue;
      rows.push(
        `${path} ${r.readyMs}ms ${r.shellKb}Ko cls=${r.clsDelta.toFixed(3)} lt=${r.longTaskMs}ms js=${r.jsFiles.join("|")}`,
      );
      if (r.readyMs >= 3000) slow.push(`${path} ${r.readyMs}ms`);
      if (r.clsDelta >= 0.1) shifty.push(`${path} ${r.clsDelta.toFixed(3)}`);
    }
    console.log("T03B ui admin\n" + rows.join("\n"));
    expect(rows.filter((x) => x.includes("ECHEC"))).toEqual([]);
    expect(slow).toEqual([]);
    expect(shifty).toEqual([]);
  });

  test("fiche publique d'un dataset de 500 000 entités : le lien GeoJSON est borné à 1 000 entités (t03-007 confirmé)", async ({
    page,
  }) => {
    const big = await getBigSeed(500_000);
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    await softNav(page, `/public/datasets/${big.collectionId}`);
    const link = page.getByRole("link", { name: /geojson/i }).first();
    await link.waitFor({ state: "visible", timeout: 20_000 });
    const href = (await link.getAttribute("href")) ?? "";
    console.log("T03B geojsonLink", href);
    expect(href).toContain("limit=1000");
    const res = await fetch(href, {
      headers: { authorization: `Bearer ${await token("creator")}` },
    });
    const body = (await res.json()) as any;
    console.log("T03B geojsonLien", res.status, body.features?.length, "sur", body.numberMatched);
    expect(body.features).toHaveLength(1000);
  });

  test("t03b-005 : le lien GeoJSON d'un dataset de 10 000 entités signale la troncature à 1 000 (P29.03)", async ({
    page,
  }) => {
    const s = await getBigSeed(10_000);
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    await softNav(page, `/public/datasets/${s.collectionId}`);
    await page
      .getByRole("link", { name: /geojson/i })
      .first()
      .waitFor({ state: "visible", timeout: 20_000 });
    await expect(page.getByText(/1000 premières entités sur 10000/)).toBeVisible();
  });
});
