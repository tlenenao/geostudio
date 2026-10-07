/* eslint-disable @typescript-eslint/no-explicit-any -- sondes navigateur */
import { test, expect, type Page } from "@playwright/test";
import { loginOidc, stamp } from "../_fixtures/env";
import {
  apiFor,
  createMap,
  getBigSeed,
  installVitals,
  netLog,
  readVitals,
  stubBasemap,
  type Vitals,
} from "./helpers";

const LCP_GOOD = 2500;
const CLS_GOOD = 0.1;

// Émule « 4G lente » + CPU ×4 (profil Lighthouse mobile) via CDP.
async function throttle(page: Page): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 150,
    downloadThroughput: (1.6 * 1024 * 1024) / 8,
    uploadThroughput: (750 * 1024) / 8,
  });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  // Premier visiteur : cache HTTP désactivé (sans Cache-Control, le cache heuristique fausse le « à froid »).
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
}

async function coldLoad(
  page: Page,
  path: string,
  settleMs = 3000,
): Promise<{ v: Vitals; kb: number; requests: number }> {
  const log = await netLog(page);
  await page.goto(path);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(settleMs);
  const n = await log.stop();
  const finalUrl = page.url();
  if (!finalUrl.startsWith("http://localhost:8300")) throw new Error(`redirigé vers ${finalUrl}`);
  const shellKb = n.byUrl
    .filter((r) => r.url.startsWith("http://localhost:8300"))
    .reduce((a, r) => a + r.kb, 0);
  return { v: await readVitals(page), kb: Math.round(shellKb), requests: n.requests };
}

function note(testInfo: any, label: string, r: { v: Vitals; kb: number; requests: number }) {
  const d = `${label} LCP=${Math.round(r.v.lcp ?? -1)}ms(${r.v.lcpTag}) FCP=${Math.round(r.v.fcp ?? -1)}ms CLS=${r.v.cls.toFixed(3)} longTasks=${r.v.longTasks}/${Math.round(r.v.longTaskMs)}ms shell=${r.kb}Ko req=${r.requests}`;
  testInfo.annotations.push({ type: "mesure", description: d });
  console.log("T03 " + d);
}

// Un rechargement dur d'une route authentifiée repasse par Keycloak et retombe sur « / »
// (j02-004) : LCP n'a donc de sens à froid que pour le catalogue. Pour les autres
// routes on mesure la navigation SPA depuis le catalogue, telle que l'utilisateur la vit.
interface Soft {
  readyMs: number;
  clsDelta: number;
  longTasks: number;
  longTaskMs: number;
}

async function softNav(page: Page, path: string, ready: string, timeout = 30_000): Promise<Soft> {
  const before = await readVitals(page);
  const t0 = Date.now();
  await page.evaluate((p) => {
    window.history.pushState({}, "", p);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
  await page.locator(ready).first().waitFor({ state: "visible", timeout });
  const readyMs = Date.now() - t0;
  await page.waitForTimeout(2500);
  const after = await readVitals(page);
  return {
    readyMs,
    clsDelta: after.cls - before.cls,
    longTasks: after.longTasks - before.longTasks,
    longTaskMs: Math.round(after.longTaskMs - before.longTaskMs),
  };
}

function noteSoft(testInfo: any, label: string, r: Soft) {
  const d = `${label} prêt=${r.readyMs}ms CLS=${r.clsDelta.toFixed(3)} longTasks=${r.longTasks}/${r.longTaskMs}ms`;
  testInfo.annotations.push({ type: "mesure", description: d });
  console.log("T03 " + d);
}

test.describe("t03 LCP / CLS", () => {
  let mapPk = "";
  let bigMapPk = "";
  let appPk = "";

  test.beforeAll(async () => {
    const creator = await apiFor("creator");
    const s50 = await getBigSeed(50_000);
    const s500 = await getBigSeed(500_000);
    mapPk = await createMap(creator, `${stamp("t03")}-carte-vide`, null);
    bigMapPk = await createMap(creator, `${stamp("t03")}-carte-500k`, s500.collectionId);
    const cfg = {
      version: 1,
      kind: "app",
      theme: {},
      dataSources: [
        { id: "s1", type: "features", service: "core", layer: s50.collectionId, query: {} },
      ],
      messages: [],
      layout: {
        type: "grid",
        breakpoints: {},
        items: [
          { id: "tbl", widget: "table", x: 0, y: 0, w: 12, h: 8, props: { dataSourceId: "s1" } },
        ],
      },
    };
    const r = await creator.send("POST", "/v1/configs", {
      title: `${stamp("t03")}-app-table-50k`,
      config: cfg,
    });
    if (r.status !== 201) throw new Error(`app ${r.status}`);
    appPk = r.body.itemId;
  });

  test.beforeEach(async ({ page }) => {
    await installVitals(page);
    await stubBasemap(page);
  });

  test("catalogue à froid : LCP et CLS dans les seuils « bon »", async ({ page }, testInfo) => {
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    const r = await coldLoad(page, "/");
    note(testInfo, "catalogue", r);
    expect(r.v.lcp).not.toBeNull();
    expect(r.v.lcp as number).toBeLessThan(LCP_GOOD);
    expect(r.v.cls).toBeLessThan(CLS_GOOD);
  });

  // Profil Lighthouse mobile (4G lente, CPU x4). LCP mesuré : ~4,64 s ; 2,6 s quand vendor-map est bloqué
  // (carte MapLibre du filtre spatial) : voir t03-005.
  test("t03-005 : catalogue à froid sous 4G lente + CPU x4 : LCP sous 4 s", async ({
    page,
  }, testInfo) => {
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    await throttle(page);
    const r = await coldLoad(page, "/", 6000);
    note(testInfo, "catalogue-4g", r);
    expect(r.v.lcp as number).toBeLessThan(4000);
  });

  test("éditeur de carte (vide) : prêt en moins de 3 s, CLS < 0,1", async ({ page }, testInfo) => {
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    const r = await softNav(page, `/maps/${mapPk}`, ".maplibregl-canvas");
    noteSoft(testInfo, "carte-vide", r);
    expect(r.readyMs).toBeLessThan(3000);
    expect(r.clsDelta).toBeLessThan(CLS_GOOD);
  });

  test("carte à 500 000 entités : prête en moins de 3 s, CLS < 0,1", async ({ page }, testInfo) => {
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    const r = await softNav(page, `/maps/${bigMapPk}`, ".maplibregl-canvas");
    noteSoft(testInfo, "carte-500k", r);
    expect(r.readyMs).toBeLessThan(3000);
    expect(r.clsDelta).toBeLessThan(CLS_GOOD);
  });

  test("builder d'app (table 50 000 lignes) : prêt en moins de 3 s, CLS < 0,1", async ({
    page,
  }, testInfo) => {
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    const r = await softNav(page, `/apps/${appPk}/edit`, "table");
    noteSoft(testInfo, "builder-50k", r);
    expect(r.readyMs).toBeLessThan(3000);
    expect(r.clsDelta).toBeLessThan(CLS_GOOD);
  });

  test("runtime d'app (table 50 000 lignes) : prêt en moins de 3 s, CLS < 0,1", async ({
    page,
  }, testInfo) => {
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    const r = await softNav(page, `/apps/${appPk}`, "table");
    noteSoft(testInfo, "runtime-50k", r);
    expect(r.readyMs).toBeLessThan(3000);
    expect(r.clsDelta).toBeLessThan(CLS_GOOD);
  });
});
