/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { execFileSync } from "node:child_process";
import { CORE_URL } from "../_fixtures/env";
import { apiFor, type Api } from "./api";

// Jeu de données de j02 : créé via l'API du cœur par le persona `creator`.
// Les lignes de la collection sont insérées en SQL (docker exec) car
// POST /collections/{id}/items refuse toute écriture sur une collection créée
// par POST /collections/empty (finding j02-001) et l'upload S3 est cassé sur
// cette stack (finding j02-002).
export interface Seed {
  tag: string;
  readerId: string;
  groupId: string;
  sharedCol: string;
  privateCol: string;
  sharedDataset: string;
  privateDataset: string;
  sharedMap: string;
  privateMap: string;
  sharedApp: string;
  privateApp: string;
  bookmark: string;
  autoApp: string;
  bookmarkOnPrivateApp: string;
  accentItem: string;
  publicApp: string;
  creator: Api;
  admin: Api;
  reader: Api;
}

function psql(sql: string) {
  execFileSync(
    "docker",
    [
      "exec",
      "geostudio-postgis-1",
      "psql",
      "-U",
      "gis",
      "-d",
      "gis",
      "-v",
      "ON_ERROR_STOP=1",
      "-c",
      sql,
    ],
    { stdio: "pipe" },
  );
}

function must<T extends { status: number; body: any }>(r: T, ok: number[], what: string): T {
  if (!ok.includes(r.status)) throw new Error(`${what}: ${r.status} ${JSON.stringify(r.body)}`);
  return r;
}

const grid = () => ({
  type: "grid" as const,
  breakpoints: {},
  items: [
    { id: "w1", widget: "text", x: 0, y: 0, w: 6, h: 2, props: { text: "Bonjour lecteur" } },
    { id: "w2", widget: "table", x: 0, y: 2, w: 6, h: 4, props: { dataSourceId: "s1" } },
  ],
});

let cached: Promise<Seed> | undefined;
export function getSeed(): Promise<Seed> {
  cached ??= build();
  return cached;
}

async function build(): Promise<Seed> {
  const tag = `aud-j02-${Date.now().toString(36)}`;
  const creator = await apiFor("creator");
  const admin = await apiFor("admin");
  const reader = await apiFor("reader");
  const readerId = (await reader.get("/v1/me")).body.id as string;

  const g = must(
    await creator.send("POST", "/v1/groups", { name: `${tag}-lecteurs` }),
    [201],
    "group",
  );
  const groupId = g.body.id as string;
  must(
    await creator.send("POST", `/v1/groups/${groupId}/members`, { userId: readerId }),
    [204],
    "member",
  );

  const mkCol = async (title: string) => {
    const c = must(
      await creator.send("POST", "/v1/collections/empty", {
        title,
        columns: [
          { name: "nom", sqlType: "text" },
          { name: "surface", sqlType: "integer" },
          { name: "secret", sqlType: "text" },
        ],
        geometryType: "Point",
        srid: 4326,
      }),
      [201],
      "collection",
    );
    const id = c.body.id as string;
    const table = c.body.tableName as string;
    psql(
      `INSERT INTO public.${table} (tenant_id, nom, surface, secret, geom) VALUES ` +
        `('default','Alpha',10,'s1',ST_SetSRID(ST_MakePoint(1.5,45.2),4326)),` +
        `('default','Beta',20,'s2',ST_SetSRID(ST_MakePoint(1.6,45.3),4326)),` +
        `('default','Gamma',30,'s3',ST_SetSRID(ST_MakePoint(1.7,45.4),4326))`,
    );
    return { id, table };
  };
  const shared = await mkCol(`${tag}-parcelles`);
  const priv = await mkCol(`${tag}-prive`);
  must(
    await creator.send("PATCH", `/v1/collections/${shared.id}`, {
      attachmentFields: [{ key: "photo", label: "Photo" }],
    }),
    [200],
    "patch col",
  );
  must(
    await creator.send("PUT", `/v1/collections/${shared.id}/sharing`, {
      public: false,
      groups: [{ groupId, role: "viewer" }],
    }),
    [200],
    "share col",
  );

  const shareItem = async (id: string) =>
    must(
      await creator.send("PUT", `/v1/items/${id}/sharing`, {
        public: false,
        groups: [{ groupId, role: "viewer" }],
      }),
      [204],
      "share item",
    );
  const mkItem = async (title: string, config: any) => {
    const r = must(
      await creator.send("POST", "/v1/configs", { title, config }),
      [201],
      `config ${title}`,
    );
    return r.body.itemId as string;
  };

  const dsCfg = (collectionId: string) => ({
    kind: "dataset",
    dataset: { source: "collection", collectionId },
  });
  const mapCfg = (collectionId: string) => ({
    kind: "map",
    map: {
      basemap: { style: "https://demotiles.maplibre.org/style.json" },
      view: { center: [1.6, 45.3], zoom: 8 },
      layers: [
        {
          id: "l1",
          title: "Parcelles",
          popup: {
            titleField: "nom",
            fields: [
              { name: "nom", label: "Nom" },
              { name: "surface", label: "Surface" },
            ],
          },
          kind: "vector",
          tilesUrl: `${CORE_URL}/v1/collections/${collectionId}/tiles/{z}/{x}/{y}.mvt`,
          sourceLayer: collectionId,
          collectionId,
          geometryKind: "point",
          pkColumn: "id",
          renderAs: "circle",
          visible: true,
        },
      ],
    },
  });
  const appCfg = (collectionId: string) => ({
    kind: "app",
    dataSources: [{ id: "s1", type: "features", service: "core", layer: collectionId, query: {} }],
    pages: [{ id: "p1", name: "Accueil", layout: grid() }],
    layout: grid(),
  });

  const sharedDataset = await mkItem(`${tag}-ds`, dsCfg(shared.id));
  const privateDataset = await mkItem(`${tag}-ds-prive`, dsCfg(priv.id));
  const sharedMap = await mkItem(`${tag}-carte`, mapCfg(shared.id));
  const privateMap = await mkItem(`${tag}-carte-privee`, mapCfg(priv.id));
  const sharedApp = await mkItem(`${tag}-app`, appCfg(shared.id));
  const privateApp = await mkItem(`${tag}-app-privee`, appCfg(priv.id));
  const publicApp = await mkItem(`${tag}-app-publique`, appCfg(shared.id));
  must(
    await creator.send("PATCH", `/v1/items/${sharedDataset}`, {
      abstract: "Parcelles de test du lecteur",
      keywords: ["cadastre", "aud"],
      license: "cc-by-4.0",
    }),
    [200],
    "patch dataset",
  );
  const autoApp = await mkItem(`${tag}-app-auto`, { ...appCfg(shared.id), interactions: "auto" });
  const accentItem = await mkItem(`${tag}-Forêt de Tulle`, appCfg(shared.id));
  await shareItem(autoApp);
  await shareItem(accentItem);
  await shareItem(sharedDataset);
  await shareItem(sharedMap);
  await shareItem(sharedApp);
  must(
    await creator.send("PUT", `/v1/items/${publicApp}/sharing`, { public: true, groups: [] }),
    [204],
    "public",
  );
  const bookmark = await mkItem(`${tag}-signet`, {
    kind: "bookmark",
    bookmark: { appId: sharedApp, pageId: "p1", extent: [1.4, 45.1, 1.8, 45.5] },
  });
  await shareItem(bookmark);
  const bookmarkOnPrivateApp = await mkItem(`${tag}-signet-app-privee`, {
    kind: "bookmark",
    bookmark: { appId: privateApp, pageId: "p1" },
  });
  await shareItem(bookmarkOnPrivateApp);

  return {
    tag,
    readerId,
    groupId,
    sharedCol: shared.id,
    privateCol: priv.id,
    sharedDataset,
    privateDataset,
    sharedMap,
    privateMap,
    sharedApp,
    privateApp,
    publicApp,
    bookmark,
    autoApp,
    bookmarkOnPrivateApp,
    accentItem,
    creator,
    admin,
    reader,
  };
}
