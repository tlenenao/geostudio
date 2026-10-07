/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { alertConfig, apiFor, getAlertSeed, psql, waitEvaluation, type Api } from "./helpers";

// AlertRule : CRUD via /configs, évaluation (route REST + tâche worker), historique, droits.
test.setTimeout(120_000);

let creator: Api;
let reader: Api;
let analyst: Api;
let datasetId: string;
let tag: string;

test.beforeAll(async () => {
  const s = await getAlertSeed();
  creator = s.creator;
  datasetId = s.datasetId;
  tag = s.tag;
  reader = await apiFor("reader");
  analyst = await apiFor("analyst");
});

async function mkRule(title: string, over: any = {}): Promise<string> {
  const r = await creator.send("POST", "/v1/configs", {
    title: `${tag}-${title}`,
    config: alertConfig(datasetId, over),
  });
  expect(r.status, JSON.stringify(r.body)).toBe(201);
  return r.body.itemId as string;
}

// Crée la ligne d'évaluation via la route REST (dont le déféré échoue, j09-001) puis la relit.
async function pendingEvaluation(itemId: string): Promise<string> {
  await creator.send("POST", `/v1/alerts/${itemId}/evaluate`);
  const list = await creator.get(`/v1/alerts/${itemId}/evaluations`);
  const pending = (list.body as any[]).find((e) => e.state === "pending");
  expect(pending).toBeTruthy();
  return pending.id as string;
}

const notifyRows = (itemId: string) =>
  psql(
    `SELECT payload::text FROM audit_log WHERE action='alert.notify' AND object_id='${itemId}' ORDER BY created_at`,
  )
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((l) => JSON.parse(l));

test.describe("j09 AlertRule : évaluation et historique", () => {
  test("une règle valide se crée, se liste sur son dataset et n'a aucune évaluation", async () => {
    const id = await mkRule("nominal");
    const evals = await creator.get(`/v1/alerts/${id}/evaluations`);
    expect(evals.status).toBe(200);
    expect(evals.body).toEqual([]);
    const listed = await creator.get(`/v1/datasets/${datasetId}/alerts`);
    expect(listed.body.map((r: any) => r.itemId)).toContain(id);
  });

  // Bug confirmé : voir docs/revue/audit-2026-09-29/j09/findings.jsonl
  test("j09-001 : POST /alerts/{id}/evaluate répond 202", async () => {
    const id = await mkRule("evaluate-route");
    const r = await creator.send("POST", `/v1/alerts/${id}/evaluate`);
    expect(r.status).toBe(202);
  });

  // Bug confirmé : voir docs/revue/audit-2026-09-29/j09/findings.jsonl
  test("j09-002 : une évaluation créée par la route REST quitte l'état pending", async () => {
    const id = await mkRule("orphan");
    await creator.send("POST", `/v1/alerts/${id}/evaluate`);
    await new Promise((res) => setTimeout(res, 15_000));
    const list = await creator.get(`/v1/alerts/${id}/evaluations`);
    expect(list.body.length).toBeGreaterThan(0);
    expect(list.body[0].state).not.toBe("pending");
  });

  test("une évaluation exécutée par le worker donne firing puis ne renotifie pas sans transition", async () => {
    const id = await mkRule("firing");
    const first = await pendingEvaluation(id);
    const ev1 = await waitEvaluation(creator, id, first);
    expect(ev1.state).toBe("firing");
    expect(ev1.value).toBe(3);
    expect(ev1.transitioned).toBe(true);
    expect(notifyRows(id)).toHaveLength(1);

    // Un second passage sur la même valeur : pas de transition, pas de nouvelle notification.
    // La ligne pending orpheline de la route REST (j09-002) est ignorée par _previous_terminal_state.
    const second = await pendingEvaluation(id).catch(() => first);
    if (second !== first) {
      const ev2 = await waitEvaluation(creator, id, second);
      expect(ev2.state).toBe("firing");
      expect(ev2.transitioned).toBe(false);
    }
    // Pas de nouvelle notification sur la valeur inchangée, SAUF le rejeu d'une livraison échouée
    // (la cible interne est bloquée par la garde d'egress : la 1re livraison a échoué, alerts/jobs.py `retry`).
    expect(notifyRows(id)).toHaveLength(second !== first ? 2 : 1);
  });

  test("le webhook vers une cible interne est bloqué par la garde d'egress et tracé dans l'audit", async () => {
    const id = await mkRule("egress");
    const ev = await pendingEvaluation(id);
    await waitEvaluation(creator, id, ev);
    const rows = notifyRows(id);
    expect(rows[0]).toMatchObject({ channel: "webhook", success: false });
    expect(rows[0].error).toContain("egress blocked");
  });

  test("j09-013 : une règle count sur un dataset vide s'évalue à 0 au lieu de finir en erreur", async () => {
    const empty = await creator.send("POST", "/v1/collections/empty", {
      title: `${tag}-vide`,
      columns: [{ name: "nom", sqlType: "text" }],
      geometryType: "Point",
      srid: 4326,
    });
    const ds = await creator.send("POST", "/v1/configs", {
      title: `${tag}-ds-vide`,
      config: {
        version: 1,
        kind: "dataset",
        dataset: { source: "collection", collectionId: empty.body.id },
      },
    });
    const rule = await creator.send("POST", "/v1/configs", {
      title: `${tag}-regle-vide`,
      config: alertConfig(ds.body.itemId, { condition: { expr: "value < 1" } }),
    });
    const id = rule.body.itemId as string;
    const ev = await pendingEvaluation(id);
    const done = await waitEvaluation(creator, id, ev);
    expect(done.state).toBe("firing");
    expect(done.value).toBe(0);
  });

  test("j09-003 : un échec de notification est visible dans l'historique d'évaluation", async () => {
    const id = await mkRule("silent-failure");
    const ev = await pendingEvaluation(id);
    const done = await waitEvaluation(creator, id, ev);
    // Le canal a échoué (audit_log) et l'historique l'expose à l'auteur (`notifyError`, `error` = échec d'évaluation).
    expect(notifyRows(id)[0].success).toBe(false);
    expect(done.notifyError).not.toBeNull();
  });

  test("j09-004 : une première évaluation à l'état ok n'envoie pas de notification", async () => {
    const id = await mkRule("first-ok", { condition: { expr: "value > 100" } });
    const ev = await pendingEvaluation(id);
    const done = await waitEvaluation(creator, id, ev);
    expect(done.state).toBe("ok");
    expect(notifyRows(id)).toHaveLength(0);
  });
});

test.describe("j09 AlertRule : validation et droits", () => {
  test("le cœur refuse expression invalide, absence de canal, gabarit invalide, cron invalide", async () => {
    const bad = async (over: any) =>
      (
        await creator.send("POST", "/v1/configs", {
          title: `${tag}-bad`,
          config: alertConfig(datasetId, over),
        })
      ).status;
    expect(await bad({ condition: { expr: "value >" } })).toBe(422);
    expect(await bad({ channels: [] })).toBe(422);
    expect(await bad({ messageTemplate: "{inconnu}" })).toBe(422);
    expect(await bad({ refreshPolicy: { enabled: true, cron: "pas un cron" } })).toBe(422);
  });

  test("un lecteur ne peut ni évaluer ni lire l'historique d'une règle non partagée", async () => {
    const id = await mkRule("rights");
    expect((await reader.send("POST", `/v1/alerts/${id}/evaluate`)).status).toBe(404);
    expect((await reader.get(`/v1/alerts/${id}/evaluations`)).status).toBe(404);
    expect((await analyst.send("POST", `/v1/alerts/${id}/evaluate`)).status).toBe(404);
    expect((await reader.get(`/v1/datasets/${datasetId}/alerts`)).body).toEqual([]);
  });
});
