/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import AxeBuilder from "@axe-core/playwright";
import { test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loginOidc, stamp, type PersonaName } from "../_fixtures/env";
import { apiFor } from "../j03/api";
import { getDatasetSeed } from "../j10/seed";
import { spaGo } from "../j02/helpers";

export async function openAs(page: Page, persona: PersonaName): Promise<void> {
  await loginOidc(page, persona);
  await page.waitForTimeout(800);
}

export async function go(page: Page, path: string, settleMs = 1500): Promise<void> {
  await spaGo(page, path, settleMs);
}

export interface A11ySeed {
  collectionId: string;
  datasetId: string;
  mapId: string;
  appId: string;
  siteSlug: string;
  siteId: string;
  pipelineId: string;
  alertId: string;
  bookmarkId: string;
  reportId: string;
}

const CACHE = join(tmpdir(), "aud-t01-seed.json");

// Un item de chaque type éditable, créés par le persona `creator` (mis en cache disque).
export async function getA11ySeed(): Promise<A11ySeed> {
  const creator = await apiFor("creator");
  if (existsSync(CACHE)) {
    const c = JSON.parse(readFileSync(CACHE, "utf8")) as A11ySeed;
    if ((await creator.get(`/v1/items/${c.alertId}`)).status === 200) return c;
  }
  const tag = stamp("t01");
  const ds = await getDatasetSeed();
  // Capacités désactivées sur cette stack (ETL, export) : création refusée en 403.
  const optional = ["pipe", "rep"];
  const mk = async (title: string, config: any): Promise<string> => {
    const r = await creator.send("POST", "/v1/configs", { title: `${tag}-${title}`, config });
    if (r.status === 403 && optional.includes(title)) return "";
    if (r.status !== 201) throw new Error(`${title} ${r.status} ${JSON.stringify(r.body)}`);
    return r.body.itemId as string;
  };
  const appCfg = {
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
          props: { markdown: "# Titre\n\nParagraphe." },
        },
      ],
    },
  };
  const appId = await mk("app", appCfg);
  const mapId = await mk("carte", {
    version: 1,
    kind: "map",
    map: {
      basemap: { style: "https://demotiles.maplibre.org/style.json" },
      view: { center: [1.6, 45.3], zoom: 8 },
      layers: [],
    },
  });
  const siteId = await mk("site", {
    version: 1,
    kind: "site",
    layout: {
      type: "grid",
      items: [
        { id: "r1", widget: "richSection", x: 0, y: 0, w: 12, h: 4, props: { markdown: "# Site" } },
      ],
    },
  });
  await creator.send("PATCH", `/v1/items/${siteId}`, { isPublished: true });
  const siteSlug = (await creator.get(`/v1/items/${siteId}`)).body.slug as string;
  const pipelineId = await mk("pipe", {
    version: 1,
    kind: "pipeline",
    pipeline: {
      nodes: [
        {
          id: "r1",
          kind: "reader",
          op: "reader.collection",
          x: 0,
          y: 0,
          params: { collectionId: ds.collectionId },
          title: "reader.collection",
        },
        {
          id: "w1",
          kind: "writer",
          op: "writer.collection",
          x: 300,
          y: 0,
          params: { collectionId: ds.collectionId },
          title: "writer.collection",
        },
      ],
      edges: [{ id: "e1", from: "r1", to: "w1" }],
    },
  });
  const alertId = await mk("alert", {
    version: 1,
    kind: "alert",
    alert: {
      datasetItemId: ds.datasetItemId,
      query: { agg: "count" },
      condition: { expr: "value > 2" },
      refreshPolicy: { enabled: false, cron: "*/5 * * * *" },
      channels: [{ kind: "webhook", url: "http://127.0.0.1:9/hook" }],
    },
  });
  const bookmarkId = await mk("bm", {
    version: 1,
    kind: "bookmark",
    bookmark: { appId, pageId: "p1" },
  });
  const reportId = await mk("rep", {
    version: 1,
    kind: "report",
    report: {
      bookmarkItemId: bookmarkId,
      refreshPolicy: { enabled: false, cron: "*/5 * * * *" },
      channels: [{ kind: "webhook", url: "https://example.test/h" }],
    },
  });
  const out: A11ySeed = {
    collectionId: ds.collectionId,
    datasetId: ds.datasetItemId,
    mapId,
    appId,
    siteSlug,
    siteId,
    pipelineId,
    alertId,
    bookmarkId,
    reportId,
  };
  writeFileSync(CACHE, JSON.stringify(out));
  return out;
}

export interface AxeNode {
  target: string;
  html: string;
  summary: string;
}
export interface AxeViolation {
  id: string;
  impact: string;
  help: string;
  nodes: AxeNode[];
}

export async function axe(page: Page, rules?: string[]): Promise<AxeViolation[]> {
  let b = new AxeBuilder({ page });
  if (rules) b = b.withRules(rules);
  const r = await b.analyze();
  return r.violations.map((v) => ({
    id: v.id,
    impact: v.impact ?? "minor",
    help: v.help,
    nodes: v.nodes.map((n) => ({
      target: n.target.join(" "),
      html: n.html.slice(0, 200),
      summary: (n.failureSummary ?? "").slice(0, 300),
    })),
  }));
}

export function fmt(vs: AxeViolation[]): string {
  return vs
    .map((v) => `${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes[0]?.target}`)
    .join("\n");
}

// Description courte de l'élément qui a le focus.
export async function focusDesc(page: Page): Promise<string> {
  return page.evaluate(() => {
    const a = document.activeElement as HTMLElement | null;
    if (!a || a === document.body) return "body";
    return `${a.tagName.toLowerCase()}|${a.getAttribute("role") ?? ""}|${(a.getAttribute("aria-label") || a.textContent || "").trim().slice(0, 40)}`;
  });
}

// Les tests qui révèlent un bug sont `test.fixme` (résultat : ignorés) ; T01_VERIFY=1 les rejoue
// pour prouver qu'ils échouent bien sur l'assertion visée.
export const bug = process.env.AUDIT_VERIFY || process.env.T01_VERIFY ? test : test.fixme;

export interface Session {
  ctx: BrowserContext;
  page: Page;
}

export async function newSession(
  browser: Browser,
  persona: PersonaName,
  colorScheme: "light" | "dark" = "light",
): Promise<Session> {
  const ctx = await browser.newContext({ colorScheme });
  const page = await ctx.newPage();
  page.setDefaultTimeout(8000);
  await openAs(page, persona);
  return { ctx, page };
}

// Ratio de contraste WCAG entre deux couleurs `rgb(...)`/`rgba(...)`.
function channels(css: string): [number, number, number] {
  const m = css.match(/[\d.]+/g) ?? ["0", "0", "0"];
  return [Number(m[0]), Number(m[1]), Number(m[2])];
}
function luminance(css: string): number {
  const [r, g, b] = channels(css).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
export function contrast(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

// Convertit un jeton `#rrggbb` en `rgb(r, g, b)`.
export function hexToRgb(hex: string): string {
  const h = hex.trim().replace("#", "");
  return `rgb(${parseInt(h.slice(0, 2), 16)}, ${parseInt(h.slice(2, 4), 16)}, ${parseInt(h.slice(4, 6), 16)})`;
}
