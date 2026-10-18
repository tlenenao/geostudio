// SPDX-License-Identifier: Apache-2.0
import { Component, type ReactNode } from "react";
import type { LakeFreshness, Page, RenderMode, Theme, WidgetItem } from "../api/types";
import { formatDateTime } from "../lib/format";
import type { Breakpoint } from "./grid";
import { getWidget } from "./registry";
import { useDataStates, useSetFilter } from "./DataContext";
import { useActionBus } from "./ActionBusContext";
import { useSetVariable, useVariables } from "./VariablesContext";
import { useAnalyticsContext } from "./AnalyticsContext";
import { useAuth } from "../auth/useAuth";
import { evaluateExpression } from "./expr";
import { resolveExprBindings } from "./exprBindings";
import { t } from "../i18n";
import "../i18n/domains/widgets";

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
      return (
        <div className="flex h-full items-center justify-center bg-danger-soft text-xs text-danger">
          {t("widgetHost.crashedFallback")}
        </div>
      );
    }
    return this.props.children;
  }
}

// AUD-061 : au-delà de ce retard de réplication, l'agrégat est signalé comme décalé.
export const LAKE_LAG_NOTICE_MS = 5 * 60_000;

export function lakeNotice(lake: LakeFreshness | undefined, now = Date.now()): string | null {
  if (!lake) return null;
  if (lake.pending) return t("widgetHost.lakePending");
  if (lake.asOf && now - new Date(lake.asOf).getTime() > LAKE_LAG_NOTICE_MS) {
    return t("widgetHost.lakeStale", { date: formatDateTime(lake.asOf) });
  }
  return null;
}

export function WidgetHost({
  item,
  mode,
  pages = [],
  navigate,
  breakpoint,
  theme,
}: {
  item: WidgetItem;
  mode: RenderMode;
  pages?: Page[];
  navigate?: (pageId: string) => void;
  breakpoint?: Breakpoint;
  theme?: Theme;
}) {
  const states = useDataStates();
  const bus = useActionBus();
  const variables = useVariables();
  const setVariable = useSetVariable();
  const setFilter = useSetFilter();
  const { username } = useAuth();
  const analyticsCtx = useAnalyticsContext();
  const user = { name: username ?? "" };
  const dsId = item.props.dataSourceId as string | undefined;
  const data = dsId ? states[dsId] : undefined;
  const def = getWidget(item.widget);
  if (!def) {
    return (
      <div className="flex h-full items-center justify-center bg-sunken text-xs text-ink-2">
        {t("widgetHost.unknownWidget", { widget: item.widget })}
      </div>
    );
  }
  const visible =
    mode === "edit" ||
    !item.visibleWhen ||
    Boolean(
      evaluateExpression(item.visibleWhen, {
        vars: variables,
        record: data?.records[0]?.properties,
        user,
        ctx: analyticsCtx,
      }),
    );
  if (!visible) return null;
  const Widget = def.Component;
  const exprCtx = {
    vars: variables,
    record: data?.records[0]?.properties,
    user,
    ctx: analyticsCtx,
  };
  const resolvedProps = resolveExprBindings(item.props, exprCtx) as Record<string, unknown>;
  const notice = lakeNotice(data?.lake);
  const rendered = (
    <WidgetErrorBoundary>
      <Widget
        props={resolvedProps}
        ctx={{
          mode,
          data,
          bus: bus ?? undefined,
          widgetId: item.id,
          pages,
          navigate,
          variables,
          setVariable,
          setFilter,
          user,
          breakpoint,
          theme,
        }}
      />
    </WidgetErrorBoundary>
  );
  // Sans retard notable le DOM est inchangé : l'enveloppe n'existe que pour porter l'avis.
  if (!notice) return rendered;
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1">{rendered}</div>
      <p role="status" data-lake-notice className="shrink-0 text-xs text-warn">
        {notice}
      </p>
    </div>
  );
}
