// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { useDocumentMeta } from "../shell/useDocumentMeta";
import { t } from "../i18n";
import { PublicNotFound } from "./PublicNotFound";
import { LoadingState } from "../ui/kit/LoadingState";

registerBuiltinWidgets();

export function PublicItemPage({ pk }: { pk: string }) {
  const client = useItemClient();
  const itemQuery = useQuery({
    queryKey: ["public-item", pk],
    queryFn: () => client.getItem(pk),
    retry: false,
  });
  const configQuery = useQuery({
    queryKey: ["public-item-config", pk],
    queryFn: () => client.getPublicAppConfig(pk),
    enabled: itemQuery.isSuccess,
    retry: false,
  });

  // Complète (ne remplace pas) le chemin robot rendu côté serveur — utile
  // pour l'onglet navigateur d'un humain et pour Googlebot, même patron que
  // SitePublicPage.tsx (SP-55 §3.4, GAP-07). configQuery est sérialisée
  // derrière itemQuery.isSuccess (comme SitePublicPage.tsx) pour qu'il soit
  // impossible d'afficher le contenu de la config avec un titre/meta encore
  // au repli "GeoStudio" — corrige une fenêtre de titre obsolète trouvée en
  // revue finale de Task 28.
  const notFound =
    itemQuery.isError || configQuery.isError || (configQuery.isSuccess && !configQuery.data);
  useDocumentMeta({
    title: notFound ? t("publicPage.notFound") : (itemQuery.data?.title ?? "GeoStudio"),
    noindex: notFound,
    description: itemQuery.data?.abstract ?? "",
    canonicalUrl: `${window.location.origin}/public/items/${pk}`,
  });

  if (itemQuery.isLoading || (itemQuery.isSuccess && configQuery.isLoading)) {
    return <LoadingState />;
  }
  if (itemQuery.isError || configQuery.isError || !configQuery.data) {
    return <PublicNotFound />;
  }
  return (
    <main className="h-full w-full">
      <AppRenderer config={configQuery.data} mode="runtime" />
    </main>
  );
}
