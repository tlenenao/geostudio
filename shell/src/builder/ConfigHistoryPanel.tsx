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
import { useCallback, useEffect, useState } from "react";
import { useItemClient } from "../api/ItemClientProvider";
import type { ConfigRevisionInfo } from "../api/types";
import { Button } from "../ui/button";

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
    if (
      !window.confirm(
        `Restaurer la version ${version} ? Les modifications non enregistrées seront perdues.`,
      )
    )
      return;
    setBusy(true);
    setRestoreError(false);
    try {
      await client.rollbackConfig(pk, version);
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
      <h3 className="text-sm font-medium">Historique</h3>
      {loadError && (
        <p role="alert" className="text-sm text-red-600">
          Impossible de charger l'historique des versions.
        </p>
      )}
      {restoreError && (
        <p role="alert" className="text-sm text-red-600">
          Impossible de restaurer cette version.
        </p>
      )}
      {!loadError && revisions !== null && revisions.length === 0 && (
        <p className="text-sm text-slate-500">Aucune version enregistrée.</p>
      )}
      <ul className="flex flex-col gap-1">
        {(revisions ?? []).map((r) => (
          <li key={r.version} className="flex items-center gap-2 text-sm">
            <span>
              Version {r.version} — {formatDate(r.createdAt)}
            </span>
            {r.version === current ? (
              <span className="text-xs text-slate-500">(courante)</span>
            ) : (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => void restore(r.version)}
              >
                Restaurer
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
