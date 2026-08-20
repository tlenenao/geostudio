// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import type { DataSource, DataSourceState, Page, RenderMode } from "../api/types";
import type { Breakpoint } from "./grid";
import type { ActionBus } from "./ActionBus";
import type { WidgetPropDescriptor } from "./widgetPropSchema";

export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
  pages?: Page[];
  variables?: Record<string, unknown>;
  data?: DataSourceState;
  bus?: ActionBus;
  widgetId?: string;
  user?: { name: string };
  breakpoint?: Breakpoint;
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
export function getWidget(type: string): WidgetDefinition | undefined {
  return registry.get(type);
}
export function listWidgets(): WidgetDefinition[] {
  return [...registry.values()];
}
export function _resetRegistry(): void {
  registry.clear();
}
