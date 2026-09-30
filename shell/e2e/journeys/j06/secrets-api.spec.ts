import { test, expect } from "@playwright/test";
import { stamp, CORE_URL } from "../_fixtures/env";
import { apiFor, type Api } from "../j03/api";
import { psql } from "../j02/helpers";

// Coffre de secrets connecteurs (POST/GET/DELETE /v1/secrets), personas OIDC réelles.
// Les routes sont inconditionnelles (hors CORE_ETL_ENABLED) : seul périmètre du
// domaine « pipelines » exécutable sur une stack où l'ETL est coupé.
const tag = stamp("j06");
let admin: Api;
let creator: Api;
let analyst: Api;
let reader: Api;

test.beforeAll(async () => {
  [admin, creator, analyst, reader] = await Promise.all([
    apiFor("admin"),
    apiFor("creator"),
    apiFor("analyst"),
    apiFor("reader"),
  ]);
});

const bearer = (name: string, token = "tok-" + name) => ({
  name,
  payload: { kind: "bearer_token", token },
});

test.describe("j06 coffre de secrets — nominal", () => {
  test("création : réponse sans aucune valeur sensible", async () => {
    const r = await creator.send(
      "POST",
      "/v1/secrets",
      bearer(`${tag}-nominal`, "VALEUR-SECRETE-1"),
    );
    expect(r.status).toBe(201);
    expect(Object.keys(r.body).sort()).toEqual(["createdAt", "id", "kind", "name", "updatedAt"]);
    expect(JSON.stringify(r.body)).not.toContain("VALEUR-SECRETE-1");
  });

  test("liste : noms et kinds seulement, jamais de payload", async () => {
    await creator.send("POST", "/v1/secrets", bearer(`${tag}-liste`, "VALEUR-SECRETE-2"));
    const r = await creator.get("/v1/secrets");
    expect(r.status).toBe(200);
    expect(r.body.some((s: { name: string }) => s.name === `${tag}-liste`)).toBe(true);
    expect(JSON.stringify(r.body)).not.toContain("VALEUR-SECRETE-2");
  });

  test("le payload est chiffré au repos (aucune trace du clair en base)", async () => {
    await creator.send("POST", "/v1/secrets", bearer(`${tag}-chiffre`, "CLAIR-INTROUVABLE-XYZ"));
    const rows = psql(`SELECT count(*) FROM connector_secrets WHERE name='${tag}-chiffre'`).trim();
    expect(rows).toBe("1");
    const leak = psql(
      `SELECT count(*) FROM connector_secrets WHERE name='${tag}-chiffre' AND position(convert_to('CLAIR-INTROUVABLE-XYZ','UTF8') in ciphertext) > 0`,
    ).trim();
    expect(leak).toBe("0");
  });

  test("l'audit_log trace secret.create sans la valeur", async () => {
    await creator.send("POST", "/v1/secrets", bearer(`${tag}-audit`, "CLAIR-AUDIT-QQQ"));
    const payload = psql(
      `SELECT payload::text FROM audit_log WHERE action='secret.create' AND payload::text LIKE '%${tag}-audit%'`,
    );
    expect(payload).toContain(`${tag}-audit`);
    expect(payload).not.toContain("CLAIR-AUDIT-QQQ");
  });

  test("suppression : 204 puis 404, et secret.delete est audité", async () => {
    const c = await creator.send("POST", "/v1/secrets", bearer(`${tag}-del`));
    const id = c.body.id as string;
    expect((await creator.send("DELETE", `/v1/secrets/${id}`)).status).toBe(204);
    expect((await creator.send("DELETE", `/v1/secrets/${id}`)).status).toBe(404);
    const n = psql(
      `SELECT count(*) FROM audit_log WHERE action='secret.delete' AND object_id='${id}'`,
    );
    expect(n.trim()).toBe("1");
  });

  test("les kinds api_key / basic_auth / postgres_dsn / smtp sont acceptés", async () => {
    const payloads = [
      { kind: "api_key", location: "header", key: "X-Key", value: "v" },
      { kind: "basic_auth", username: "u", password: "p" },
      { kind: "postgres_dsn", dsn: "postgresql://u:p@example.org:5432/db" },
      {
        kind: "smtp",
        host: "smtp.example.org",
        port: 587,
        username: "u",
        password: "p",
        useTls: true,
        fromAddress: "a@example.org",
      },
    ];
    for (const [i, payload] of payloads.entries()) {
      const r = await creator.send("POST", "/v1/secrets", { name: `${tag}-kind${i}`, payload });
      expect(r.status, JSON.stringify(r.body)).toBe(201);
      expect(r.body.kind).toBe(payload.kind);
    }
  });
});

test.describe("j06 coffre de secrets — erreurs et droits", () => {
  test("nom en double : 409", async () => {
    await creator.send("POST", "/v1/secrets", bearer(`${tag}-dup`));
    const r = await creator.send("POST", "/v1/secrets", bearer(`${tag}-dup`));
    expect(r.status).toBe(409);
  });

  test("kind inconnu : 422", async () => {
    const r = await creator.send("POST", "/v1/secrets", {
      name: `${tag}-zzz`,
      payload: { kind: "zzz" },
    });
    expect(r.status).toBe(422);
  });

  test("nom vide ou de plus de 200 caractères : 422", async () => {
    expect((await creator.send("POST", "/v1/secrets", bearer(""))).status).toBe(422);
    expect((await creator.send("POST", "/v1/secrets", bearer("n".repeat(201)))).status).toBe(422);
  });

  test("lecteur et analyste : 403 sur les trois routes", async () => {
    for (const api of [reader, analyst]) {
      expect((await api.send("POST", "/v1/secrets", bearer(`${tag}-nope`))).status).toBe(403);
      expect((await api.get("/v1/secrets")).status).toBe(403);
      expect((await api.send("DELETE", "/v1/secrets/x")).status).toBe(403);
    }
  });

  test("sans jeton : 401", async () => {
    const r = await fetch(`${CORE_URL}/v1/secrets`);
    expect(r.status).toBe(401);
  });

  test("le coffre n'expose aucune route de mise à jour (PUT/PATCH refusés)", async () => {
    const c = await creator.send("POST", "/v1/secrets", bearer(`${tag}-noput`));
    // 404 constaté (et non 405) : la route n'existe pas du tout.
    expect([404, 405]).toContain(
      (await creator.send("PUT", `/v1/secrets/${c.body.id}`, bearer("x"))).status,
    );
    expect([404, 405]).toContain(
      (await creator.send("PATCH", `/v1/secrets/${c.body.id}`, { name: "x" })).status,
    );
  });
});

test.describe("j06 coffre de secrets — défauts constatés", () => {
  // Finding j06-006 : impossible de faire tourner un secret sans le supprimer, ce qui
  // casse les références par nom (pipelines, moissonnage, alertes SMTP).
  test.fixme("j06-006 : un secret peut être mis à jour en place (rotation)", async () => {
    const c = await creator.send("POST", "/v1/secrets", bearer(`${tag}-rot`));
    const r = await creator.send(
      "PUT",
      `/v1/secrets/${c.body.id}`,
      bearer(`${tag}-rot`, "nouveau"),
    );
    expect(r.status).toBe(200);
  });

  // Finding j06-005 : aucune notion de propriétaire, tout Créateur gère tous les secrets du tenant.
  test.fixme("j06-005 : un Créateur ne peut pas supprimer le secret créé par l'administrateur", async () => {
    const c = await admin.send("POST", "/v1/secrets", bearer(`${tag}-admin-owned`));
    expect(c.status).toBe(201);
    const r = await creator.send("DELETE", `/v1/secrets/${c.body.id}`);
    expect(r.status).toBe(403);
  });

  // Finding j06-007 : la 422 FastAPI par défaut renvoie le corps fautif dans `input`.
  test.fixme("j06-007 : une 422 sur POST /secrets ne renvoie pas la valeur du secret", async () => {
    const r = await creator.send("POST", "/v1/secrets", {
      payload: { kind: "bearer_token", token: "ECHO-SECRET-VALUE" },
    });
    expect(r.status).toBe(422);
    expect(JSON.stringify(r.body)).not.toContain("ECHO-SECRET-VALUE");
  });

  // Finding j06-008 : aucun contrôle de contenu (jeton vide, DSN vide).
  test.fixme("j06-008 : un secret dont la valeur est vide est refusé", async () => {
    const r = await creator.send("POST", "/v1/secrets", bearer(`${tag}-vide`, ""));
    expect(r.status).toBe(422);
  });

  // Finding j06-004 : un DSN vers un hôte interne est accepté d'un Créateur (aucune garde d'egress).
  test.fixme("j06-004 : un DSN postgres vers un hôte interne du compose est refusé", async () => {
    const r = await creator.send("POST", "/v1/secrets", {
      name: `${tag}-dsn-interne`,
      payload: { kind: "postgres_dsn", dsn: "postgresql://gis:x@postgis:5432/gis" },
    });
    expect(r.status).toBe(422);
  });
});
