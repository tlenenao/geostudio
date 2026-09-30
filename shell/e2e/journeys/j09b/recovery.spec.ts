/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { alertConfig, getAlertSeed, mkRule, psql, type Api } from "./helpers";
import { exportWriter, reader } from "../j06b/helpers";

// Reprise des jobs : des lignes périmées sont posées en SQL (la seule façon de simuler un worker
// tué sans toucher à la stack), puis les balayages périodiques RÉELS du worker (*/5 et */15) sont
// observés sans aucune intervention. Les lignes sont toutes antidatées de 2 h (seuil : 60 min).
test.setTimeout(1_200_000);

let creator: Api;
let creatorId: string;
let datasetId: string;
let colId: string;
let appId: string;
let pipelineId: string;
let ruleId: string;
const ids = {
  exportRunning: randomUUID().replaceAll("-", ""),
  exportPending: randomUUID().replaceAll("-", ""),
  ingRunning: randomUUID().replaceAll("-", ""),
  ingPending: randomUUID().replaceAll("-", ""),
  appRunning: randomUUID().replaceAll("-", ""),
  appPending: randomUUID().replaceAll("-", ""),
  pipeRun: randomUUID().replaceAll("-", ""),
  evalPending: randomUUID().replaceAll("-", ""),
};
const OLD = "((now() at time zone 'utc') - interval '2 hours')";
const q = (sql: string) => psql(sql).trim();

test.beforeAll(async () => {
  const s = await getAlertSeed();
  creator = s.creator;
  datasetId = s.datasetId;
  colId = s.colId;
  creatorId = (await creator.get("/v1/me")).body.id;
  // J09B_REUSE=1 : rejoue les assertions sur les lignes déjà posées (un test en échec redémarre le
  // worker Playwright donc rejoue ce beforeAll) — sert à vérifier les test.fixme un par un.
  const cache = join(tmpdir(), "j09b-recovery-state.json");
  if (process.env.J09B_REUSE && existsSync(cache)) {
    const c = JSON.parse(readFileSync(cache, "utf8"));
    Object.assign(ids, c.ids);
    ({ appId, pipelineId, ruleId } = c);
    return;
  }
  const app = await creator.send("POST", "/v1/configs", {
    title: `${s.tag}-rec-app`,
    config: {
      version: 1,
      kind: "app",
      theme: {},
      dataSources: [],
      messages: [],
      layout: { type: "grid", breakpoints: {}, items: [] },
    },
  });
  appId = app.body.itemId;
  const p = await creator.send("POST", "/v1/configs", {
    title: `${s.tag}-rec-pipe`,
    config: {
      version: 1,
      kind: "pipeline",
      pipeline: {
        nodes: [reader(colId), exportWriter(`${s.tag}-rec.csv`)],
        edges: [{ id: "e1", from: "r", to: "w" }],
        refreshPolicy: { enabled: true, cron: "0 3 1 1 *" },
      },
    },
  });
  expect(p.status, JSON.stringify(p.body)).toBe(201);
  pipelineId = p.body.itemId;
  ruleId = await mkRule(creator, datasetId, `${s.tag}-rec-rule`, {
    refreshPolicy: { enabled: true, cron: "0 3 1 1 *" },
    channels: [{ kind: "webhook", url: "https://example.test/h" }],
  });
  expect(alertConfig(datasetId).alert.query.agg).toBe("count");

  q(`INSERT INTO export_jobs (id,tenant_id,item_id,user_id,format,status,started_at,created_at)
     VALUES ('${ids.exportRunning}','default','${appId}','${creatorId}','pdf','running',${OLD},${OLD}),
            ('${ids.exportPending}','default','${appId}','${creatorId}','pdf','pending',NULL,${OLD})`);
  q(`INSERT INTO app_export_jobs (id,tenant_id,item_id,user_id,mode,status,started_at,created_at)
     VALUES ('${ids.appRunning}','default','${appId}','${creatorId}','static','running',${OLD},${OLD}),
            ('${ids.appPending}','default','${appId}','${creatorId}','static','pending',NULL,${OLD})`);
  q(`INSERT INTO ingestion_jobs (id,tenant_id,created_by,status,source_key,filename,collection_title,created_at,updated_at)
     VALUES ('${ids.ingRunning}','default','${creatorId}','running','default/x.csv','x.csv','aud-j09b-rec-run',${OLD},${OLD}),
            ('${ids.ingPending}','default','${creatorId}','pending','default/y.csv','y.csv','aud-j09b-rec-pend',${OLD},${OLD})`);
  q(`INSERT INTO pipeline_runs (id,tenant_id,pipeline_item_id,status,started_at,created_at)
     VALUES ('${ids.pipeRun}','default','${pipelineId}','running',${OLD},${OLD})`);
  q(`INSERT INTO alert_evaluations (id,tenant_id,alert_rule_item_id,state,transitioned,created_at)
     VALUES ('${ids.evalPending}','default','${ruleId}','pending',false,${OLD})`);
  writeFileSync(cache, JSON.stringify({ ids, appId, pipelineId, ruleId }));
});

const status = (table: string, id: string) =>
  q(
    `SELECT status || '|' || coalesce(${table === "ingestion_jobs" ? "error_message" : "error"},'') FROM ${table} WHERE id='${id}'`,
  );

test("export_jobs et app_export_jobs 'running' depuis 2 h : le balayage réel les passe en erreur (timeout du worker)", async () => {
  await expect
    .poll(() => status("export_jobs", ids.exportRunning), { timeout: 420_000, intervals: [10_000] })
    .toMatch(/^error\|export timed out/);
  await expect
    .poll(() => status("app_export_jobs", ids.appRunning), {
      timeout: 420_000,
      intervals: [10_000],
    })
    .toMatch(/^error\|app export timed out/);
});

test("pipeline et alerte : un run 'running' / une évaluation 'pending' périmés rendent l'objet dû, le balayage crée une nouvelle exécution", async () => {
  await expect
    .poll(
      () => Number(q(`SELECT count(*) FROM pipeline_runs WHERE pipeline_item_id='${pipelineId}'`)),
      { timeout: 420_000, intervals: [10_000] },
    )
    .toBeGreaterThanOrEqual(2);
  await expect
    .poll(
      () =>
        Number(q(`SELECT count(*) FROM alert_evaluations WHERE alert_rule_item_id='${ruleId}'`)),
      { timeout: 420_000, intervals: [10_000] },
    )
    .toBeGreaterThanOrEqual(2);
});

// Finding j09b-009 : le balayage ne ferme pas la ligne périmée, il en crée une nouvelle : le run
// zombie reste 'running' (et l'évaluation 'pending') à jamais dans l'historique affiché.
bug(
  "j09b-009 : le run 'running' périmé d'un pipeline et l'évaluation 'pending' périmée d'une alerte sont clos en erreur à la reprise",
  async () => {
    await expect
      .poll(() => status("pipeline_runs", ids.pipeRun), { timeout: 420_000, intervals: [10_000] })
      .toMatch(/^error\|/);
    await expect
      .poll(() => status("alert_evaluations", ids.evalPending), {
        timeout: 420_000,
        intervals: [10_000],
      })
      .toMatch(/^error\|/);
  },
);

test("ingestion_jobs 'running' depuis 2 h : le balayage */15 le passe en erreur et notifie le créateur", async () => {
  await expect
    .poll(() => status("ingestion_jobs", ids.ingRunning), {
      timeout: 1_000_000,
      intervals: [15_000],
    })
    .toMatch(/^error\|ingestion timed out/);
  const notifs = await creator.get("/v1/notifications?limit=50");
  const mine = notifs.body.notifications.filter((n: any) =>
    JSON.stringify(n).includes("aud-j09b-rec-run"),
  );
  expect(mine.length).toBeGreaterThanOrEqual(1);
});

// Finding j09b-010 : seuls les jobs 'running' sont repris ; un job resté 'pending' (file jamais
// consommée, déféré perdu, POST en 500 après commit) n'est jamais clos et reste « en attente »
// indéfiniment, pour les trois types de jobs.
bug(
  "j09b-010 : des jobs 'pending' vieux de 2 h (export, appexport, ingestion) finissent clos en erreur",
  async () => {
    const states = () =>
      [
        status("export_jobs", ids.exportPending),
        status("app_export_jobs", ids.appPending),
        status("ingestion_jobs", ids.ingPending),
      ].map((s) => s.split("|")[0]);
    expect(states()).not.toContain("pending");
  },
);
