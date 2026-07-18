// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateItem, useCreateMap } from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";
import { TEMPLATES } from "../builder/templates";
import { isValidSlug, slugify } from "../lib/slug";

export function NewItemButton() {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"app" | "dashboard" | "map" | "site">("app");
  const [title, setTitle] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const { username } = useAuth();
  const navigate = useNavigate();
  const create = useCreateItem();
  const createMap = useCreateMap();

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
    create.reset();
    createMap.reset();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    if (kind === "site" && !isValidSlug(slug)) return;
    try {
      const item =
        kind === "map"
          ? await createMap.mutateAsync({ title: clean, owner: username ?? "" })
          : await create.mutateAsync({
              kind,
              title: clean,
              owner: username ?? "",
              templateId: templateId || undefined,
              slug: kind === "site" ? slug : undefined,
            });
      close();
      navigate(kind === "map" ? `/maps/${item.pk}` : `/apps/${item.pk}/edit`);
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
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Type
            <select
              aria-label="Type"
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
              value={kind}
              onChange={(e) => { setKind(e.target.value as "app" | "dashboard" | "map" | "site"); setTemplateId(""); }}
            >
              <option value="app">App</option>
              <option value="dashboard">Dashboard</option>
              <option value="map">Map</option>
              <option value="site">Site</option>
            </select>
          </label>
          {kind !== "map" && (
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
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </label>
          )}
          <label className="flex flex-col gap-1 text-sm">
            Titre
            <Input
              aria-label="Titre"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          {kind === "site" && (
            <label className="flex flex-col gap-1 text-sm">
              Slug
              <Input
                aria-label="Slug"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); setSlugTouched(true); }}
              />
              {slug && !isValidSlug(slug) && (
                <span className="text-xs text-red-600">Slug invalide (minuscules, chiffres, tirets).</span>
              )}
            </label>
          )}
          {(create.isError || createMap.isError) && (
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
              disabled={create.isPending || createMap.isPending || (kind === "site" && !isValidSlug(slug))}
            >
              Créer
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
