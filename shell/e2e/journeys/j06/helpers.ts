import { execFileSync } from "node:child_process";
import type { Page } from "@playwright/test";
import { loginOidc, type PersonaName } from "../_fixtures/env";

// Un rechargement complet perd le chemin demandé après la reconnexion OIDC
// (défaut j02-004) : on navigue donc dans le routeur SPA sans recharger.
export async function spaGoto(page: Page, path: string): Promise<void> {
  await page.evaluate((p) => {
    history.pushState({}, "", p);
    dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

export async function openAs(page: Page, persona: PersonaName): Promise<void> {
  await loginOidc(page, persona);
  await page.getByRole("navigation", { name: /domaines/i }).waitFor();
}

// Exécute du Python dans le conteneur cœur (mêmes dépendances que la prod).
export function corePython(code: string): string {
  return execFileSync("docker", ["exec", "-i", "geostudio-core-1", "python", "-"], {
    input: code,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
  });
}
