/* eslint-disable @typescript-eslint/no-explicit-any -- sondes navigateur */
import { bug } from "../_fixtures/verify";
import { test, expect, type Page } from "@playwright/test";
import { loginOidc, stamp } from "../_fixtures/env";
import { spaGo } from "../j02/helpers";
import { apiFor, createMap, stubMapEnv } from "./helpers";

const POLL_URL = /\/v1\/notifications\/unread-count/;

function countPolls(page: Page): { n: () => number; times: () => number[] } {
  const t: number[] = [];
  page.on("request", (r) => {
    if (POLL_URL.test(r.url())) t.push(Date.now());
  });
  return { n: () => t.length, times: () => [...t] };
}

async function gcMetrics(
  page: Page,
): Promise<{ heapMb: number; nodes: number; listeners: number }> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  await cdp.send("HeapProfiler.enable");
  await cdp.send("HeapProfiler.collectGarbage");
  await page.waitForTimeout(300);
  await cdp.send("HeapProfiler.collectGarbage");
  const { metrics } = await cdp.send("Performance.getMetrics");
  await cdp.detach();
  const m = Object.fromEntries(metrics.map((x: any) => [x.name, x.value]));
  return {
    heapMb: Math.round((m.JSHeapUsedSize / 1048576) * 10) / 10,
    nodes: m.Nodes,
    listeners: m.JSEventListeners,
  };
}

test.describe("t03 sondages et démontage", () => {
  test("cloche de notifications : un sondage toutes les 45 s (±1) sur 100 s", async ({
    page,
  }, testInfo) => {
    test.setTimeout(150_000);
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    const polls = countPolls(page);
    await page.waitForTimeout(100_000);
    const times = polls.times();
    const gaps = times.slice(1).map((x, i) => Math.round((x - times[i]) / 1000));
    testInfo.annotations.push({
      type: "mesure",
      description: `${polls.n()} sondages en 100 s, écarts ${gaps.join(",")} s`,
    });
    console.log("T03 polls", polls.n(), JSON.stringify(gaps));
    expect(polls.n()).toBeGreaterThanOrEqual(2);
    expect(polls.n()).toBeLessThanOrEqual(3);
    for (const g of gaps) expect(g).toBeGreaterThanOrEqual(40);
  });

  test("onglet masqué : le sondage des notifications est suspendu", async ({ page }) => {
    test.setTimeout(120_000);
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", { get: () => "hidden" });
      Object.defineProperty(document, "hidden", { get: () => true });
      document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
    });
    const polls = countPolls(page);
    await page.waitForTimeout(95_000);
    expect(polls.n()).toBe(0);
  });

  test("retour au premier plan : rafraîchissement immédiat du compteur", async ({ page }) => {
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    const polls = countPolls(page);
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", {
        get: () => "hidden",
        configurable: true,
      });
      document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
      Object.defineProperty(document, "visibilityState", {
        get: () => "visible",
        configurable: true,
      });
      document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
    });
    await page.waitForTimeout(2000);
    expect(polls.n()).toBeGreaterThanOrEqual(1);
  });

  const leak = async (page: Page, testInfo: any, withMap: boolean) => {
    test.setTimeout(240_000);
    const creator = await apiFor("creator");
    const pk = await createMap(creator, `${stamp("t03")}-carte-fuite`, null);
    await stubMapEnv(page);
    await page.addInitScript(() => {
      const w = window as any;
      w.__gl = { created: 0, lost: 0, intervals: 0, cleared: 0 };
      const orig = HTMLCanvasElement.prototype.getContext;
      (HTMLCanvasElement.prototype as any).getContext = function (type: string, ...a: any[]) {
        const ctx = (orig as any).call(this, type, ...a);
        if (ctx && /webgl/.test(type) && !(ctx as any).__t) {
          (ctx as any).__t = true;
          w.__gl.created++;
          const ge = ctx.getExtension.bind(ctx);
          ctx.getExtension = (n: string) => {
            const e = ge(n);
            if (n === "WEBGL_lose_context" && e && !e.__w) {
              const lc = e.loseContext.bind(e);
              e.loseContext = () => {
                w.__gl.lost++;
                lc();
              };
              e.__w = true;
            }
            return e;
          };
        }
        return ctx;
      };
      const si = window.setInterval.bind(window);
      const ci = window.clearInterval.bind(window);
      const live = new Set<number>();
      (window as any).setInterval = (...a: any[]) => {
        const id = (si as any)(...a);
        live.add(id);
        w.__gl.intervals = live.size;
        return id;
      };
      (window as any).clearInterval = (id: number) => {
        live.delete(id);
        w.__gl.intervals = live.size;
        return ci(id);
      };
    });
    await loginOidc(page, "creator");
    await page.waitForTimeout(1500);
    const cycle = async () => {
      if (withMap) await spaGo(page, `/maps/${pk}`, 1800);
      else await spaGo(page, "/reports", 800);
      await spaGo(page, "/settings", 800);
      await spaGo(page, "/", 1500);
    };
    for (let i = 0; i < 2; i++) await cycle();
    const base = await gcMetrics(page);
    const baseGl = await page.evaluate(() => (window as any).__gl);
    for (let i = 0; i < 8; i++) await cycle();
    const end = await gcMetrics(page);
    const endGl = await page.evaluate(() => (window as any).__gl);
    const canvases = await page.locator(".maplibregl-canvas").count();
    const d = {
      heapMb: +(end.heapMb - base.heapMb).toFixed(1),
      nodes: end.nodes - base.nodes,
      listeners: end.listeners - base.listeners,
      glCreated: endGl.created - baseGl.created,
      glLost: endGl.lost - baseGl.lost,
      intervalsLive: endGl.intervals,
      canvasesOnCatalogue: canvases,
    };
    testInfo.annotations.push({ type: "mesure", description: JSON.stringify({ base, ...d }) });
    console.log("T03 leak", JSON.stringify({ base, end, ...d }));
    expect(d.heapMb).toBeLessThan(15);
    expect(d.nodes).toBeLessThan(400);
    expect(d.listeners).toBeLessThan(200);
    expect(d.glLost).toBeGreaterThanOrEqual(d.glCreated - 1);
    expect(d.intervalsLive).toBeLessThan(6);
  };

  test("navigation catalogue / rapports / paramètres x8 : pas de fuite (tas, nœuds, écouteurs, WebGL)", async ({
    page,
  }, testInfo) => {
    await leak(page, testInfo, false);
  });

  // Mesuré : +3984 nœuds DOM, +296 écouteurs, +4,7 Mo de tas sur 8 ouvertures de l'éditeur de carte
  // (catalogue et paramètres seuls : 0).
  bug(
    "t03-012 : ouvrir/fermer l'éditeur de carte ne retient ni nœuds DOM ni écouteurs",
    async ({ page }, testInfo) => {
      await leak(page, testInfo, true);
    },
  );
});
