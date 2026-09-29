/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { apiFor, type Api } from "./api";
import { psql } from "./helpers";
import { stamp } from "../_fixtures/env";

export interface Seed {
  tag: string;
  creator: Api;
  reader: Api;
  admin: Api;
  colId: string;
  colTable: string;
  emptyApp: string;
  mkApp(title: string, cfg?: any): Promise<string>;
}

export const grid = (items: any[] = []) => ({ type: "grid" as const, breakpoints: {}, items });

export const baseApp = (over: any = {}) => ({
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: grid(),
  ...over,
});

let cached: Promise<Seed> | undefined;
export function getSeed(): Promise<Seed> {
  cached ??= build();
  return cached;
}

async function build(): Promise<Seed> {
  const tag = stamp("j04");
  const creator = await apiFor("creator");
  const reader = await apiFor("reader");
  const admin = await apiFor("admin");
  const c = await creator.send("POST", "/v1/collections/empty", {
    title: `${tag}-col`,
    columns: [
      { name: "nom", sqlType: "text" },
      { name: "surface", sqlType: "integer" },
      { name: "statut", sqlType: "text" },
    ],
    geometryType: "Point",
    srid: 4326,
  });
  if (c.status !== 201) throw new Error(`col ${c.status} ${JSON.stringify(c.body)}`);
  const colId = c.body.id as string;
  const colTable = c.body.tableName as string;
  psql(
    `INSERT INTO public.${colTable} (tenant_id, nom, surface, statut, geom) VALUES ` +
      `('default','Alpha',10,'ouvert',ST_SetSRID(ST_MakePoint(1.5,45.2),4326)),` +
      `('default','Beta',20,'ferme',ST_SetSRID(ST_MakePoint(1.6,45.3),4326)),` +
      `('default','Gamma',30,'ouvert',ST_SetSRID(ST_MakePoint(1.7,45.4),4326))`,
  );
  const mkApp = async (title: string, cfg: any = baseApp()) => {
    const r = await creator.send("POST", "/v1/configs", { title: `${tag}-${title}`, config: cfg });
    if (r.status !== 201) throw new Error(`app ${r.status} ${JSON.stringify(r.body)}`);
    return r.body.itemId as string;
  };
  const emptyApp = await mkApp("vide");
  return { tag, creator, reader, admin, colId, colTable, emptyApp, mkApp };
}
