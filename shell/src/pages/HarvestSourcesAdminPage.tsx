// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from "react";
import {
  useDeleteHarvestSource,
  useHarvestSourceRecords,
  useHarvestSources,
  useInstanceInfo,
  useRunHarvestSource,
} from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Link } from "react-router-dom";
import { Badge } from "../ui/kit/Badge";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { DataTable } from "../ui/kit/DataTable";
import { EmptyState } from "../ui/kit/EmptyState";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { CreateHarvestSourcePanel } from "../shell/CreateHarvestSourcePanel";
import { EditHarvestSourcePanel } from "../shell/EditHarvestSourcePanel";
import { SettingsNav } from "../shell/chrome/SettingsNav";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { plural, t } from "../i18n";
import { LoadingState } from "../ui/kit/LoadingState";
import { Banner } from "../ui/kit/Banner";
import { PageTitle } from "../ui/kit/PageTitle";

const RECORDS_PAGE_SIZE = 100;

function HarvestRecordsPanel({ source }: { source: HarvestSource }) {
  const [limit, setLimit] = useState(RECORDS_PAGE_SIZE);
  const query = useHarvestSourceRecords(source.id, { limit });
  return (
    <section aria-label={t("harvest.recordsHeading", { url: source.url })}>
      <h2 className="mb-2 text-sm font-medium text-ink">
        {t("harvest.recordsHeading", { url: source.url })}
      </h2>
      {query.isLoading && <LoadingState />}
      {query.isError && <Banner variant="danger">{t("harvest.recordsLoadError")}</Banner>}
      {query.data && query.data.records.length === 0 && (
        <p className="text-sm text-ink-2">{t("harvest.recordsEmpty")}</p>
      )}
      {query.data && query.data.records.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {query.data.records.map((record) => (
            <li key={record.id} className="flex flex-wrap items-center gap-2">
              {record.itemId ? (
                <Link to={`/items/${record.itemId}`} className="text-accent hover:underline">
                  {record.externalId}
                </Link>
              ) : (
                <span>{record.externalId}</span>
              )}
              {record.state === "stale" && <Badge variant="warn">{t("harvest.recordStale")}</Badge>}
            </li>
          ))}
        </ul>
      )}
      {query.data &&
        query.data.records.length >= limit &&
        query.data.records.length < query.data.total && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => setLimit((l) => l + RECORDS_PAGE_SIZE)}
          >
            {t("harvest.loadMore")}
          </Button>
        )}
    </section>
  );
}

export function HarvestSourcesAdminPage() {
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const sourcesQuery = useHarvestSources();
  const deleteSource = useDeleteHarvestSource();
  const runSource = useRunHarvestSource();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<HarvestSource | null>(null);
  const [deleting, setDeleting] = useState<HarvestSource | null>(null);
  const [viewingRecords, setViewingRecords] = useState<HarvestSource | null>(null);
  const recordsPanel = usePanelTrigger(viewingRecords !== null);
  const createPanel = usePanelTrigger(creating);
  const editPanel = usePanelTrigger(editing !== null);
  const [sortKey, setSortKey] = useState<string | undefined>(undefined);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  function handleSortChange(key: string) {
    if (key === sortKey) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  }

  const sortedSources = useMemo(() => {
    const rows = sourcesQuery.data ?? [];
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "type":
          cmp = a.type.localeCompare(b.type);
          break;
        case "mode":
          cmp = a.mode.localeCompare(b.mode);
          break;
        case "enabled":
          cmp = Number(a.enabled) - Number(b.enabled);
          break;
        case "lastStatus":
          cmp = (a.lastStatus ?? "").localeCompare(b.lastStatus ?? "");
          break;
        default:
          cmp = a.url.localeCompare(b.url);
      }
      return sortDirection === "asc" ? cmp : -cmp;
    });
  }, [sourcesQuery.data, sortKey, sortDirection]);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteSource.mutateAsync(deleting.id);
      // Croisement entre tâches (revue finale SP-30j) : editing n'est plus
      // un Dialog modal, donc peut rester ouvert sur la ligne qu'on vient de
      // supprimer si l'utilisateur clique Supprimer sans le fermer d'abord.
      // Fermer explicitement s'il pointait vers l'objet supprimé.
      if (editing?.id === deleting.id) setEditing(null);
      if (viewingRecords?.id === deleting.id) setViewingRecords(null);
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
          content: <SettingsNav />,
        }}
        work={{
          id: "sources",
          label: t("harvest.title"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <PageTitle>{t("harvest.title")}</PageTitle>
                {!readOnly && (
                  <Button
                    size="sm"
                    {...createPanel.triggerProps}
                    onClick={() => {
                      // Exclusivité mutuelle avec editing (décision 5, plan
                      // SP-30j) : plus de barrière modale pour l'empêcher.
                      setEditing(null);
                      setViewingRecords(null);
                      setCreating(true);
                    }}
                  >
                    {t("harvest.addSource")}
                  </Button>
                )}
              </div>
              {sourcesQuery.isLoading && <LoadingState />}
              {sourcesQuery.isError && (
                <Banner variant="danger" onRetry={() => void sourcesQuery.refetch()}>
                  {t("harvest.loadError")}
                </Banner>
              )}
              {deleteSource.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("harvest.deleteError")}
                </p>
              )}
              {runSource.isError && (
                <p role="alert" className="text-sm text-danger">
                  {t("harvest.runFailed")}
                </p>
              )}
              {runSource.isSuccess && (
                <p role="status" className="text-sm text-ink">
                  {t("harvest.runQueued")}
                </p>
              )}
              {sourcesQuery.data && sourcesQuery.data.length === 0 && (
                <EmptyState title={t("harvest.empty")} />
              )}
              {sourcesQuery.data && sourcesQuery.data.length > 0 && (
                <DataTable
                  columns={[
                    {
                      key: "type",
                      label: t("catalog.typeLabel"),
                      render: (source: HarvestSource) => source.type,
                    },
                    {
                      key: "url",
                      label: t("harvest.columnUrl"),
                      render: (source: HarvestSource) => (
                        <span className="text-xs text-ink-2">{source.url}</span>
                      ),
                    },
                    {
                      key: "mode",
                      label: t("harvest.columnMode"),
                      render: (source: HarvestSource) => source.mode,
                    },
                    {
                      key: "enabled",
                      label: t("extensions.columnActive"),
                      render: (source: HarvestSource) =>
                        source.enabled ? t("collectionsAdmin.yes") : t("collectionsAdmin.no"),
                    },
                    {
                      key: "lastStatus",
                      label: t("harvest.columnLastStatus"),
                      render: (source: HarvestSource) => (
                        <div className="flex flex-col">
                          <span>{source.lastStatus ?? "—"}</span>
                          {source.lastError && (
                            <span
                              className="max-w-xs truncate text-xs text-danger"
                              title={source.lastError}
                            >
                              {source.lastError}
                            </span>
                          )}
                        </div>
                      ),
                    },
                    {
                      key: "lastRunAt",
                      label: t("harvest.columnLastRun"),
                      render: (source: HarvestSource) =>
                        source.lastRunAt
                          ? new Date(source.lastRunAt).toLocaleString("fr-FR")
                          : t("harvest.neverRun"),
                    },
                    {
                      key: "recordCount",
                      label: t("harvest.columnRecords"),
                      render: (source: HarvestSource) => (
                        <span>
                          {source.recordCount ?? 0}
                          {source.staleCount
                            ? ` (${t(plural(source.staleCount, "harvest.recordsStaleOne", "harvest.recordsStaleMany"), { count: source.staleCount })})`
                            : ""}
                        </span>
                      ),
                    },
                    {
                      key: "actions",
                      label: t("collectionsAdmin.columnActions"),
                      render: (source: HarvestSource) => (
                        <div className="flex gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            aria-controls={recordsPanel.panelId}
                            aria-expanded={viewingRecords?.id === source.id}
                            onClick={() => {
                              setCreating(false);
                              setEditing(null);
                              setViewingRecords(source);
                            }}
                          >
                            {t("harvest.recordsButton")}
                          </Button>
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
                                  setViewingRecords(null);
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
                        </div>
                      ),
                    },
                  ]}
                  rows={sortedSources}
                  getRowId={(source) => source.id}
                  sortKey={sortKey}
                  sortDirection={sortDirection}
                  onSortChange={handleSortChange}
                />
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
              {viewingRecords && (
                <div id={recordsPanel.panelId}>
                  <HarvestRecordsPanel key={viewingRecords.id} source={viewingRecords} />
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
