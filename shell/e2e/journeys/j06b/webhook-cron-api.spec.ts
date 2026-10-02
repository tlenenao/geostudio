import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import { apiFor, type Api } from "./seeds";
import { stamp, CORE_URL } from "../_fixtures/env";
import { psql } from "../j02/helpers";
import {
  createPipeline,
  deferRun,
  edge,
  ensureExportsBucket,
  exportWriter,
  getPlainSeed,
  reader,
} from "./helpers";

const tag = stamp("j06b");
let creator: Api;
let plain: string;

test.beforeAll(async () => {
  creator = await apiFor("creator");
  plain = (await getPlainSeed()).collection;
  ensureExportsBucket();
});

const mk = (suffix: string, extra: Record<string, unknown> = {}) =>
  createPipeline(
    creator,
    `${tag}-${suffix}`,
    [reader(plain), exportWriter(`j06b/${tag}-${suffix}.csv`)],
    [edge("r", "w")],
    extra,
  );

const trigger = (id: string, token?: string) =>
  fetch(`${CORE_URL}/v1/pipelines/${id}/trigger`, {
    method: "POST",
    headers: token === undefined ? {} : { authorization: `Bearer ${token}` },
  });

test.describe("j06b webhook entrant", () => {
  test("cycle de vie : création (jeton montré une fois), liste sans jeton, refus 401/404, révocation", async () => {
    const a = await mk("wh-a");
    const b = await mk("wh-b");
    const t = await creator.send("POST", `/v1/pipelines/${a.itemId}/webhook-tokens`);
    expect(t.status).toBe(201);
    expect(t.body.token.length).toBeGreaterThanOrEqual(32);
    const list = await creator.get(`/v1/pipelines/${a.itemId}/webhook-tokens`);
    expect(list.body).toHaveLength(1);
    expect(JSON.stringify(list.body)).not.toContain(t.body.token);
    expect(list.body[0].lastUsedAt).toBeNull();
    // Stocké haché : le clair n'apparaît nulle part en base.
    const leak = psql(
      `SELECT count(*) FROM pipeline_webhook_tokens WHERE token_hash LIKE '%${t.body.token}%'`,
    );
    expect(leak.trim()).toBe("0");

    expect((await trigger(a.itemId!)).status).toBe(401);
    expect((await trigger(a.itemId!, "faux-jeton")).status).toBe(404);
    // Jeton valide mais pour un autre pipeline : même 404 (pas d'oracle d'existence).
    expect((await trigger(b.itemId!, t.body.token)).status).toBe(404);

    const before = psql(`SELECT count(*) FROM pipeline_runs WHERE pipeline_item_id='${a.itemId}'`);
    const ok = await trigger(a.itemId!, t.body.token);
    // 202 attendu ; 500 = AppNotOpen (j06b-001) APRÈS création du run : on rattrape pour la suite.
    expect([202, 500]).toContain(ok.status);
    const runs = psql(`SELECT id FROM pipeline_runs WHERE pipeline_item_id='${a.itemId}'`).trim();
    expect(runs.split("\n")).toHaveLength(Number(before.trim()) + 1);
    if (ok.status === 500) deferRun(runs.split("\n")[0]);

    const del = await creator.send(
      "DELETE",
      `/v1/pipelines/${a.itemId}/webhook-tokens/${t.body.id}`,
    );
    expect(del.status).toBe(204);
    expect((await trigger(a.itemId!, t.body.token)).status).toBe(404);
    expect(
      (await creator.send("DELETE", `/v1/pipelines/${a.itemId}/webhook-tokens/${t.body.id}`))
        .status,
    ).toBe(404);
  });

  // Finding j06b-011 : la clé du limiteur est l'en-tête Authorization brut → jeton variable = budget neuf.
  test("j06b-011 : 60 essais avec des jetons faux DIFFÉRENTS sont limités (429), comme avec le même jeton", async () => {
    const a = await mk("wh-rl");
    const same: number[] = [];
    for (let i = 0; i < 35; i++) same.push((await trigger(a.itemId!, `meme-${tag}`)).status);
    expect(same.filter((c) => c === 429).length).toBeGreaterThanOrEqual(1); // contrôle : passe
    const vary: number[] = [];
    for (let i = 0; i < 60; i++) vary.push((await trigger(a.itemId!, `${tag}-essai-${i}`)).status);
    expect(vary.filter((c) => c === 429).length).toBeGreaterThanOrEqual(1);
  });
});

test.describe("j06b planification cron", () => {
  // Finding j06b-012 : croniter accepte 6 champs (secondes) ; la politique enregistrée « chaque seconde » est valide.
  test("j06b-012 : un cron à 6 champs (secondes) est refusé à l'enregistrement", async () => {
    const p = await mk("cron6", { refreshPolicy: { enabled: true, cron: "* * * * * *" } });
    expect(p.status).toBe(422);
  });

  test.describe.serial("balayage périodique (*/5 min)", () => {
    let onId: string;
    let yearlyId: string;

    test("une politique activée « * * * * * » déclenche un run via le worker, une politique coupée non", async () => {
      test.setTimeout(400_000);
      const on = await mk("cron-on", { refreshPolicy: { enabled: true, cron: "* * * * *" } });
      const off = await mk("cron-off", { refreshPolicy: { enabled: false, cron: "* * * * *" } });
      const yearly = await mk("cron-yearly", {
        refreshPolicy: { enabled: true, cron: "0 3 1 1 *" },
      });
      onId = on.itemId!;
      yearlyId = yearly.itemId!;
      const count = (id: string) =>
        Number(psql(`SELECT count(*) FROM pipeline_runs WHERE pipeline_item_id='${id}'`).trim());
      const t0 = Date.now();
      while (Date.now() - t0 < 370_000 && count(onId) === 0) {
        await new Promise((r) => setTimeout(r, 5000));
      }
      expect(count(onId)).toBeGreaterThanOrEqual(1);
      expect(count(off.itemId!)).toBe(0);
      const runs = await creator.get(`/v1/pipelines/${onId}/runs`);
      expect(runs.body.length).toBeGreaterThanOrEqual(1);
    });

    // Finding j06b-013 : sans run antérieur, tout pipeline activé est « dû » au premier balayage, quel que soit son cron.
    bug(
      "j06b-013 : un pipeline planifié « 1er janvier 3h » ne s'exécute pas au premier balayage",
      async () => {
        const n = psql(`SELECT count(*) FROM pipeline_runs WHERE pipeline_item_id='${yearlyId}'`);
        expect(Number(n.trim())).toBe(0);
      },
    );
  });
});
