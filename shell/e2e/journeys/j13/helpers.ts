/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import type { Page } from "@playwright/test";
import { loginOidc, stamp, type PersonaName } from "../_fixtures/env";
import { apiFor, type Api } from "../j03/api";
import { spaGo } from "../j02/helpers";

export { apiFor, stamp };
export type { Api };

export const TAG = stamp("j13");

export function appConfig() {
  return { version: 1, kind: "app", layout: { type: "grid", breakpoints: {}, items: [] } };
}

export async function meId(api: Api): Promise<string> {
  const r = await api.get("/v1/me");
  if (r.status !== 200) throw new Error(`me ${r.status}`);
  return r.body.id as string;
}

export async function mkItem(api: Api, title: string, config: any = appConfig()) {
  const r = await api.send("POST", "/v1/configs", { title, config });
  if (r.status !== 201) throw new Error(`config ${r.status} ${JSON.stringify(r.body)}`);
  return { pk: r.body.itemId as string, configId: r.body.id as string };
}

export async function mkGroup(api: Api, name: string, members: string[] = []): Promise<string> {
  const g = await api.send("POST", "/v1/groups", { name });
  if (g.status !== 201) throw new Error(`group ${g.status} ${JSON.stringify(g.body)}`);
  for (const userId of members) {
    const m = await api.send("POST", `/v1/groups/${g.body.id}/members`, { userId });
    if (m.status !== 204) throw new Error(`member ${m.status}`);
  }
  return g.body.id as string;
}

export async function share(
  api: Api,
  pk: string,
  groups: { groupId: string; role: "viewer" | "editor" | "manager" }[],
  isPublic = false,
): Promise<number> {
  return (await api.send("PUT", `/v1/items/${pk}/sharing`, { public: isPublic, groups })).status;
}

export async function mkCollection(api: Api, title: string): Promise<string> {
  const c = await api.send("POST", "/v1/collections/empty", {
    title,
    columns: [{ name: "nom", sqlType: "text" }],
    geometryType: "Point",
    srid: 4326,
  });
  if (c.status !== 201) throw new Error(`col ${c.status} ${JSON.stringify(c.body)}`);
  return c.body.id as string;
}

export function mapConfigOn(collectionId: string) {
  return {
    version: 1,
    kind: "map",
    map: {
      basemap: { style: "https://demotiles.maplibre.org/style.json" },
      view: { center: [1.6, 45.3], zoom: 8 },
      layers: [
        {
          id: "j13-l",
          title: "Couche j13",
          visible: true,
          kind: "vector",
          tilesUrl: `http://localhost:8200/v1/collections/${collectionId}/tiles/{z}/{x}/{y}.mvt`,
          sourceLayer: collectionId,
          collectionId,
          geometryKind: "point",
          pkColumn: "id",
        },
      ],
    },
  };
}

export async function anon(path: string): Promise<number> {
  const doFetch = () => fetch(`http://localhost:8200${path}`);
  const r = await doFetch().catch(() => doFetch());
  await r.text();
  return r.status;
}

export async function openAs(page: Page, persona: PersonaName): Promise<void> {
  await loginOidc(page, persona);
  await page.waitForTimeout(800);
}

export async function go(page: Page, path: string, settleMs = 1500): Promise<void> {
  await spaGo(page, path, settleMs);
}
