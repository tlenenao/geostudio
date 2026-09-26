// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { LoadingState } from "../ui/kit/LoadingState";

registerBuiltinWidgets();

export function PublicItemPage({ pk }: { pk: string }) {
  const client = useItemClient();
  const configQuery = useQuery({
    queryKey: ["public-item-config", pk],
    queryFn: () => client.getPublicAppConfig(pk),
    retry: false,
  });

  if (configQuery.isLoading) {
    return <LoadingState />;
  }
  if (configQuery.isError || !configQuery.data) {
    return (
      <div className="p-8 text-center">
        <p role="alert" className="text-sm text-ink-2">
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
