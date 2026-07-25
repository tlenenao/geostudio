// SPDX-License-Identifier: Apache-2.0
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAppConfig, useItem } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { EXTENT_DEBOUNCE_MS, type AnalyticsContextState } from "../builder/AnalyticsContext";
import { decodeAnalyticsContext, encodeAnalyticsContext } from "../lib/analyticsContextUrl";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
import { useEffect, useMemo, useRef, useState } from "react";
import { useActiveExtensions } from "../api/hooks";
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";

registerBuiltinWidgets();
registerCounterExampleWidget();
registerCounterWcExampleWidget();

export function AppRuntimePage({ pk, pageId }: { pk: string; pageId?: string }) {
  const itemQuery = useItem(pk);
  const query = useAppConfig(pk, { enabled: itemQuery.isSuccess, mode: "runtime" });
  const navigate = useNavigate();

  const [searchParams, setSearchParams] = useSearchParams();
  // Read once at mount ("au montage" per spec) — this component itself
  // writes ?ctx= back, so re-reading on every searchParams change would
  // create a feedback loop.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const initialAnalyticsContext = useMemo(() => decodeAnalyticsContext(searchParams.get("ctx")), []);
  const writeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Toujours écrire via le setSearchParams du dernier rendu : ce setter est lié
  // à la localisation courante, donc il préserve le pathname (ex. le segment
  // :pageId d'une story). Le débounce peut se déclencher après une navigation
  // de page ; sans ce ref, la fermeture capturée au montage réécrirait l'URL
  // relative à l'ancien pathname (avec replace) et ferait « reculer » la page.
  const setSearchParamsRef = useRef(setSearchParams);
  useEffect(() => { setSearchParamsRef.current = setSearchParams; });
  useEffect(() => () => { if (writeTimer.current) clearTimeout(writeTimer.current); }, []);

  function handleAnalyticsContextChange(state: AnalyticsContextState) {
    if (writeTimer.current) clearTimeout(writeTimer.current);
    writeTimer.current = setTimeout(() => {
      setSearchParamsRef.current((prev) => {
        const next = new URLSearchParams(prev);
        next.set("ctx", encodeAnalyticsContext(state));
        return next;
      }, { replace: true });
    }, EXTENT_DEBOUNCE_MS);
  }

  const extensionsQuery = useActiveExtensions();
  const [extensionsRegistered, setExtensionsRegistered] = useState(false);

  useEffect(() => {
    if (extensionsQuery.isLoading) return;
    (extensionsQuery.data ?? []).forEach(registerExtensionWidget);
    setExtensionsRegistered(true);
  }, [extensionsQuery.isLoading, extensionsQuery.data]);

  if (itemQuery.isLoading || (itemQuery.isSuccess && query.isLoading) || !extensionsRegistered) {
    return <p role="status">Chargement…</p>;
  }
  if (itemQuery.isError) {
    return <p role="alert" className="text-sm text-red-600">Accès refusé.</p>;
  }
  if (query.isError || !query.data) {
    return <p role="alert" className="text-sm text-red-600">Application introuvable.</p>;
  }
  return (
    <div className="h-full w-full">
      <AppRenderer
        config={query.data}
        mode="runtime"
        pageId={pageId}
        onNavigate={(nextPageId) => navigate(`/apps/${encodeURIComponent(pk)}/${encodeURIComponent(nextPageId)}`)}
        initialAnalyticsContext={initialAnalyticsContext}
        onAnalyticsContextChange={handleAnalyticsContextChange}
      />
    </div>
  );
}
