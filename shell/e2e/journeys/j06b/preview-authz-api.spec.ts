/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { apiFor, type Api } from "./seeds";
import { stamp, CORE_URL } from "../_fixtures/env";
import {
  createPipeline,
  createPlainCollection,
  edge,
  exportWriter,
  getPlainSeed,
  reader,
  type PNode,
} from "./helpers";

const tag = stamp("j06b");
let admin: Api;
let creator: Api;
let analyst: Api;
let viewer: Api;
let plain: string;
let pipe: string;

const filter = (expr: string): PNode => ({
  id: "f",
  kind: "transform",
  op: "transform.filter",
  params: { expr },
});

test.beforeAll(async () => {
  [admin, creator, analyst, viewer] = await Promise.all([
    apiFor("admin"),
    apiFor("creator"),
    apiFor("analyst"),
    apiFor("reader"),
  ]);
  plain = (await getPlainSeed()).collection;
  const p = await createPipeline(
    creator,
    `${tag}-prev`,
    [reader(plain), filter("pop > 5"), exportWriter(`j06b/${tag}-prev.csv`)],
    [edge("r", "f"), edge("f", "w")],
  );
  pipe = p.itemId!;
});

test.describe("j06b aperçu, historique des runs, catalogue", () => {
  test("aperçu : lignes jusqu'au nœud demandé, avec ou sans graphe non enregistré en corps", async () => {
    const atReader = await creator.send("POST", `/v1/pipelines/${pipe}/preview?upTo=r`);
    expect(atReader.status).toBe(200);
    expect(atReader.body).toHaveLength(6);
    const atFilter = await creator.send("POST", `/v1/pipelines/${pipe}/preview?upTo=f`);
    expect(atFilter.body).toHaveLength(4);
    // Le graphe du corps prime sur celui enregistré (filtre durci, jamais sauvegardé).
    const override = await creator.send("POST", `/v1/pipelines/${pipe}/preview?upTo=f`, {
      pipeline: {
        nodes: [reader(plain), filter("pop > 25"), exportWriter("x.csv")],
        edges: [edge("r", "f"), edge("f", "w")],
      },
    });
    expect(override.body).toHaveLength(2);
  });

  test("aperçu et historique : erreurs (nœud inconnu, writer, upTo absent, corps invalide, pagination)", async () => {
    const unknown = await creator.send("POST", `/v1/pipelines/${pipe}/preview?upTo=zzz`);
    expect(unknown.status).toBe(400);
    expect(unknown.body.detail).toContain("zzz");
    const onWriter = await creator.send("POST", `/v1/pipelines/${pipe}/preview?upTo=w`);
    expect(onWriter.status).toBe(400);
    expect((await creator.send("POST", `/v1/pipelines/${pipe}/preview`)).status).toBe(422);
    const bad = await creator.send("POST", `/v1/pipelines/${pipe}/preview?upTo=r`, {
      pipeline: { nodes: [{ id: "r" }], edges: [] },
    });
    expect(bad.status).toBe(422);
    const noPipe = await creator.send("POST", `/v1/pipelines/inexistant/preview?upTo=r`);
    expect(noPipe.status).toBe(404);
    // Historique des runs : limit plafonné côté serveur, valeurs invalides refusées.
    expect((await creator.get(`/v1/pipelines/${pipe}/runs?limit=100000`)).status).toBe(200);
    expect((await creator.get(`/v1/pipelines/${pipe}/runs?limit=0`)).status).toBe(422);
    expect((await creator.get(`/v1/pipelines/${pipe}/runs?offset=-1`)).status).toBe(422);
    expect((await creator.get(`/v1/pipelines/${pipe}/runs?offset=99999`)).body).toEqual([]);
  });

  test("droits : collection privée d'autrui illisible, pipeline inconnu → 404, public en lecture → runs 200 mais preview/run/jeton 403", async () => {
    const priv = await createPlainCollection(admin, `${tag}-privee`, [["secret", 42]]);
    const leak = await creator.send("POST", `/v1/pipelines/${pipe}/preview?upTo=r`, {
      pipeline: { nodes: [reader(priv), exportWriter("x.csv")], edges: [edge("r", "w")] },
    });
    expect(leak.status).toBe(400);
    expect(JSON.stringify(leak.body)).not.toContain("secret");

    for (const who of [analyst, viewer]) {
      expect((await who.get(`/v1/pipelines/${pipe}/runs`)).status).toBe(404);
      expect((await who.send("POST", `/v1/pipelines/${pipe}/preview?upTo=r`)).status).toBe(404);
      expect((await who.send("POST", `/v1/pipelines/${pipe}/run`)).status).toBe(404);
    }
    const shared = await createPipeline(
      creator,
      `${tag}-public`,
      [reader(plain), exportWriter(`j06b/${tag}-public.csv`)],
      [edge("r", "w")],
    );
    await creator.send("PUT", `/v1/items/${shared.itemId}/sharing`, { public: true, groups: [] });
    const id = shared.itemId;
    expect((await viewer.get(`/v1/pipelines/${id}/runs`)).status).toBe(200);
    expect((await viewer.send("POST", `/v1/pipelines/${id}/preview?upTo=r`)).status).toBe(403);
    expect((await viewer.send("POST", `/v1/pipelines/${id}/run`)).status).toBe(403);
    expect((await viewer.send("POST", `/v1/pipelines/${id}/webhook-tokens`)).status).toBe(403);
    // Un lecteur voit la liste des jetons d'un pipeline public (ids, dates), jamais leur valeur.
    expect((await viewer.get(`/v1/pipelines/${id}/webhook-tokens`)).status).toBe(200);
    for (const who of [analyst, viewer]) {
      expect((await who.send("POST", `/v1/pipelines/${pipe}/webhook-tokens`)).status).toBe(404);
    }
  });

  // Confirme j06-004 par exécution : l'aperçu s'exécute dans le cœur (qui a la clé de secrets) et
  // le DSN d'un secret Créateur atteint le Postgres interne du compose (échec d'authentification
  // renvoyé par postgis, pas un refus d'egress).
  test.fixme("j06b-010 : l'aperçu d'un reader postgres ne joint pas le Postgres interne du compose", async () => {
    const secretName = `${tag}-dsn-interne`;
    const s = await creator.send("POST", "/v1/secrets", {
      name: secretName,
      payload: { kind: "postgres_dsn", dsn: "postgresql://gis:mauvais@postgis:5432/gis" },
    });
    expect(s.status).toBe(201);
    const r = await creator.send("POST", `/v1/pipelines/${pipe}/preview?upTo=r`, {
      pipeline: {
        nodes: [
          {
            id: "r",
            kind: "reader",
            op: "reader.connector.postgres",
            params: { secretName, query: "SELECT 1 AS un" },
          },
          exportWriter("x.csv"),
        ],
        edges: [edge("r", "w")],
      },
    });
    expect(JSON.stringify(r.body)).not.toMatch(/authentication failed|password/i);
  });

  // Finding j06b-009 : le catalogue n'exige aucune authentification (route sans get_current_user).
  test.fixme("j06b-009 : GET /pipelines/ops exige une session", async () => {
    const r = await fetch(`${CORE_URL}/v1/pipelines/ops`);
    expect(r.status).toBe(401);
  });

  test("catalogue (57 op), enregistrement et next-run : op inconnue, params invalides, cron invalide refusés", async () => {
    // Catalogue : 57 op, schéma de params pour chacune, reader.file/writer.file absents (flag éteint).

    const cat = await creator.get("/v1/pipelines/ops");
    expect(cat.status).toBe(200);
    const ops = Object.keys(cat.body);
    expect(ops).toHaveLength(57);
    for (const [op, c] of Object.entries<any>(cat.body)) {
      expect(c.kind, op).toMatch(/^(reader|transform|writer)$/);
      expect(c.paramsSchema, op).toBeTruthy();
    }
    expect(ops).not.toContain("reader.file");
    expect(ops).not.toContain("writer.file");

    const save = (nodes: any[], edges: any[], extra: any = {}) =>
      createPipeline(creator, `${tag}-val`, nodes, edges, extra);
    const W = exportWriter("x.csv");
    const unknownOp = await save(
      [reader(plain), { id: "t", kind: "transform", op: "transform.nexistepas", params: {} }, W],
      [edge("r", "t"), edge("t", "w")],
    );
    expect(unknownOp.status).toBeGreaterThanOrEqual(400);
    expect(unknownOp.status).toBeLessThan(500);
    const badParams = await save(
      [reader(plain), { id: "t", kind: "transform", op: "transform.filter", params: {} }, W],
      [edge("r", "t"), edge("t", "w")],
    );
    expect(badParams.status).toBe(422);
    const badCron = await save([reader(plain), W], [edge("r", "w")], {
      refreshPolicy: { enabled: true, cron: "pas un cron" },
    });
    expect(badCron.status).toBe(422);
    // GET /pipelines/next-run : valide, invalide, sans occurrence future.
    const nextOk = await creator.get(
      `/v1/pipelines/next-run?cron=${encodeURIComponent("*/5 * * * *")}`,
    );
    expect(nextOk.status).toBe(200);
    expect(new Date(nextOk.body.nextRun).getTime()).toBeGreaterThan(Date.now());
    const nextBad = await creator.get(
      `/v1/pipelines/next-run?cron=${encodeURIComponent("pas un cron")}`,
    );
    expect(nextBad.status).toBe(400);
    const never = await creator.get(
      `/v1/pipelines/next-run?cron=${encodeURIComponent("0 0 31 2 *")}`,
    );
    expect(never.status).toBe(400);
  });
});
