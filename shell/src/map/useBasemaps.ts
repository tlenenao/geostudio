// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useOptionalItemClient } from "../api/ItemClientProvider";
import { BASEMAPS, allowedBasemaps, type Basemap } from "./basemaps";

/** AUD-122 : l'instance autorise-t-elle les fonds tiers ? Sans client, sans réponse ou champ
 * absent : oui (comportement historique). ponytail: `true` jusqu'à la réponse de /instance —
 * un widget sans fond configuré peut tenter un fond tiers une fois ; les cartes créées
 * (createMapItem, import) portent déjà le bon fond, choisi côté requête. */
export function useExternalBasemapsEnabled(): boolean {
  const client = useOptionalItemClient();
  const [enabled, setEnabled] = useState(true);
  useEffect(() => {
    let cancelled = false;
    if (!client?.getInstanceInfo) return;
    client
      .getInstanceInfo()
      .then((info) => {
        if (!cancelled) setEnabled(info.externalBasemapsEnabled !== false);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [client]);
  return enabled;
}

/** Fonds intégrés autorisés + fonds partagés du tenant (REV-367 i, déclarés par un admin :
 * jamais filtrés). Sans client, sans `listTenantBasemaps` ou en cas d'échec : intégrés seuls. */
export function useBasemaps(): Basemap[] {
  const client = useOptionalItemClient();
  const external = useExternalBasemapsEnabled();
  const [tenant, setTenant] = useState<Basemap[]>([]);
  useEffect(() => {
    let cancelled = false;
    const load = client?.listTenantBasemaps;
    if (!load) return;
    load
      .call(client)
      .then((rows) => {
        if (!cancelled) setTenant(rows.map((r) => ({ ...r, id: `tenant-${r.id}` })));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [client]);
  const builtIn = allowedBasemaps(BASEMAPS, external);
  const known = new Set(builtIn.map((b) => b.style));
  return [...builtIn, ...tenant.filter((b) => !known.has(b.style))];
}
