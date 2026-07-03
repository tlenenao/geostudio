import type { ReactNode } from "react";
import type { DataSourceState, RenderMode } from "../api/types";

export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
  data?: DataSourceState;
};

export type WidgetDefinition<P extends Record<string, unknown> = Record<string, unknown>> = {
  type: string;
  label: string;
  icon?: ReactNode;
  defaultProps: P;
  defaultSize: { w: number; h: number };
  PropsPanel: (p: { props: P; onChange: (props: P) => void }) => ReactNode;
  Component: (p: { props: P; ctx: WidgetContext }) => ReactNode;
};

const registry = new Map<string, WidgetDefinition>();

export function registerWidget(def: WidgetDefinition): void {
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
