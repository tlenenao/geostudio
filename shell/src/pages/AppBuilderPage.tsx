// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { useUndoableDraft } from "../builder/useUndoableDraft";
import { toBlob } from "html-to-image";
import {
  useAppConfig,
  useCreateDataset,
  useInstanceInfo,
  useItem,
  useSaveApp,
  useUploadThumbnail,
} from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { PrintLayoutConfig, RenderMode, WidgetItem } from "../api/types";
import { hasPermission } from "../auth/permissions";
import { ActionsPanel } from "../builder/ActionsPanel";
import { AppExportPanel } from "../builder/appexport/AppExportPanel";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { CopilotPanel } from "../builder/copilot/CopilotPanel";
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
import { AppRenderer } from "../builder/AppRenderer";
import { NavigationPanel } from "../builder/NavigationPanel";
import { DataSourcePanel } from "../builder/DataSourcePanel";
import { DataSourcesEditProvider } from "../builder/DataSourcesEditContext";
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
import { pruneMessagesForIds } from "../builder/actionMessages";
import { Button } from "../ui/kit/Button";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { useAuth } from "../auth/useAuth";
import { t } from "../i18n";

registerBuiltinWidgets();
registerCounterExampleWidget();
registerCounterWcExampleWidget();

export function AppBuilderPage({ pk }: { pk: string }) {
  const client = useItemClient();
  const query = useAppConfig(pk);
  const save = useSaveApp(pk);
  const itemQuery = useItem(pk);
  // SP-42/F-shell-pages-04 : cf. commentaire jumeau sur DatasetEditPage.tsx —
  // même doctrine, même résidu documenté (permissions.write incomplet vs
  // garde de privilège de domaine).
  //
  // SP-42, revue finale (point 2, Critical) : `itemQuery.data` est
  // `undefined` pendant tout le chargement ET en cas d'erreur — hasPermission
  // renvoie alors `false`, verrouillant Enregistrer pour la mauvaise raison.
  // Le garde de rendu plus bas inclut désormais itemQuery.isLoading/isError
  // (même patron que DatasetEditPage.tsx:52-58) : `readOnly` n'est calculé
  // qu'une fois l'item effectivement résolu.
  const readOnly = !hasPermission(itemQuery.data, "write");
  const thumbnail = useUploadThumbnail(pk);
  const instanceQuery = useInstanceInfo();
  const appExportEnabled = instanceQuery.data?.appExportEnabled === true;
  const copilotEnabled = instanceQuery.data?.copilotEnabled === true;
  const { username } = useAuth();
  const createDataset = useCreateDataset();
  const [promotingId, setPromotingId] = useState<string | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  const { draft, setDraft, seedDraft, resetDraft, undo, redo, canUndo, canRedo } =
    useUndoableDraft();
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
    // seedDraft (not setDraft) — this is the session's starting point, not
    // an edit, and must not create an undo step (SP-19).
    if (query.data) seedDraft(query.data);
  }, [query.data, seedDraft]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = document.activeElement;
      const isTextField =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (isTextField) return;
      if ((e.key === "Delete" || e.key === "Backspace") && selectedId) {
        e.preventDefault();
        removeSelected();
        return;
      }
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // removeSelected n'est pas listée : c'est une function declaration hoisted et stable
    // (redéfinie identiquement à chaque rendu, capture les mêmes dépendances que le reste
    // du composant) — l'ajouter au tableau ne changerait rien.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [undo, redo, selectedId]);

  const pages = useMemo(() => (draft ? getPages(draft) : []), [draft]);
  // Validate activePageId against the current draft's pages rather than
  // trusting it blindly: undoing a page addition (Ctrl+Z) reverts `draft`
  // but `activePageId` is a plain useState, not part of the undo stack, so
  // it keeps pointing at a page that no longer exists. setPageLayout()
  // silently no-ops for an unknown pageId (see builder/pages.ts), so every
  // edit made while activePageId is stale was previously a silent no-op —
  // SP-19 final-branch-review fix pass, finding C2.
  const activePage =
    activePageId && pages.some((p) => p.id === activePageId)
      ? activePageId
      : (pages[0]?.id ?? null);
  const activeLayout = useMemo(
    () => (draft && activePage ? getPageLayout(draft, activePage) : null),
    [draft, activePage],
  );

  const selected = useMemo(
    () => activeLayout?.items.find((i) => i.id === selectedId) ?? null,
    [activeLayout, selectedId],
  );

  // Same class of bug as C2 above, for the other piece of state that lives
  // outside the undo stack: undoing a widget addition leaves `selectedId`
  // pointing at a removed item. `selected` above already resolves to null
  // in that case, but the stale id itself should not linger indefinitely —
  // reconcile it explicitly once the item it points to stops existing in
  // the active layout (SP-19 final-branch-review fix pass, finding M2).
  useEffect(() => {
    if (selectedId && activeLayout && !activeLayout.items.some((i) => i.id === selectedId)) {
      setSelectedId(null);
    }
  }, [selectedId, activeLayout]);

  if (query.isLoading || itemQuery.isLoading || !extensionsRegistered || (!draft && !query.isError))
    return <p role="status">{t("common.loading")}</p>;
  if (
    query.isError ||
    itemQuery.isError ||
    !draft ||
    !activeLayout ||
    !activePage ||
    !itemQuery.data
  )
    return (
      <p role="alert" className="text-sm text-danger">
        {t("appBuilder.notFound")}
      </p>
    );

  function addWidget(type: string) {
    const def = getWidget(type);
    if (!def || !activePage) return;
    const id = crypto.randomUUID();
    // Functional updater (like setSources/setMessages/… below): a plain
    // `setDraft(newValue)` here would read the `draft` closed over at render
    // time, silently dropping any other setDraft call batched in the same
    // event (e.g. DataSourceSelect's onAdd via DataSourcesEditContext when a
    // newly-added widget is bound to a shared dataset in the same handler).
    setDraft((d) => {
      if (!d) return d;
      const layout = getPageLayout(d, activePage);
      const { x, y } = nextFreePosition(layout.items);
      const item: WidgetItem = {
        id,
        widget: type,
        x,
        y,
        w: def.defaultSize.w,
        h: def.defaultSize.h,
        props: { ...def.defaultProps },
      };
      return setPageLayout(d, activePage, { ...layout, items: [...layout.items, item] });
    });
    setSelectedId(id);
  }

  function removeSelected() {
    if (!selectedId || !activePage) return;
    const id = selectedId;
    setDraft((d) => {
      if (!d) return d;
      const layout = getPageLayout(d, activePage);
      const next = setPageLayout(d, activePage, {
        ...layout,
        items: layout.items.filter((i) => i.id !== id),
      });
      return { ...next, messages: pruneMessagesForIds(next.messages, [id]) };
    });
    setSelectedId(null);
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
    if (!selectedId || !activePage) return;
    // Functional updater — see addWidget's comment: DataSourceSelect fires
    // this (via PropsPanel's onChange) right after DataSourcesEditContext's
    // onAdd in the same handler when binding a new shared dataset, so both
    // setDraft calls land in one React batch.
    setDraft((d) => {
      if (!d) return d;
      const layout = getPageLayout(d, activePage);
      return setPageLayout(d, activePage, {
        ...layout,
        items: layout.items.map((i) => (i.id === selectedId ? { ...i, props } : i)),
      });
    });
  }

  function updateSelectedVisibleWhen(expr: string) {
    if (!selectedId || !activePage) return;
    setDraft((d) => {
      if (!d) return d;
      const layout = getPageLayout(d, activePage);
      return setPageLayout(d, activePage, {
        ...layout,
        items: layout.items.map((i) =>
          i.id === selectedId ? { ...i, visibleWhen: expr || undefined } : i,
        ),
      });
    });
  }

  const setSources = (dataSources: typeof draft.dataSources) =>
    setDraft((d) => (d ? { ...d, dataSources } : d));

  async function promoteSource(id: string) {
    if (!draft) return;
    const source = draft.dataSources.find((s) => s.id === id);
    if (!source || !source.layer) return;
    setPromotingId(id);
    try {
      const item = await createDataset.mutateAsync({
        title: source.layer,
        owner: username ?? "",
        source: "collection",
        collectionId: source.layer,
      });
      setSources(draft.dataSources.map((s) => (s.id === id ? { ...s, datasetId: item.pk } : s)));
    } catch {
      /* surfaced via createDataset.isError */
    } finally {
      setPromotingId(null);
    }
  }

  const setMessages = (messages: typeof draft.messages) =>
    setDraft((d) => (d ? { ...d, messages } : d));

  const setTheme = (theme: typeof draft.theme) => setDraft((d) => (d ? { ...d, theme } : d));

  const setPages = (nextPages: typeof pages) =>
    setDraft((d) => (d ? { ...d, pages: nextPages, layout: nextPages[0]?.layout ?? d.layout } : d));

  const setNavigationMode = (navigationMode: "tabs" | "story") =>
    setDraft((d) => (d ? { ...d, navigationMode } : d));

  const setInteractions = (interactions: "auto" | "manual") =>
    setDraft((d) => (d ? { ...d, interactions } : d));

  const setActivePageOnEnter = (updated: (typeof pages)[number]) =>
    setDraft((d) =>
      d ? { ...d, pages: getPages(d).map((p) => (p.id === updated.id ? updated : p)) } : d,
    );

  const setVariables = (variables: typeof draft.variables) =>
    setDraft((d) => {
      if (!d) return d;
      const before = new Set((d.variables ?? []).map((v) => v.id));
      const after = new Set((variables ?? []).map((v) => v.id));
      const removedIds = [...before].filter((id) => !after.has(id)).map((id) => `var:${id}`);
      return { ...d, variables, messages: pruneMessagesForIds(d.messages, removedIds) };
    });

  function setPrintLayout(printLayout: PrintLayoutConfig | null) {
    setDraft((d) => (d ? { ...d, printLayout } : d));
  }

  const expressionErrors = draft ? getConfigExpressionErrors(draft) : [];

  return (
    <DataSourcesEditProvider onAdd={(source) => setSources([...draft.dataSources, source])}>
      <div className="-m-6 flex flex-1 flex-col overflow-hidden">
        <TriptychLayout
          defaultTabId="canvas"
          browse={{
            id: "structure",
            label: t("appBuilder.structureLabel"),
            content: (
              <div className="flex flex-col gap-1 p-2">
                <p className="mb-1 text-xs font-medium text-ink-2">{t("appBuilder.pagesLabel")}</p>
                <PageManager
                  pages={pages}
                  activePageId={activePage}
                  onChange={setPages}
                  onSelectPage={setActivePageId}
                />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                  {t("appBuilder.widgetsLabel")}
                </p>
                <WidgetPalette onAdd={addWidget} />
              </div>
            ),
          }}
          work={{
            id: "canvas",
            label: t("appBuilder.canvasLabel"),
            content: (
              <div className="flex h-full flex-col overflow-hidden">
                <div className="flex flex-wrap items-center gap-2 border-b border-rule p-2">
                  <Button
                    size="sm"
                    variant={mode === "edit" ? "default" : "outline"}
                    onClick={() => setMode("edit")}
                  >
                    {t("appBuilder.editMode")}
                  </Button>
                  <Button
                    size="sm"
                    variant={mode === "preview" ? "default" : "outline"}
                    onClick={() => setMode("preview")}
                  >
                    {t("appBuilder.previewMode")}
                  </Button>
                  <div className="ml-2 flex items-center gap-1">
                    <Button size="sm" variant="outline" disabled={!canUndo} onClick={undo}>
                      {t("appBuilder.undo")}
                    </Button>
                    <Button size="sm" variant="outline" disabled={!canRedo} onClick={redo}>
                      {t("appBuilder.redo")}
                    </Button>
                  </div>
                  <div className="ml-2 flex items-center gap-1">
                    {BREAKPOINTS.map((bp) => (
                      <Button
                        key={bp}
                        size="sm"
                        variant={breakpoint === bp ? "default" : "outline"}
                        aria-label={t("appBuilder.editBreakpointAria", { bp })}
                        onClick={() => setBreakpoint(bp)}
                      >
                        {bp}
                      </Button>
                    ))}
                  </div>
                  <div className="flex-1" />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={thumbnail.isPending}
                    onClick={() => void captureThumbnail()}
                  >
                    {t("appBuilder.captureThumbnail")}
                  </Button>
                  {thumbnail.isError && (
                    <span role="alert" className="text-sm text-danger">
                      {t("appBuilder.captureError")}
                    </span>
                  )}
                </div>
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
              </div>
            ),
          }}
          inspect={{
            id: "props",
            label: t("appBuilder.propertiesLabel"),
            content: (
              <aside className="flex flex-col gap-1 p-2">
                <p className="mb-1 text-xs font-medium text-ink-2">
                  {t("appBuilder.propertiesLabel")}
                </p>
                <PropsPanel
                  item={selected}
                  dataSources={draft.dataSources}
                  theme={draft.theme}
                  variables={draft.variables ?? []}
                  onChange={updateSelectedProps}
                  onVisibleWhenChange={updateSelectedVisibleWhen}
                />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                  {t("appBuilder.dataSourcesLabel")}
                </p>
                <DataSourcePanel
                  sources={draft.dataSources}
                  onChange={setSources}
                  onPromote={(id) => void promoteSource(id)}
                  promotingId={promotingId}
                />
                {createDataset.isError && (
                  <p role="alert" className="text-xs text-danger">
                    {t("appBuilder.promoteError")}
                  </p>
                )}
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                  {t("appBuilder.actionsLabel")}
                </p>
                <ActionsPanel
                  items={activeLayout.items}
                  variables={draft.variables ?? []}
                  messages={draft.messages}
                  onChange={setMessages}
                />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                  {t("appBuilder.navigationLabel")}
                </p>
                <NavigationPanel
                  navigationMode={draft.navigationMode ?? "tabs"}
                  onNavigationModeChange={setNavigationMode}
                  page={pages.find((p) => p.id === activePage) ?? pages[0]}
                  onPageChange={setActivePageOnEnter}
                />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                  {t("appBuilder.interactionsLabel")}
                </p>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    aria-label={t("appBuilder.autoInteractionsLabel")}
                    checked={draft.interactions === "auto"}
                    onChange={(e) => setInteractions(e.target.checked ? "auto" : "manual")}
                  />
                  {t("appBuilder.autoInteractionsLabel")}
                </label>
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                  {t("appBuilder.variablesLabel")}
                </p>
                <VariablesPanel variables={draft.variables ?? []} onChange={setVariables} />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                  {t("appBuilder.themeLabel")}
                </p>
                <ThemePanel theme={draft.theme} onChange={setTheme} />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                  {t("appBuilder.printLabel")}
                </p>
                <PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
                <div className="mt-3">
                  <ConfigHistoryPanel
                    pk={pk}
                    currentVersion={null}
                    onRestored={async () => {
                      const restored = await client.getAppConfig(pk);
                      // resetDraft, pas setDraft : la pile undo ne peut pas défaire
                      // une écriture serveur (cf. useUndoableDraft.resetDraft).
                      resetDraft(restored);
                    }}
                  />
                </div>
                {appExportEnabled && (
                  <>
                    <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                      {t("appBuilder.exportStandaloneLabel")}
                    </p>
                    <AppExportPanel itemId={pk} config={draft} />
                  </>
                )}
                {copilotEnabled && (
                  <>
                    <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                      {t("appBuilder.copilotLabel")}
                    </p>
                    <CopilotPanel
                      itemId={pk}
                      config={draft}
                      activePageId={activePage}
                      setDraft={setDraft}
                    />
                  </>
                )}
                <div className="mt-3 flex flex-col gap-2 border-t border-rule pt-3">
                  <Button
                    size="sm"
                    className="w-fit"
                    disabled={save.isPending || expressionErrors.length > 0 || readOnly}
                    onClick={() => save.mutate(draft)}
                  >
                    {t("appBuilder.save")}
                  </Button>
                  {readOnly && <p className="text-xs text-ink-2">{t("locked.needWrite")}</p>}
                  {expressionErrors.length > 0 && (
                    <span
                      role="alert"
                      aria-label={t("appBuilder.expressionErrorAria")}
                      className="text-sm text-danger"
                    >
                      {expressionErrors[0]}
                    </span>
                  )}
                  {save.isError && (
                    <span role="alert" className="text-sm text-danger">
                      {t("actions.saveFailed")}
                    </span>
                  )}
                </div>
              </aside>
            ),
          }}
        />
      </div>
    </DataSourcesEditProvider>
  );
}
