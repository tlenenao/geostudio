// SPDX-License-Identifier: Apache-2.0
import { useNavigate } from "react-router-dom";
import { useAppConfig, useItem } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
import { useState, useEffect } from "react";
import { useActiveExtensions } from "../api/hooks";
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";

registerBuiltinWidgets();
registerCounterExampleWidget();
registerCounterWcExampleWidget();

export function AppRuntimePage({ pk, pageId }: { pk: string; pageId?: string }) {
  const itemQuery = useItem(pk);
  const query = useAppConfig(pk, { enabled: itemQuery.isSuccess, mode: "runtime" });
  const navigate = useNavigate();

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
      />
    </div>
  );
}
