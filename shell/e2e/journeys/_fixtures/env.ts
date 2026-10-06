import type { Page } from "@playwright/test";

export const SHELL_URL = process.env.SHELL_URL ?? "http://localhost:8300";
export const CORE_URL = process.env.CORE_URL ?? "http://localhost:8200";

// Personas de rôle : créées par scripts/audit/seed-personas.sh (mode oidc).
// En mode mock, il n'existe qu'un utilisateur admin implicite (`mockuser`).
export const PERSONAS = {
  admin: { username: "audit-admin", password: "Demo1234!" },
  creator: { username: "audit-creator", password: "Demo1234!" },
  analyst: { username: "audit-analyst", password: "Demo1234!" },
  reader: { username: "audit-reader", password: "Demo1234!" },
} as const;

export type PersonaName = keyof typeof PERSONAS;

export async function loginOidc(page: Page, persona: PersonaName): Promise<void> {
  const { username, password } = PERSONAS[persona];
  await page.goto("/");
  await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth/);
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  // Le waiter est enregistré avant la soumission : un login qui atteint le
  // shell sans atteindre le cœur doit échouer bruyamment.
  const me = page.waitForResponse(
    (r) => r.url() === `${CORE_URL}/v1/me` && r.request().method() === "GET" && r.ok(),
    { timeout: 30_000 },
  );
  await page.click('input[type="submit"], button[type="submit"]');
  // Retour sur l'origine du shell (jamais une URL Keycloak). Le shell garde
  // ?code=&state= dans l'URL après l'échange : on ne les exclut donc pas, la
  // preuve que le callback a abouti est la réponse 2xx de /v1/me ci-dessous.
  await page.waitForURL((url) => url.origin === new URL(SHELL_URL).origin);
  await me;
}

// Préfixe unique pour tout objet qu'un agent crée (traçabilité dans les logs
// et l'audit_log, jamais utilisé pour le nettoyage : c'est le reset qui nettoie).
export function stamp(agentId: string): string {
  return `aud-${agentId}-${Date.now().toString(36)}`;
}

// Capacité ETL de la stack rejouée (GET /v1/instance, public) : les parcours
// « ETL éteint » n'ont de sens que si elle est coupée.
export async function etlEnabled(): Promise<boolean> {
  const r = await fetch(`${CORE_URL}/v1/instance`);
  return Boolean((await r.json()).etlEnabled);
}
