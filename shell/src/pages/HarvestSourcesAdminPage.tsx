// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useDeleteHarvestSource,
  useHarvestSources,
  useInstanceInfo,
  useRunHarvestSource,
} from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { CreateHarvestSourcePanel } from "../shell/CreateHarvestSourcePanel";
import { EditHarvestSourcePanel } from "../shell/EditHarvestSourcePanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

export function HarvestSourcesAdminPage() {
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const sourcesQuery = useHarvestSources();
  const deleteSource = useDeleteHarvestSource();
  const runSource = useRunHarvestSource();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<HarvestSource | null>(null);
  const [deleting, setDeleting] = useState<HarvestSource | null>(null);
  const createPanel = usePanelTrigger(creating);
  const editPanel = usePanelTrigger(editing !== null);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteSource.mutateAsync(deleting.id);
      // Croisement entre tâches (revue finale SP-30j) : editing n'est plus
      // un Dialog modal, donc peut rester ouvert sur la ligne qu'on vient de
      // supprimer si l'utilisateur clique Supprimer sans le fermer d'abord.
      // Fermer explicitement s'il pointait vers l'objet supprimé.
      if (editing?.id === deleting.id) setEditing(null);
      setDeleting(null);
    } catch {
      // surfaced via deleteSource.isError
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "sources",
          label: "Moissonnage",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h1 className="text-lg font-bold text-ink">Moissonnage</h1>
                {!readOnly && (
                  <Button
                    size="sm"
                    {...createPanel.triggerProps}
                    onClick={() => {
                      // Exclusivité mutuelle avec editing (décision 5, plan
                      // SP-30j) : plus de barrière modale pour l'empêcher.
                      setEditing(null);
                      setCreating(true);
                    }}
                  >
                    Ajouter une source
                  </Button>
                )}
              </div>
              {sourcesQuery.isLoading && <p role="status">Chargement…</p>}
              {sourcesQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec du chargement des sources.
                </p>
              )}
              {deleteSource.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de la suppression.
                </p>
              )}
              {sourcesQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">Type</th>
                      <th className="py-2 text-ink">URL</th>
                      <th className="py-2 text-ink">Mode</th>
                      <th className="py-2 text-ink">Actif</th>
                      <th className="py-2 text-ink">Dernier statut</th>
                      <th className="py-2 text-ink">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sourcesQuery.data.map((source) => (
                      <tr key={source.id} className="border-b border-rule-2">
                        <td className="py-2 text-ink">{source.type}</td>
                        <td className="py-2 text-xs text-ink-2">{source.url}</td>
                        <td className="py-2 text-ink">{source.mode}</td>
                        <td className="py-2 text-ink">{source.enabled ? "Oui" : "Non"}</td>
                        <td className="py-2 text-ink">{source.lastStatus ?? "—"}</td>
                        <td className="py-2 flex gap-2">
                          {!readOnly && (
                            <>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => runSource.mutate(source.id)}
                              >
                                Moissonner maintenant
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                aria-controls={editPanel.panelId}
                                aria-expanded={editing?.id === source.id}
                                onClick={() => {
                                  setCreating(false);
                                  setEditing(source);
                                }}
                              >
                                Éditer
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setDeleting(source)}
                              >
                                Supprimer
                              </Button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "detail",
          label: "Détail",
          content: (
            <div className="flex flex-col gap-3 p-3">
              {/* id seul (pas role="region" du hook) : CreateHarvestSourcePanel/
                  EditHarvestSourcePanel rendent déjà un <section aria-label=…>,
                  donc une région implicite nommée — cf. même correction sur
                  CollectionsAdminPage. */}
              {creating && (
                <div id={createPanel.panelId}>
                  <CreateHarvestSourcePanel onClose={() => setCreating(false)} />
                </div>
              )}
              {editing && (
                <div id={editPanel.panelId}>
                  <EditHarvestSourcePanel
                    key={editing.id}
                    source={editing}
                    onClose={() => setEditing(null)}
                  />
                </div>
              )}
            </div>
          ),
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        title="Supprimer la source"
        message={
          deleting
            ? `Supprimer la source « ${deleting.url} » ? Les items/collections déjà produits survivent.`
            : ""
        }
        confirmLabel="Supprimer"
        pending={deleteSource.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
