// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { useDocumentMeta } from "../shell/useDocumentMeta";
import { t } from "../i18n";
import { PublicNotFound } from "./PublicNotFound";
import { LoadingState } from "../ui/kit/LoadingState";
import "../i18n/domains/misc";

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
  const notFound =
    itemQuery.isError || configQuery.isError || (configQuery.isSuccess && !configQuery.data);
  useDocumentMeta({
    title: notFound ? t("publicPage.notFound") : (itemQuery.data?.title ?? "GeoStudio"),
    noindex: notFound,
    description: itemQuery.data?.abstract ?? "",
    canonicalUrl: itemQuery.isSuccess
      ? `${window.location.origin}/sites/${slug}`
      : window.location.href,
  });

  if (itemQuery.isLoading || (itemQuery.isSuccess && configQuery.isLoading)) {
    return <LoadingState />;
  }
  if (itemQuery.isError || configQuery.isError || !configQuery.data) {
    return <PublicNotFound />;
  }
  return (
    <main className="h-full w-full">
      {/* REV-284(b) : repère de titre pour les technologies d'assistance. */}
      <h1 className="sr-only">{itemQuery.data?.title}</h1>
      <AppRenderer config={configQuery.data} mode="runtime" />
    </main>
  );
}
