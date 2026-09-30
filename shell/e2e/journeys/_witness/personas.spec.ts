import { test } from "@playwright/test";
import { loginOidc, PERSONAS, type PersonaName } from "../_fixtures/env";

// Premier login de chaque persona d'audit (crée l'utilisateur côté cœur,
// requis avant `seed-personas.sh --set-roles`). Uniquement en mode oidc :
// lancer avec AUDIT_AUTH=oidc ; en mock, les tests sont ignorés (pas en échec).
test.describe("premier login des personas (auth oidc)", () => {
  test.skip(process.env.AUDIT_AUTH !== "oidc", "AUDIT_AUTH=oidc requis (stack en mode oidc)");

  for (const persona of Object.keys(PERSONAS) as PersonaName[]) {
    test(`login ${persona}`, async ({ page }) => {
      await loginOidc(page, persona);
    });
  }
});
