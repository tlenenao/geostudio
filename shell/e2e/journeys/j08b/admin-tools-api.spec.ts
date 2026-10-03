import { bug } from "../_fixtures/verify";
import { test, expect, request } from "@playwright/test";
import { stamp } from "../_fixtures/env";
import { CORE_URL, apiFor, makeUser, roleIdBySlug, simulateLockout, type Api } from "./helpers";

// Passerelle /admin-tools (CORE_ADMIN_TOOLS_ENABLED=true) : lancement, cookie, forwardAuth Traefik.
test.setTimeout(120_000);
const tag = stamp("j08b");
let admin: Api;

test.beforeAll(async () => {
  admin = await apiFor("admin");
});

async function session(tool: string): Promise<{ cookie: string; setCookie: string; loc: string }> {
  const launch = await admin.send("POST", `/v1/admin-tools/launch/${tool}`);
  expect(launch.status).toBe(200);
  const r = await fetch(launch.body.url, { redirect: "manual" });
  expect(r.status).toBe(302);
  const setCookie = r.headers.get("set-cookie") ?? "";
  const cookie = /gs_admin_session=([^;]+)/.exec(setCookie)?.[1] ?? "";
  return { cookie, setCookie, loc: r.headers.get("location") ?? "" };
}

async function gateway(path: string, cookie?: string): Promise<{ status: number; text: string }> {
  const ctx = await request.newContext({
    baseURL: "https://localhost",
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: cookie ? { cookie: `gs_admin_session=${cookie}` } : {},
  });
  const r = await ctx.get(path);
  const out = { status: r.status(), text: (await r.text()).slice(0, 300) };
  await ctx.dispose();
  return out;
}

test("lancement : admin reçoit l'URL de session des 3 outils ; lecteur/créateur/analyste 403 ; anonyme 401", async () => {
  for (const tool of ["martin", "titiler", "grafana"]) {
    const r = await admin.send("POST", `/v1/admin-tools/launch/${tool}`);
    expect(r.status).toBe(200);
    expect(r.body.url).toContain(`/v1/admin-tools/session/${tool}?_at=`);
  }
  for (const persona of ["reader", "creator", "analyst"] as const) {
    const api = await apiFor(persona);
    expect((await api.send("POST", "/v1/admin-tools/launch/grafana")).status).toBe(403);
  }
  const anon = await fetch(`${CORE_URL}/v1/admin-tools/launch/grafana`, { method: "POST" });
  expect(anon.status).toBe(401);
  expect((await admin.send("POST", "/v1/admin-tools/launch/redis")).status).toBe(422);
});

test("cookie de session : HttpOnly, Secure, SameSite=Strict, Path=/admin, 30 min ; jeton d'un autre outil ou falsifié refusé", async () => {
  const s = await session("martin");
  expect(s.setCookie).toMatch(/HttpOnly/i);
  expect(s.setCookie).toMatch(/Secure/i);
  expect(s.setCookie).toMatch(/SameSite=strict/i);
  expect(s.setCookie).toMatch(/Path=\/admin/);
  expect(s.setCookie).toMatch(/Max-Age=1800/);
  const launch = await admin.send("POST", "/v1/admin-tools/launch/martin");
  const wrongTool = (launch.body.url as string).replace("/session/martin", "/session/grafana");
  expect((await fetch(wrongTool, { redirect: "manual" })).status).toBe(401);
  expect((await fetch(`${CORE_URL}/v1/admin-tools/session/martin?_at=x`)).status).toBe(401);
  expect((await fetch(`${CORE_URL}/v1/admin-tools/verify`)).status).toBe(403);
  expect(
    (
      await fetch(`${CORE_URL}/v1/admin-tools/verify`, {
        headers: { cookie: "gs_admin_session=zzz" },
      })
    ).status,
  ).toBe(403);
});

test("passerelle Traefik : Martin et Grafana répondent 200 avec le cookie, 403 sans", async () => {
  for (const tool of ["martin", "grafana"]) {
    const s = await session(tool);
    expect((await gateway(`/admin/${tool}/`)).status).toBe(403);
    expect((await gateway(`/admin/${tool}/`, s.cookie)).status).toBe(200);
  }
});

test("révocation : retirer settings.instance.manage à un porteur invalide immédiatement son cookie", async () => {
  const u = await makeUser(`aud-j08b-tools-${Date.now().toString(36)}`);
  const role = await admin.send("POST", "/v1/roles", {
    name: `${tag}-tools`,
    privileges: ["settings.instance.manage"],
  });
  expect(role.status).toBe(201);
  const patch = await admin.send("PATCH", `/v1/users/${u.id}`, { roleId: role.body.id });
  expect(patch.status).toBe(200);
  const launch = await u.api.send("POST", "/v1/admin-tools/launch/grafana");
  expect(launch.status).toBe(200);
  const r = await fetch(launch.body.url, { redirect: "manual" });
  const cookie = /gs_admin_session=([^;]+)/.exec(r.headers.get("set-cookie") ?? "")?.[1] ?? "";
  expect((await gateway("/admin/grafana/", cookie)).status).toBe(200);
  const reader = await roleIdBySlug(admin, "reader");
  expect((await admin.send("PATCH", `/v1/users/${u.id}`, { roleId: reader })).status).toBe(200);
  expect((await gateway("/admin/grafana/", cookie)).status).toBe(403);
  expect((await u.api.send("POST", "/v1/admin-tools/launch/grafana")).status).toBe(403);
});

// Finding j08b-005 : la page racine de Titiler (derrière la passerelle) répond 500.
test("j08b-005 : /admin/titiler/ derrière la passerelle répond 200", async () => {
  const s = await session("titiler");
  expect((await gateway("/admin/titiler/", s.cookie)).status).toBe(200);
});

// Finding j08b-006 : l'URL de lancement (CORE_BASE_URL) puis la redirection relative /admin/<outil>/
// retombent sur le cœur (:8200) qui ne sert pas /admin : 404 dans le compose de dev.
test("j08b-006 : suivre l'URL de lancement aboutit à l'outil, pas à un 404 du cœur", async () => {
  const launch = await admin.send("POST", "/v1/admin-tools/launch/grafana");
  const r = await fetch(launch.body.url, { redirect: "manual" });
  const target = new URL(r.headers.get("location") ?? "", launch.body.url).toString();
  const final = await fetch(target, {
    headers: { cookie: r.headers.get("set-cookie")?.split(";")[0] ?? "" },
  });
  expect(final.status).toBe(200);
});

// Finding j08b-004 : un compte anonymisé garde son rôle et compte comme titulaire : la garde
// anti-lockout ne se déclenche plus et le dernier administrateur actif peut être anonymisé.
bug("j08b-004 : le dernier administrateur actif ne peut pas être anonymisé", async () => {
  const out = simulateLockout(`audj08bs${Date.now().toString(36)}`);
  expect(out.erase_a2_ok).toBe(true);
  expect(out.erase_last_active_admin).toBe("refused");
  expect(out.active_admins_final).toBeGreaterThanOrEqual(1);
});
