// SPDX-License-Identifier: Apache-2.0
// P30.01 (t03-012) : ouvrir/fermer l'éditeur de carte ne retient ni nœuds DOM ni
// écouteurs. Cause trouvée par heap snapshot : le CanvasContext luma.gl attaché
// par deck.gl (interleaved) laissait un écouteur matchMedia (DPR) retenir le canvas.
import { expect, test, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function metrics(page: Page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  await cdp.send("HeapProfiler.enable");
  await cdp.send("HeapProfiler.collectGarbage");
  await page.waitForTimeout(300);
  await cdp.send("HeapProfiler.collectGarbage");
  const { metrics: m } = await cdp.send("Performance.getMetrics");
  await cdp.detach();
  const o = Object.fromEntries(m.map((x) => [x.name, x.value]));
  return { nodes: o.Nodes as number, listeners: o.JSEventListeners as number };
}

async function spaGo(page: Page, path: string) {
  await page.evaluate((p) => {
    window.history.pushState({}, "", p);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
  await page.waitForTimeout(1200);
}

test("8 ouvertures de l'éditeur de carte : pas de croissance de nœuds ni d'écouteurs", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await mockCore(page);
  await page.goto("/maps/map-1");
  const canvas = page.locator("canvas.maplibregl-canvas");
  await expect(canvas).toHaveCount(1);
  const cycle = async () => {
    await spaGo(page, "/settings");
    await spaGo(page, "/maps/map-1");
    // Garde-fou : la carte est bien remontée (sinon le test ne prouve rien).
    await expect(canvas).toHaveCount(1);
  };
  for (let i = 0; i < 2; i++) await cycle();
  await spaGo(page, "/settings");
  const base = await metrics(page);
  for (let i = 0; i < 8; i++) {
    await cycle();
    await spaGo(page, "/settings");
  }
  const end = await metrics(page);
  expect(end.nodes - base.nodes).toBeLessThan(400);
  expect(end.listeners - base.listeners).toBeLessThan(200);
});
