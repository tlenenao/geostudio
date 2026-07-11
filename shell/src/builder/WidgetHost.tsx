import { Component, type ReactNode } from "react";
import type { Page, RenderMode, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { useDataStates } from "./DataContext";
import { useActionBus } from "./ActionBusContext";
import { useVariables } from "./VariablesContext";
import { useAuth } from "../auth/useAuth";
import { evaluateExpression } from "./expr";

class WidgetErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(err: unknown) {
    console.error("WidgetHost: widget crashed", err);
  }
  render() {
    if (this.state.failed) {
      return <div className="flex h-full items-center justify-center bg-red-50 text-xs text-red-600">Erreur du widget</div>;
    }
    return this.props.children;
  }
}

export function WidgetHost({
  item,
  mode,
  pages = [],
  navigate,
}: {
  item: WidgetItem;
  mode: RenderMode;
  pages?: Page[];
  navigate?: (pageId: string) => void;
}) {
  const states = useDataStates();
  const bus = useActionBus();
  const variables = useVariables();
  const { username } = useAuth();
  const user = { name: username ?? "" };
  const dsId = item.props.dataSourceId as string | undefined;
  const data = dsId ? states[dsId] : undefined;
  const def = getWidget(item.widget);
  if (!def) {
    return <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">Widget inconnu : {item.widget}</div>;
  }
  const visible = mode === "edit" || !item.visibleWhen
    || Boolean(evaluateExpression(item.visibleWhen, { vars: variables, record: data?.records[0]?.properties, user }));
  if (!visible) return null;
  const Widget = def.Component;
  return (
    <WidgetErrorBoundary>
      <Widget props={item.props} ctx={{ mode, data, bus: bus ?? undefined, widgetId: item.id, pages, navigate, variables, user }} />
    </WidgetErrorBoundary>
  );
}
