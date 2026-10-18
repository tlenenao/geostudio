// SPDX-License-Identifier: Apache-2.0
// Contrat DOM v1 (préversion) d'un widget GeoStudio : ce que l'hôte pose sur votre
// custom element. Voir docs/guides/2026-07-13-ecrire-un-widget-web-component.md.

export interface DataSourceState {
  loading: boolean;
  error: boolean;
  /** Enregistrements de la source référencée par `props.dataSourceId`. */
  records: Array<{ id?: string | number; properties: Record<string, unknown> }>;
  [key: string]: unknown;
}

export type GsMode = "edit" | "preview" | "runtime";

export interface GeoStudioWidgetElement extends HTMLElement {
  props: Record<string, unknown>;
  data?: DataSourceState;
  user?: { name: string };
  navigate?: (pageId: string) => void;
  /** v1 : variables d'app courantes (lecture). */
  variables: Record<string, unknown>;
  theme?: unknown;
  mode: GsMode;
  breakpoint?: string;
  sdkVersion: 1;
  /** v1 : écrit une variable d'app existante ; inerte en mode `edit`. */
  setVariable(name: string, value: unknown): void;
  /** v1 : pose le filtre d'une source de données ; inerte en mode `edit`. */
  setFilter(sourceId: string, query: Record<string, unknown>): void;
}

/** Émis une fois sur l'élément quand les propriétés ci-dessus sont posées. */
export type GsReadyEvent = CustomEvent<{ sdkVersion: 1 }>;
