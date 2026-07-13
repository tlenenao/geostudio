import { useEffect, useMemo, useRef, useState } from "react";
import { toBlob } from "html-to-image";
import { useAppConfig, useSaveApp, useUploadThumbnail } from "../api/hooks";
import type { AppConfig, RenderMode, WidgetItem } from "../api/types";
import { ActionsPanel } from "../builder/ActionsPanel";
import { AppRenderer } from "../builder/AppRenderer";
import { DataSourcePanel } from "../builder/DataSourcePanel";
import { PageManager } from "../builder/PageManager";
import { WidgetPalette } from "../builder/WidgetPalette";
import { PropsPanel } from "../builder/PropsPanel";
import { ThemePanel } from "../builder/ThemePanel";
import { VariablesPanel } from "../builder/VariablesPanel";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
import { useActiveExtensions } from "../api/hooks";
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";
import { getWidget } from "../builder/registry";
import { BREAKPOINTS, nextFreePosition, type Breakpoint } from "../builder/grid";
import { getPages, getPageLayout, setPageLayout } from "../builder/pages";
import { getConfigExpressionErrors } from "../builder/configExpressionErrors";
import { Button } from "../ui/button";

registerBuiltinWidgets();
registerCounterExampleWidget();
registerCounterWcExampleWidget();

export function AppBuilderPage({ pk }: { pk: string }) {
  const query = useAppConfig(pk);
  const save = useSaveApp(pk);
  const thumbnail = useUploadThumbnail(pk);
  const mainRef = useRef<HTMLElement>(null);
  const [draft, setDraft] = useState<AppConfig | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<RenderMode>("edit");
  const [breakpoint, setBreakpoint] = useState<Breakpoint>("lg");
  const [activePageId, setActivePageId] = useState<string | null>(null);

  const extensionsQuery = useActiveExtensions();
  const [extensionsRegistered, setExtensionsRegistered] = useState(false);

  useEffect(() => {
    if (extensionsQuery.isLoading) return;
    (extensionsQuery.data ?? []).forEach(registerExtensionWidget);
    setExtensionsRegistered(true);
    // Se déclenche une fois les données arrivées OU en erreur (fail-open :
    // un /extensions en échec ne doit pas rendre le builder inutilisable) —
    // jamais tant que isLoading est vrai.
  }, [extensionsQuery.isLoading, extensionsQuery.data]);

  useEffect(() => {
    // Seed the draft once on first load. Re-seeding on every query.data change
    // (e.g. the refetch after a save) would clobber in-flight local edits.
    if (query.data) setDraft((d) => d ?? query.data);
  }, [query.data]);

  const pages = useMemo(() => (draft ? getPages(draft) : []), [draft]);
  const activePage = activePageId ?? pages[0]?.id ?? null;
  const activeLayout = useMemo(
    () => (draft && activePage ? getPageLayout(draft, activePage) : null),
    [draft, activePage],
  );

  const selected = useMemo(
    () => activeLayout?.items.find((i) => i.id === selectedId) ?? null,
    [activeLayout, selectedId],
  );

  if (query.isLoading || !extensionsRegistered || (!draft && !query.isError))
    return <p role="status">Chargement…</p>;
  if (query.isError || !draft || !activeLayout || !activePage)
    return <p role="alert" className="text-sm text-red-600">Application introuvable.</p>;

  function addWidget(type: string) {
    const def = getWidget(type);
    if (!def || !draft || !activeLayout || !activePage) return;
    const { x, y } = nextFreePosition(activeLayout.items);
    const item: WidgetItem = {
      id: crypto.randomUUID(),
      widget: type,
      x,
      y,
      w: def.defaultSize.w,
      h: def.defaultSize.h,
      props: { ...def.defaultProps },
    };
    setDraft(setPageLayout(draft, activePage, { ...activeLayout, items: [...activeLayout.items, item] }));
    setSelectedId(item.id);
  }

  async function captureThumbnail() {
    if (!mainRef.current) return;
    const blob = await toBlob(mainRef.current);
    if (!blob) return;
    const file = new File([blob], "thumbnail.png", { type: "image/png" });
    try {
      await thumbnail.mutateAsync(file);
    } catch {
      /* surfaced via thumbnail.isError */
    }
  }

  function updateSelectedProps(props: Record<string, unknown>) {
    if (!draft || !selectedId || !activeLayout || !activePage) return;
    setDraft(setPageLayout(draft, activePage, {
      ...activeLayout,
      items: activeLayout.items.map((i) => (i.id === selectedId ? { ...i, props } : i)),
    }));
  }

  function updateSelectedVisibleWhen(expr: string) {
    if (!draft || !selectedId || !activeLayout || !activePage) return;
    setDraft(setPageLayout(draft, activePage, {
      ...activeLayout,
      items: activeLayout.items.map((i) => (i.id === selectedId ? { ...i, visibleWhen: expr || undefined } : i)),
    }));
  }

  const setSources = (dataSources: typeof draft.dataSources) =>
    setDraft((d) => (d ? { ...d, dataSources } : d));

  const setMessages = (messages: typeof draft.messages) =>
    setDraft((d) => (d ? { ...d, messages } : d));

  const setTheme = (theme: typeof draft.theme) =>
    setDraft((d) => (d ? { ...d, theme } : d));

  const setPages = (nextPages: typeof pages) =>
    setDraft((d) => (d ? { ...d, pages: nextPages, layout: nextPages[0]?.layout ?? d.layout } : d));

  const setVariables = (variables: typeof draft.variables) =>
    setDraft((d) => (d ? { ...d, variables } : d));

  const expressionErrors = draft ? getConfigExpressionErrors(draft) : [];

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b p-2">
        <Button size="sm" variant={mode === "edit" ? "default" : "outline"} onClick={() => setMode("edit")}>Édition</Button>
        <Button size="sm" variant={mode === "preview" ? "default" : "outline"} onClick={() => setMode("preview")}>Aperçu</Button>
        <div className="ml-2 flex items-center gap-1">
          {BREAKPOINTS.map((bp) => (
            <Button
              key={bp}
              size="sm"
              variant={breakpoint === bp ? "default" : "outline"}
              aria-label={`Éditer en ${bp}`}
              onClick={() => setBreakpoint(bp)}
            >
              {bp}
            </Button>
          ))}
        </div>
        <div className="flex-1" />
        <Button size="sm" variant="outline" disabled={thumbnail.isPending} onClick={captureThumbnail}>
          Capturer une miniature
        </Button>
        <Button size="sm" disabled={save.isPending || expressionErrors.length > 0} onClick={() => save.mutate(draft)}>
          Enregistrer
        </Button>
        {expressionErrors.length > 0 && (
          <span role="alert" aria-label="Erreur de condition d'affichage" className="text-sm text-red-600">
            {expressionErrors[0]}
          </span>
        )}
        {save.isError && <span role="alert" className="text-sm text-red-600">Échec de l'enregistrement.</span>}
        {thumbnail.isError && <span role="alert" className="text-sm text-red-600">Échec de la capture.</span>}
      </div>
      <div className="flex flex-1 overflow-hidden">
        {mode === "edit" && (
          <aside className="w-48 overflow-auto border-r p-2">
            <p className="mb-1 text-xs font-medium text-slate-500">Widgets</p>
            <WidgetPalette onAdd={addWidget} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Pages</p>
            <PageManager pages={pages} activePageId={activePage} onChange={setPages} onSelectPage={setActivePageId} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Sources de données</p>
            <DataSourcePanel sources={draft.dataSources} onChange={setSources} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Actions</p>
            <ActionsPanel items={activeLayout.items} variables={draft.variables ?? []} messages={draft.messages} onChange={setMessages} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Variables</p>
            <VariablesPanel variables={draft.variables ?? []} onChange={setVariables} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Thème</p>
            <ThemePanel theme={draft.theme} onChange={setTheme} />
          </aside>
        )}
        <main ref={mainRef} className="flex-1 overflow-auto p-2">
          <AppRenderer
            config={draft}
            mode={mode}
            onChange={setDraft}
            selectedId={selectedId}
            onSelect={setSelectedId}
            breakpoint={breakpoint}
            pageId={activePage}
            onNavigate={setActivePageId}
          />
        </main>
        {mode === "edit" && (
          <aside className="w-64 overflow-auto border-l p-2">
            <p className="mb-1 text-xs font-medium text-slate-500">Propriétés</p>
            <PropsPanel
              item={selected}
              dataSources={draft.dataSources}
              onChange={updateSelectedProps}
              onVisibleWhenChange={updateSelectedVisibleWhen}
            />
          </aside>
        )}
      </div>
    </div>
  );
}
