// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import type { DataSource, DataSourceState, Page, RenderMode, Theme, Variable } from "../api/types";
import type { Breakpoint } from "./grid";
import type { ActionBus } from "./ActionBus";
import type { WidgetPropDescriptor } from "./widgetPropSchema";

export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
  pages?: Page[];
  variables?: Record<string, unknown>;
  /** SDK v1 (L10) : écriture d'une variable d'app / d'un filtre de source, fournies par le host. */
  setVariable?: (name: string, value: unknown) => void;
  setFilter?: (sourceId: string, query: Record<string, unknown>) => void;
  data?: DataSourceState;
  bus?: ActionBus;
  widgetId?: string;
  user?: { name: string };
  breakpoint?: Breakpoint;
  theme?: Theme;
};

export type WidgetDefinition<P extends Record<string, unknown> = Record<string, unknown>> = {
  type: string;
  label: string;
  icon?: ReactNode;
  defaultProps: P;
  defaultSize: { w: number; h: number };
  events?: readonly string[];
  actions?: readonly string[];
  // Sous-ensemble des props éditables par le copilote (SP-20) — seules les
  // props scalaires (string/number/boolean/dataSource) ; les props
  // array/object (colonnes de table, items de tiroir, encodages...) restent
  // hors de portée, non listées ici.
  configSchema?: WidgetPropDescriptor[];
  PropsPanel: (p: {
    props: P;
    onChange: (props: P) => void;
    dataSources: DataSource[];
    theme?: Theme;
    variables?: Variable[];
    // REV-183 : présent = le panneau peut proposer le générateur CEL.
    generateItemId?: string;
  }) => ReactNode;
  Component: (p: { props: P; ctx: WidgetContext }) => ReactNode;
};

const registry = new Map<string, WidgetDefinition>();

export function registerWidget(def: WidgetDefinition): void {
  if (registry.has(def.type)) {
    console.warn(`registerWidget: overwriting an already-registered widget type "${def.type}"`);
  }
  registry.set(def.type, def);
}
/** L10 (AUD-109) : retire un type (extension désactivée/supprimée) du catalogue. */
export function unregisterWidget(type: string): void {
  registry.delete(type);
}
export function getWidget(type: string): WidgetDefinition | undefined {
  return registry.get(type);
}
export function listWidgets(): WidgetDefinition[] {
  return [...registry.values()];
}
export function _resetRegistry(): void {
  registry.clear();
}
