// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useItemClient } from "../api/ItemClientProvider";
import { apiErrorMessage } from "../api/apiErrorMessage";
import { useItem, useMetadataCatalog, useUpdateItem, useUploadThumbnail } from "../api/hooks";
import type { Item } from "../api/types";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { MetadataForm } from "../ui/kit/MetadataForm";
import { ThumbnailUpload } from "../ui/kit/ThumbnailUpload";
import { ShareForm, copyToClipboard } from "../shell/ShareForm";
import { ItemActions } from "../shell/ItemActions";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { Gate } from "../auth/Gate";
import { Locked } from "../auth/Locked";
import { hasPermission } from "../auth/permissions";
import { plural, t } from "../i18n";
import { formatDateTime } from "../lib/format";
import { LoadingState } from "../ui/kit/LoadingState";
import { QueryErrorState } from "../ui/kit/QueryErrorState";
import { PageTitle } from "../ui/kit/PageTitle";

type PanelKind = "edit" | "thumbnail" | "share" | null;

export function ItemDetailPage({
  pk,
  onDeleted,
  onOpenEditor,
}: {
  pk: string;
  onDeleted?: () => void;
  onOpenEditor?: (type: string, item: Item) => void;
}) {
  const query = useItem(pk);
  const [searchParams, setSearchParams] = useSearchParams();
  const panelParam = searchParams.get("panel");
  // Doit accepter exactement les mêmes trois valeurs que goToPanel() dans
  // ItemActions.tsx ("edit" | "thumbnail" | "share") : c'est le contrat
  // implicite entre les deux fichiers (cf. brief Task 4).
  const panel: PanelKind =
    panelParam === "edit" || panelParam === "thumbnail" || panelParam === "share"
      ? panelParam
      : null;
  const closePanel = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("panel");
    setSearchParams(params, { replace: true });
  };

  const update = useUpdateItem(pk);
  const thumbnail = useUploadThumbnail(pk);
  const catalogQuery = useMetadataCatalog();

  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data)
    return <QueryErrorState queries={[query]} notFoundMessage={t("itemDetail.notFound")} />;

  const item = query.data;

  async function save(v: {
    title: string;
    abstract: string;
    keywords: string[];
    license: string;
    language: string;
    slug?: string;
  }) {
    try {
      await update.mutateAsync(v);
      closePanel();
    } catch {
      /* surfaced via update.isError */
    }
  }

  async function upload(file: File) {
    try {
      await thumbnail.mutateAsync(file);
      closePanel();
    } catch {
      /* surfaced via thumbnail.isError */
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="item"
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
                <dd>{RESOURCE_TYPE_LABELS[item.resourceType]}</dd>
                <dt>{t("datasetEdit.modifiedLabel")}</dt>
                <dd>{item.updatedAt ? formatDateTime(item.updatedAt) : "—"}</dd>
              </dl>
            </Panel>
          ),
        }}
        work={{
          id: "item",
          label: t("itemDetail.elementLabel"),
          content: (
            <article className="flex h-full flex-col gap-3 overflow-y-auto p-6">
              <span className="w-fit rounded bg-sunken px-2 py-0.5 text-xs uppercase text-ink-2">
                {RESOURCE_TYPE_LABELS[item.resourceType]}
              </span>
              <PageTitle>{item.title}</PageTitle>
              <p className="text-sm text-ink-2">
                {t("itemDetail.ownerLabel", { owner: item.owner })}
              </p>
              <p className="text-sm text-ink">{item.abstract}</p>
              <ItemFacts
                item={item}
                licenseLabel={catalogQuery.data?.licenses.find((l) => l.id === item.license)?.label}
                languageLabel={
                  catalogQuery.data?.languages.find((l) => l.id === item.language)?.label
                }
              />
              {["map", "app", "dashboard", "dataset", "pipeline", "site"].includes(
                item.resourceType,
              ) ? (
                <Button className="w-fit" onClick={() => onOpenEditor?.(item.resourceType, item)}>
                  {hasPermission(item, "write") || item.resourceType === "map"
                    ? t("itemDetail.openEditor")
                    : t("itemDetail.openView")}
                </Button>
              ) : (
                <Button className="w-fit" disabled title={t("itemDetail.editorUnavailableTitle")}>
                  {t("itemDetail.openEditor")}
                </Button>
              )}
            </article>
          ),
        }}
        inspect={{
          id: "actions",
          label: t("actions.menu"),
          content: (
            <div className="flex flex-col gap-3 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-ink">{t("actions.menu")}</span>
                <ItemActions item={item} onDeleted={onDeleted} />
              </div>
              {panel === "edit" && (
                <Panel className="flex flex-col gap-2">
                  {hasPermission(item, "write") ? (
                    <>
                      <MetadataForm
                        initial={{
                          title: item.title,
                          abstract: item.abstract,
                          keywords: item.keywords ?? [],
                          license: item.license,
                          language: item.language,
                          slug: item.resourceType === "site" ? (item.slug ?? "") : undefined,
                        }}
                        licenses={catalogQuery.data?.licenses ?? []}
                        languages={catalogQuery.data?.languages ?? []}
                        onSubmit={(v) => void save(v)}
                        onCancel={closePanel}
                        pending={update.isPending}
                      />
                      {update.isError && (
                        <p role="alert" className="text-sm text-danger">
                          {apiErrorMessage(update.error, t("actions.saveFailed"))}
                        </p>
                      )}
                    </>
                  ) : (
                    // Point d'entrée par URL (favori, retour arrière, lien
                    // périmé si le partage a changé depuis) : contrairement au
                    // menu d'ItemActions qui se contente de ne pas montrer
                    // l'entrée, l'utilisateur est déjà sur cette page — un
                    // panneau vide serait déroutant. On explique plutôt
                    // pourquoi (doctrine §6.2, cf. ItemActions.tsx).
                    <Locked reason={t("locked.needWrite")}>
                      <MetadataForm
                        initial={{
                          title: item.title,
                          abstract: item.abstract,
                          keywords: item.keywords ?? [],
                          license: item.license,
                          language: item.language,
                          slug: item.resourceType === "site" ? (item.slug ?? "") : undefined,
                        }}
                        licenses={catalogQuery.data?.licenses ?? []}
                        languages={catalogQuery.data?.languages ?? []}
                        onSubmit={closePanel}
                        onCancel={closePanel}
                        pending={false}
                      />
                    </Locked>
                  )}
                </Panel>
              )}
              {panel === "thumbnail" && (
                <Panel className="flex flex-col gap-2">
                  {hasPermission(item, "write") ? (
                    <>
                      <ThumbnailUpload
                        onUpload={(file) => void upload(file)}
                        pending={thumbnail.isPending}
                      />
                      {thumbnail.isError && (
                        <p role="alert" className="text-sm text-danger">
                          {t("actions.uploadFailed")}
                        </p>
                      )}
                    </>
                  ) : (
                    <Locked reason={t("locked.needWrite")}>
                      <ThumbnailUpload onUpload={() => {}} pending={false} />
                    </Locked>
                  )}
                </Panel>
              )}
              {panel === "share" && (
                <Panel>
                  <Gate
                    on={item}
                    can="share"
                    fallback={
                      <Locked reason={t("locked.needShare")}>
                        <ShareForm item={item} onDone={closePanel} />
                      </Locked>
                    }
                  >
                    <ShareForm item={item} onDone={closePanel} />
                  </Gate>
                </Panel>
              )}
            </div>
          ),
        }}
      />
    </div>
  );
}

// Métadonnées ouvertes lisibles par le lecteur (P35.08) + URL publique d'un site
// publié (P35.11). Volume/colonnes d'un jeu de données : lus via sa collection.
function ItemFacts({
  item,
  licenseLabel,
  languageLabel,
}: {
  item: Item;
  licenseLabel?: string;
  languageLabel?: string;
}) {
  const [copied, setCopied] = useState(false);
  const publicUrl =
    item.resourceType === "site" && item.isPublished && item.slug
      ? `${window.location.origin}/sites/${item.slug}`
      : null;
  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm text-ink-2">
        {item.license && (
          <>
            <dt>{t("itemDetail.licenseLabel")}</dt>
            <dd>{licenseLabel ?? item.license}</dd>
          </>
        )}
        {(item.keywords ?? []).length > 0 && (
          <>
            <dt>{t("itemDetail.keywordsLabel")}</dt>
            <dd>{(item.keywords ?? []).join(", ")}</dd>
          </>
        )}
        {item.language && (
          <>
            <dt>{t("itemDetail.languageLabel")}</dt>
            <dd>{languageLabel ?? item.language}</dd>
          </>
        )}
        {item.resourceType === "dataset" && <DatasetFacts pk={item.pk} />}
      </dl>
      {publicUrl && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-ink-2">{t("itemDetail.publicUrlLabel")}</span>
          <code className="rounded bg-sunken px-1.5 py-0.5 text-ink">{publicUrl}</code>
          {/* eslint-disable-next-line geostudio/panel-trigger-aria -- bouton « Copier » : etat transitoire, pas un panneau */}
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              void copyToClipboard(publicUrl).then(() => setCopied(true));
            }}
          >
            {t("itemDetail.copyUrl")}
          </Button>
          {copied && (
            <span role="status" className="text-xs text-ink-2">
              {t("itemDetail.urlCopied")}
            </span>
          )}
        </div>
      )}
    </>
  );
}

function DatasetFacts({ pk }: { pk: string }) {
  const client = useItemClient();
  const config = useQuery({
    queryKey: ["dataset", pk],
    queryFn: () => client.getDatasetConfig(pk),
    retry: false,
  });
  const collectionId = config.data?.source === "collection" ? config.data.collectionId : undefined;
  const schema = useQuery({
    queryKey: ["item-facts-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId!),
    enabled: !!collectionId,
    retry: false,
  });
  const collection = useQuery({
    queryKey: ["item-facts-collection", collectionId],
    queryFn: () => client.getCollection(collectionId!),
    enabled: !!collectionId,
    retry: false,
  });
  const count = collection.data?.featureCount;
  return (
    <>
      {schema.data && schema.data.fields.length > 0 && (
        <>
          <dt>{t("itemDetail.columnsLabel")}</dt>
          <dd>{schema.data.fields.map((f) => f.label ?? f.name).join(", ")}</dd>
        </>
      )}
      {typeof count === "number" && (
        <>
          <dt>{t("itemDetail.featureCountLabel")}</dt>
          <dd>
            {t(plural(count, "datasetPage.featureCountOne", "datasetPage.featureCountMany"), {
              n: count,
            })}
          </dd>
        </>
      )}
    </>
  );
}
