// SPDX-License-Identifier: Apache-2.0
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAppConfig } from "../api/hooks";
import { loadConfig } from "../config";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerExampleWidgets } from "../builder/examples";
import { resolveShareLink } from "./embed/resolveShareLink";
import { t } from "../i18n";
import { LoadingState } from "../ui/kit/LoadingState";

registerBuiltinWidgets();
registerExampleWidgets();

// EmbedPage est monté hors `<ProtectedLayout>` (route publique `/embed/:token`,
// cf. shell/src/shell/routes.tsx) : ce module n'a donc jamais accès à
// l'AuthProvider/getAccessToken du shell authentifié. loadConfig() est déjà
// appelé (et sa validation déjà passée) au chargement du module racine
// App.tsx avant que cette route lazy() ne soit jamais atteinte — cet appel
// séparé ne fait que relire les mêmes variables d'environnement déjà
// disponibles pour le bundle entier, sans dépendance à un état d'auth.
const runtimeEnv = (window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> })
  .__GEOSTUDIO_ENV__;
const embedConfig = loadConfig(
  import.meta.env as unknown as Record<string, string | undefined>,
  runtimeEnv,
);

const EMBEDDABLE_RESOURCE_TYPES = new Set(["app", "dashboard"]);

function EmbedApp({ itemId, token }: { itemId: string; token: string }) {
  // Client dédié à l'embed, jamais partagé avec l'ItemClient du shell
  // authentifié : `getToken` renvoie toujours `undefined` — aucune
  // requête émise par ce client ne doit jamais porter d'en-tête
  // Authorization, seulement X-Share-Link-Token (cf. createBase()).
  const client = useMemo(
    () =>
      createItemClient({
        coreUrl: embedConfig.coreUrl,
        getToken: () => undefined,
        getShareLinkToken: () => token,
      }),
    [token],
  );
  return (
    <ItemClientProvider client={client}>
      <EmbedAppRenderer itemId={itemId} />
    </ItemClientProvider>
  );
}

function EmbedAppRenderer({ itemId }: { itemId: string }) {
  const query = useAppConfig(itemId, { mode: "runtime" });
  if (query.isLoading) {
    return <LoadingState />;
  }
  if (query.isError || !query.data) {
    return (
      <p role="alert" className="text-sm text-danger">
        {t("appRuntime.notFound")}
      </p>
    );
  }
  return (
    <main className="h-screen w-screen">
      <AppRenderer config={query.data} mode="runtime" />
    </main>
  );
}

export function EmbedPage({ token }: { token: string }) {
  const linkQuery = useQuery({
    queryKey: ["embed-share-link", token],
    queryFn: () => resolveShareLink(embedConfig.coreUrl, token),
    retry: false,
  });

  if (linkQuery.isLoading) {
    return <LoadingState />;
  }
  if (linkQuery.isError || !linkQuery.data) {
    return (
      <p role="alert" className="p-4 text-sm text-danger">
        {t("embed.linkExpiredOrRevoked")}
      </p>
    );
  }
  if (!EMBEDDABLE_RESOURCE_TYPES.has(linkQuery.data.resourceType)) {
    return (
      <p role="alert" className="p-4 text-sm text-danger">
        {t("embed.notEmbeddable")}
      </p>
    );
  }
  return <EmbedApp itemId={linkQuery.data.itemId} token={token} />;
}
