// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCollectionsAdmin, useDeleteCollection } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Gate } from "../auth/Gate";
import { Locked } from "../auth/Locked";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { CollectionSharePanel } from "../shell/CollectionSharePanel";
import { EditCollectionPanel } from "../shell/EditCollectionPanel";
import { RegisterCollectionPanel } from "../shell/RegisterCollectionPanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

export function CollectionsAdminPage() {
  const collectionsQuery = useCollectionsAdmin();
  const deleteCollection = useDeleteCollection();
  const [registering, setRegistering] = useState(false);
  const [editing, setEditing] = useState<CollectionAdmin | null>(null);
  const [sharing, setSharing] = useState<CollectionAdmin | null>(null);
  const [deleting, setDeleting] = useState<CollectionAdmin | null>(null);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteCollection.mutateAsync(deleting.id);
      // Croisement entre tâches (revue finale SP-30j) : editing/sharing ne
      // sont plus des Dialog modaux, donc peuvent rester ouverts sur la
      // ligne qu'on vient de supprimer si l'utilisateur clique Supprimer
      // sans les fermer d'abord. Fermer explicitement s'ils pointaient
      // vers l'objet supprimé.
      if (editing?.id === deleting.id) setEditing(null);
      if (sharing?.id === deleting.id) setSharing(null);
      setDeleting(null);
    } catch {
      // surfaced via deleteCollection.isError
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
          id: "collections",
          label: "Collections",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h1 className="text-lg font-bold text-ink">Collections</h1>
                <Button
                  size="sm"
                  onClick={() => {
                    // Exclusivité mutuelle avec editing/sharing (décision 5,
                    // plan SP-30j) : plus de barrière modale pour l'empêcher.
                    setEditing(null);
                    setSharing(null);
                    setRegistering(true);
                  }}
                >
                  Enregistrer une table
                </Button>
              </div>
              {collectionsQuery.isLoading && <p role="status">Chargement…</p>}
              {collectionsQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec du chargement des collections.
                </p>
              )}
              {deleteCollection.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de la suppression.
                </p>
              )}
              {collectionsQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">Titre</th>
                      <th className="py-2 text-ink">Table</th>
                      <th className="py-2 text-ink">Public</th>
                      <th className="py-2 text-ink">Éditable</th>
                      <th className="py-2 text-ink">Entités</th>
                      <th className="py-2 text-ink">Propriétaire</th>
                      <th className="py-2 text-ink">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {collectionsQuery.data.map((col) => (
                      <tr key={col.id} className="border-b border-rule-2">
                        <td className="py-2 text-ink">{col.title}</td>
                        <td className="py-2 text-xs text-ink-2">{col.tableName}</td>
                        <td className="py-2 text-ink">{col.isPublic ? "Oui" : "Non"}</td>
                        <td className="py-2 text-ink">{col.editable ? "Oui" : "Non"}</td>
                        <td className="py-2 text-ink">{col.featureCount ?? "—"}</td>
                        <td className="py-2 text-ink">{col.owner ?? "—"}</td>
                        <td className="py-2 flex gap-2">
                          {/* SP-42/F-securite-autorisation-06 : le cœur refuse
                              PATCH/sharing sur can()/decide() (write/share),
                              jamais reflété par can_manage_collections seul
                              (qui n'ouvre que la visibilité de la liste) —
                              proposer ces boutons sans condition produisait
                              un 403 au clic pour un porteur non-propriétaire
                              de admin.collections.manage. */}
                          <Gate
                            on={col}
                            can="write"
                            fallback={
                              <Locked reason={t("locked.needWrite")}>
                                <Button type="button" variant="outline" size="sm">
                                  Éditer
                                </Button>
                              </Locked>
                            }
                          >
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setRegistering(false);
                                setSharing(null);
                                setEditing(col);
                              }}
                            >
                              Éditer
                            </Button>
                          </Gate>
                          <Gate
                            on={col}
                            can="share"
                            fallback={
                              <Locked reason={t("locked.needShare")}>
                                <Button type="button" variant="outline" size="sm">
                                  Partager
                                </Button>
                              </Locked>
                            }
                          >
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setRegistering(false);
                                setEditing(null);
                                setSharing(col);
                              }}
                            >
                              Partager
                            </Button>
                          </Gate>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => setDeleting(col)}
                          >
                            Supprimer
                          </Button>
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
              {registering && <RegisterCollectionPanel onClose={() => setRegistering(false)} />}
              {editing && (
                <EditCollectionPanel
                  key={editing.id}
                  collection={editing}
                  onClose={() => setEditing(null)}
                />
              )}
              {sharing && (
                <CollectionSharePanel
                  key={sharing.id}
                  collectionId={sharing.id}
                  onClose={() => setSharing(null)}
                />
              )}
            </div>
          ),
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        title="Supprimer la collection"
        message={
          deleting
            ? `Désenregistrer « ${deleting.title} » ? La table PostGIS ne sera pas supprimée.`
            : ""
        }
        confirmLabel="Supprimer"
        pending={deleteCollection.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
