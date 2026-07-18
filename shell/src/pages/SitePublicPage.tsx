// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";

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

  if (itemQuery.isLoading || (itemQuery.isSuccess && configQuery.isLoading)) {
    return <p role="status">Chargement…</p>;
  }
  if (itemQuery.isError || configQuery.isError || !configQuery.data) {
    return (
      <div className="p-8 text-center">
        <p role="alert" className="text-sm text-slate-600">Page introuvable.</p>
      </div>
    );
  }
  return (
    <div className="h-full w-full">
      <AppRenderer config={configQuery.data} mode="runtime" />
    </div>
  );
}
