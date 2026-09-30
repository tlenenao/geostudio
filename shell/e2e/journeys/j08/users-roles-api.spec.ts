/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { apiFor, makeUser, roleIdBySlug, type Api, type Throwaway } from "./helpers";

// Utilisateurs (rôle par ligne, recherche, pagination) et rôles sur mesure (API cœur).
test.setTimeout(120_000);
const tag = stamp("j08");
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

async function customRole(name: string, privileges: string[]) {
  const r = await admin.send("POST", "/v1/roles", { name, privileges });
  expect(r.status).toBe(201);
  return r.body as { id: string; slug: string; name: string; privileges: string[] };
}

async function assign(user: Throwaway, roleId: string) {
  const r = await admin.send("PATCH", `/v1/users/${user.id}`, { roleId });
  expect(r.status).toBe(200);
}

test.describe("j08 utilisateurs — API", () => {
  test("liste, recherche insensible à la casse et total", async () => {
    const all = await admin.get("/v1/users");
    expect(all.status).toBe(200);
    expect(all.body.total).toBeGreaterThanOrEqual(4);
    const names = all.body.users.map((u: any) => u.username);
    expect(names).toEqual(expect.arrayContaining(["audit-admin", "audit-reader"]));
    const found = await admin.get("/v1/users?q=AUDIT-READ");
    expect(found.body.users.map((u: any) => u.username)).toEqual(["audit-reader"]);
    const none = await admin.get(`/v1/users?q=${tag}-inexistant`);
    expect(none.body).toEqual({ users: [], total: 0 });
  });

  test("droits : créateur, analyste et lecteur reçoivent 403 sur users, roles et catalogue", async () => {
    for (const api of [creator, analyst, reader]) {
      for (const path of ["/v1/users", "/v1/roles", "/v1/roles/catalog", "/v1/admin/usage"]) {
        expect((await api.get(path)).status, path).toBe(403);
      }
      expect((await api.send("POST", "/v1/roles", { name: "x", privileges: [] })).status).toBe(403);
    }
  });

  test("changement de rôle : effet immédiat, audit ; roleId ou utilisateur inconnu refusés", async () => {
    const u = await makeUser(`${tag}-role`);
    const before = await u.api.get("/v1/me");
    expect(before.body.role.slug).toBe("creator");
    const readerRole = await roleIdBySlug(admin, "reader");
    await assign(u, readerRole);
    const after = await u.api.get("/v1/me");
    expect(after.body.role.slug).toBe("reader");
    expect(after.body.privileges).toEqual([]);
    const listed = await admin.get(`/v1/users?q=${u.username}`);
    expect(listed.body.users[0].roleSlug).toBe("reader");
    const { psql } = await import("./helpers");
    const audit = psql(
      `SELECT count(*) FROM audit_log WHERE action='user.role_change' AND object_id='${u.id}'`,
    );
    expect(Number(audit.trim())).toBe(1);
    expect((await admin.send("PATCH", `/v1/users/${u.id}`, { roleId: "nope" })).status).toBe(400);
    expect((await admin.send("PATCH", "/v1/users/inconnu", { roleId: readerRole })).status).toBe(
      404,
    );
  });

  // Finding j08-003 : paramètres de pagination hors bornes → 500 au lieu de 422.
  test.fixme("j08-003 : page=0 ou pageSize négatif → 4xx, jamais 500", async () => {
    for (const path of [
      "/v1/users?page=0",
      "/v1/users?pageSize=-1",
      "/v1/usage/tasks?page=0",
      "/v1/usage/tasks?pageSize=-5",
    ]) {
      const r = await admin.get(path);
      expect(r.status, path).toBeGreaterThanOrEqual(400);
      expect(r.status, path).toBeLessThan(500);
    }
  });
});

test.describe("j08 rôles — API", () => {
  test("catalogue : 20 privilèges avec domaine et clé de libellé", async () => {
    const r = await admin.get("/v1/roles/catalog");
    expect(r.status).toBe(200);
    expect(r.body).toHaveLength(20);
    for (const e of r.body) {
      expect(e.privilege).toMatch(/^[a-z_]+(\.[a-z_]+)+$/);
      expect(e.labelKey).toMatch(/^roles\.privilege\./);
      expect(e.domain).toBeTruthy();
    }
    const names = r.body.map((e: any) => e.privilege);
    expect(names).toEqual(expect.arrayContaining(["compliance.manage", "data.view_sensitive"]));
  });

  test("cycle de vie : création, renommage, changement de privilèges, suppression", async () => {
    const role = await customRole(`${tag}-cycle`, ["tasks.view"]);
    expect(role.privileges).toEqual(["tasks.view"]);
    const renamed = await admin.send("PATCH", `/v1/roles/${role.id}`, {
      name: `${tag}-cycle-2`,
      privileges: ["data.view", "tasks.view"],
    });
    expect(renamed.status).toBe(200);
    expect(renamed.body.name).toBe(`${tag}-cycle-2`);
    expect(renamed.body.privileges).toEqual(["data.view", "tasks.view"]);
    expect((await admin.send("DELETE", `/v1/roles/${role.id}`)).status).toBe(204);
    expect((await admin.send("DELETE", `/v1/roles/${role.id}`)).status).toBe(404);
    expect((await admin.send("PATCH", `/v1/roles/${role.id}`, { name: "x" })).status).toBe(404);
  });

  test("les 4 rôles prédéfinis sont immuables (PATCH et DELETE → 400)", async () => {
    const roles = await admin.get("/v1/roles");
    const builtIn = roles.body.filter((r: any) => r.isBuiltIn);
    expect(builtIn.map((r: any) => r.slug).sort()).toEqual([
      "admin",
      "analyst",
      "creator",
      "reader",
    ]);
    for (const r of builtIn) {
      expect((await admin.send("PATCH", `/v1/roles/${r.id}`, { name: "hack" })).status).toBe(400);
      expect((await admin.send("DELETE", `/v1/roles/${r.id}`)).status).toBe(400);
    }
  });

  test("suppression bloquée (409) tant qu'un utilisateur porte le rôle", async () => {
    const role = await customRole(`${tag}-held`, []);
    const u = await makeUser(`${tag}-holder`);
    await assign(u, role.id);
    const blocked = await admin.send("DELETE", `/v1/roles/${role.id}`);
    expect(blocked.status).toBe(409);
    expect(String(blocked.body.detail)).toContain("1 user");
    await assign(u, await roleIdBySlug(admin, "reader"));
    expect((await admin.send("DELETE", `/v1/roles/${role.id}`)).status).toBe(204);
  });

  test("un privilège ajouté ou retiré à un rôle agit immédiatement sur ses titulaires", async () => {
    const role = await customRole(`${tag}-live`, ["tasks.view"]);
    const u = await makeUser(`${tag}-live`);
    await assign(u, role.id);
    expect((await u.api.get("/v1/usage/summary")).status).toBe(403);
    await admin.send("PATCH", `/v1/roles/${role.id}`, { privileges: ["tasks.view_all"] });
    expect((await u.api.get("/v1/usage/summary")).status).toBe(200);
    await admin.send("PATCH", `/v1/roles/${role.id}`, { privileges: [] });
    expect((await u.api.get("/v1/usage/summary")).status).toBe(403);
    expect((await u.api.get("/v1/usage/tasks")).status).toBe(403);
  });

  // Finding j08-005 : aucune validation du nom ni des privilèges dupliqués.
  test.fixme("j08-005 : nom vide, blanc, doublon ou homonyme d'un rôle prédéfini refusés", async () => {
    const name = `${tag}-dup`;
    await customRole(name, ["tasks.view", "tasks.view"]);
    const bad = [
      { name: "", privileges: [] },
      { name: "   ", privileges: [] },
      { name, privileges: [] },
      { name: "Administrateur", privileges: [] },
    ];
    for (const body of bad) {
      const r = await admin.send("POST", "/v1/roles", body);
      expect(r.status, JSON.stringify(body)).toBeGreaterThanOrEqual(400);
    }
    const again = await admin.get("/v1/roles");
    const created = again.body.find((r: any) => r.name === name);
    expect(created.privileges).toEqual(["tasks.view"]);
  });

  // Finding j08-007 : admin.roles.manage seul suffit à s'octroyer n'importe quel privilège.
  test.fixme("j08-007 : un titulaire de admin.roles.manage seul ne peut pas s'auto-élever", async () => {
    const role = await customRole(`${tag}-esc`, ["admin.roles.manage"]);
    const u = await makeUser(`${tag}-esc`);
    await assign(u, role.id);
    const r = await u.api.send("PATCH", `/v1/roles/${role.id}`, {
      privileges: ["admin.roles.manage", "admin.users.manage", "compliance.manage"],
    });
    expect(r.status).toBeGreaterThanOrEqual(400);
    const me = await u.api.get("/v1/me");
    expect(me.body.privileges).not.toContain("compliance.manage");
  });
});
