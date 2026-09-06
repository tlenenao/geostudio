// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCollectionsAdmin, useDeleteCollection, useInstanceInfo } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Gate } from "../auth/Gate";
import { Locked } from "../auth/Locked";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { CollectionSharePanel } from "../shell/CollectionSharePanel";
import { EditCollectionPanel } from "../shell/EditCollectionPanel";
import { RegisterCollectionPanel } from "../shell/RegisterCollectionPanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

// GET /collections pagine déjà côté cœur (limit/offset, SP-50) mais tronquait
// silencieusement au-delà de sa limite par défaut (100) sans exposer de
// contrôle ici — REV pagination, correctif shell.
const PAGE_SIZE = 100;

export function CollectionsAdminPage() {
  // REV-089 : doctrine tranchée (backlog, 2026-09-06) — toujours masquer les
  // actions mutantes sous !readOnly en mode démo publique, comme
  // HarvestSourcesAdminPage le fait déjà. S'ajoute aux gardes Gate can="write"/
  // can="share" existantes (permission par objet), ne les remplace pas :
  // readOnly est un interrupteur d'instance, indépendant des permissions par
  // collection.
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const collectionsQuery = useCollectionsAdmin({ q, limit });
  const deleteCollection = useDeleteCollection();
  const [registering, setRegistering] = useState(false);
  const [editing, setEditing] = useState<CollectionAdmin | null>(null);
  const [sharing, setSharing] = useState<CollectionAdmin | null>(null);
  const [deleting, setDeleting] = useState<CollectionAdmin | null>(null);
  const editPanel = usePanelTrigger(editing !== null);
  const sharingPanel = usePanelTrigger(sharing !== null);

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
          label: t("domain.catalog"),
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                {t("nav.backToCatalog")}
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "collections",
          label: t("collectionsAdmin.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h1 className="text-lg font-bold text-ink">{t("collectionsAdmin.title")}</h1>
                {!readOnly && (
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
                    {t("collectionsAdmin.registerTable")}
                  </Button>
                )}
              </div>
              <input
                type="search"
                role="searchbox"
                aria-label={t("collectionsAdmin.searchAria")}
                placeholder={t("collectionsAdmin.searchPlaceholder")}
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  // Une recherche qui change redémarre depuis la première
                  // page (même patron que UsersAdminPage) : sinon "Charger
                  // plus" cliqué avant de chercher laisserait une limite
                  // agrandie invisible pour la nouvelle recherche.
                  setLimit(PAGE_SIZE);
                }}
              />
              {collectionsQuery.isLoading && <p role="status">{t("common.loading")}</p>}
              {collectionsQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("collectionsAdmin.loadError")}
                </p>
              )}
              {deleteCollection.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("collectionsAdmin.deleteError")}
                </p>
              )}
              {collectionsQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">{t("collectionsAdmin.columnTitle")}</th>
                      <th className="py-2 text-ink">{t("collectionsAdmin.columnTable")}</th>
                      <th className="py-2 text-ink">{t("collectionsAdmin.columnPublic")}</th>
                      <th className="py-2 text-ink">{t("collectionsAdmin.columnEditable")}</th>
                      <th className="py-2 text-ink">{t("collectionsAdmin.columnFeatureCount")}</th>
                      <th className="py-2 text-ink">{t("collectionsAdmin.columnOwner")}</th>
                      <th className="py-2 text-ink">{t("collectionsAdmin.columnActions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {collectionsQuery.data.map((col) => (
                      <tr key={col.id} className="border-b border-rule-2">
                        <td className="py-2 text-ink">{col.title}</td>
                        <td className="py-2 text-xs text-ink-2">{col.tableName}</td>
                        <td className="py-2 text-ink">
                          {col.isPublic ? t("collectionsAdmin.yes") : t("collectionsAdmin.no")}
                        </td>
                        <td className="py-2 text-ink">
                          {col.editable ? t("collectionsAdmin.yes") : t("collectionsAdmin.no")}
                        </td>
                        <td className="py-2 text-ink">{col.featureCount ?? "—"}</td>
                        <td className="py-2 text-ink">{col.owner ?? "—"}</td>
                        <td className="py-2 flex gap-2">
                          {/* REV-089 : les quatre actions mutantes de la ligne
                              masquées sous !readOnly (doctrine tranchée,
                              alignée sur HarvestSourcesAdminPage) — s'ajoute
                              aux gardes Gate can="write"/can="share"
                              existantes ci-dessous (permission par objet,
                              cf. commentaire SP-42/F-securite-autorisation-06
                              conservé), ne les remplace pas. */}
                          {!readOnly && (
                            <>
                              <Gate
                                on={col}
                                can="write"
                                fallback={
                                  <Locked reason={t("locked.needWrite")}>
                                    <Button type="button" variant="outline" size="sm">
                                      {t("collectionsAdmin.edit")}
                                    </Button>
                                  </Locked>
                                }
                              >
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  aria-controls={editPanel.panelId}
                                  aria-expanded={editing?.id === col.id}
                                  onClick={() => {
                                    setRegistering(false);
                                    setSharing(null);
                                    setEditing(col);
                                  }}
                                >
                                  {t("collectionsAdmin.edit")}
                                </Button>
                              </Gate>
                              <Gate
                                on={col}
                                can="share"
                                fallback={
                                  <Locked reason={t("locked.needShare")}>
                                    <Button type="button" variant="outline" size="sm">
                                      {t("actions.share")}
                                    </Button>
                                  </Locked>
                                }
                              >
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  aria-controls={sharingPanel.panelId}
                                  aria-expanded={sharing?.id === col.id}
                                  onClick={() => {
                                    setRegistering(false);
                                    setEditing(null);
                                    setSharing(col);
                                  }}
                                >
                                  {t("actions.share")}
                                </Button>
                              </Gate>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setDeleting(col)}
                              >
                                {t("actions.delete")}
                              </Button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {collectionsQuery.data && collectionsQuery.data.length >= limit && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="self-start"
                  onClick={() => setLimit((l) => l + PAGE_SIZE)}
                >
                  {t("collectionsAdmin.loadMore")}
                </Button>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "detail",
          label: t("collectionsAdmin.detail"),
          content: (
            <div className="flex flex-col gap-3 p-3">
              {registering && <RegisterCollectionPanel onClose={() => setRegistering(false)} />}
              {editing && (
                // id seul (pas role="region" du hook) : EditCollectionPanel
                // rend déjà un <section aria-label=…>, donc une région
                // implicite nommée — un role="region" supplémentaire sur ce
                // wrapper créerait une région imbriquée non nommée,
                // redondante pour les lecteurs d'écran (vérifié contre le
                // composant réel, cf. piège CLAUDE.md n°3 — le brief
                // supposait un wrapper neutre).
                <div id={editPanel.panelId}>
                  <EditCollectionPanel
                    key={editing.id}
                    collection={editing}
                    onClose={() => setEditing(null)}
                  />
                </div>
              )}
              {sharing && (
                <div id={sharingPanel.panelId}>
                  <CollectionSharePanel
                    key={sharing.id}
                    collectionId={sharing.id}
                    onClose={() => setSharing(null)}
                  />
                </div>
              )}
            </div>
          ),
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        title={t("collectionsAdmin.deleteTitle")}
        message={deleting ? t("collectionsAdmin.deleteMessage", { title: deleting.title }) : ""}
        confirmLabel={t("actions.delete")}
        pending={deleteCollection.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
