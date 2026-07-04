import { useNavigate } from "react-router-dom";
import { useAppConfig } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";

registerBuiltinWidgets();

export function AppRuntimePage({ pk, pageId }: { pk: string; pageId?: string }) {
  const query = useAppConfig(pk);
  const navigate = useNavigate();
  if (query.isLoading) return <p role="status">Chargement…</p>;
  if (query.isError || !query.data)
    return <p role="alert" className="text-sm text-red-600">Application introuvable.</p>;
  return (
    <div className="h-full w-full">
      <AppRenderer
        config={query.data}
        mode="runtime"
        pageId={pageId}
        onNavigate={(nextPageId) => navigate(`/apps/${pk}/${nextPageId}`)}
      />
    </div>
  );
}
