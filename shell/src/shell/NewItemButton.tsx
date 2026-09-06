// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCreateItem,
  useCreateMap,
  useCreateDataset,
  useCollectionsAdmin,
  useFeatureLayers,
  useInstanceInfo,
  useMe,
} from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Drawer } from "../ui/kit/Drawer";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { TEMPLATES } from "../builder/templates";
import { isValidSlug, slugify } from "../lib/slug";
import { t } from "../i18n";

type Kind = "app" | "dashboard" | "map" | "site" | "dataset" | "pipeline" | "visual-query";

export function NewItemButton() {
  const [open, setOpen] = useState(false);
  const drawerPanel = usePanelTrigger(open);
  const [kind, setKind] = useState<Kind>("app");
  const [title, setTitle] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [collectionId, setCollectionId] = useState("");
  const [datasetSource, setDatasetSource] = useState<"collection" | "arcgis">("collection");
  const [arcgisItemId, setArcgisItemId] = useState("");
  const { username } = useAuth();
  const navigate = useNavigate();
  const create = useCreateItem();
  const createMap = useCreateMap();
  const createDataset = useCreateDataset();
  const instanceQuery = useInstanceInfo();
  const etlEnabled = instanceQuery.data?.etlEnabled === true;
  const collectionsQuery = useCollectionsAdmin({
    enabled: open && kind === "dataset" && datasetSource === "collection",
  });
  const featureLayersQuery = useFeatureLayers({
    enabled: open && kind === "dataset" && datasetSource === "arcgis",
  });

  // SP-42/F-shell-pages-01 : ce bouton de chrome (monté sans condition dans
  // TopBar, sur toutes les routes protégées) ne lisait aucun privilège —
  // un rôle Lecteur (0 privilège) créait Map/App/Dashboard/Site/Dataset de
  // bout en bout, malgré le domaine correspondant masqué dans la barre de
  // domaines. Mapping calé sur celui du cœur (create_config,
  // core/app/configs/routes.py::_KIND_PRIVILEGE) : app/dashboard/site
  // partagent apps.manage (même domaine « Apps & sites »), map ->
  // maps.manage, dataset -> data.manage. Pipeline/visual-query ne créent
  // rien via ce formulaire (navigation pure vers un brouillon) — restent
  // gatés sur la seule capacité etlEnabled comme avant, hors périmètre de
  // cette trouvaille (jamais cités par son scénario d'échec).
  const meQuery = useMe();
  const privileges = meQuery.data?.privileges;
  // Tant que le profil n'est pas encore chargé, ne pas masquer
  // prématurément (le profil réel tranchera au rendu suivant) — évite un
  // flash « bouton absent » à chaque montage du chrome.
  const canCreateApp = privileges === undefined || privileges.includes("apps.manage");
  const canCreateMap = privileges === undefined || privileges.includes("maps.manage");
  const canCreateDataset = privileges === undefined || privileges.includes("data.manage");
  const hasAnyCreatableKind = canCreateApp || canCreateMap || canCreateDataset || etlEnabled;

  // Slug auto-suivi du titre tant que l'utilisateur ne l'a pas édité lui-même.
  useEffect(() => {
    if (kind === "site" && !slugTouched) setSlug(slugify(title));
  }, [title, kind, slugTouched]);

  // Si le kind actuellement sélectionné cesse d'être autorisé (profil
  // chargé après le montage, ou changé sous nos pieds), retombe sur le
  // premier kind encore disponible plutôt que de laisser un <select>
  // contrôlé pointer vers une <option> qui n'est plus rendue.
  useEffect(() => {
    if (privileges === undefined) return;
    const stillAllowed =
      ((kind === "app" || kind === "dashboard" || kind === "site") && canCreateApp) ||
      (kind === "map" && canCreateMap) ||
      (kind === "dataset" && canCreateDataset) ||
      ((kind === "pipeline" || kind === "visual-query") && etlEnabled);
    if (stillAllowed) return;
    const fallback: Kind | undefined = canCreateApp
      ? "app"
      : canCreateMap
        ? "map"
        : canCreateDataset
          ? "dataset"
          : etlEnabled
            ? "visual-query"
            : undefined;
    if (fallback) setKind(fallback);
  }, [privileges, kind, canCreateApp, canCreateMap, canCreateDataset, etlEnabled]);

  if (!hasAnyCreatableKind) return null;

  function close() {
    setOpen(false);
    setTitle("");
    setKind("app");
    setTemplateId("");
    setSlug("");
    setSlugTouched(false);
    setCollectionId("");
    setDatasetSource("collection");
    setArcgisItemId("");
    create.reset();
    createMap.reset();
    createDataset.reset();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    if (kind === "site" && !isValidSlug(slug)) return;
    if (kind === "dataset" && datasetSource === "collection" && !collectionId) return;
    if (kind === "dataset" && datasetSource === "arcgis" && !arcgisItemId) return;
    if (kind === "pipeline") {
      close();
      navigate("/pipelines/new", { state: { title: clean } });
      return;
    }
    if (kind === "visual-query") {
      close();
      navigate("/datasets/visual-query/new", { state: { title: clean } });
      return;
    }
    try {
      const item =
        kind === "map"
          ? await createMap.mutateAsync({ title: clean, owner: username ?? "" })
          : kind === "dataset"
            ? await createDataset.mutateAsync(
                datasetSource === "arcgis"
                  ? { title: clean, owner: username ?? "", source: "arcgis", arcgisItemId }
                  : { title: clean, owner: username ?? "", source: "collection", collectionId },
              )
            : await create.mutateAsync({
                kind,
                title: clean,
                owner: username ?? "",
                templateId: templateId || undefined,
                slug: kind === "site" ? slug : undefined,
              });
      close();
      navigate(
        kind === "map"
          ? `/maps/${item.pk}`
          : kind === "dataset"
            ? `/datasets/${item.pk}/edit`
            : `/apps/${item.pk}/edit`,
      );
    } catch {
      // error surfaced via isError
    }
  }

  return (
    <>
      <Button size="sm" {...drawerPanel.triggerProps} onClick={() => setOpen(true)}>
        {t("newItem.button")}
      </Button>
      <Drawer
        open={open}
        onOpenChange={(next) => !next && close()}
        title={t("newItem.drawerTitle")}
        id={drawerPanel.panelId}
      >
        <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm text-ink">
            {t("catalog.typeLabel")}
            <select
              aria-label={t("catalog.typeLabel")}
              className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as Kind);
                setTemplateId("");
              }}
            >
              {canCreateApp && <option value="app">{t("newItem.appOption")}</option>}
              {canCreateApp && <option value="dashboard">{t("newItem.dashboardOption")}</option>}
              {canCreateMap && <option value="map">{t("newItem.mapOption")}</option>}
              {canCreateApp && <option value="site">{t("newItem.siteOption")}</option>}
              {canCreateDataset && (
                <option value="dataset">{t("newItem.datasetSharedOption")}</option>
              )}
              {etlEnabled && (
                <option value="visual-query">{t("newItem.datasetVisualQueryOption")}</option>
              )}
              {etlEnabled && <option value="pipeline">{t("newItem.pipelineOption")}</option>}
            </select>
          </label>
          {kind !== "map" && kind !== "dataset" && kind !== "pipeline" && (
            <label className="flex flex-col gap-1 text-sm text-ink">
              {t("newItem.templateLabel")}
              <select
                aria-label={t("newItem.templateLabel")}
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
              >
                <option value="">{t("newItem.emptyTemplateOption")}</option>
                {TEMPLATES.filter((tpl) => tpl.kind === kind).map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind === "dataset" && (
            <label className="flex flex-col gap-1 text-sm text-ink">
              {t("newItem.datasetSourceTypeLabel")}
              <select
                aria-label={t("newItem.datasetSourceTypeLabel")}
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={datasetSource}
                onChange={(e) => setDatasetSource(e.target.value as "collection" | "arcgis")}
              >
                <option value="collection">{t("newItem.sourceCollectionOption")}</option>
                <option value="arcgis">{t("harvest.typeArcgis")}</option>
              </select>
            </label>
          )}
          {kind === "dataset" && datasetSource === "collection" && (
            <label className="flex flex-col gap-1 text-sm text-ink">
              {t("newItem.collectionSourceLabel")}
              <select
                aria-label={t("newItem.collectionSourceLabel")}
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={collectionId}
                onChange={(e) => setCollectionId(e.target.value)}
              >
                <option value="">{t("visualQuery.chooseOption")}</option>
                {(collectionsQuery.data ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind === "dataset" && datasetSource === "arcgis" && (
            <label className="flex flex-col gap-1 text-sm text-ink">
              {t("newItem.arcgisLayerLabel")}
              <select
                aria-label={t("newItem.arcgisLayerLabel")}
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={arcgisItemId}
                onChange={(e) => setArcgisItemId(e.target.value)}
              >
                <option value="">{t("visualQuery.chooseOption")}</option>
                {(featureLayersQuery.data ?? []).map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.title}
                  </option>
                ))}
              </select>
              {featureLayersQuery.data?.length === 0 && (
                <span className="text-xs text-ink-2">{t("newItem.noHarvestedLayers")}</span>
              )}
            </label>
          )}
          <label className="flex flex-col gap-1 text-sm text-ink">
            {t("visualQuery.titleLabel")}
            <Input
              aria-label={t("visualQuery.titleLabel")}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          {kind === "site" && (
            <label className="flex flex-col gap-1 text-sm text-ink">
              {t("newItem.slugLabel")}
              <Input
                aria-label={t("newItem.slugLabel")}
                value={slug}
                onChange={(e) => {
                  setSlug(e.target.value);
                  setSlugTouched(true);
                }}
              />
              {slug && !isValidSlug(slug) && (
                <span className="text-xs text-danger">{t("newItem.invalidSlugMessage")}</span>
              )}
            </label>
          )}
          {(create.isError || createMap.isError || createDataset.isError) && (
            <p role="alert" className="text-sm text-danger">
              {t("newItem.createFailed")}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close}>
              {t("confirmDialog.cancel")}
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={
                create.isPending ||
                createMap.isPending ||
                createDataset.isPending ||
                (kind === "site" && !isValidSlug(slug)) ||
                (kind === "dataset" && datasetSource === "collection" && !collectionId) ||
                (kind === "dataset" && datasetSource === "arcgis" && !arcgisItemId)
              }
            >
              {t("newItem.createButton")}
            </Button>
          </div>
        </form>
      </Drawer>
    </>
  );
}
