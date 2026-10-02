// SPDX-License-Identifier: Apache-2.0
// Destination à restaurer après le retour Keycloak (P07.02).

/** Chemin+query+hash courant, sauf sur l'URL de callback OIDC (code+state) -> "/". */
export function currentReturnTo(loc: { pathname: string; search: string; hash: string }): string {
  const q = new URLSearchParams(loc.search);
  if (q.has("code") && q.has("state")) return "/";
  return `${loc.pathname}${loc.search}${loc.hash}`;
}

/** N'accepte qu'un chemin interne (anti open-redirect) ; sinon "/". */
export function safeReturnTo(value: unknown): string {
  // Pas de `\` ni de caractère de contrôle : l'analyseur d'URL les lit comme `/`
  // ou les retire (`/\evil.com`, `/<TAB>/evil.com` valent `//evil.com`).
  if (typeof value !== "string" || !/^\/(?![/\\])/.test(value)) return "/";
  return [...value].some((c) => c === "\\" || c.charCodeAt(0) < 32) ? "/" : value;
}
