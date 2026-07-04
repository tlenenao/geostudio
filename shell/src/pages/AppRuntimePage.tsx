import { useNavigate } from "react-router-dom";
import { useAppConfig, useItem } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";

registerBuiltinWidgets();
registerCounterExampleWidget();

export function AppRuntimePage({ pk, pageId }: { pk: string; pageId?: string }) {
  const itemQuery = useItem(pk);
  const query = useAppConfig(pk, { enabled: itemQuery.isSuccess });
  const navigate = useNavigate();
  if (itemQuery.isLoading || (itemQuery.isSuccess && query.isLoading)) {
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
