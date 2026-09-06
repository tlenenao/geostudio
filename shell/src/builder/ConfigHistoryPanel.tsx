// SPDX-License-Identifier: Apache-2.0
// Panneau « Historique » générique (SP-23, chantier 4.18). Les configs
// versionnées et POST /configs/{id}/rollback existent depuis SP-0 et
// n'avaient aucun appelant côté shell. Un seul composant sert les cinq
// éditeurs adossés à une config (app/dashboard/site, carte, dataset,
// pipeline, rapport) : la route serveur est générique, le coût marginal par
// éditeur est le point de montage seul.
//
// Pas de sondage, contrairement à PipelineRunPanel/ReportRunPanel : un
// historique de versions ne bouge que quand CET utilisateur enregistre ou
// restaure. On charge au montage et après chaque restauration.
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useItemClient } from "../api/ItemClientProvider";
import type { ConfigRevisionInfo } from "../api/types";
import { t } from "../i18n";
import { Button } from "../ui/kit/Button";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fr-FR");
}

export function ConfigHistoryPanel({
  pk,
  currentVersion,
  onRestored,
}: {
  pk: string;
  currentVersion: number | null;
  onRestored: () => void | Promise<void>;
}) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  const [revisions, setRevisions] = useState<ConfigRevisionInfo[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [restoreError, setRestoreError] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const rows = await client.listConfigRevisions(pk);
      // Plus récente en tête. Le serveur trie par version croissante.
      setRevisions([...rows].sort((a, b) => b.version - a.version));
      setLoadError(false);
    } catch {
      // Sans cet état, un historique vide pour cause de panne réseau serait
      // indiscernable d'un « aucune version » légitime (même défaut corrigé
      // en revue sur SP-16b puis SP-17b).
      setLoadError(true);
    }
  }, [client, pk]);

  useEffect(() => {
    void load();
  }, [load]);

  const latest = revisions?.[0]?.version ?? null;
  const current = currentVersion ?? latest;

  async function restore(version: number) {
    // Confirmation systématique, sans chercher à savoir si le brouillon est
    // modifié : aucun des cinq éditeurs ne porte de drapeau « sale », et une
    // confirmation n'est jamais fausse devant une écriture serveur
    // (spec SP-23 §3.4).
    if (!window.confirm(t("configHistory.confirmMessage", { version }))) return;
    setBusy(true);
    setRestoreError(false);
    try {
      await client.rollbackConfig(pk, version);
      // Une restauration est une écriture, et toute écriture de ce dépôt
      // invalide la clé de requête de sa config (useSaveApp/useSaveMap/
      // useSaveDataset/useSavePipeline). Sans ça, le cache garde le contenu
      // d'avant le rollback : le premier refetch (staleTime: 0 et
      // refetchOnWindowFocus par défaut, App.tsx) ramène alors un contenu
      // différent, donc une nouvelle référence, et réécrase le brouillon sur
      // les éditeurs dont l'effet de seed est inconditionnel.
      //
      // L'invalidation est portée ici plutôt que dans les cinq pages : leurs
      // clés diffèrent (["app", pk, mode], ["map", pk], ["dataset", pk],
      // ["pipeline", pk], ["report-schedule", pk]), et un prédicat sur le pk
      // les couvre toutes — y compris un sixième éditeur futur — sans liste à
      // tenir synchronisée. Tout ce qui est mis en cache pour CET item est de
      // fait périmé par la restauration. `void`, comme les mutations de
      // hooks.ts : un refetch en échec ne doit pas se faire passer pour un
      // échec de restauration.
      void queryClient.invalidateQueries({ predicate: (q) => q.queryKey.includes(pk) });
      await load();
      await onRestored();
    } catch {
      setRestoreError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">{t("configHistory.heading")}</h3>
      {loadError && (
        <p role="alert" className="text-sm text-danger">
          {t("configHistory.loadError")}
        </p>
      )}
      {restoreError && (
        <p role="alert" className="text-sm text-danger">
          {t("configHistory.restoreError")}
        </p>
      )}
      {!loadError && revisions !== null && revisions.length === 0 && (
        <p className="text-sm text-ink-2">{t("configHistory.empty")}</p>
      )}
      <ul className="flex flex-col gap-1">
        {(revisions ?? []).map((r) => (
          <li key={r.version} className="flex items-center gap-2 text-sm">
            <span>
              {t("configHistory.versionLabel", {
                version: r.version,
                date: formatDate(r.createdAt),
              })}
            </span>
            {r.version === current ? (
              <span className="text-xs text-ink-2">{t("configHistory.currentLabel")}</span>
            ) : (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => void restore(r.version)}
              >
                {t("configHistory.restoreButton")}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
