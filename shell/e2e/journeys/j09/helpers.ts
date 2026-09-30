/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { apiFor, type Api } from "../j03/api";
import { psql } from "../j02/helpers";
import { stamp } from "../_fixtures/env";
import { corePython } from "../j06/helpers";

export { apiFor, psql };
export { openAs, spaGoto, corePython } from "../j06/helpers";
export type { Api };

export interface AlertSeed {
  tag: string;
  creator: Api;
  colId: string;
  colTable: string;
  datasetId: string;
}

let cached: Promise<AlertSeed> | undefined;
export function getAlertSeed(): Promise<AlertSeed> {
  cached ??= build();
  return cached;
}

async function build(): Promise<AlertSeed> {
  const tag = stamp("j09");
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
  const colTable = c.body.tableName as string;
  psql(
    `INSERT INTO public.${colTable} (tenant_id, nom, val, geom) VALUES ` +
      `('default','A',1,ST_SetSRID(ST_MakePoint(1.5,45.2),4326)),` +
      `('default','B',2,ST_SetSRID(ST_MakePoint(1.6,45.3),4326)),` +
      `('default','C',3,ST_SetSRID(ST_MakePoint(1.7,45.4),4326))`,
  );
  // Les agrégats (donc les alertes) lisent le lakehouse GeoParquet alimenté par le CDC : on attend.
  for (let i = 0; i < 60; i++) {
    const a = await creator.send("POST", `/v1/collections/${c.body.id}/aggregate`, {
      agg: "count",
    });
    if (a.status === 200 && a.body.rows?.[0]?.value === 3) break;
    await new Promise((res) => setTimeout(res, 2000));
  }
  const d = await creator.send("POST", "/v1/configs", {
    title: `${tag}-dataset`,
    config: {
      version: 1,
      kind: "dataset",
      dataset: { source: "collection", collectionId: c.body.id },
    },
  });
  if (d.status !== 201) throw new Error(`dataset ${d.status} ${JSON.stringify(d.body)}`);
  return { tag, creator, colId: c.body.id, colTable, datasetId: d.body.itemId };
}

export function alertConfig(datasetId: string, over: any = {}) {
  return {
    version: 1,
    kind: "alert",
    alert: {
      datasetItemId: datasetId,
      query: { agg: "count" },
      condition: { expr: "value > 2" },
      refreshPolicy: { enabled: false, cron: "*/5 * * * *" },
      channels: [{ kind: "webhook", url: "http://127.0.0.1:9/hook" }],
      ...over,
    },
  };
}

export async function meId(api: Api): Promise<string> {
  const me = await api.get("/v1/me");
  return me.body.id as string;
}

// POST /v1/alerts/{id}/evaluate répond 500 sur cette stack (cf. j09-001) : on
// défère la tâche depuis un process qui ouvre l'App procrastinate, comme le
// ferait le balayage périodique du worker.
export function deferEvaluation(evaluationId: string): void {
  corePython(
    [
      "from app.jobs import app",
      "from app.alerts.jobs import evaluate_alert_task",
      "with app.open():",
      `    evaluate_alert_task.defer(evaluation_id="${evaluationId}", tenant_id="default")`,
    ].join("\n"),
  );
}

export async function waitEvaluation(api: Api, itemId: string, evaluationId: string): Promise<any> {
  for (let i = 0; i < 30; i++) {
    const r = await api.get(`/v1/alerts/${itemId}/evaluations`);
    const ev = (r.body as any[]).find((e) => e.id === evaluationId);
    if (ev && ev.state !== "pending") return ev;
    await new Promise((res) => setTimeout(res, 1000));
  }
  throw new Error(`évaluation ${evaluationId} toujours pending`);
}
