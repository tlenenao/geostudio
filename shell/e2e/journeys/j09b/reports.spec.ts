/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  HOOK,
  RECV,
  apiFor,
  getAlertSeed,
  psql,
  recvLog,
  startHarness,
  stopHarness,
  type Api,
} from "./helpers";

// Rapports planifiés (ReportSchedule) avec l'export ALLUMÉ : CRUD, API des runs, déclenchement
// par le balayage réel du worker, notifications (in-app, webhook, e-mail).
test.setTimeout(900_000);

let creator: Api;
let reader: Api;
let admin: Api;
let tag: string;
let creatorId: string;
let appId: string;
let bookmarkId: string;
let smtpName: string;
let reportC: string;
const q = (sql: string) => psql(sql).trim();
const OLD = "((now() at time zone 'utc') - interval '1 minute')";

function report(over: any = {}) {
  return {
    version: 1,
    kind: "report",
    report: {
      bookmarkItemId: bookmarkId,
      refreshPolicy: { enabled: false, cron: "*/5 * * * *" },
      channels: [{ kind: "webhook", url: `${HOOK}/hook` }],
      ...over,
    },
  };
}
async function mkReport(title: string, over: any = {}): Promise<string> {
  const r = await creator.send("POST", "/v1/configs", { title, config: report(over) });
  expect(r.status, JSON.stringify(r.body)).toBe(201);
  return r.body.itemId as string;
}

function runNotify(): string {
  return execFileSync("docker", ["exec", "-i", RECV, "python", "-"], {
    encoding: "utf8",
    input: [
      "from app.reports.jobs import _notify_pending_reports",
      "from app.jobs.common import session_factory",
      "_notify_pending_reports(session_factory())",
    ].join("\n"),
    stdio: ["pipe", "pipe", "pipe"],
  });
}

test.beforeAll(async () => {
  startHarness();
  const s = await getAlertSeed();
  tag = s.tag;
  creator = await apiFor("creator"); // jeton frais : le seed attend le CDC, l ancien peut avoir expiré
  reader = await apiFor("reader");
  admin = await apiFor("admin");
  creatorId = (await creator.get("/v1/me")).body.id;
  const app = await creator.send("POST", "/v1/configs", {
    title: `${tag}-rep-app`,
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
  const bm = await creator.send("POST", "/v1/configs", {
    title: `${tag}-rep-bm`,
    config: { version: 1, kind: "bookmark", bookmark: { appId, pageId: "p1" } },
  });
  bookmarkId = bm.body.itemId;
  smtpName = `${tag}-rep-smtp`;
  // Coffre à propriétaire (P16.08) : le secret doit appartenir au propriétaire du rapport (le Créateur).
  const sm = await creator.send("POST", "/v1/secrets", {
    name: smtpName,
    payload: {
      kind: "smtp",
      host: RECV,
      // Port STARTTLS : certificat de recv.py approuvé par le harnais (cf. trustReceiverCert).
      port: 2526,
      username: "alerts",
      password: "s3cret-pw",
      useTls: true,
      fromAddress: "reports@audit.test",
    },
  });
  expect(sm.status).toBe(201);
  reportC = await mkReport(`${tag}-rep-C`, {
    channels: [
      { kind: "webhook", url: `${HOOK}/hook` },
      { kind: "email", to: "ops@audit.test", smtpSecretName: smtpName },
    ],
  });
});

test.afterAll(() => {
  stopHarness();
});

test("rendu abouti simulé : webhook et e-mail livrés, notif in-app, API des runs (présigné, pagination, droits), validations de création", async () => {
  const jobId = randomUUID().replaceAll("-", "");
  q(`INSERT INTO export_jobs (id,tenant_id,item_id,user_id,format,status,result_key,started_at,finished_at,created_at)
     VALUES ('${jobId}','default','${appId}','${creatorId}','pdf','done','default/${jobId}.pdf',${OLD},${OLD},${OLD})`);
  q(`INSERT INTO report_runs (id,tenant_id,report_item_id,export_job_id,created_at)
     VALUES ('${randomUUID().replaceAll("-", "")}','default','${reportC}','${jobId}',${OLD})`);
  await creator.send("PATCH", "/v1/notifications/preference", { value: "all" });
  runNotify();
  const title = `${tag}-rep-C`;
  const hooks = recvLog("http").filter((h) => h.body.includes(reportC));
  expect(hooks).toHaveLength(1);
  const body = JSON.parse(hooks[0].body);
  expect(body).toMatchObject({ reportItemId: reportC, status: "done", error: null });
  expect(body.resultUrl).toMatch(/^https?:\/\//);
  const mails = recvLog("smtp").filter((m) => m.data.includes(title));
  expect(mails).toHaveLength(1);
  expect(mails[0].data).toContain(`Subject: [GeoStudio] Rapport : ${title}`);
  expect(mails[0].data).toContain("done");
  const notifs = await creator.get("/v1/notifications?page=1&pageSize=100");
  const mine = (notifs.body.notifications as any[]).filter((n: any) =>
    JSON.stringify(n).includes(title),
  );
  expect(mine.some((n: any) => n.kind === "report" && n.status === "success")).toBe(true);
  // un run notifié ne l'est jamais deux fois
  runNotify();
  expect(recvLog("http").filter((h) => h.body.includes(reportC))).toHaveLength(1);

  const r = await creator.get(`/v1/reports/${reportC}/runs`);
  expect(r.status).toBe(200);
  expect(r.body).toHaveLength(1);
  expect(r.body[0]).toMatchObject({ status: "done" });
  expect(r.body[0].resultUrl).toMatch(/Signature=/);
  expect(r.body[0].notifiedAt).toBeTruthy();
  expect((await creator.get(`/v1/reports/${reportC}/runs?limit=0`)).status).toBe(422);
  expect((await creator.get(`/v1/reports/${reportC}/runs?offset=-1`)).status).toBe(422);
  expect((await reader.get(`/v1/reports/${reportC}/runs`)).status).toBe(404);
  expect((await creator.get(`/v1/reports/inexistant/runs`)).status).toBe(404);

  const noChannel = await creator.send("POST", "/v1/configs", {
    title: `${tag}-rep-x1`,
    config: report({ channels: [] }),
  });
  expect(noChannel.status).toBe(422);
  const badCron = await creator.send("POST", "/v1/configs", {
    title: `${tag}-rep-x2`,
    config: report({ refreshPolicy: { enabled: true, cron: "pas un cron" } }),
  });
  expect(badCron.status).toBe(422);
  const noBm = await creator.send("POST", "/v1/configs", {
    title: `${tag}-rep-x3`,
    config: report({ bookmarkItemId: "inexistant" }),
  });
  expect([403, 404, 422]).toContain(noBm.status);

  const other = admin;
  const app = await other.send("POST", "/v1/configs", {
    title: `${tag}-rep-priv-app`,
    config: {
      version: 1,
      kind: "app",
      theme: {},
      dataSources: [],
      messages: [],
      layout: { type: "grid", breakpoints: {}, items: [] },
    },
  });
  const bm = await other.send("POST", "/v1/configs", {
    title: `${tag}-rep-priv-bm`,
    config: { version: 1, kind: "bookmark", bookmark: { appId: app.body.itemId, pageId: "p1" } },
  });
  expect(bm.status).toBe(201);
  const rPriv = await creator.send("POST", "/v1/configs", {
    title: `${tag}-rep-priv`,
    config: report({ bookmarkItemId: bm.body.itemId }),
  });
  expect([403, 404, 422]).toContain(rPriv.status);
});

// Finding j09b-011 : le lien de téléchargement posé dans le webhook et l'e-mail est signé sur
// l'hôte interne du stockage (S3_ENDPOINT_URL, http://minio:9000) : inutilisable pour le
// destinataire d'un e-mail ou d'un webhook externe (7 jours de validité, mais nom d'hôte interne).
bug(
  "j09b-011 : le lien du rapport envoyé par webhook/e-mail est joignable hors du réseau Docker",
  async () => {
    const hooks = recvLog("http").filter((h) => h.body.includes(reportC));
    const url = new URL(JSON.parse(hooks[0].body).resultUrl);
    expect(url.hostname).not.toMatch(/^(minio|localhost|127\.|10\.|172\.|192\.168\.)/);
  },
);

test.describe("balayage réel du worker", () => {
  let repA: string;
  let repB: string;

  test("le balayage */5 du worker prend en compte les rapports planifiés : un run est écrit pour le rapport dû et notifié", async () => {
    repA = await mkReport(`${tag}-rep-A`, {
      refreshPolicy: { enabled: true, cron: "*/5 * * * *" },
      channels: [{ kind: "webhook", url: `${HOOK}/hook` }],
    });
    repB = await mkReport(`${tag}-rep-B`, {
      refreshPolicy: { enabled: true, cron: "0 3 1 1 *" },
    });
    // repB (cron annuel) n'est plus dû au premier balayage (j09b-013 corrigé) : seul repA court.
    await expect
      .poll(() => Number(q(`SELECT count(*) FROM report_runs WHERE report_item_id='${repA}'`)), {
        timeout: 420_000,
        intervals: [10_000],
      })
      .toBeGreaterThanOrEqual(1);
    // Le worker dispose maintenant de CORE_EXPORT_ENABLED (j09b-001) : chaque run porte une tâche d'export
    // et finit notifié ; seul le résultat du rendu (réussite/échec) dépend de l'export-worker.
    await expect
      .poll(
        () =>
          Number(
            q(
              `SELECT count(*) FROM report_runs WHERE report_item_id='${repA}' AND notified_at IS NOT NULL`,
            ),
          ),
        { timeout: 420_000, intervals: [10_000] },
      )
      .toBeGreaterThanOrEqual(1);
    creator = await apiFor("creator"); // le jeton du setup a expiré pendant l'attente
    const notifs = await creator.get("/v1/notifications?page=1&pageSize=100");
    expect(
      (notifs.body.notifications as any[]).some((n) => n.itemId === repA && n.kind === "report"),
    ).toBe(true);
  });

  // Finding j09b-001 : le service `worker` ne reçoit pas CORE_EXPORT_ENABLED (docker-compose.yml ne
  // le passe qu'à core et export-worker) : is_export_enabled() y est faux, donc CHAQUE rapport
  // planifié échoue au déclenchement avec « export capability disabled on this instance » alors
  // que l'export est allumé sur l'instance. Aucun rapport planifié ne s'exécute jamais.
  bug(
    "j09b-001 : un rapport planifié est déclenché par le worker (un rendu est mis en file)",
    async () => {
      const r = q(`SELECT count(export_job_id) FROM report_runs WHERE report_item_id='${repA}'`);
      expect(Number(r)).toBeGreaterThanOrEqual(1);
    },
  );

  // Finding j09b-013 : comme pour les pipelines (j06b-013), un rapport sans run antérieur est
  // dû au premier balayage quel que soit son cron (« 0 3 1 1 * » = 1er janvier, 3 h).
  bug(
    "j09b-013 : un rapport au cron « 0 3 1 1 * » n'est pas déclenché au premier balayage",
    async () => {
      expect(Number(q(`SELECT count(*) FROM report_runs WHERE report_item_id='${repB}'`))).toBe(0);
    },
  );
});

test("chaîne complète hors balayage du worker (déclenchement exécuté avec l'env du cœur) : run + export_jobs + tâche de rendu, puis notification du résultat réel", async () => {
  test.setTimeout(600_000);
  const repD = await mkReport(`${tag}-rep-D`, {
    refreshPolicy: { enabled: true, cron: "*/5 * * * *" },
    channels: [{ kind: "webhook", url: `${HOOK}/hook` }],
  });
  // la cadence se mesure depuis la création (j09b-013) : antidater pour que le rapport soit dû
  q(`UPDATE items SET created_at = now() - interval '1 hour' WHERE id='${repD}'`);
  execFileSync("docker", ["exec", "-i", RECV, "python", "-"], {
    encoding: "utf8",
    input: [
      "from app.jobs import app",
      "from app.reports.jobs import _trigger_due_reports",
      "from app.jobs.common import session_factory",
      "with app.open():",
      "    _trigger_due_reports(session_factory())",
    ].join("\n"),
    stdio: ["pipe", "pipe", "pipe"],
  });
  const row = q(
    `SELECT export_job_id FROM report_runs WHERE report_item_id='${repD}' ORDER BY created_at DESC LIMIT 1`,
  );
  expect(row).toMatch(/^[0-9a-f]{32}$/);
  // l'export-worker réel (qui redémarre en boucle, j05b-008) prend la tâche : état terminal attendu
  await expect
    .poll(() => q(`SELECT status FROM export_jobs WHERE id='${row}'`), {
      timeout: 360_000,
      intervals: [10_000],
    })
    .toMatch(/^(done|error)$/);
  runNotify();
  const hooks = recvLog("http").filter((h) => h.body.includes(repD));
  expect(hooks).toHaveLength(1);
  const body = JSON.parse(hooks[0].body);
  expect(["done", "error"]).toContain(body.status);
});
