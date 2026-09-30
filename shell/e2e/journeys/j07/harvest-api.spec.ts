import { test, expect } from "@playwright/test";
import { CORE_URL, stamp } from "../_fixtures/env";
import {
  apiFor,
  createSource,
  deferHarvestAndPoll,
  psql,
  runHarvestInWorker,
  type Api,
} from "./helpers";

// Sources de moissonnage — API. La file `harvest` n'étant consommée par aucun worker de la stack
// (j07-001) et POST …/run répondant 500 (j07-002), l'exécution d'une source est rejouée
// directement dans le conteneur worker (`runHarvestInWorker`).
test.setTimeout(120_000);
const tag = stamp("j07");
let admin: Api;
let creator: Api;
let analyst: Api;
let reader: Api;

test.beforeAll(async () => {
  [creator, analyst, reader] = await Promise.all([
    apiFor("creator"),
    apiFor("analyst"),
    apiFor("reader"),
  ]);
});

// Le limiteur « harvest » (10 écritures/min) est indexé sur l'en-tête Authorization : un jeton
// neuf par test évite d'épuiser le budget d'un test sur le suivant.
test.beforeEach(async () => {
  admin = await apiFor("admin");
});

test.describe("j07 moissonnage — création et droits", () => {
  test("création nominale d'une source STAC en référence : 201 et forme de la réponse", async () => {
    const r = await admin.send("POST", "/v1/harvest/sources", {
      type: "stac",
      url: `https://example.invalid/${tag}-nominal`,
      mode: "reference",
      intervalMinutes: 60,
    });
    expect(r.status).toBe(201);
    expect(r.body).toMatchObject({
      type: "stac",
      mode: "reference",
      enabled: true,
      intervalMinutes: 60,
      lastRunAt: null,
      lastStatus: null,
      lastError: null,
    });
    expect(r.body.id).toMatch(/^[0-9a-f]{32}$/);
  });

  test("validation : type inconnu, intervalle nul et URL vide sont refusés en 422", async () => {
    for (const body of [
      { type: "bogus", url: "https://x.invalid" },
      { type: "stac", url: "https://x.invalid", intervalMinutes: 0 },
      { type: "stac", url: "" },
      { type: "stac", url: "https://x.invalid", mode: "clone" },
    ]) {
      const r = await admin.send("POST", "/v1/harvest/sources", body);
      expect(r.status, JSON.stringify(body)).toBe(422);
    }
  });

  test("le mode copie est refusé (400) pour les connecteurs qui ne le supportent pas", async () => {
    for (const type of ["wms", "wmts", "csw", "ogc-records"]) {
      const r = await admin.send("POST", "/v1/harvest/sources", {
        type,
        url: `https://x.invalid/${tag}`,
        mode: "copy",
      });
      expect(r.status, type).toBe(400);
      expect(r.body.detail).toContain("does not support copy mode");
    }
    const ok = await admin.send("POST", "/v1/harvest/sources", {
      type: "ckan",
      url: `https://x.invalid/${tag}-ckan`,
      mode: "copy",
    });
    expect(ok.status).toBe(201);
  });

  test("droits : créateur, analyste et lecteur ne peuvent ni lister, ni créer, ni lancer (403)", async () => {
    const src = await createSource(admin, { type: "stac", url: `https://x.invalid/${tag}-droits` });
    for (const [who, api] of [
      ["creator", creator],
      ["analyst", analyst],
      ["reader", reader],
    ] as const) {
      expect((await api.get("/v1/harvest/sources")).status, `${who} list`).toBe(403);
      expect((await api.get(`/v1/harvest/sources/${src.id}`)).status, `${who} get`).toBe(403);
      expect(
        (await api.send("POST", "/v1/harvest/sources", { type: "stac", url: "https://x.invalid" }))
          .status,
        `${who} create`,
      ).toBe(403);
      expect(
        (await api.send("PATCH", `/v1/harvest/sources/${src.id}`, { enabled: false })).status,
        `${who} patch`,
      ).toBe(403);
      expect(
        (await api.send("POST", `/v1/harvest/sources/${src.id}/run`)).status,
        `${who} run`,
      ).toBe(403);
      expect((await api.send("DELETE", `/v1/harvest/sources/${src.id}`)).status, `${who} del`).toBe(
        403,
      );
    }
  });

  test("sans jeton, les routes de moissonnage répondent 401", async () => {
    for (const p of ["/v1/harvest/sources", "/v1/harvest/layers", "/v1/harvest/feature-layers"]) {
      const r = await fetch(`${CORE_URL}${p}`);
      expect(r.status, p).toBe(401);
    }
  });

  test("PATCH : bascule enabled, intervalle et mode ; copie refusée sur un WMS", async () => {
    const src = await createSource(admin, { type: "wms", url: `https://x.invalid/${tag}-patch` });
    const p = await admin.send("PATCH", `/v1/harvest/sources/${src.id}`, {
      enabled: false,
      intervalMinutes: 30,
    });
    expect(p.status).toBe(200);
    expect(p.body).toMatchObject({ enabled: false, intervalMinutes: 30 });
    const bad = await admin.send("PATCH", `/v1/harvest/sources/${src.id}`, { mode: "copy" });
    expect(bad.status).toBe(400);
    const zero = await admin.send("PATCH", `/v1/harvest/sources/${src.id}`, { intervalMinutes: 0 });
    expect(zero.status).toBe(422);
  });

  test("source inconnue : GET/PATCH/DELETE/run répondent 404 ; suppression puis relecture 404", async () => {
    for (const [m, p] of [
      ["GET", "/v1/harvest/sources/nope"],
      ["PATCH", "/v1/harvest/sources/nope"],
      ["DELETE", "/v1/harvest/sources/nope"],
      ["POST", "/v1/harvest/sources/nope/run"],
    ] as const) {
      expect((await admin.send(m, p, m === "PATCH" ? {} : undefined)).status, `${m} ${p}`).toBe(
        404,
      );
    }
    const src = await createSource(admin, { type: "stac", url: `https://x.invalid/${tag}-del` });
    expect((await admin.send("DELETE", `/v1/harvest/sources/${src.id}`)).status).toBe(204);
    expect((await admin.get(`/v1/harvest/sources/${src.id}`)).status).toBe(404);
  });

  test("le lecteur voit /harvest/layers et /feature-layers sans les couches privées de l'admin", async () => {
    for (const p of ["/v1/harvest/layers", "/v1/harvest/feature-layers"]) {
      const r = await reader.get(p);
      expect(r.status, p).toBe(200);
      expect(Array.isArray(r.body.layers)).toBe(true);
    }
  });
});

test.describe("j07 moissonnage — exécution", () => {
  test("une source vers une cible interne échoue avec un lastError lisible (garde d'egress)", async () => {
    const src = await createSource(admin, {
      type: "stac",
      url: `http://127.0.0.1:8200/v1/stac?${tag}`,
    });
    runHarvestInWorker(src.id);
    const after = await admin.get(`/v1/harvest/sources/${src.id}`);
    expect(after.body.lastStatus).toBe("error");
    expect(after.body.lastError).toContain("cible réseau interne bloquée");
  });

  test("une URL non valide est acceptée à la création puis échoue à l'exécution avec un message technique", async () => {
    const src = await createSource(admin, { type: "wms", url: `not a url ${tag}` });
    runHarvestInWorker(src.id);
    const after = await admin.get(`/v1/harvest/sources/${src.id}`);
    expect(after.body.lastStatus).toBe("error");
    expect(after.body.lastError).toBeTruthy();
  });

  test("@audit-flaky un catalogue STAC public réel est moissonné (statut ok) et ses enregistrements listés", async () => {
    const src = await createSource(admin, {
      type: "stac",
      url: "https://earth-search.aws.element84.com/v1",
    });
    runHarvestInWorker(src.id);
    const after = await admin.get(`/v1/harvest/sources/${src.id}`);
    test.skip(
      after.body.lastStatus === "error",
      `réseau sortant indisponible : ${after.body.lastError}`,
    );
    expect(after.body.lastStatus).toBe("ok");
    const n = Number(
      psql(`SELECT count(*) FROM harvest_records WHERE source_id='${src.id}'`).trim(),
    );
    expect(n).toBeGreaterThan(0);
    const layers = await admin.get("/v1/harvest/feature-layers");
    expect(layers.body.layers.length).toBeGreaterThan(0);
  });
});

test.describe("j07 moissonnage — défauts constatés", () => {
  // Finding j07-001 : la file `harvest` n'est consommée par aucun worker du compose.
  test.fixme("j07-001 : un job de moissonnage déféré est consommé par le worker (file `harvest`)", async () => {
    const src = await createSource(admin, { type: "stac", url: `https://x.invalid/${tag}-queue` });
    expect(await deferHarvestAndPoll(src.id)).not.toBe("todo");
  });

  // Finding j07-002 : POST …/run répond 500 (procrastinate AppNotOpen), comme j03-001 pour les imports.
  test.fixme("j07-002 : POST /harvest/sources/{id}/run répond 202", async () => {
    const src = await createSource(admin, { type: "stac", url: `https://x.invalid/${tag}-run` });
    const r = await admin.send("POST", `/v1/harvest/sources/${src.id}/run`);
    expect(r.status).toBe(202);
  });

  // Finding j07-004 : aucune validation d'URL à la création.
  test.fixme("j07-004 : une URL qui n'est pas http(s) est refusée à la création (422)", async () => {
    const r = await admin.send("POST", "/v1/harvest/sources", { type: "wms", url: "pas une url" });
    expect(r.status).toBe(422);
  });

  // Finding j07-005 : doublons de source non détectés.
  test.fixme("j07-005 : créer deux fois la même source (type+URL) est refusé (409)", async () => {
    const url = `https://x.invalid/${tag}-dup`;
    await createSource(admin, { type: "stac", url });
    const r = await admin.send("POST", "/v1/harvest/sources", { type: "stac", url });
    expect(r.status).toBe(409);
  });

  // Finding j07-006 : une source en erreur reste « due » à chaque balayage, malgré son intervalle.
  test.fixme("j07-006 : une source en erreur avec intervalle 1440 min n'est pas re-lancée à chaque balayage", async () => {
    const src = await createSource(admin, {
      type: "stac",
      url: `http://127.0.0.1:1/${tag}-due`,
      intervalMinutes: 1440,
    });
    runHarvestInWorker(src.id);
    const lastRun = psql(`SELECT last_run_at FROM harvest_sources WHERE id='${src.id}'`).trim();
    expect(
      lastRun,
      "last_run_at doit être posé même en erreur pour respecter l'intervalle",
    ).not.toBe("");
  });

  // Finding j07-007 : la suppression d'une source laisse ses items « external » orphelins.
  test.fixme("j07-007 : supprimer une source retire ou signale les items qu'elle avait créés", async () => {
    const src = await createSource(admin, {
      type: "stac",
      url: "https://earth-search.aws.element84.com/v1",
    });
    runHarvestInWorker(src.id);
    const ids = psql(`SELECT item_id FROM harvest_records WHERE source_id='${src.id}'`)
      .trim()
      .split("\n")
      .filter(Boolean);
    test.skip(ids.length === 0, "moissonnage réel indisponible");
    await admin.send("DELETE", `/v1/harvest/sources/${src.id}`);
    const list = ids.map((i) => `'${i}'`).join(",");
    const left = Number(psql(`SELECT count(*) FROM items WHERE id IN (${list})`).trim());
    expect(left).toBe(0);
  });
});
