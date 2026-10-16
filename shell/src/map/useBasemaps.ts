// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useOptionalItemClient } from "../api/ItemClientProvider";
import { BASEMAPS, type Basemap } from "./basemaps";

/** Fonds intégrés + fonds partagés du tenant (REV-367 i). Sans client (rendu isolé), sans
 * `listTenantBasemaps` (export statique, desktop) ou en cas d'échec : fonds intégrés seuls. */
export function useBasemaps(): Basemap[] {
  const client = useOptionalItemClient();
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
  const known = new Set(BASEMAPS.map((b) => b.style));
  return [...BASEMAPS, ...tenant.filter((b) => !known.has(b.style))];
}
