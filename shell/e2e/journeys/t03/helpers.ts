/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import type { Page } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CORE_URL, stamp } from "../_fixtures/env";
import { apiFor, type Api } from "../j03/api";
import { psql } from "../j02/helpers";
import { stubBasemap } from "../j12/helpers";

export { apiFor, psql, stubBasemap };

// Emprise France métropolitaine (lon -5..8, lat 42..51) : les points générés
// couvrent un cadre réaliste pour une carte de zoom 5 à 12.
export const FR = { west: -5, east: 8, south: 42, north: 51 };

export interface BigSeed {
  n: number;
  collectionId: string;
  tag: string;
}

const cacheFile = (n: number) => join(tmpdir(), `aud-t03-big-${n}.json`);

// Crée une collection ponctuelle vide via l'API du produit (POST
// /v1/collections/empty : POST /v1/uploads répond 500, cf. j03-001), puis y
// insère `n` points par SQL (INSERT ... generate_series) dans la table de CETTE
// collection uniquement. Mis en cache disque.
export async function getBigSeed(n: number): Promise<BigSeed> {
  const creator = await apiFor("creator");
  if (existsSync(cacheFile(n))) {
    const c = JSON.parse(readFileSync(cacheFile(n), "utf8")) as BigSeed;
    if ((await creator.get(`/v1/collections/${c.collectionId}`)).status === 200) return c;
  }
  const tag = stamp("t03");
  const r = await creator.send("POST", "/v1/collections/empty", {
    title: `${tag}-pts-${n}`,
    geometryType: "Point",
    srid: 4326,
    columns: [
      { name: "nom", sqlType: "text" },
      { name: "cat", sqlType: "text" },
      { name: "val", sqlType: "integer" },
    ],
  });
  if (r.status !== 201) throw new Error(`collection ${r.status} ${JSON.stringify(r.body)}`);
  const id = r.body.tableName as string;
  psql(
    `INSERT INTO public."${id}" (tenant_id, nom, cat, val, geom) ` +
      `SELECT 'default', 'pt-' || g, 'c' || (g % 8), (g % 1000), ` +
      `ST_SetSRID(ST_MakePoint(${FR.west} + random() * ${FR.east - FR.west}, ${FR.south} + random() * ${FR.north - FR.south}), 4326) ` +
      `FROM generate_series(1, ${n}) g`,
  );
  psql(`ANALYZE public."${id}"`);
  const seed = { n, collectionId: id, tag };
  writeFileSync(cacheFile(n), JSON.stringify(seed));
  return seed;
}

export async function createMap(
  api: Api,
  title: string,
  collectionId: string | null,
  center: [number, number] = [2.5, 46.5],
  zoom = 5,
): Promise<string> {
  const layers = collectionId
    ? [
        {
          id: "big",
          title: "Points",
          visible: true,
          kind: "vector",
          tilesUrl: `${CORE_URL}/v1/collections/${collectionId}/tiles/{z}/{x}/{y}.mvt`,
          sourceLayer: collectionId,
          collectionId,
          geometryKind: "point",
          pkColumn: "id",
          renderAs: "circle",
          paint: { "circle-radius": 3, "circle-color": "#d33" },
        },
      ]
    : [];
  const cfg = {
    version: 1,
    kind: "map",
    map: {
      basemap: { style: "https://demotiles.maplibre.org/style.json" },
      view: { center, zoom },
      layers,
    },
  };
  const r = await api.send("POST", "/v1/configs", { title, config: cfg });
  if (r.status !== 201) throw new Error(`map ${r.status} ${JSON.stringify(r.body)}`);
  return r.body.itemId as string;
}

export interface Vitals {
  lcp: number | null;
  lcpTag: string | null;
  cls: number;
  fcp: number | null;
  longTasks: number;
  longTaskMs: number;
}

// Observateurs Web Vitals installés avant tout script de la page.
export async function installVitals(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as any;
    w.__v = { lcp: null, lcpTag: null, cls: 0, fcp: null, longTasks: 0, longTaskMs: 0 };
    const obs = (type: string, cb: (e: any) => void) => {
      try {
        new PerformanceObserver((l) => l.getEntries().forEach(cb)).observe({
          type,
          buffered: true,
        } as any);
      } catch {
        /* type non supporté */
      }
    };
    obs("largest-contentful-paint", (e) => {
      w.__v.lcp = e.startTime;
      w.__v.lcpTag = e.element ? e.element.tagName.toLowerCase() : null;
    });
    obs("layout-shift", (e) => {
      if (!e.hadRecentInput) w.__v.cls += e.value;
    });
    obs("paint", (e) => {
      if (e.name === "first-contentful-paint") w.__v.fcp = e.startTime;
    });
    obs("longtask", (e) => {
      w.__v.longTasks += 1;
      w.__v.longTaskMs += e.duration;
    });
  });
}

export function readVitals(page: Page): Promise<Vitals> {
  return page.evaluate(() => (window as any).__v as Vitals);
}

// Charge JS/CSS/images transférée depuis une page (Resource Timing).
export async function resourceStats(page: Page): Promise<{
  requests: number;
  jsRequests: number;
  transferKb: number;
  decodedKb: number;
  files: string[];
}> {
  return page.evaluate(() => {
    const r = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
    const js = r.filter((e) => /\.m?js(\?|$)/.test(e.name));
    return {
      requests: r.length,
      jsRequests: js.length,
      transferKb: Math.round(r.reduce((s, e) => s + e.transferSize, 0) / 1024),
      decodedKb: Math.round(r.reduce((s, e) => s + e.decodedBodySize, 0) / 1024),
      files: js.map((e) => e.name.split("/").pop() ?? e.name),
    };
  });
}

export interface NetLog {
  stop(): Promise<{ requests: number; kb: number; byUrl: { url: string; kb: number }[] }>;
}

// Octets réellement transférés (CDP Network.loadingFinished.encodedDataLength) :
// contrairement à Resource Timing, indépendant du cache mémoire du navigateur.
export async function netLog(page: Page): Promise<NetLog> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  const urls = new Map<string, string>();
  const sizes = new Map<string, number>();
  cdp.on("Network.requestWillBeSent", (e: any) => urls.set(e.requestId, e.request.url));
  cdp.on("Network.loadingFinished", (e: any) => sizes.set(e.requestId, e.encodedDataLength));
  return {
    async stop() {
      await cdp.detach().catch(() => undefined);
      const byUrl = [...sizes.entries()].map(([id, b]) => ({
        url: urls.get(id) ?? id,
        kb: Math.round(b / 102.4) / 10,
      }));
      return {
        requests: urls.size,
        kb: Math.round(byUrl.reduce((s, r) => s + r.kb, 0)),
        byUrl: byUrl.sort((a, b) => b.kb - a.kb),
      };
    },
  };
}
