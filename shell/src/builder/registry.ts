import type { ReactNode } from "react";
import type { DataSource, DataSourceState, Page, RenderMode } from "../api/types";
import type { ActionBus } from "./ActionBus";

export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
  pages?: Page[];
  variables?: Record<string, string>;
  data?: DataSourceState;
  bus?: ActionBus;
  widgetId?: string;
  user?: { name: string };
};

export type WidgetDefinition<P extends Record<string, unknown> = Record<string, unknown>> = {
  type: string;
  label: string;
  icon?: ReactNode;
  defaultProps: P;
  defaultSize: { w: number; h: number };
  events?: readonly string[];
  actions?: readonly string[];
  PropsPanel: (p: { props: P; onChange: (props: P) => void; dataSources: DataSource[] }) => ReactNode;
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
