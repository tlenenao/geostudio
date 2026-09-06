// SPDX-License-Identifier: Apache-2.0
/**
 * REV-053 : `shell/src/api/generated/core-schema.d.ts` (généré depuis
 * `core/openapi.json` par `npm run gen:api-types`) n'était importé par aucun
 * fichier — rien ne garantissait que les types manuscrits d'`ItemClient`
 * (`Me`, `RoleSummary`, `InstanceInfo`) restent synchronisés avec la forme
 * réelle servie par le cœur. `GET /me` est le point le plus à risque de
 * dérive (10+ champs, `capabilities` imbriqué, doublon délibéré avec
 * `GET /instance` déjà gardé côté cœur par
 * `core/tests/test_auth_me_capabilities.py`).
 *
 * Deux gardes complémentaires, sur le patron de ce test côté cœur :
 * 1. Un contrôle **runtime** (ce fichier) qui relit `core/openapi.json` — la
 *    source de la génération — et compare mécaniquement l'ensemble de
 *    propriétés de `MeResponse`/`MeCapabilities`/`RoleSummary` à la liste
 *    figée que consomme le shell. Falsifiable : renommer un champ dans
 *    `openapi.json` fait échouer ce test.
 * 2. Un contrôle **à la compilation** (`meSchemaParity.types.ts`, importé
 *    ci-dessous) qui force `tsc --noEmit` (`npm run build`, déjà une porte
 *    de qualité de ce dépôt) à échouer si les types manuscrits et
 *    `components["schemas"]["MeResponse"]` du fichier généré divergent en
 *    forme — c'est ce qui donne à `core-schema.d.ts` un premier consommateur
 *    réel.
 *
 * Portée assumée (temps disponible, cf. docs/revue/2026-09-04-backlog.md
 * REV-053) : limité à `GET /me`, pas une garantie générale de non-dérive sur
 * toute la surface de l'API. `npm run test` (Vitest, esbuild) n'exécute
 * jamais de vérification de type — seul (2) via `npm run build` détecte une
 * divergence purement structurelle qu'aucune valeur de test ne révélerait.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { _AssertMeResponseShapeMatchesGeneratedSchema } from "./meSchemaParity.types";

// Précédent : shell/src/styles/tokens.test.ts — ne pas résoudre ce chemin via
// `new URL(..., import.meta.url)` sous jsdom (substitue une URL non-file://).
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const openapi = JSON.parse(readFileSync(join(repoRoot, "core", "openapi.json"), "utf8")) as {
  components: { schemas: Record<string, { properties?: Record<string, unknown> }> };
};

function schemaKeys(name: string): string[] {
  const schema = openapi.components.schemas[name];
  expect(schema, `schéma introuvable dans core/openapi.json : ${name}`).toBeDefined();
  return Object.keys(schema.properties ?? {}).sort();
}

// Miroir manuscrit de `Me` (shell/src/api/types.ts) — à mettre à jour dans le
// même geste que tout ajout/retrait de champ sur MeResponse côté cœur.
const ME_FIELDS = [
  "capabilities",
  "email",
  "firstName",
  "id",
  "lastName",
  "privileges",
  "role",
  "tenantId",
  "tenantSlug",
  "username",
  "version",
].sort();

// Miroir manuscrit d'`InstanceInfo` (shell/src/api/types.ts), qui sert aussi
// de forme à `Me.capabilities` (GAP-65 1/3, doublon délibéré avec
// GET /instance).
const INSTANCE_INFO_FIELDS = [
  "adminToolsEnabled",
  "appExportEnabled",
  "copilotEnabled",
  "etlEnabled",
  "exportEnabled",
  "quotasEnabled",
  "readOnly",
  "terrain3dEnabled",
  "tileset3dEnabled",
].sort();

// Miroir manuscrit de `RoleSummary` (shell/src/api/types.ts).
const ROLE_SUMMARY_FIELDS = ["id", "name", "slug"].sort();

describe("core-schema.d.ts / openapi.json ne dérivent pas des types manuscrits (GET /me)", () => {
  it("MeResponse porte exactement les champs consommés par `Me`", () => {
    expect(schemaKeys("MeResponse")).toEqual(ME_FIELDS);
  });

  it("MeCapabilities porte exactement les champs consommés par `InstanceInfo`", () => {
    expect(schemaKeys("MeCapabilities")).toEqual(INSTANCE_INFO_FIELDS);
  });

  it("RoleSummary porte exactement les champs consommés par `RoleSummary`", () => {
    expect(schemaKeys("RoleSummary")).toEqual(ROLE_SUMMARY_FIELDS);
  });

  // Ancre pour le contrôle de compilation (2) : un import de type mort serait
  // supprimé silencieusement par un outil de nettoyage — cette assertion
  // runtime, toujours vraie, empêche `_AssertMeResponseShapeMatchesGeneratedSchema`
  // de passer pour "inutilisé" et documente le lien entre les deux gardes.
  it("référence le contrôle de compilation compagnon", () => {
    const marker: _AssertMeResponseShapeMatchesGeneratedSchema = true;
    expect(marker).toBe(true);
  });
});
