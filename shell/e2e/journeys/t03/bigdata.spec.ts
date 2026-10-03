/* eslint-disable @typescript-eslint/no-explicit-any -- sondes navigateur */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { CORE_URL, loginOidc, stamp } from "../_fixtures/env";
import { spaGo } from "../j02/helpers";
import { FIND_MAP } from "../j12/helpers";
import { token } from "../j03/api";
import { apiFor, createMap, getBigSeed, stubBasemap, type BigSeed } from "./helpers";

// Jeux de données créés par POST /v1/collections/empty puis INSERT ... generate_series
// dans la table de la collection (le présigné d'upload répond 500, j03-001).
let s50: BigSeed;
let s500: BigSeed;

async function timed(
  persona: "creator" | "reader",
  path: string,
  init: { method?: string; body?: unknown; accept?: string } = {},
): Promise<{ status: number; ms: number; bytes: number; headers: Headers; text: () => string }> {
  const tok = await token(persona);
  const t0 = performance.now();
  const r = await fetch(`${CORE_URL}${path}`, {
    method: init.method ?? "GET",
    headers: {
      authorization: `Bearer ${tok}`,
      ...(init.body ? { "content-type": "application/json" } : {}),
    },
    body: init.body ? JSON.stringify(init.body) : undefined,
  });
  const buf = Buffer.from(await r.arrayBuffer());
  return {
    status: r.status,
    ms: Math.round(performance.now() - t0),
    bytes: buf.length,
    headers: r.headers,
    text: () => buf.toString("utf8"),
  };
}

test.beforeAll(async () => {
  test.setTimeout(300_000);
  s50 = await getBigSeed(50_000);
  s500 = await getBigSeed(500_000);
});

test.describe("t03 API sur 50 000 et 500 000 entités", () => {
  test("GET /items : page de 1000 sur 500k en moins de 500 ms, numberMatched exact", async () => {
    const r = await timed("creator", `/v1/collections/${s500.collectionId}/items?limit=1000`);
    console.log("T03 items500k", r.status, r.ms, "ms", r.bytes, "B");
    expect(r.status).toBe(200);
    expect(r.ms).toBeLessThan(500);
    expect(JSON.parse(r.text()).numberMatched).toBe(500_000);
  });

  test("GET /items : offset profond (490 000) sur 500k en moins de 1 s", async () => {
    const r = await timed(
      "creator",
      `/v1/collections/${s500.collectionId}/items?limit=1000&offset=490000`,
    );
    console.log("T03 offset490k", r.ms, "ms");
    expect(r.status).toBe(200);
    expect(r.ms).toBeLessThan(1000);
    expect(JSON.parse(r.text()).numberReturned).toBe(1000);
  });

  test("GET /items?bbox : petite emprise sur 500k en moins de 500 ms (index GiST)", async () => {
    const r = await timed(
      "creator",
      `/v1/collections/${s500.collectionId}/items?bbox=2,48,2.5,48.5&limit=1000`,
    );
    console.log("T03 bbox500k", r.ms, "ms");
    expect(r.status).toBe(200);
    expect(r.ms).toBeLessThan(500);
  });

  test("POST /aggregate : comptage par catégorie sur 500k en moins de 1 s", async () => {
    const r = await timed("creator", `/v1/collections/${s500.collectionId}/aggregate`, {
      method: "POST",
      body: { groupBy: "cat", metrics: [{ op: "count" }] },
    });
    console.log("T03 aggregate500k", r.ms, "ms");
    expect(r.status).toBe(200);
    expect(r.ms).toBeLessThan(1000);
    const rows = JSON.parse(r.text()).rows as { value: number }[];
    expect(rows.reduce((a, x) => a + x.value, 0)).toBe(500_000);
  });

  test("tuiles : z0/z5/z8 de 500k sous 300 ms et signalées tronquées, z12 complète", async () => {
    const base = `/v1/collections/${s500.collectionId}/tiles`;
    for (const [z, x, y, trunc] of [
      [0, 0, 0, true],
      [5, 16, 11, true],
      [8, 127, 89, true],
      [12, 2040, 1430, false],
    ] as const) {
      const r = await timed("creator", `${base}/${z}/${x}/${y}.mvt`);
      console.log("T03 tile", z, r.ms, "ms", r.bytes, "B", r.headers.get("x-tile-truncated"));
      expect(r.status).toBe(200);
      expect(r.ms).toBeLessThan(300);
      expect(r.headers.get("x-tile-truncated") === "true").toBe(trunc);
    }
  });

  test("droits : un lecteur ne lit ni les tuiles ni les entités d'une collection privée", async () => {
    const tile = await timed("reader", `/v1/collections/${s500.collectionId}/tiles/5/16/11.mvt`);
    const items = await timed("reader", `/v1/collections/${s500.collectionId}/items?limit=10`);
    expect(tile.status).toBe(404);
    expect(items.status).toBe(404);
  });

  test("erreurs : coordonnées de tuile hors pyramide rejetées en 400 sans requête SQL lourde", async () => {
    const a = await timed("creator", `/v1/collections/${s500.collectionId}/tiles/99/1/1.mvt`);
    const b = await timed("creator", `/v1/collections/${s500.collectionId}/tiles/5/99/1.mvt`);
    expect([a.status, b.status]).toEqual([400, 400]);
    expect(Math.max(a.ms, b.ms)).toBeLessThan(200);
  });

  test("état vide : collection vide, tuile et page immédiates", async () => {
    const creator = await apiFor("creator");
    const r = await creator.send("POST", "/v1/collections/empty", {
      title: `${stamp("t03")}-vide`,
      geometryType: "Point",
      srid: 4326,
      columns: [{ name: "nom", sqlType: "text" }],
    });
    expect(r.status).toBe(201);
    const id = r.body.tableName;
    const tile = await timed("creator", `/v1/collections/${id}/tiles/0/0/0.mvt`);
    const items = await timed("creator", `/v1/collections/${id}/items`);
    expect([200, 204]).toContain(tile.status);
    expect(tile.ms).toBeLessThan(300);
    expect(JSON.parse(items.text()).numberMatched).toBe(0);
  });

  // EXPORT_ITEMS_CAP = 10 000 (core/app/features/routes.py) : un export CSV/GeoJSON d'une
  // collection de 50k est refusé en 413 ; le bouton GeoJSON du shell, lui, ne reçoit que 1000.
  test("t03-008 : exporter les 50 000 entités d'une collection (CSV)", async () => {
    const r = await timed("creator", `/v1/collections/${s50.collectionId}/export/items?format=csv`);
    expect(r.status).toBe(200);
    expect(r.text().split("\n").length).toBeGreaterThan(50_000);
  });
});

test.describe("t03 carte et tableau sur gros volumes (navigateur)", () => {
  test("carte 500k à zoom 5 : quatre repositionnements à moins de 2 s, images fluides", async ({
    page,
  }, testInfo) => {
    test.setTimeout(120_000);
    const creator = await apiFor("creator");
    const pk = await createMap(creator, `${stamp("t03")}-carte-500k`, s500.collectionId);
    await stubBasemap(page);
    await loginOidc(page, "creator");
    await spaGo(page, `/maps/${pk}`, 4000);
    const r = await page.evaluate(async (find) => {
      const m: any = eval(find);
      const frames: number[] = [];
      let last = performance.now();
      let go = true;
      const loop = () => {
        const t = performance.now();
        frames.push(t - last);
        last = t;
        if (go) requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
      const idle = () =>
        new Promise<number>((res) => {
          const t0 = performance.now();
          m.once("idle", () => res(performance.now() - t0));
        });
      const steps: number[] = [];
      for (let i = 0; i < 4; i++) {
        m.jumpTo({ center: [-3 + i * 3, 44 + (i % 3)], zoom: 5 });
        steps.push(Math.round(await idle()));
      }
      for (let i = 0; i < 40; i++) {
        m.panBy([20, 5], { duration: 0 });
        await new Promise((res) => requestAnimationFrame(res));
      }
      go = false;
      frames.sort((a, b) => a - b);
      return { steps, p95: Math.round(frames[Math.floor(frames.length * 0.95)]) };
    }, FIND_MAP);
    testInfo.annotations.push({
      type: "mesure",
      description: `idle ${r.steps.join("/")} ms, p95 image ${r.p95} ms (rendu logiciel headless)`,
    });
    console.log("T03 map500k", JSON.stringify(r));
    for (const st of r.steps) expect(st).toBeLessThan(2000);
    expect(r.p95).toBeLessThan(50);
  });

  // À z5 chaque tuile est plafonnée à 5000 entités : 50k et 500k se rendent avec presque
  // le même nombre de points, la densité perçue est fausse d'un facteur ~10.
  bug("t03-009 : la densité rendue à z5 distingue 50k de 500k entités", async ({ page }) => {
    test.setTimeout(120_000);
    const creator = await apiFor("creator");
    await stubBasemap(page);
    await loginOidc(page, "creator");
    const rendered: Record<string, number> = {};
    for (const [name, seed] of [
      ["50k", s50],
      ["500k", s500],
    ] as const) {
      const pk = await createMap(creator, `${stamp("t03")}-dens-${name}`, seed.collectionId);
      await spaGo(page, `/maps/${pk}`, 5000);
      rendered[name] = await page.evaluate(
        (find) => (eval(find) as any).queryRenderedFeatures({ layers: ["big"] }).length as number,
        FIND_MAP,
      );
    }
    console.log("T03 densité", JSON.stringify(rendered));
    expect(rendered["500k"] / rendered["50k"]).toBeGreaterThan(3);
  });

  // LayersPanel sonde une seule fois la tuile 0/0/0 : le badge reste affiché après un zoom
  // à z12 où toutes les tuiles visibles sont complètes.
  test("t03-010 : le badge « Tuile tronquée » disparaît quand la vue n'est plus tronquée", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const creator = await apiFor("creator");
    const pk = await createMap(creator, `${stamp("t03")}-badge`, s500.collectionId);
    await stubBasemap(page);
    await loginOidc(page, "creator");
    await spaGo(page, `/maps/${pk}`, 4000);
    await expect(page.getByText("Tuile tronquée").first()).toBeVisible();
    await page.evaluate(
      (find) => (eval(find) as any).jumpTo({ center: [2.35, 48.85], zoom: 12 }),
      FIND_MAP,
    );
    await page.waitForTimeout(4000);
    await expect(page.getByText("Tuile tronquée")).toHaveCount(0);
  });

  test("tableau 50k : une page de 25 lignes s'affiche, DOM borné", async ({ page }, testInfo) => {
    const creator = await apiFor("creator");
    const pk = await appWithTable(creator, s50.collectionId);
    await loginOidc(page, "creator");
    await spaGo(page, `/apps/${pk}`, 4000);
    const rows = await page.locator("table tbody tr").count();
    testInfo.annotations.push({ type: "mesure", description: `${rows} lignes dans le DOM` });
    expect(rows).toBe(25);
  });

  // queryDataSource n'envoie aucun limit : le cœur répond 100 entités par défaut ; le widget
  // affiche « Page 1 / 4 » pour 500 000 entités, sans total ni message de troncature.
  test("t03-011 : le tableau signale le total réel ou la troncature (500k)", async ({ page }) => {
    const creator = await apiFor("creator");
    const pk = await appWithTable(creator, s500.collectionId);
    await loginOidc(page, "creator");
    await spaGo(page, `/apps/${pk}`, 4000);
    const pager =
      (await page
        .getByText(/Page \d+ \/ \d+/)
        .first()
        .textContent()) ?? "";
    const pages = Number(/\/ (\d+)/.exec(pager)?.[1] ?? "0");
    const mentionsLimit = (await page.getByText(/limit|tronqu|premiers|sur 500/i).count()) > 0;
    expect(pages * 25 >= 500_000 || mentionsLimit).toBe(true);
  });
});

async function appWithTable(api: Awaited<ReturnType<typeof apiFor>>, layer: string) {
  const cfg = {
    version: 1,
    kind: "app",
    theme: {},
    dataSources: [{ id: "s1", type: "features", service: "core", layer, query: {} }],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "tbl",
          widget: "table",
          x: 0,
          y: 0,
          w: 12,
          h: 8,
          props: { dataSourceId: "s1", pageSize: 25 },
        },
      ],
    },
  };
  const r = await api.send("POST", "/v1/configs", { title: `${stamp("t03")}-tbl`, config: cfg });
  if (r.status !== 201) throw new Error(`app ${r.status}`);
  return r.body.itemId as string;
}
