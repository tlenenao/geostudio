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
} from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";
import { TEMPLATES } from "../builder/templates";
import { isValidSlug, slugify } from "../lib/slug";

type Kind = "app" | "dashboard" | "map" | "site" | "dataset" | "pipeline" | "visual-query";

export function NewItemButton() {
  const [open, setOpen] = useState(false);
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

  // Slug auto-suivi du titre tant que l'utilisateur ne l'a pas édité lui-même.
  useEffect(() => {
    if (kind === "site" && !slugTouched) setSlug(slugify(title));
  }, [title, kind, slugTouched]);

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
      <Button size="sm" onClick={() => setOpen(true)}>
        Nouveau
      </Button>
      <Dialog open={open} onClose={close} title="Nouvel élément">
        <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Type
            <select
              aria-label="Type"
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as Kind);
                setTemplateId("");
              }}
            >
              <option value="app">App</option>
              <option value="dashboard">Dashboard</option>
              <option value="map">Map</option>
              <option value="site">Site</option>
              <option value="dataset">Dataset partagé</option>
              {etlEnabled && <option value="visual-query">Dataset par requête visuelle</option>}
              {etlEnabled && <option value="pipeline">Pipeline</option>}
            </select>
          </label>
          {kind !== "map" && kind !== "dataset" && kind !== "pipeline" && (
            <label className="flex flex-col gap-1 text-sm">
              Modèle
              <select
                aria-label="Modèle"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
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
            <label className="flex flex-col gap-1 text-sm">
              Type de source
              <select
                aria-label="Type de source"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                value={datasetSource}
                onChange={(e) => setDatasetSource(e.target.value as "collection" | "arcgis")}
              >
                <option value="collection">Collection</option>
                <option value="arcgis">ArcGIS Feature Service</option>
              </select>
            </label>
          )}
          {kind === "dataset" && datasetSource === "collection" && (
            <label className="flex flex-col gap-1 text-sm">
              Collection source
              <select
                aria-label="Collection source"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
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
            <label className="flex flex-col gap-1 text-sm">
              Couche ArcGIS
              <select
                aria-label="Couche ArcGIS"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
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
                <span className="text-xs text-slate-500">
                  Aucune couche moissonnée. Configurez une source de moissonnage ArcGIS (mode
                  référence) dans l'administration.
                </span>
              )}
            </label>
          )}
          <label className="flex flex-col gap-1 text-sm">
            Titre
            <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          {kind === "site" && (
            <label className="flex flex-col gap-1 text-sm">
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
                <span className="text-xs text-red-600">
                  Slug invalide (minuscules, chiffres, tirets).
                </span>
              )}
            </label>
          )}
          {(create.isError || createMap.isError || createDataset.isError) && (
            <p role="alert" className="text-sm text-red-600">
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
      </Dialog>
    </>
  );
}
