// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import type { AppConfig, RenderMode, Variable } from "../api/types";
import { GridCanvas } from "./GridCanvas";
import { WidgetHost } from "./WidgetHost";
import { moveItemAt, breakpointForWidth, type Breakpoint } from "./grid";
import { getPages, getPageLayout, setPageLayout } from "./pages";
import { DataProvider } from "./DataContext";
import { ActionBus } from "./ActionBus";
import { ActionBusProvider, useBusAction } from "./ActionBusContext";
import { VariablesProvider, useSetVariable, useVariables } from "./VariablesContext";
import { AnalyticsContextProvider, useAnalyticsContext, type AnalyticsContextState } from "./AnalyticsContext";
import { AnalyticsContextIndicator } from "./AnalyticsContextIndicator";
import { ExplorerProvider } from "./ExplorerContext";
import { ExplorerDrawer } from "./ExplorerDrawer";
import { useAuth } from "../auth/useAuth";
import { themeToCssVars } from "./theme";

// A message's payload is whatever shape its emitter chose (Button emits
// {widgetId}, Filtre emits {[field]: value}, …). For string/number/bool/date
// variables, extract the payload key matching the variable's own name (e.g.
// a Filtre configured with field === the variable's name) and coerce to the
// declared type — degrade silently (keep the previous value) if not
// coercible, never throw. For record/list variables, the whole emitter
// payload is stored as-is (no by-name extraction) — this is what makes
// wiring e.g. Table.itemSelected into a record variable useful, since its
// payload is already a full DataRecord, not an object keyed by variable name.
function coerceForVariable(payload: unknown, variable: Variable): unknown {
  const type = variable.type ?? "string";
  if (type === "record") {
    return payload && typeof payload === "object" && !Array.isArray(payload) ? payload : undefined;
  }
  if (type === "list") {
    return Array.isArray(payload) ? payload : undefined;
  }
  const raw = payload && typeof payload === "object"
    ? (payload as Record<string, unknown>)[variable.name]
    : payload;
  if (type === "number") {
    const n = Number(raw);
    return Number.isNaN(n) ? undefined : n;
  }
  if (type === "bool") {
    if (typeof raw === "boolean") return raw;
    return ["true", "1"].includes(String(raw ?? "").toLowerCase());
  }
  // string, date
  return raw === null || raw === undefined ? "" : String(raw);
}

function VariableBusBridge({ variable, bus }: { variable: Variable; bus: ActionBus }) {
  const setVariable = useSetVariable();
  useBusAction(bus, `var:${variable.id}`, "set", (payload) => {
    const value = coerceForVariable(payload, variable);
    if (value === undefined) return; // not coercible for this type — keep the previous value, never crash
    setVariable(variable.name, value);
  });
  return null;
}

// Keeps ActionBus.context fresh with the live app variables and the
// authenticated user, so an ActionMessage.when condition (SP-5b) can
// reference vars.x/user.name — mirrors VariableBusBridge's live-value wiring.
function ActionConditionBridge({ bus }: { bus: ActionBus }) {
  const variables = useVariables();
  const { username } = useAuth();
  const analyticsCtx = useAnalyticsContext();
  useEffect(() => {
    bus.setContext({ vars: variables, user: { name: username ?? "" }, ctx: analyticsCtx });
  }, [bus, variables, username, analyticsCtx]);
  return null;
}

export function AppRenderer({
  config,
  mode,
  onChange,
  selectedId = null,
  onSelect,
  breakpoint,
  pageId,
  onNavigate,
  initialAnalyticsContext,
  onAnalyticsContextChange,
}: {
  config: AppConfig;
  mode: RenderMode;
  onChange?: (config: AppConfig) => void;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  breakpoint?: Breakpoint;
  pageId?: string;
  onNavigate?: (pageId: string) => void;
  initialAnalyticsContext?: AnalyticsContextState;
  onAnalyticsContextChange?: (state: AnalyticsContextState) => void;
}) {
  const editable = mode === "edit";
  const analyticsUiEnabled = mode !== "edit" && config.interactions === "auto";
  const bus = useMemo(() => new ActionBus(), []);
  useEffect(() => {
    bus.configure(config.messages);
  }, [bus, config.messages]);

  // When no breakpoint is controlled (runtime/preview without a switcher),
  // auto-detect from the container width. jsdom has no ResizeObserver → keep lg.
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoBp, setAutoBp] = useState<Breakpoint>("lg");
  useEffect(() => {
    if (breakpoint) return;
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const update = () => setAutoBp(breakpointForWidth(el.clientWidth));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [breakpoint]);
  const bp = breakpoint ?? autoBp;

  // When no pageId is controlled, fall back to internal state defaulting to
  // the first page. A widget-triggered navigation (e.g. the Navigation widget)
  // calls handleNavigate, which either bubbles to the controlling parent
  // (editor page selector, runtime route) or updates this local fallback.
  const pages = useMemo(() => getPages(config), [config]);
  const [internalPageId, setInternalPageId] = useState<string | null>(null);
  const activePageId = pageId ?? internalPageId ?? pages[0].id;
  const activeLayout = getPageLayout(config, activePageId);

  function handleNavigate(nextPageId: string) {
    if (onNavigate) onNavigate(nextPageId);
    else setInternalPageId(nextPageId);
  }

  const storyMode = config.navigationMode === "story" && mode !== "edit";
  const chapterIndex = pages.findIndex((p) => p.id === activePageId);

  // À l'entrée d'un chapitre (preview/runtime, mode story), déclenche ses onEnter.
  // Ré-émis à chaque entrée, y compris en revenant en arrière — cohérent avec
  // map.flyTo qui est idempotent (comportement par défaut acté au plan).
  useEffect(() => {
    if (!storyMode) return;
    const page = pages.find((p) => p.id === activePageId);
    if (page?.onEnter && page.onEnter.length > 0) bus.dispatch(page.onEnter);
  }, [storyMode, activePageId, pages, bus]);

  function handleMove(id: string, dx: number, dy: number) {
    if (!onChange) return;
    const items = activeLayout.items.map((it) => (it.id === id ? moveItemAt(it, bp, dx, dy) : it));
    onChange(setPageLayout(config, activePageId, { ...activeLayout, items }));
  }

  return (
    <div ref={containerRef} className="flex h-full w-full flex-col bg-[var(--gs-color-background)] font-[var(--gs-font)]" style={themeToCssVars(config.theme)}>
      {storyMode && (
        <nav className="flex items-center gap-2 border-b border-[var(--gs-color-border)] p-2 text-sm">
          <button
            type="button"
            className="rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] px-2 py-1 disabled:opacity-30"
            disabled={chapterIndex <= 0}
            onClick={() => handleNavigate(pages[chapterIndex - 1].id)}
          >
            Précédent
          </button>
          <span className="text-[var(--gs-color-muted)]">Chapitre {chapterIndex + 1} / {pages.length}</span>
          <button
            type="button"
            className="rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] px-2 py-1 disabled:opacity-30"
            disabled={chapterIndex >= pages.length - 1}
            onClick={() => handleNavigate(pages[chapterIndex + 1].id)}
          >
            Suivant
          </button>
        </nav>
      )}
      <div className="min-h-0 flex-1">
        <ActionBusProvider bus={bus}>
          <VariablesProvider variables={config.variables ?? []}>
            <ExplorerProvider enabled={analyticsUiEnabled}>
              <AnalyticsContextProvider
                interactions={config.interactions}
                initialState={initialAnalyticsContext}
                onStateChange={onAnalyticsContextChange}
              >
                {analyticsUiEnabled && <AnalyticsContextIndicator />}
                <ExplorerDrawer />
                <ActionConditionBridge bus={bus} />
                {(config.variables ?? []).map((v) => (
                  <VariableBusBridge key={v.id} variable={v} bus={bus} />
                ))}
                <DataProvider sources={config.dataSources}>
                  <GridCanvas
                    items={activeLayout.items}
                    breakpoint={bp}
                    editable={editable}
                    selectedId={selectedId}
                    onSelect={(id) => onSelect?.(id)}
                    onMoveItem={handleMove}
                    renderItem={(item) => <WidgetHost item={item} mode={mode} pages={pages} navigate={handleNavigate} breakpoint={bp} />}
                  />
                </DataProvider>
              </AnalyticsContextProvider>
            </ExplorerProvider>
          </VariablesProvider>
        </ActionBusProvider>
      </div>
    </div>
  );
}
