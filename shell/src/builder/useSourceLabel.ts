// SPDX-License-Identifier: Apache-2.0
import { useCollectionsAdmin, useItems } from "../api/hooks";
import type { DataSource } from "../api/types";

// P10.13 : libellé lisible d'une source de données — titre de la collection ou du
// dataset plutôt que son identifiant technique (ex. query_0edaceaa9d3b).
// `enabled` : la résolution n'interroge le cœur que dans l'éditeur.
export function useSourceLabel(enabled: boolean): (s: DataSource) => string {
  const collections = useCollectionsAdmin({ limit: 200, enabled });
  const datasets = useItems({ type: "dataset", pageSize: 100 }, { enabled });
  const titles = new Map<string, string>();
  for (const c of collections.data ?? []) titles.set(c.id, c.title);
  const datasetTitles = new Map((datasets.data?.items ?? []).map((d) => [d.pk, d.title]));
  return (s) =>
    (s.datasetId && datasetTitles.get(s.datasetId)) || titles.get(s.layer) || s.layer || s.id;
}
