// SPDX-License-Identifier: Apache-2.0
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAppConfig, useInstanceInfo, useItem } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { EXTENT_DEBOUNCE_MS, type AnalyticsContextState } from "../builder/AnalyticsContext";
import { getPageLayout } from "../builder/pages";
import type { MapLayer } from "../api/types";
import { decodeAnalyticsContext, encodeAnalyticsContext } from "../lib/analyticsContextUrl";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
import { useEffect, useMemo, useRef, useState } from "react";
import { useActiveExtensions, useCreateBookmark } from "../api/hooks";
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";
import { ApiError } from "../api/ApiError";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/kit/Button";
import { Dialog } from "../ui/kit/Dialog";
import { Input } from "../ui/kit/Input";
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";
import { ExportPanel } from "../builder/print/ExportPanel";
import { t } from "../i18n";

registerBuiltinWidgets();
registerCounterExampleWidget();
registerCounterWcExampleWidget();

export function AppRuntimePage({ pk, pageId }: { pk: string; pageId?: string }) {
  // P07.03 : la route /apps/:pk est hors RequireAuth (lecture publique
  // possible) ; au rechargement le jeton OIDC n'est pas encore là. On
  // attend l'auth avant toute requête, puis un 401 sans session mène à la
  // connexion (returnTo conservé) au lieu de « Accès refusé ».
  const { username, isLoading: authLoading, isAuthenticated, signIn } = useAuth();
  const itemQuery = useItem(pk, { enabled: !authLoading });
  const needsSignIn =
    !authLoading &&
    !isAuthenticated &&
    itemQuery.error instanceof ApiError &&
    itemQuery.error.status === 401;
  useEffect(() => {
    if (needsSignIn) signIn();
  }, [needsSignIn, signIn]);
  const query = useAppConfig(pk, { enabled: itemQuery.isSuccess, mode: "runtime" });
  const navigate = useNavigate();
  const isExportRender = useIsExportRender();
  const instanceQuery = useInstanceInfo();
  const exportEnabled = instanceQuery.data?.exportEnabled === true;

  const extensionsQuery = useActiveExtensions();
  const [extensionsRegistered, setExtensionsRegistered] = useState(false);

  useEffect(() => {
    if (extensionsQuery.isLoading) return;
    (extensionsQuery.data ?? []).forEach(registerExtensionWidget);
    setExtensionsRegistered(true);
  }, [extensionsQuery.isLoading, extensionsQuery.data]);

  // Export/print chrome (SP-17a Task 10): the Playwright worker (Task 6)
  // navigates here with ?exportRender=1. Non-map apps/dashboards have no
  // per-widget "fully rendered" signal yet (out of SP-17a scope, documented
  // limitation) — the best real signal available is "the config request
  // succeeded" plus one paint frame, not a fixed timer. `extensionsRegistered`
  // must also be true (fix round, finding I3): without it, the page can still
  // be showing the "Chargement…" spinner below (gated on the same flag) while
  // query.isSuccess alone would already fire the ready signal — the worker
  // would then capture a spinner, not the rendered app.
  useEffect(() => {
    if (isExportRender && query.isSuccess && extensionsRegistered) {
      requestAnimationFrame(() => markExportReady());
    }
  }, [isExportRender, query.isSuccess, extensionsRegistered]);

  const [searchParams, setSearchParams] = useSearchParams();
  // Read once at mount ("au montage" per spec) — this component itself
  // writes ?ctx= back, so re-reading on every searchParams change would
  // create a feedback loop. Le disable ci-dessous vise le tableau de
  // dépendances (ESLint y rapporte le problème, pas sur la ligne
  // `useMemo(` elle-même — `eslint-disable-next-line` posé plus haut ne le
  // couvrait pas réellement, jamais remarqué avant le premier vrai passage
  // d'ESLint sur ce fichier, SP-22 Task 3).
  const initialAnalyticsContext = useMemo(
    () => decodeAnalyticsContext(searchParams.get("ctx")),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  const writeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Toujours écrire via le setSearchParams du dernier rendu : ce setter est lié
  // à la localisation courante, donc il préserve le pathname (ex. le segment
  // :pageId d'une story). Le débounce peut se déclencher après une navigation
  // de page ; sans ce ref, la fermeture capturée au montage réécrirait l'URL
  // relative à l'ancien pathname (avec replace) et ferait « reculer » la page.
  const setSearchParamsRef = useRef(setSearchParams);
  useEffect(() => {
    setSearchParamsRef.current = setSearchParams;
  });
  useEffect(
    () => () => {
      if (writeTimer.current) clearTimeout(writeTimer.current);
    },
    [],
  );

  function handleAnalyticsContextChange(state: AnalyticsContextState) {
    // Additivité (contrainte globale #1) : une app sans interactions="auto"
    // (absent ou "manual") ne doit jamais gagner de ?ctx= dans l'URL — même le
    // contexte vide émis au montage par AnalyticsContextProvider. On ignore
    // silencieusement tout changement tant que le mode auto n'est pas actif ;
    // ne pas planifier le debounce du tout (pas seulement l'écriture finale),
    // pour ne laisser aucune trace d'un timer en attente.
    if (query.data?.interactions !== "auto") return;
    if (writeTimer.current) clearTimeout(writeTimer.current);
    writeTimer.current = setTimeout(() => {
      setSearchParamsRef.current(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("ctx", encodeAnalyticsContext(state));
          return next;
        },
        { replace: true },
      );
    }, EXTENT_DEBOUNCE_MS);
  }

  const [currentAnalyticsContext, setCurrentAnalyticsContext] =
    useState<AnalyticsContextState>(initialAnalyticsContext);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [viewTitle, setViewTitle] = useState("");
  const createBookmark = useCreateBookmark();

  function handleAnalyticsContextChangeAndTrack(state: AnalyticsContextState) {
    setCurrentAnalyticsContext(state);
    handleAnalyticsContextChange(state);
  }

  async function saveView() {
    const title = viewTitle.trim();
    if (!title) return;
    try {
      await createBookmark.mutateAsync({
        title,
        owner: username ?? "",
        appId: pk,
        pageId: pageId ?? query.data?.pages?.[0]?.id ?? "",
        ...currentAnalyticsContext,
      });
      setSaveDialogOpen(false);
      setViewTitle("");
      createBookmark.reset();
    } catch {
      // surfaced via createBookmark.isError
    }
  }

  if (
    authLoading ||
    needsSignIn ||
    itemQuery.isLoading ||
    (itemQuery.isSuccess && query.isLoading) ||
    !extensionsRegistered
  ) {
    return <p role="status">{t("common.loading")}</p>;
  }
  if (itemQuery.isError) {
    return (
      <p role="alert" className="text-sm text-danger">
        {t("appRuntime.accessDenied")}
      </p>
    );
  }
  if (query.isError || !query.data) {
    return (
      <p role="alert" className="text-sm text-danger">
        {t("appRuntime.notFound")}
      </p>
    );
  }
  // Fix round (finding I1): the export bar/button must show whenever
  // exportEnabled is true, regardless of interactions === "auto" — that flag
  // is an unrelated save-view/cross-filter feature and defaults to
  // absent/"manual", which previously trapped ExportPanel inside a condition
  // that hid it on most apps/dashboards. The interactions-gated "Enregistrer
  // la vue" button keeps its own independent gate.
  const showActionBar = !isExportRender && (exportEnabled || query.data.interactions === "auto");
  // Finition SP-B12/D14 (cf. plan SP-C3) : une app/dashboard n'a pas de
  // `layers` de premier niveau comme MapConfig — ses couches vivent dans les
  // widgets "map" de la page actuellement affichée. `pageId` est absent sur
  // la route racine `/apps/:pk` (config mono-page) : dans ce cas
  // `query.data.layout` EST déjà la page unique (invariant documenté dans
  // builder/pages.ts).
  const legendLayout = pageId ? getPageLayout(query.data, pageId) : query.data.layout;
  const legendLayers: MapLayer[] = legendLayout.items
    .filter((item) => item.widget === "map")
    .flatMap((item) => (item.props.layers as MapLayer[] | undefined) ?? [])
    .filter((layer) => layer.visible);
  return (
    <div className="relative flex h-full w-full flex-col">
      {showActionBar && (
        <div className="flex justify-end gap-2 border-b border-rule p-2">
          {exportEnabled && <ExportPanel itemId={pk} />}
          {query.data.interactions === "auto" && (
            <Button size="sm" variant="outline" onClick={() => setSaveDialogOpen(true)}>
              {t("appRuntime.saveView")}
            </Button>
          )}
        </div>
      )}
      <div className="min-h-0 flex-1">
        <AppRenderer
          config={query.data}
          mode="runtime"
          pageId={pageId}
          onNavigate={(nextPageId) =>
            navigate(`/apps/${encodeURIComponent(pk)}/${encodeURIComponent(nextPageId)}`)
          }
          initialAnalyticsContext={initialAnalyticsContext}
          onAnalyticsContextChange={handleAnalyticsContextChangeAndTrack}
        />
      </div>
      {/* Export/print chrome (fix round, finding I4): mirrors MapEditorPage's
          title/cartouche overlay markup so PrintLayout authoring isn't
          silently dropped for app/dashboard exports. showScaleBar/
          showNorthArrow were removed entirely from the schema (REV-128) —
          never rendered, authorable-but-inert either way.
          gs-raw-color-ok: bg-white/90 stays hardcoded here on purpose, same rationale as
          MapEditorPage (SP-B12a grounding): a print artifact meant to look
          like paper, not UI chrome — it must stay light regardless of
          ambiance, so it is deliberately NOT a --gs-* token. */}
      {isExportRender && query.data.printLayout?.title && (
        // gs-raw-color-ok: bg-white/90, cf. commentaire plus haut
        <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-sm font-medium">
          {query.data.printLayout.title}
        </div>
      )}
      {isExportRender && query.data.printLayout?.showLegend && legendLayers.length > 0 && (
        // gs-raw-color-ok: bg-white/90, cf. commentaire plus haut
        <ul className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs">
          {legendLayers.map((layer) => (
            <li key={layer.id}>{layer.title}</li>
          ))}
        </ul>
      )}
      {isExportRender && query.data.printLayout?.cartouche && (
        // gs-raw-color-ok: bg-white/90, cf. commentaire plus haut
        <div className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs">
          {query.data.printLayout.cartouche}
        </div>
      )}
      <Dialog
        open={saveDialogOpen}
        onOpenChange={setSaveDialogOpen}
        title={t("appRuntime.saveView")}
      >
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t("appRuntime.viewNameLabel")}
            <Input
              aria-label={t("appRuntime.viewNameLabel")}
              value={viewTitle}
              onChange={(e) => setViewTitle(e.target.value)}
            />
          </label>
          {createBookmark.isError && (
            <p role="alert" className="text-sm text-danger">
              {t("actions.saveFailed")}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setSaveDialogOpen(false)}
            >
              {t("confirmDialog.cancel")}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={createBookmark.isPending || !viewTitle.trim()}
              onClick={() => void saveView()}
            >
              {t("common.save")}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
