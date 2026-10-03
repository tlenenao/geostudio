// SPDX-License-Identifier: Apache-2.0
/**
 * P22.05 (c08-009) — parité de compilation, sens « ce que le shell ENVOIE » :
 * un MapConfig/MapLayer/Variable/DataSource manuscrit doit rester assignable
 * au schéma généré depuis l'OpenAPI du cœur (donc accepté par le serveur).
 * `tsc --noEmit` (npm run build) échoue si le shell écrit une forme que le
 * cœur ne connaît pas. Le sens inverse (cœur -> shell) est volontairement
 * non asserté (ni `Variable`, dont `type` est optionnel côté shell alors que le
 * schéma de sortie le rend requis via son défaut) : le schéma serveur est plus lâche (`type: string`, `pitch: null`).
 */
import type { components } from "./generated/core-schema";
import type { DataSource, MapConfig, MapLayer } from "./types";

type G = components["schemas"];
type AssertAssignable<_A extends B, B> = true;

export type _MapConfigSent = AssertAssignable<MapConfig, NonNullable<G["BuilderConfig"]["map"]>>;
export type _MapLayerSent = AssertAssignable<MapLayer, G["MapLayer"]>;
export type _DataSourceSent = AssertAssignable<
  DataSource,
  NonNullable<G["BuilderConfig"]["dataSources"]>[number]
>;
