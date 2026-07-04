import { useEffect, useMemo, useState } from "react";
import { useAppConfig, useSaveApp } from "../api/hooks";
import type { AppConfig, RenderMode, WidgetItem } from "../api/types";
import { ActionsPanel } from "../builder/ActionsPanel";
import { AppRenderer } from "../builder/AppRenderer";
import { DataSourcePanel } from "../builder/DataSourcePanel";
import { WidgetPalette } from "../builder/WidgetPalette";
import { PropsPanel } from "../builder/PropsPanel";
import { ThemePanel } from "../builder/ThemePanel";
import { registerBuiltinWidgets } from "../builder/widgets";
import { getWidget } from "../builder/registry";
import { BREAKPOINTS, type Breakpoint } from "../builder/grid";
import { Button } from "../ui/button";

registerBuiltinWidgets();

export function AppBuilderPage({ pk }: { pk: string }) {
  const query = useAppConfig(pk);
  const save = useSaveApp(pk);
  const [draft, setDraft] = useState<AppConfig | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<RenderMode>("edit");
  const [breakpoint, setBreakpoint] = useState<Breakpoint>("lg");

  useEffect(() => {
    // Seed the draft once on first load. Re-seeding on every query.data change
    // (e.g. the refetch after a save) would clobber in-flight local edits.
    if (query.data) setDraft((d) => d ?? query.data);
  }, [query.data]);

  const selected = useMemo(
    () => draft?.layout.items.find((i) => i.id === selectedId) ?? null,
    [draft, selectedId],
  );

  if (query.isLoading || (!draft && !query.isError)) return <p role="status">Chargement…</p>;
  if (query.isError || !draft)
    return <p role="alert" className="text-sm text-red-600">Application introuvable.</p>;

  function addWidget(type: string) {
    const def = getWidget(type);
    if (!def || !draft) return;
    const item: WidgetItem = {
      id: crypto.randomUUID(),
      widget: type,
      x: 0,
      y: 0,
      w: def.defaultSize.w,
      h: def.defaultSize.h,
      props: { ...def.defaultProps },
    };
    setDraft({ ...draft, layout: { ...draft.layout, items: [...draft.layout.items, item] } });
    setSelectedId(item.id);
  }

  function updateSelectedProps(props: Record<string, unknown>) {
    if (!draft || !selectedId) return;
    setDraft({
      ...draft,
      layout: {
        ...draft.layout,
        items: draft.layout.items.map((i) => (i.id === selectedId ? { ...i, props } : i)),
      },
    });
  }

  const setSources = (dataSources: typeof draft.dataSources) =>
    setDraft((d) => (d ? { ...d, dataSources } : d));

  const setMessages = (messages: typeof draft.messages) =>
    setDraft((d) => (d ? { ...d, messages } : d));

  const setTheme = (theme: typeof draft.theme) =>
    setDraft((d) => (d ? { ...d, theme } : d));

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
        <Button size="sm" disabled={save.isPending} onClick={() => save.mutate(draft)}>Enregistrer</Button>
        {save.isError && <span role="alert" className="text-sm text-red-600">Échec de l'enregistrement.</span>}
      </div>
      <div className="flex flex-1 overflow-hidden">
        {mode === "edit" && (
          <aside className="w-48 overflow-auto border-r p-2">
            <p className="mb-1 text-xs font-medium text-slate-500">Widgets</p>
            <WidgetPalette onAdd={addWidget} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Sources de données</p>
            <DataSourcePanel sources={draft.dataSources} onChange={setSources} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Actions</p>
            <ActionsPanel items={draft.layout.items} messages={draft.messages} onChange={setMessages} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Thème</p>
            <ThemePanel theme={draft.theme} onChange={setTheme} />
          </aside>
        )}
        <main className="flex-1 overflow-auto p-2">
          <AppRenderer
            config={draft}
            mode={mode}
            onChange={setDraft}
            selectedId={selectedId}
            onSelect={setSelectedId}
            breakpoint={breakpoint}
          />
        </main>
        {mode === "edit" && (
          <aside className="w-64 overflow-auto border-l p-2">
            <p className="mb-1 text-xs font-medium text-slate-500">Propriétés</p>
            <PropsPanel item={selected} dataSources={draft.dataSources} onChange={updateSelectedProps} />
          </aside>
        )}
      </div>
    </div>
  );
}
