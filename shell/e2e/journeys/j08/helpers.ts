/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { CORE_URL, SHELL_URL } from "../_fixtures/env";
import { psql } from "../j02/helpers";
import type { Api } from "../j03/api";

export { psql };
export { apiFor } from "../j03/api";
export { spaGoto } from "../j06/helpers";
export type { Api };

const KC = process.env.KC_URL ?? "http://localhost:8180";
export const PASSWORD = "Demo1234!";

function kcAdminPassword(): string {
  if (process.env.KC_PASSWORD) return process.env.KC_PASSWORD;
  const env = readFileSync(join(process.cwd(), "..", ".env"), "utf8");
  const m = /^KC_PASSWORD=(.*)$/m.exec(env);
  if (!m) throw new Error("KC_PASSWORD introuvable (.env)");
  return m[1].trim();
}

function kcadm(args: string[]): string {
  return execFileSync(
    "docker",
    ["exec", "geostudio-keycloak-1", "/opt/keycloak/bin/kcadm.sh", ...args],
    {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
}

let kcLogged = false;
function kcLogin(): void {
  if (kcLogged) return;
  kcadm([
    "config",
    "credentials",
    "--server",
    "http://localhost:8080",
    "--realm",
    "master",
    "--user",
    "admin",
    "--password",
    kcAdminPassword(),
  ]);
  kcLogged = true;
}

export async function tokenFor(username: string): Promise<string> {
  const r = await fetch(`${KC}/realms/geostudio/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "password",
      client_id: "geostudio-shell",
      username,
      password: PASSWORD,
    }),
  });
  if (!r.ok) throw new Error(`token ${username}: ${r.status}`);
  return ((await r.json()) as { access_token: string }).access_token;
}

export function apiWithToken(getToken: () => Promise<string>): Api {
  const send = async (method: string, path: string, body?: unknown) => {
    const tok = await getToken();
    const doFetch = () =>
      fetch(`${CORE_URL}${path}`, {
        method,
        headers: {
          authorization: `Bearer ${tok}`,
          ...(body !== undefined ? { "content-type": "application/json" } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    const r = await doFetch().catch(() => doFetch());
    const text = await r.text();
    let parsed: any = text;
    try {
      parsed = JSON.parse(text);
    } catch {
      /* corps non JSON */
    }
    return { status: r.status, body: parsed };
  };
  return { get: (p) => send("GET", p), send };
}

export interface Throwaway {
  username: string;
  id: string;
  api: Api;
}

// Compte Keycloak jetable + ligne `users` créée par une première requête /v1/me.
// Jamais un des 4 personas audit-* : c'est lui qu'on anonymise, rôle-change, etc.
export async function makeUser(username: string): Promise<Throwaway> {
  kcLogin();
  kcadm([
    "create",
    "users",
    "-r",
    "geostudio",
    "-s",
    `username=${username}`,
    "-s",
    "enabled=true",
    "-s",
    `email=${username}@audit.local`,
    "-s",
    "emailVerified=true",
    "-s",
    "firstName=Jetable",
    "-s",
    `lastName=${username}`,
  ]);
  kcadm(["set-password", "-r", "geostudio", "--username", username, "--new-password", PASSWORD]);
  const api = apiWithToken(() => tokenFor(username));
  const me = await api.get("/v1/me");
  if (me.status !== 200) throw new Error(`me ${username}: ${me.status}`);
  return { username, id: me.body.id, api };
}

export async function roleIdBySlug(admin: Api, slug: string): Promise<string> {
  const roles = await admin.get("/v1/roles");
  return roles.body.find((r: any) => r.slug === slug).id;
}

// Connexion OIDC d'un compte jetable (loginOidc n'accepte que les personas).
export async function openAsUser(page: Page, username: string): Promise<void> {
  await page.goto("/");
  await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth/);
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', PASSWORD);
  const me = page.waitForResponse(
    (r) => r.url() === `${CORE_URL}/v1/me` && r.request().method() === "GET" && r.ok(),
    { timeout: 30_000 },
  );
  await page.click('input[type="submit"], button[type="submit"]');
  await page.waitForURL((url) => url.origin === new URL(SHELL_URL).origin);
  await me;
  await page.getByRole("navigation", { name: /domaines/i }).waitFor();
}
