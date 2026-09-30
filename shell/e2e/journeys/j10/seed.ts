/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { stamp } from "../_fixtures/env";
import { apiFor, type Api } from "../j03/api";
import { psql } from "../j02/helpers";

export { apiFor, psql };
export type { Api };

export const XSS_MARKDOWN =
  "# Titre du site\n\nParagraphe **gras**.\n\n" +
  '<img src="x" onerror="window.__xss=1">\n\n' +
  "<script>window.__xss=2</script>\n\n" +
  "[lien piégé](javascript:window.__xss=3)\n\n" +
  '<a href="https://example.org" target="_blank">externe</a>';

export function siteConfig(items: any[] = [], extra: any = {}) {
  return { version: 1, kind: "site", layout: { type: "grid", items }, ...extra };
}

export function richItem(id: string, markdown: string, y = 0) {
  return { id, widget: "richSection", x: 0, y, w: 12, h: 4, props: { markdown } };
}

export async function createSite(
  api: Api,
  title: string,
  config: any,
  opts: { slug?: string; publish?: boolean } = {},
) {
  const r = await api.send("POST", "/v1/configs", {
    title,
    ...(opts.slug ? { slug: opts.slug } : {}),
    config,
  });
  if (r.status !== 201) throw new Error(`site ${r.status} ${JSON.stringify(r.body)}`);
  const pk = r.body.itemId as string;
  if (opts.publish) {
    const p = await api.send("PATCH", `/v1/items/${pk}`, { isPublished: true });
    if (p.status !== 200) throw new Error(`publish ${p.status}`);
  }
  const item = (await api.get(`/v1/items/${pk}`)).body;
  return { pk, slug: item.slug as string, configId: r.body.id as string };
}

export interface DatasetSeed {
  tag: string;
  collectionId: string;
  tableName: string;
  datasetItemId: string;
}

let cached: Promise<DatasetSeed> | undefined;
// Collection de 3 points (créée vide puis remplie en SQL : l'import est cassé,
// cf. j03-001), rendue publique, + item dataset.
export function getDatasetSeed(): Promise<DatasetSeed> {
  cached ??= (async () => {
    const tag = stamp("j10");
    const creator = await apiFor("creator");
    const c = await creator.send("POST", "/v1/collections/empty", {
      title: `${tag}-col`,
      columns: [
        { name: "nom", sqlType: "text" },
        { name: "val", sqlType: "integer" },
      ],
      geometryType: "Point",
      srid: 4326,
    });
    if (c.status !== 201) throw new Error(`col ${c.status} ${JSON.stringify(c.body)}`);
    const table = c.body.tableName as string;
    psql(
      `INSERT INTO public.${table} (tenant_id, nom, val, geom) VALUES ` +
        `('default','A',1,ST_SetSRID(ST_MakePoint(1.5,45.2),4326)),` +
        `('default','B',2,ST_SetSRID(ST_MakePoint(1.6,45.3),4326)),` +
        `('default','C',3,ST_SetSRID(ST_MakePoint(1.7,45.4),4326))`,
    );
    psql(`UPDATE collections SET feature_count=3 WHERE id='${c.body.id}'`);
    const sh = await creator.send("PUT", `/v1/collections/${c.body.id}/sharing`, {
      public: true,
      groups: [],
    });
    if (sh.status !== 200) throw new Error(`sharing ${sh.status} ${JSON.stringify(sh.body)}`);
    const d = await creator.send("POST", "/v1/configs", {
      title: `${tag}-dataset`,
      config: {
        version: 1,
        kind: "dataset",
        dataset: { source: "collection", collectionId: c.body.id },
      },
    });
    if (d.status !== 201) throw new Error(`dataset ${d.status} ${JSON.stringify(d.body)}`);
    return { tag, collectionId: c.body.id, tableName: table, datasetItemId: d.body.itemId };
  })();
  return cached;
}

export function storyConfig(over: any = {}) {
  const page = (n: number, extra: any = {}) => ({
    id: `ch${n}`,
    name: `Chapitre ${n}`,
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        richItem(`t${n}`, `# Titre chapitre ${n}`),
        {
          id: `v${n}`,
          widget: "text",
          x: 0,
          y: 4,
          w: 6,
          h: 2,
          props: { text: "Variable : {{var:etape}}" },
        },
      ],
    },
    onEnter: [
      {
        from: `ch${n}`,
        event: "enter",
        to: "var:vv",
        action: "set",
        payload: { etape: `etape-${n}` },
      },
    ],
    ...extra,
  });
  const pages = [page(1), page(2), page(3)];
  return {
    version: 1,
    kind: "app",
    navigationMode: "story",
    variables: [{ id: "vv", name: "etape", type: "string", initialValue: "" }],
    layout: pages[0].layout,
    pages,
    ...over,
  };
}
