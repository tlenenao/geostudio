import type { Page } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CORE_URL, loginOidc, stamp, type PersonaName } from "../_fixtures/env";
import { apiFor } from "../j03/api";
import { getDatasetSeed } from "../j10/seed";
import { getSeed, type Seed } from "../j03/seed";
import { spaGo } from "../j02/helpers";

export const VIEWPORTS = {
  phone: { width: 360, height: 740 },
  tablet: { width: 768, height: 1024 },
  narrowEdge: { width: 899, height: 800 },
  wideEdge: { width: 900, height: 800 },
  desktop: { width: 1280, height: 800 },
} as const;

export async function openAs(page: Page, persona: PersonaName): Promise<void> {
  await loginOidc(page, persona);
  await page.waitForTimeout(800);
}

export async function go(page: Page, path: string, settleMs = 1500): Promise<void> {
  await spaGo(page, path, settleMs);
}

export async function seed(): Promise<Seed> {
  return getSeed();
}

export interface SmallTarget {
  tag: string;
  text: string;
  w: number;
  h: number;
}

// Cibles interactives visibles dont la boîte fait moins de 44 px dans une dimension.
export async function smallTargets(page: Page, scope = "body"): Promise<SmallTarget[]> {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel) ?? document.body;
    const q = "a[href],button,input:not([type=hidden]),select,textarea,[role=tab],[role=button]";
    const out: { tag: string; text: string; w: number; h: number }[] = [];
    for (const el of root.querySelectorAll<HTMLElement>(q)) {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      if (r.width === 0 || r.height === 0 || cs.visibility === "hidden") continue;
      if (r.right < 0 || r.bottom < 0 || r.left > innerWidth) continue;
      if (r.width < 44 || r.height < 44) {
        out.push({
          tag: el.tagName.toLowerCase(),
          text: (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 40),
          w: Math.round(r.width),
          h: Math.round(r.height),
        });
      }
    }
    return out;
  }, scope);
}

// Éléments qui débordent à droite du viewport (hors scroll interne).
export async function overflowX(
  page: Page,
): Promise<{ doc: number; win: number; culprits: string[] }> {
  return page.evaluate(() => {
    const culprits: string[] = [];
    for (const el of document.querySelectorAll<HTMLElement>("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > innerWidth + 1 && r.left < innerWidth) {
        culprits.push(
          `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 40)}|${(el.textContent ?? "").trim().slice(0, 25)}`,
        );
      }
    }
    return {
      doc: document.documentElement.scrollWidth,
      win: innerWidth,
      culprits: culprits.slice(0, 8),
    };
  });
}

// Le style « clair » vient de demotiles.maplibre.org (hors réseau ici, cf. j03-017) :
// on le remplace par un style vide local pour que la carte atteigne l'état « loaded ».
export async function stubBasemap(page: Page): Promise<void> {
  const style = {
    version: 8,
    sources: {},
    layers: [{ id: "bg", type: "background", paint: { "background-color": "#e8eef2" } }],
  };
  await page.route(
    /demotiles\.maplibre\.org\/style\.json|basemaps\.cartocdn\.com\/.*style\.json/,
    (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(style) }),
  );
}

const CACHE = join(tmpdir(), "aud-j12-map.json");

export interface MapSeed {
  pk: string;
  collectionId: string;
}

// Carte à une couche vectorielle (tuiles du cœur, rendu « circle ») avec popup,
// centrée sur les 12 points du seed j03. Mise en cache disque.
export async function getMapSeed(): Promise<MapSeed> {
  const creator = await apiFor("creator");
  if (existsSync(CACHE)) {
    const c = JSON.parse(readFileSync(CACHE, "utf8")) as MapSeed;
    if ((await creator.get(`/v1/items/${c.pk}`)).status === 200) return c;
  }
  const s = await getSeed();
  const cfg = {
    version: 1,
    kind: "map",
    map: {
      basemap: { style: "https://demotiles.maplibre.org/style.json" },
      view: { center: [2.55, 46.275], zoom: 8 },
      layers: [
        {
          id: "j12-pts",
          title: "Points j12",
          visible: true,
          kind: "vector",
          tilesUrl: `${CORE_URL}/v1/collections/${s.pointsCollection}/tiles/{z}/{x}/{y}.mvt`,
          sourceLayer: s.pointsCollection,
          collectionId: s.pointsCollection,
          geometryKind: "point",
          pkColumn: "id",
          renderAs: "circle",
          paint: { "circle-radius": 14, "circle-color": "#d33" },
          popup: { titleField: "nom", fields: [{ name: "cat" }, { name: "val" }] },
        },
      ],
    },
  };
  const r = await creator.send("POST", "/v1/configs", {
    title: `${stamp("j12")}-carte`,
    config: cfg,
  });
  if (r.status !== 201) throw new Error(`map ${r.status} ${JSON.stringify(r.body)}`);
  const out = { pk: r.body.itemId as string, collectionId: s.pointsCollection };
  writeFileSync(CACHE, JSON.stringify(out));
  return out;
}

// MapView n'expose pas l'instance MapLibre : on la retrouve par les hooks React
// (ref `mapRef`) du composant qui possède `.maplibregl-map`. Sonde de test uniquement.
export const FIND_MAP = `(() => {
  const el = document.querySelector(".maplibregl-map");
  if (!el) return null;
  const key = Object.keys(el).find((k) => k.startsWith("__reactFiber$"));
  let f = key ? el[key] : null;
  const seen = new Set();
  const isMap = (v) => v && typeof v === "object" && typeof v.queryRenderedFeatures === "function";
  while (f) {
    for (let h = f.memoizedState; h; h = h.next) {
      const v = h.memoizedState;
      if (isMap(v)) return v;
      if (v && isMap(v.current)) return v.current;
    }
    f = f.return;
    if (seen.has(f)) break;
    seen.add(f);
  }
  return null;
})()`;

export function evalMap<T>(page: Page, body: string): Promise<T> {
  return page.evaluate(`(() => { const m = ${FIND_MAP}; ${body} })()`) as Promise<T>;
}

export interface TouchPoint {
  x: number;
  y: number;
  id?: number;
}

// Geste tactile réel (Input.dispatchTouchEvent) : `steps` déplacements linéaires
// par doigt. Le pincement s'obtient avec deux doigts.
export async function touchGesture(
  page: Page,
  from: TouchPoint[],
  to: TouchPoint[],
  steps = 8,
): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  const pts = (k: number) =>
    from.map((f, i) => ({
      x: f.x + ((to[i].x - f.x) * k) / steps,
      y: f.y + ((to[i].y - f.y) * k) / steps,
      id: i,
    }));
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pts(0) });
  for (let k = 1; k <= steps; k++) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pts(k) });
    await page.waitForTimeout(30);
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await cdp.detach();
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre
export type Json = any;

// App deux colonnes (table 6/12 + section riche 6/12) sur la collection publique de j10 :
// gabarit typique d'un tableau de bord conçu au bureau.
export async function getTwoColApp(): Promise<string> {
  const creator = await apiFor("creator");
  const ds = await getDatasetSeed();
  const cfg: Json = {
    version: 1,
    kind: "app",
    theme: {},
    dataSources: [
      { id: "s1", type: "features", service: "core", layer: ds.collectionId, query: {} },
    ],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "tbl", widget: "table", x: 0, y: 0, w: 6, h: 6, props: { dataSourceId: "s1" } },
        {
          id: "txt",
          widget: "richSection",
          x: 6,
          y: 0,
          w: 6,
          h: 6,
          props: {
            markdown:
              "# Titre\n\nUn paragraphe assez long pour tester le retour à la ligne sur mobile.",
          },
        },
      ],
    },
  };
  const r = await creator.send("POST", "/v1/configs", {
    title: `${stamp("j12")}-app2col`,
    config: cfg,
  });
  if (r.status !== 201) throw new Error(`app ${r.status} ${JSON.stringify(r.body)}`);
  return r.body.itemId as string;
}
