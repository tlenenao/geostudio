// SPDX-License-Identifier: Apache-2.0
import { Link, useSearchParams } from "react-router-dom";
import { useItem, useMetadataCatalog, useUpdateItem, useUploadThumbnail } from "../api/hooks";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { MetadataForm } from "../ui/MetadataForm";
import { ThumbnailUpload } from "../ui/ThumbnailUpload";
import { ShareForm } from "../shell/ShareForm";
import { ItemActions } from "../shell/ItemActions";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { Gate } from "../auth/Gate";
import { Locked } from "../auth/Locked";
import { hasPermission } from "../auth/permissions";
import { t } from "../i18n";

type PanelKind = "edit" | "thumbnail" | "share" | null;

export function ItemDetailPage({
  pk,
  onDeleted,
  onOpenEditor,
}: {
  pk: string;
  onDeleted?: () => void;
  onOpenEditor?: (type: string) => void;
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

  if (query.isLoading) return <p role="status">{t("common.loading")}</p>;
  if (query.isError || !query.data)
    return (
      <p role="alert" className="text-sm text-danger">
        {t("itemDetail.notFound")}
      </p>
    );

  const item = query.data;

  async function save(v: {
    title: string;
    abstract: string;
    keywords: string[];
    license: string;
    language: string;
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
                <dd>{item.updatedAt || "—"}</dd>
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
                {item.resourceType}
              </span>
              <h2 className="text-xl font-semibold text-ink">{item.title}</h2>
              <p className="text-sm text-ink-2">
                {t("itemDetail.ownerLabel", { owner: item.owner })}
              </p>
              <p className="text-sm text-ink">{item.abstract}</p>
              {["map", "app", "dashboard", "dataset", "pipeline"].includes(item.resourceType) ? (
                <Button className="w-fit" onClick={() => onOpenEditor?.(item.resourceType)}>
                  {t("itemDetail.openEditor")}
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
                        }}
                        licenses={catalogQuery.data?.licenses ?? []}
                        languages={catalogQuery.data?.languages ?? []}
                        onSubmit={(v) => void save(v)}
                        onCancel={closePanel}
                        pending={update.isPending}
                      />
                      {update.isError && (
                        <p role="alert" className="text-sm text-danger">
                          {t("actions.saveFailed")}
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
