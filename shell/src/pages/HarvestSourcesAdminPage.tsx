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
import { t } from "../i18n";

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
          id: "sources",
          label: t("harvest.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h1 className="text-lg font-bold text-ink">{t("harvest.title")}</h1>
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
                    {t("harvest.addSource")}
                  </Button>
                )}
              </div>
              {sourcesQuery.isLoading && <p role="status">{t("common.loading")}</p>}
              {sourcesQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("harvest.loadError")}
                </p>
              )}
              {deleteSource.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("harvest.deleteError")}
                </p>
              )}
              {sourcesQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">{t("catalog.typeLabel")}</th>
                      <th className="py-2 text-ink">{t("harvest.columnUrl")}</th>
                      <th className="py-2 text-ink">{t("harvest.columnMode")}</th>
                      <th className="py-2 text-ink">{t("extensions.columnActive")}</th>
                      <th className="py-2 text-ink">{t("harvest.columnLastStatus")}</th>
                      <th className="py-2 text-ink">{t("collectionsAdmin.columnActions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sourcesQuery.data.map((source) => (
                      <tr key={source.id} className="border-b border-rule-2">
                        <td className="py-2 text-ink">{source.type}</td>
                        <td className="py-2 text-xs text-ink-2">{source.url}</td>
                        <td className="py-2 text-ink">{source.mode}</td>
                        <td className="py-2 text-ink">
                          {source.enabled ? t("collectionsAdmin.yes") : t("collectionsAdmin.no")}
                        </td>
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
                                {t("harvest.runNow")}
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
                                {t("collectionsAdmin.edit")}
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setDeleting(source)}
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
            </div>
          ),
        }}
        inspect={{
          id: "detail",
          label: t("harvest.detail"),
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
        title={t("harvest.deleteTitle")}
        message={deleting ? t("harvest.deleteMessage", { url: deleting.url }) : ""}
        confirmLabel={t("actions.delete")}
        pending={deleteSource.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
