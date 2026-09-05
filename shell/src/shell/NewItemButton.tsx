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
        Nouveau
      </Button>
      <Drawer
        open={open}
        onOpenChange={(next) => !next && close()}
        title="Nouvel élément"
        id={drawerPanel.panelId}
      >
        <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm text-ink">
            Type
            <select
              aria-label="Type"
              className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as Kind);
                setTemplateId("");
              }}
            >
              {canCreateApp && <option value="app">App</option>}
              {canCreateApp && <option value="dashboard">Dashboard</option>}
              {canCreateMap && <option value="map">Map</option>}
              {canCreateApp && <option value="site">Site</option>}
              {canCreateDataset && <option value="dataset">Dataset partagé</option>}
              {etlEnabled && <option value="visual-query">Dataset par requête visuelle</option>}
              {etlEnabled && <option value="pipeline">Pipeline</option>}
            </select>
          </label>
          {kind !== "map" && kind !== "dataset" && kind !== "pipeline" && (
            <label className="flex flex-col gap-1 text-sm text-ink">
              Modèle
              <select
                aria-label="Modèle"
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
              >
                <option value="">Vide</option>
                {TEMPLATES.filter((t) => t.kind === kind).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind === "dataset" && (
            <label className="flex flex-col gap-1 text-sm text-ink">
              Type de source
              <select
                aria-label="Type de source"
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={datasetSource}
                onChange={(e) => setDatasetSource(e.target.value as "collection" | "arcgis")}
              >
                <option value="collection">Collection</option>
                <option value="arcgis">ArcGIS Feature Service</option>
              </select>
            </label>
          )}
          {kind === "dataset" && datasetSource === "collection" && (
            <label className="flex flex-col gap-1 text-sm text-ink">
              Collection source
              <select
                aria-label="Collection source"
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={collectionId}
                onChange={(e) => setCollectionId(e.target.value)}
              >
                <option value="">Choisir…</option>
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
              Couche ArcGIS
              <select
                aria-label="Couche ArcGIS"
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={arcgisItemId}
                onChange={(e) => setArcgisItemId(e.target.value)}
              >
                <option value="">Choisir…</option>
                {(featureLayersQuery.data ?? []).map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.title}
                  </option>
                ))}
              </select>
              {featureLayersQuery.data?.length === 0 && (
                <span className="text-xs text-ink-2">
                  Aucune couche moissonnée. Configurez une source de moissonnage ArcGIS (mode
                  référence) dans l'administration.
                </span>
              )}
            </label>
          )}
          <label className="flex flex-col gap-1 text-sm text-ink">
            Titre
            <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          {kind === "site" && (
            <label className="flex flex-col gap-1 text-sm text-ink">
              Slug
              <Input
                aria-label="Slug"
                value={slug}
                onChange={(e) => {
                  setSlug(e.target.value);
                  setSlugTouched(true);
                }}
              />
              {slug && !isValidSlug(slug) && (
                <span className="text-xs text-danger">
                  Slug invalide (minuscules, chiffres, tirets).
                </span>
              )}
            </label>
          )}
          {(create.isError || createMap.isError || createDataset.isError) && (
            <p role="alert" className="text-sm text-danger">
              Échec de la création.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Annuler
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
              Créer
            </Button>
          </div>
        </form>
      </Drawer>
    </>
  );
}
