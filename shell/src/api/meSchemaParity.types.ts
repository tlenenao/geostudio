// SPDX-License-Identifier: Apache-2.0
/**
 * REV-053 — voir `meSchemaParity.test.ts` pour le contexte complet.
 *
 * Contrôle à la compilation : force `tsc --noEmit` (`npm run build`) à
 * échouer si les types manuscrits `Me`/`InstanceInfo`/`RoleSummary`
 * (shell/src/api/types.ts) divergent en forme de
 * `components["schemas"]["MeResponse"|"MeCapabilities"|"RoleSummary"]`
 * (shell/src/api/generated/core-schema.d.ts, généré depuis
 * `core/openapi.json`). Premier import réel de ce fichier généré.
 *
 * `Equal<A, B>` est le patron standard de comparaison structurelle stricte de
 * deux types TypeScript (distributivité conditionnelle sur un type
 * générique nu) : il vaut `true` seulement si A et B acceptent exactement les
 * mêmes valeurs, dans les deux sens — contrairement à `A extends B`, qui ne
 * détecterait pas un champ manquant côté A.
 */
import type { components } from "./generated/core-schema";
import type { InstanceInfo, Me, RoleSummary } from "./types";

type Equal<A, B> =
  (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;

type AssertTrue<T extends true> = T;

type MeResponseSchema = components["schemas"]["MeResponse"];
type MeCapabilitiesSchema = components["schemas"]["MeCapabilities"];
type RoleSummarySchema = components["schemas"]["RoleSummary"];

// `Me.capabilities` réutilise volontairement `InstanceInfo` plutôt que
// `MeCapabilitiesSchema` (GAP-65 1/3) — comparées séparément ci-dessous,
// donc omises ici pour comparer le reste des champs à l'identique.
type MeWithoutNestedTypes = Omit<Me, "capabilities" | "role">;
type MeResponseSchemaWithoutNestedTypes = Omit<MeResponseSchema, "capabilities" | "role">;

export type _AssertMeResponseShapeMatchesGeneratedSchema = AssertTrue<
  Equal<MeWithoutNestedTypes, MeResponseSchemaWithoutNestedTypes>
>;

export type _AssertMeCapabilitiesMatchesInstanceInfo = AssertTrue<
  Equal<InstanceInfo, MeCapabilitiesSchema>
>;

export type _AssertRoleSummaryMatchesGeneratedSchema = AssertTrue<
  Equal<RoleSummary, RoleSummarySchema>
>;
