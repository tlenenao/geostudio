// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  useDatasetConfig,
  useItem,
  useItems,
  useMetadataCatalog,
  useSaveDataset,
  useUpdateItem,
} from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { CrossFilterLink, DatasetColumnMeta, DatasetConfig } from "../api/types";
import { mergeDatasetSchema } from "../lib/datasetSchema";
import { hasPermission } from "../auth/permissions";
import { MetadataForm } from "../ui/kit/MetadataForm";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { LoadingState } from "../ui/kit/LoadingState";
import { QueryErrorState } from "../ui/kit/QueryErrorState";
import { CrossFilterLinkEditor } from "../builder/CrossFilterLinkEditor";
import { AlertRuleEditor } from "../builder/AlertRuleEditor";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { isConflictError } from "../api/ApiError";
import { SaveConflictNotice } from "../builder/SaveConflictNotice";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { useDirtyGuard } from "../lib/useDirtyGuard";
import { t } from "../i18n";
import { saveExportedFile } from "../api/saveExportedFile";
import { PageTitle } from "../ui/kit/PageTitle";
import "../i18n/domains/admin";
import { useUrlTab } from "../lib/useUrlTab";
import "../i18n/domains/misc";

export function DatasetEditPage({ pk }: { pk: string }) {
  const tabProps = useUrlTab("dataset");
  const itemQuery = useItem(pk);
  const configQuery = useDatasetConfig(pk);
  const save = useSaveDataset(pk);
  const updateItem = useUpdateItem(pk);
  const catalogQuery = useMetadataCatalog();
  const client = useItemClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DatasetConfig | null>(null);
  const baseVersionRef = useRef<number | undefined>(undefined);
  const versionSeededRef = useRef(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);
  // SP-60 : le sondage d'un export asynchrone s'arrête au démontage.
  const exportAbort = useRef<AbortController | null>(null);
  useEffect(() => () => exportAbort.current?.abort(), []);
  // SP-B6d : même patron que MapEditorPage (Tâche 27) — `updateDraft`
  // centralise toute mutation du brouillon issue d'une action utilisateur ;
  // l'effet de synchronisation initiale ci-dessous passe volontairement par
  // le `setDraft` brut pour ne pas marquer le brouillon sale au chargement.
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const updateDraft: typeof setDraft = (next) => {
    setHasUnsavedChanges(true);
    setDraft(next);
  };
  const { ConfirmLeaveDialog } = useDirtyGuard(hasUnsavedChanges);

  useEffect(() => {
    if (!configQuery.data) return;
    setDraft((d) => d ?? configQuery.data);
    // Le brouillon n'est seedé qu'une fois : la version de base est celle du
    // chargement initial, jamais celle d'un refetch (cf. AppBuilderPage).
    if (!versionSeededRef.current) {
      versionSeededRef.current = true;
      baseVersionRef.current = configQuery.data.baseVersion;
    }
  }, [configQuery.data]);

  const draftCollectionId = draft && draft.source === "collection" ? draft.collectionId : undefined;
  const schemaQuery = useQuery({
    queryKey: ["collection-schema", draftCollectionId],
    queryFn: () => client.getCollectionSchema(draftCollectionId!),
    enabled: Boolean(draftCollectionId),
  });
  const otherDatasetsQuery = useItems({ type: "dataset", pageSize: 100 });

  if (itemQuery.isLoading || configQuery.isLoading || (!draft && !configQuery.isError))
    return <LoadingState />;
  if (itemQuery.isError || configQuery.isError || !draft || !itemQuery.data)
    return (
      <QueryErrorState
        queries={[itemQuery, configQuery]}
        notFoundMessage={t("datasetEdit.notFound")}
      />
    );

  const item = itemQuery.data;
  // SP-42/F-shell-pages-04 : un item partagé en lecture seule (permissions.write
  // false, cas légitime du modèle de partage) ne doit pas laisser cliquer
  // Enregistrer pour découvrir le 403 après coup — doctrine SP-29a
  // (ItemActions/ItemDetailPage). Résidu documenté (rapport de lot) :
  // permissions.write ne reflète que can()/decide(), pas la garde de
  // privilège de domaine (PUT /configs) — ce correctif ne ferme donc pas
  // tous les 403 possibles.
  const readOnly = !hasPermission(item, "write");
  const isConflict = isConflictError(save.error);
  async function reloadLatest() {
    client.invalidateDatasetCache(pk); // sinon getDatasetConfig relit le cache (5 min)
    const latest = await client.getDatasetConfig(pk);
    setDraft(latest);
    baseVersionRef.current = latest.baseVersion;
    setHasUnsavedChanges(false);
    save.reset();
  }

  function setColumn(name: string, patch: DatasetColumnMeta) {
    updateDraft((d) =>
      d ? { ...d, columns: { ...d.columns, [name]: { ...d.columns[name], ...patch } } } : d,
    );
  }

  const targetOptions = (otherDatasetsQuery.data?.items ?? [])
    .filter((d) => d.pk !== pk)
    .map((d) => ({ pk: d.pk, title: d.title }));

  function addCrossFilterLink() {
    updateDraft((d) =>
      d
        ? {
            ...d,
            crossFilterLinks: [
              ...(d.crossFilterLinks ?? []),
              { targetDatasetId: "", mode: "attribute" as const, sourceField: "", targetField: "" },
            ],
          }
        : d,
    );
  }
  function updateCrossFilterLink(index: number, next: CrossFilterLink) {
    updateDraft((d) => {
      if (!d) return d;
      const links = [...(d.crossFilterLinks ?? [])];
      links[index] = next;
      return { ...d, crossFilterLinks: links };
    });
  }
  function removeCrossFilterLink(index: number) {
    updateDraft((d) => {
      if (!d) return d;
      const links = (d.crossFilterLinks ?? []).filter((_, i) => i !== index);
      return { ...d, crossFilterLinks: links };
    });
  }

  const merged = schemaQuery.data ? mergeDatasetSchema(schemaQuery.data, draft.columns) : [];

  const hasGeometry = draft.source === "arcgis" ? true : Boolean(schemaQuery.data?.geometry);
  const exportFormats = hasGeometry ? ["csv", "xlsx", "geojson", "gpkg"] : ["csv", "xlsx"];

  async function handleExport(format: string) {
    const source = {
      id: "__dataset-export__",
      type: "features" as const,
      service: "core",
      layer: "",
      datasetId: pk,
      query: {},
    };
    setExportError(null);
    setExportingFormat(format);
    exportAbort.current?.abort();
    const ac = new AbortController();
    exportAbort.current = ac;
    try {
      const file = await client.exportDataSource(source, format, ac.signal);
      saveExportedFile(file);
    } catch (err) {
      if (!ac.signal.aborted) {
        setExportError(err instanceof Error ? err.message : t("datasetEdit.exportError"));
      }
    } finally {
      if (!ac.signal.aborted) setExportingFormat(null);
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        {...tabProps}
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                {t("nav.backToCatalog")}
              </Link>
              <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                <dt>{t("catalog.typeLabel")}</dt>
                <dd>{t("datasetEdit.datasetLabel")}</dd>
                <dt>{t("datasetEdit.modifiedLabel")}</dt>
                <dd>{item.updatedAt || "—"}</dd>
              </dl>
            </Panel>
          ),
        }}
        work={{
          id: "dataset",
          label: t("datasetEdit.datasetLabel"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <PageTitle>{t("datasetEdit.heading", { title: item.title })}</PageTitle>
              <MetadataForm
                key={item.updatedAt}
                initial={{
                  title: item.title,
                  abstract: item.abstract,
                  keywords: item.keywords ?? [],
                  license: item.license,
                  language: item.language,
                }}
                licenses={catalogQuery.data?.licenses ?? []}
                languages={catalogQuery.data?.languages ?? []}
                onSubmit={(v) => updateItem.mutate({ ...v, baseUpdatedAt: item.updatedAt })}
                onCancel={() => {}}
                pending={updateItem.isPending}
              />
              {isConflictError(updateItem.error) && (
                <SaveConflictNotice
                  onReload={() => {
                    updateItem.reset();
                    void itemQuery.refetch();
                  }}
                />
              )}
              <div>
                <p className="mb-1 text-xs font-medium text-ink-2">
                  {t("datasetEdit.columnsLabel")}
                </p>
                {schemaQuery.isLoading && <LoadingState label={t("datasetEdit.schemaLoading")} />}
                {schemaQuery.isError && (
                  <p role="alert" className="text-sm text-danger">
                    {t("datasetEdit.sourceNotFound")}
                  </p>
                )}
                {merged.length > 0 && (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-ink-2">
                        <th className="p-1">{t("datasetEdit.columnHeader")}</th>
                        <th className="p-1">{t("datasetEdit.labelHeader")}</th>
                        <th className="p-1">{t("datasetEdit.descriptionHeader")}</th>
                        <th className="p-1">{t("datasetEdit.formatHeader")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {merged.map((f) => (
                        <tr key={f.name} className="border-t border-rule">
                          <td className="p-1 font-mono text-xs">{f.name}</td>
                          <td className="p-1">
                            <input
                              aria-label={t("datasetEdit.labelAria", { name: f.name })}
                              className="h-9 w-full rounded border border-control bg-surface px-2 text-xs text-ink"
                              value={f.label ?? ""}
                              onChange={(e) => setColumn(f.name, { label: e.target.value })}
                            />
                          </td>
                          <td className="p-1">
                            <input
                              aria-label={t("datasetEdit.descriptionAria", { name: f.name })}
                              className="h-9 w-full rounded border border-control bg-surface px-2 text-xs text-ink"
                              value={f.description ?? ""}
                              onChange={(e) => setColumn(f.name, { description: e.target.value })}
                            />
                          </td>
                          <td className="p-1">
                            <input
                              aria-label={t("datasetEdit.formatAria", { name: f.name })}
                              className="h-9 w-full rounded border border-control bg-surface px-2 text-xs text-ink"
                              value={f.format ?? ""}
                              onChange={(e) => setColumn(f.name, { format: e.target.value })}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <label className="mt-2 flex flex-col gap-1 text-xs">
                  {t("datasetEdit.timeFieldLabel")}
                  <select
                    className="h-9 w-full rounded border border-control bg-surface px-2 text-xs text-ink"
                    value={draft.timeField ?? ""}
                    onChange={(e) =>
                      updateDraft((d) => (d ? { ...d, timeField: e.target.value || null } : d))
                    }
                  >
                    <option value="">{t("datasetEdit.noneOption")}</option>
                    {merged.map((f) => (
                      <option key={f.name} value={f.name}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={Boolean(draft.reactsToExtent)}
                    onChange={(e) =>
                      updateDraft((d) => (d ? { ...d, reactsToExtent: e.target.checked } : d))
                    }
                  />
                  {t("datasetEdit.reactsToExtentLabel")}
                </label>
                <div className="mt-2 flex flex-col gap-2">
                  <p className="text-xs font-medium text-ink-2">
                    {t("datasetEdit.crossFilterLinksLabel")}
                  </p>
                  {(draft.crossFilterLinks ?? []).map((link, i) => (
                    <CrossFilterLinkEditor
                      key={i}
                      link={link}
                      sourceFields={merged.map((f) => f.name)}
                      targetOptions={targetOptions}
                      onChange={(next) => updateCrossFilterLink(i, next)}
                      onRemove={() => removeCrossFilterLink(i)}
                    />
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-fit"
                    onClick={addCrossFilterLink}
                  >
                    {t("datasetEdit.addLink")}
                  </Button>
                </div>
              </div>
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: t("datasetEdit.settingsLabel"),
          content: (
            <div className="flex flex-col gap-4 p-3">
              <div className="flex flex-col gap-2">
                <p className="text-xs font-medium text-ink-2">{t("datasetEdit.exportLabel")}</p>
                <div className="flex gap-2">
                  {exportFormats.map((format) => (
                    <button
                      key={format}
                      type="button"
                      aria-label={t("datasetEdit.exportAria", { format: format.toUpperCase() })}
                      disabled={exportingFormat === format}
                      className="rounded border border-rule px-2 py-1 text-xs text-ink hover:bg-sunken disabled:opacity-50"
                      onClick={() => void handleExport(format)}
                    >
                      {format.toUpperCase()}
                    </button>
                  ))}
                </div>
                {exportError && (
                  <p role="alert" className="text-sm text-danger">
                    {exportError}
                  </p>
                )}
              </div>
              <AlertRuleEditor datasetItemId={pk} owner={item.owner} />
              <ConfigHistoryPanel
                pk={pk}
                currentVersion={null}
                onRestored={async () => {
                  const restored = await client.getDatasetConfig(pk);
                  updateDraft(restored);
                  baseVersionRef.current = restored.baseVersion;
                }}
              />
              {draft.sourcePipelineId && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="w-fit"
                  onClick={() => navigate(`/datasets/visual-query/${draft.sourcePipelineId}/edit`)}
                >
                  {t("datasetEdit.editQuery")}
                </Button>
              )}
              <Button
                size="sm"
                className="w-fit"
                disabled={save.isPending || readOnly}
                onClick={() =>
                  save.mutate(
                    { ...draft, baseVersion: baseVersionRef.current },
                    {
                      onSuccess: (version) => {
                        baseVersionRef.current = version;
                        setHasUnsavedChanges(false);
                      },
                    },
                  )
                }
              >
                {t("datasetEdit.saveColumns")}
              </Button>
              {readOnly && <p className="text-xs text-ink-2">{t("locked.needWrite")}</p>}
              {save.isError && !isConflict && (
                <p role="alert" className="text-sm text-danger">
                  {t("actions.saveFailed")}
                </p>
              )}
              {isConflict && <SaveConflictNotice onReload={() => void reloadLatest()} />}
            </div>
          ),
        }}
      />
      <ConfirmLeaveDialog />
    </div>
  );
}
