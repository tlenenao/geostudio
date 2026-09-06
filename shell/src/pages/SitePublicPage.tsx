// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { useDocumentMeta } from "../shell/useDocumentMeta";

registerBuiltinWidgets();

export function SitePublicPage({ slug }: { slug: string }) {
  const client = useItemClient();
  const itemQuery = useQuery({
    queryKey: ["public-site", slug],
    queryFn: () => client.getItemBySlug(slug),
    retry: false,
  });
  const configQuery = useQuery({
    queryKey: ["public-site-config", itemQuery.data?.pk],
    queryFn: () => client.getPublicAppConfig(itemQuery.data!.pk),
    enabled: itemQuery.isSuccess,
    retry: false,
  });

  // Complète (ne remplace pas) le chemin robot rendu côté serveur
  // (core/app/public/routes.py, SP-55 Tâches 7/8) — utile pour l'onglet
  // navigateur d'un humain et pour Googlebot (exécute le JS avant
  // indexation). Undefined tant que l'item n'est pas chargé : useDocumentMeta
  // n'est appelé qu'une fois les deux valeurs connues (règle des Hooks —
  // pas d'appel conditionnel), donc gardé par `itemQuery.isSuccess` via une
  // valeur de repli plutôt qu'un retour anticipé.
  useDocumentMeta({
    title: itemQuery.data?.title ?? "GeoStudio",
    description: itemQuery.data?.abstract ?? "",
    canonicalUrl: itemQuery.isSuccess
      ? `${window.location.origin}/sites/${slug}`
      : window.location.href,
  });

  if (itemQuery.isLoading || (itemQuery.isSuccess && configQuery.isLoading)) {
    return <p role="status">Chargement…</p>;
  }
  if (itemQuery.isError || configQuery.isError || !configQuery.data) {
    return (
      <div className="p-8 text-center">
        <p role="alert" className="text-sm text-slate-600">
          Page introuvable.
        </p>
      </div>
    );
  }
  return (
    <div className="h-full w-full">
      <AppRenderer config={configQuery.data} mode="runtime" />
    </div>
  );
}
