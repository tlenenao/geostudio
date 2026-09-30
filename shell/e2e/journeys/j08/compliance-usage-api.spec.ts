/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { putUpload } from "../j03/api";
import { apiFor, makeUser, psql, type Api } from "./helpers";

// Conformité RGPD (anonymisation ; la purge de tenant n'est JAMAIS déclenchée), usage et quotas.
test.setTimeout(120_000);
const tag = stamp("j08");
let admin: Api;
let creator: Api;
let reader: Api;

test.beforeAll(async () => {
  [admin, creator, reader] = await Promise.all([
    apiFor("admin"),
    apiFor("creator"),
    apiFor("reader"),
  ]);
});

test.describe("j08 conformité — anonymisation", () => {
  test("un admin anonymise un autre utilisateur : identité écrasée, lignes liées supprimées", async () => {
    const u = await makeUser(`${tag}-erase`);
    const r = await admin.send("POST", `/v1/compliance/users/${u.id}/erase`);
    expect(r.status).toBe(204);
    const row = psql(
      `SELECT username||'|'||coalesce(email,'NULL')||'|'||first_name||'|'||last_name||'|'||(oidc_sub LIKE 'erased:%')||'|'||(erased_at IS NOT NULL) FROM users WHERE id='${u.id}'`,
    ).trim();
    expect(row).toBe(`utilisateur-efface-${u.id.slice(0, 8)}|NULL|||true|true`);
    const audit = psql(
      `SELECT count(*) FROM audit_log WHERE action='user.erase' AND object_id='${u.id}'`,
    );
    expect(Number(audit.trim())).toBe(1);
  });

  test("second effacement → 409 ; identifiant inconnu → 404", async () => {
    const u = await makeUser(`${tag}-twice`);
    expect((await admin.send("POST", `/v1/compliance/users/${u.id}/erase`)).status).toBe(204);
    expect((await admin.send("POST", `/v1/compliance/users/${u.id}/erase`)).status).toBe(409);
    expect((await admin.send("POST", "/v1/compliance/users/inconnu/erase")).status).toBe(404);
  });

  test("droits : un créateur ne peut effacer qu'un autre compte → 403, mais 'me' est permis", async () => {
    const victim = await makeUser(`${tag}-victim`);
    expect((await creator.send("POST", `/v1/compliance/users/${victim.id}/erase`)).status).toBe(
      403,
    );
    expect((await reader.send("POST", `/v1/compliance/users/${victim.id}/erase`)).status).toBe(403);
    const self = await makeUser(`${tag}-self`);
    expect((await self.api.send("POST", "/v1/compliance/users/me/erase")).status).toBe(204);
    const row = psql(`SELECT username FROM users WHERE id='${self.id}'`).trim();
    expect(row).toBe(`utilisateur-efface-${self.id.slice(0, 8)}`);
  });

  test("purge de tenant : garde-fous sans jamais déclencher de purge", async () => {
    // L'Administrateur prédéfini n'a pas compliance.manage : 403 avant toute vérification.
    expect(
      (await admin.send("POST", "/v1/compliance/tenants/default/purge", { confirmSlug: "default" }))
        .status,
    ).toBe(403);
    const role = await admin.send("POST", "/v1/roles", {
      name: `${tag}-compliance`,
      privileges: ["compliance.manage"],
    });
    const u = await makeUser(`${tag}-purger`);
    await admin.send("PATCH", `/v1/users/${u.id}`, { roleId: role.body.id });
    // Slug erroné → 400 ; autre tenant → 403 ; aucun de ces appels ne défère de job.
    const wrong = await u.api.send("POST", "/v1/compliance/tenants/default/purge", {
      confirmSlug: "pas-le-bon",
    });
    expect(wrong.status).toBe(400);
    const cross = await u.api.send("POST", "/v1/compliance/tenants/autre/purge", {
      confirmSlug: "autre",
    });
    expect(cross.status).toBe(403);
    const missing = await u.api.send("POST", "/v1/compliance/tenants/default/purge", {});
    expect(missing.status).toBe(422);
    const audit = psql("SELECT count(*) FROM audit_log WHERE action='tenant.purge_requested'");
    expect(Number(audit.trim())).toBe(0);
    // Reçu inconnu : 202 « en cours ou inconnu » (indistinguable).
    expect((await u.api.get("/v1/compliance/purges/inconnu")).status).toBe(202);
    expect((await admin.get("/v1/compliance/purges/inconnu")).status).toBe(403);
  });

  // Finding j08-001 : l'anonymisation est annulée par la reconnexion Keycloak.
  test.fixme("j08-001 : après anonymisation, une reconnexion ne recrée pas un compte nominatif", async () => {
    const u = await makeUser(`${tag}-relogin`);
    expect((await admin.send("POST", `/v1/compliance/users/${u.id}/erase`)).status).toBe(204);
    const again = await u.api.get("/v1/me");
    expect(again.status).toBeGreaterThanOrEqual(400);
    const n = psql(
      `SELECT count(*) FROM users WHERE username='${u.username}' AND erased_at IS NULL`,
    );
    expect(Number(n.trim())).toBe(0);
  });

  // Finding j08-013 : un compte anonymisé reste dans la liste, sans indicateur.
  test.fixme("j08-013 : la liste des utilisateurs distingue les comptes anonymisés", async () => {
    const u = await makeUser(`${tag}-flag`);
    await admin.send("POST", `/v1/compliance/users/${u.id}/erase`);
    const listed = await admin.get(`/v1/users?q=efface-${u.id.slice(0, 8)}`);
    expect(listed.body.users).toHaveLength(1);
    expect(listed.body.users[0].erased).toBe(true);
  });
});

test.describe("j08 usage (/tasks) — API", () => {
  test("journal : lecteur 403, créateur limité à ses actions, admin voit tout et filtre par acteur", async () => {
    const me = (await creator.get("/v1/me")).body;
    const adm = (await admin.get("/v1/me")).body;
    psql(
      `INSERT INTO audit_log (tenant_id, actor_id, actor_kind, action, object_type, object_id, payload, created_at) VALUES ` +
        `('default','${me.id}','user','pipeline.run','item','${tag}-c','{}',now()),` +
        `('default','${adm.id}','user','report.run','item','${tag}-a','{}',now())`,
    );
    expect((await reader.get("/v1/usage/tasks")).status).toBe(403);
    const mine = await creator.get("/v1/usage/tasks?pageSize=200");
    expect(mine.status).toBe(200);
    expect(mine.body.tasks.every((t: any) => t.actorId === me.id)).toBe(true);
    expect(mine.body.tasks.some((t: any) => t.objectId === `${tag}-c`)).toBe(true);
    expect((await creator.get(`/v1/usage/tasks?actorId=${adm.id}`)).status).toBe(403);
    const all = await admin.get("/v1/usage/tasks?pageSize=200");
    const ids = all.body.tasks.map((t: any) => t.objectId);
    expect(ids).toEqual(expect.arrayContaining([`${tag}-c`, `${tag}-a`]));
    const only = await admin.get(`/v1/usage/tasks?actorId=${me.id}&pageSize=200`);
    expect(only.body.tasks.every((t: any) => t.actorId === me.id)).toBe(true);
    // Trié du plus récent au plus ancien.
    const dates = all.body.tasks.map((t: any) => t.createdAt);
    expect([...dates].sort().reverse()).toEqual(dates);
  });

  test("résumé : réservé à tasks.view_all, agrégats par acteur et ressource bornés par limit", async () => {
    expect((await creator.get("/v1/usage/summary")).status).toBe(403);
    const s = await admin.get("/v1/usage/summary?limit=1");
    expect(s.status).toBe(200);
    expect(s.body.byActor).toHaveLength(1);
    expect(s.body.byResource).toHaveLength(1);
    expect(s.body.totalActions).toBeGreaterThan(0);
    const win = await admin.get(
      "/v1/usage/summary?since=2020-01-01T00:00:00&until=2020-01-02T00:00:00",
    );
    expect(win.body.totalActions).toBe(0);
  });

  // Finding j08-004 : paramètres de fenêtre invalides → 500.
  test.fixme("j08-004 : since illisible ou limit négatif → 4xx, jamais 500", async () => {
    for (const q of ["since=pas-une-date", "until=32/13/2026", "limit=-1"]) {
      const r = await admin.get(`/v1/usage/summary?${q}`);
      expect(r.status, q).toBeGreaterThanOrEqual(400);
      expect(r.status, q).toBeLessThan(500);
    }
  });
});

test.describe("j08 quotas de stockage — API", () => {
  test("GET /admin/usage : comptages, stockage S3 mesuré, limites nulles quand non configurées", async () => {
    const before = (await admin.get("/v1/admin/usage")).body;
    expect(before).toMatchObject({ maxItems: null, maxCollections: null, maxStorageBytes: null });
    putUpload(`${tag}-usage.bin`, Buffer.alloc(8192, 1));
    const after = (await admin.get("/v1/admin/usage")).body;
    expect(after.storageBytes - before.storageBytes).toBe(8192);
    const users = await admin.get("/v1/users?pageSize=1");
    expect(after.userCount).toBe(users.body.total);
  });

  test("les comptes anonymisés restent comptés dans userCount", async () => {
    const before = (await admin.get("/v1/admin/usage")).body.userCount;
    const u = await makeUser(`${tag}-count`);
    expect((await admin.get("/v1/admin/usage")).body.userCount).toBe(before + 1);
    await admin.send("POST", `/v1/compliance/users/${u.id}/erase`);
    expect((await admin.get("/v1/admin/usage")).body.userCount).toBe(before + 1);
  });
});
