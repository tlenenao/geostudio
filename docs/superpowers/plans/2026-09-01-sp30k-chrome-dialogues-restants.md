# SP-30k — Chrome (NewItemButton/ImportFileButton/Tileset3DUploadButton) : dialogues → Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer les trois derniers composants de chrome qui utilisent
encore l'ancienne primitive `ui/dialog.tsx` — `NewItemButton`,
`ImportFileButton`, `Tileset3DUploadButton` (`shell/src/shell/`,
`docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` §2.1,
liste de « Suppression ») — vers `ui/kit/Drawer`, en migrant au passage leurs
`Button`/`Input` internes vers le kit et leurs couleurs Tailwind en dur vers
les tokens. Les 12 pages de la spec (familles 1-9, SP-30a→j) sont toutes
basculées ; ces trois boutons sont le dernier reliquat nommé explicitement
par `docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md:70`
(`ImportFileButton`, `NewItemButton`, `Tileset3DUploadButton`) qui reste sur
l'ancienne primitive. `ItemActions` (même liste) est déjà kit-ifié — vérifié
par lecture directe de `shell/src/shell/ItemActions.tsx` avant d'écrire ce
plan (piège n°3) : il consomme déjà `ui/kit/Button`/`ui/kit/ConfirmDialog`,
rien à faire dessus ici.

**Ce que ce plan NE fait PAS** :
- **N'utilise pas `ui/kit/Dialog` (le composant centré) pour ces trois
  boutons.** `ui/kit/Dialog.tsx` n'a aujourd'hui qu'un seul consommateur :
  `ui/kit/ConfirmDialog.tsx` — vérifié par grep avant d'écrire ce plan
  (`grep -rln 'kit/Dialog"' src` ne retourne que ce fichier). La spec est
  explicite : « Seul `ConfirmDialog` survit […] confirmation d'action
  destructive uniquement » (§2.1). Aucun des trois boutons de ce plan n'est
  une confirmation destructive (ce sont des formulaires de création/import) :
  leur utiliser `ui/kit/Dialog` élargirait la liste des consommateurs de ce
  composant réservé, contredisant l'intention de la spec.
- **N'utilise pas non plus « contenu de volet d'une page »**, à la
  différence de toutes les conversions précédentes (SP-30c→j). Ces trois
  composants ne sont montés nulle part dans une page : ils vivent dans
  `TopBar` (`shell/src/shell/chrome/TopBar.tsx:12-14`), le chrome global
  rendu au-dessus de **toutes** les routes protégées — il n'existe pas de
  « page hôte » dont le triptyque pourrait accueillir leur formulaire en
  onglet Détail/Inspecter, contrairement à `ExportPanel` (`MapEditorPage`) ou
  aux cinq dialogues admin (SP-30j). `ui/kit/Drawer` (déjà livré par SP-29b,
  jamais consommé en dehors de `KitGalleryPage.tsx` avant ce plan — vérifié
  par grep) est le composant du kit conçu précisément pour ce cas : une
  action globale, indépendante de toute page, qui doit rester joignable
  depuis n'importe où. Ce plan en est le premier consommateur de production.
- **Ne supprime pas `ui/dialog.tsx`, `ui/button.tsx`, `ui/input.tsx`
  eux-mêmes.** `shell/src/pages/AppRuntimePage.tsx` (rendu public d'une app,
  hors périmètre de SP-30 — spec §2.2 : « `AppRuntimePage` […] — inchangés »)
  et `shell/src/builder/widgets/modal.tsx` (le widget runtime « Modale »,
  consommé par `AppRenderer(config, mode)` à l'intérieur d'une app publiée —
  pas un écran de chrome/admin, jamais importé par aucune page basculée par
  SP-30 : vérifié par `grep -rln "widgets/modal" src` avant d'écrire ce
  plan, aucun résultat en dehors du fichier lui-même et de son enregistrement
  dans le registre de widgets) continuent d'en dépendre après ce plan. Les
  trois primitives restent donc dans l'arbre — leur suppression n'est un
  critère de sortie d'aucune spec ; seul leur usage dans le **chrome/admin**
  (§2.1) devait disparaître, et c'est chose faite après ce plan.
- **Ne touche pas `TopBar.tsx` ni `TopBar.test.tsx`.** `TopBar` monte déjà
  les trois composants sans connaître leur implémentation interne ; son test
  les mocke entièrement (`vi.mock("../NewItemButton", …)` etc.,
  `TopBar.test.tsx:20-26`) — aucune des deux modifications de ce plan n'y est
  visible.
- **Ne fait pas la revue transverse de fin de SP-30** (spec §7, « la plus
  grosse revue de branche jamais pratiquée sur ce dépôt : 16 pages, 20
  routes »). Ce plan clôt la dernière brique **nommée** de la spec §2.1 ; la
  revue de sortie complète (les 8 critères du §7, badge de rôle sur les
  quatre profils, 390 px sur les 8 écrans de référence, etc.) reste à faire
  dans une étape séparée après ce plan — hors périmètre ici.

**Décision de conception (à ne pas re-débattre en exécution) :** `Drawer`
attend `onOpenChange(open: boolean)`, pas `onClose()`. Radix appelle
`onOpenChange(false)` aussi bien sur Échap que sur un pointerdown hors du
panneau (clic sur la zone assombrie) — **vérifié empiriquement avant
d'écrire ce plan** (piège n°3 : jamais présumé) via un composant de sonde
jetable (`Drawer` + un bouton `toggle-busy` placé **dans** son contenu, pour
éviter le `pointer-events: none` que Radix pose sur le reste de la page
pendant qu'un dialogue modal est ouvert — un premier essai avec le bouton
hors du `Drawer` échouait pour cette raison, pas pour une raison liée à
`Drawer` lui-même) : `fireEvent.keyDown(document, { key: "Escape" })` et
`await userEvent.click(overlay)` (où `overlay` est
`dialog.previousSibling`, le `DialogPrimitive.Overlay` rendu juste avant le
contenu portalé) appellent tous deux `onOpenChange(false)`, et ignorer cet
appel quand un état `busy` est vrai bloque effectivement les deux — jetable
supprimé après vérification, jamais commité. Chaque composant convertit donc
son ancien funnel `onClose` en `onOpenChange={(next) => !next &&
<funnel>()}` :
- `NewItemButton`/`ImportFileButton` n'avaient **aucune garde `busy`** sur
  leur ancien `onClose` (Échap/clic-hors fermaient toujours, même
  `create.isPending`) — ce plan **préserve ce comportement à l'identique**,
  pas une régression à corriger ici : `onOpenChange={(next) => !next &&
  close()}` suffit, aucune tâche de ce plan n'ajoute de garde qui n'existait
  pas.
- `Tileset3DUploadButton` avait la garde `busy` documentée en commentaire
  (`requestClose()`, ligne ~106 de l'ancien fichier) et testée
  explicitement (« blocks closing (Annuler, Escape, backdrop) while an
  upload is in progress ») : ce plan **la préserve**, adaptée à
  `onOpenChange={(next) => !next && requestClose()}` — Task 3 réécrit le
  test correspondant, dont l'ancien sélecteur de fond
  (`container.querySelector('[aria-hidden="true"]')`) reposait sur le
  balisage fait main de `ui/dialog.tsx` (`<div … aria-hidden="true"
  onClick={onClose} />`, `shell/src/ui/dialog.tsx:30`) : le
  `DialogPrimitive.Overlay` de Radix (utilisé par `Drawer`) ne porte **pas**
  `aria-hidden="true"` — confirmé par la sonde ci-dessus, pas par lecture du
  code Radix seule.

**Architecture:** Chacun des trois fichiers remplace `import { Dialog } from
"../ui/dialog"` par `import { Drawer } from "../ui/kit/Drawer"`, et
`import { Button } from "../ui/button"` / `import { Input } from
"../ui/input"` par leurs équivalents `ui/kit/*`. `<Dialog open={open}
onClose={fn} title="…">…</Dialog>` devient `<Drawer open={open}
onOpenChange={(next) => !next && fn()} title="…">…</Drawer>` — même
structure de formulaire interne, inchangée, seules les couleurs Tailwind en
dur (`border-slate-300`, `bg-white`, `text-red-600`, `text-slate-500`)
deviennent des tokens (`border-rule`, `bg-surface`, `text-danger`,
`text-ink-2`, `text-ink`). Aucun changement de comportement fonctionnel
hors de la garde `busy` de `Tileset3DUploadButton`, déjà présente et
préservée à l'identique.

**Tech Stack:** React 19, `@radix-ui/react-dialog` (via `ui/kit/Drawer`,
déjà livré SP-29b), Vitest + Testing Library, MSW, Playwright.

## Global Constraints

- Docs et identifiants de test en français ; code/identifiants en anglais
  (CLAUDE.md).
- Aucune couleur Tailwind en dur (`slate-*`, `red-*`, `blue-*`, `gray-*`,
  `white`, `black`) dans les trois fichiers touchés : tokens uniquement
  (`bg-surface`, `text-ink`, `text-ink-2`, `border-rule`, `text-danger` —
  `shell/src/styles/tokens.css`).
- Aucun import résiduel de `ui/button"`, `ui/input"` ou `ui/dialog"` dans les
  trois fichiers touchés après leur tâche respective.
- Pas de changement au cœur (`core/`) dans ce plan. Diff vide attendu
  (vérifié en Task 4). Régénération OpenAPI/TS **non nécessaire**.
- `TopBar` est monté sur **toutes** les routes protégées : une régression
  dans l'un de ces trois composants n'est pas isolée à une seule page.
  Suite E2E **complète** (`npm run e2e`) exigée après **chaque** tâche de ce
  plan (pas seulement à la fin) — risque plus large que les conversions
  page-par-page de SP-30c→j, où une régression restait bornée à la page
  concernée (piège n°6, aggravé ici par la portée globale du composant).
- `Drawer` (`shell/src/ui/kit/Drawer.tsx`) n'a jamais eu de consommateur de
  production avant ce plan : toute divergence de comportement par rapport à
  l'ancien `ui/dialog.tsx` (garde de fermeture, sélecteur de fond dans les
  tests) doit être vérifiée empiriquement, pas supposée depuis le code de
  `ConfirmDialog`/`ui/kit/Dialog` (piège n°3 — voir la sonde jetable décrite
  ci-dessus).
- Pas de stub `matchMedia` nécessaire dans les fichiers de test de ce plan :
  aucun des trois composants ne consomme `TriptychLayout`/
  `useNarrowViewport` (piège n°10 sans objet ici).

---

## Task 1: Shell — `NewItemButton` : `Dialog` → `Drawer`, kit + tokens

**Files:**
- Modify: `shell/src/shell/NewItemButton.tsx`

**Interfaces:**
- Consumes: `Drawer` (`shell/src/ui/kit/Drawer.tsx`, props `open`/
  `onOpenChange`/`title`/`side?`/`children`) ; `Button`/`Input`
  (`shell/src/ui/kit/`).
- Produces: `NewItemButton()` — aucune prop, inchangé ; consommé par
  `TopBar.tsx` sans changement d'interface.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/shell/NewItemButton.test.tsx
```

Expected: PASS — 17 tests, état actuel avant modification.

- [ ] **Step 2: Réécrire `NewItemButton.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
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
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Drawer } from "../ui/kit/Drawer";
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
      <Drawer open={open} onOpenChange={(next) => !next && close()} title="Nouvel élément">
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
```

- [ ] **Step 3: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/shell/NewItemButton.test.tsx
```

Expected: PASS — 17 tests, **sans aucune modification du fichier de test**
(`screen.getByRole("dialog", { name: /nouvel/i })`, ligne 58, matche
`Drawer` de façon identique : `DialogPrimitive.Title` de Radix rend un
`<h2>` réel et porte le nom accessible via `aria-labelledby`, même que
l'ancien `role="dialog" aria-label={title}` fait main).

- [ ] **Step 4: Vérifier l'absence de couleur Tailwind en dur et d'ancien import**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/shell/NewItemButton.tsx
grep -n 'ui/button"\|ui/input"\|ui/dialog"' shell/src/shell/NewItemButton.tsx
```

Expected: aucune sortie pour les deux commandes.

- [ ] **Step 5: Suite E2E complète (piège n°6, aggravé — `TopBar` est global)**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed, ou mieux.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/shell/NewItemButton.tsx
git commit -m "feat(shell): newItemButton — dialogue converti en Drawer (kit)"
```

---

## Task 2: Shell — `ImportFileButton` : `Dialog` → `Drawer`, kit + tokens

**Files:**
- Modify: `shell/src/shell/ImportFileButton.tsx`

**Interfaces:**
- Consumes: `Drawer`, `Button`/`Input` (`shell/src/ui/kit/`).
- Produces: `ImportFileButton()` — aucune prop, inchangé.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/shell/ImportFileButton.test.tsx
```

Expected: PASS — 6 tests, état actuel avant modification.

- [ ] **Step 2: Réécrire `ImportFileButton.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Drawer } from "../ui/kit/Drawer";

type Phase = "form" | "uploading" | "selecting-layer" | "polling" | "error";
type LayerInfo = { name: string; featureCount: number; geometryType: string };

const LAT_NAMES = ["lat", "latitude", "y"];
const LON_NAMES = ["lon", "lng", "longitude", "x"];

function detectLatLon(headers: string[]): boolean {
  const byLower = new Set(headers.map((h) => h.trim().toLowerCase()));
  const hasLat = LAT_NAMES.some((n) => byLower.has(n));
  const hasLon = LON_NAMES.some((n) => byLower.has(n));
  return hasLat && hasLon;
}

function isLayeredFormat(filename: string): boolean {
  const lower = filename.toLowerCase();
  return lower.endsWith(".gpkg") || lower.endsWith(".zip");
}

export function ImportFileButton() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [csvHeaders, setCsvHeaders] = useState<string[] | null>(null);
  const [latField, setLatField] = useState("");
  const [lonField, setLonField] = useState("");
  const [uploadedKey, setUploadedKey] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerInfo[]>([]);
  const [layerName, setLayerName] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const client = useItemClient();
  const navigate = useNavigate();

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setCsvHeaders(null);
    setLatField("");
    setLonField("");
    setUploadedKey(null);
    setLayers([]);
    setLayerName("");
    setPhase("form");
    setError("");
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setCsvHeaders(null);
    if (f && f.name.toLowerCase().endsWith(".csv")) {
      const blob = f.slice(0, 4096);
      const text = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => resolve("");
        reader.readAsText(blob);
      });
      const firstLine = text.split(/\r?\n/)[0] ?? "";
      const headers = firstLine.split(",").map((h) => h.trim());
      if (!detectLatLon(headers)) setCsvHeaders(headers);
    }
  }

  const needsManualLatLon = csvHeaders !== null;

  async function poll(jobId: string) {
    for (;;) {
      const job = await client.getIngestionJob(jobId);
      if (job.status === "done" && job.itemId) {
        close();
        navigate(`/maps/${job.itemId}`);
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? "Échec de l'import.");
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function startJob(key: string, chosenLayerName: string | undefined) {
    const { jobId } = await client.createIngestionJob({
      key,
      filename: file!.name,
      collectionTitle: title.trim(),
      latField: needsManualLatLon ? latField : undefined,
      lonField: needsManualLatLon ? lonField : undefined,
      layerName: chosenLayerName,
    });
    setPhase("polling");
    await poll(jobId);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    if (needsManualLatLon && (!latField || !lonField)) return;
    setPhase("uploading");
    setError("");
    try {
      const { uploadUrl, key } = await client.presignUpload(
        file.name,
        file.type || "application/octet-stream",
      );
      await client.uploadToPresignedUrl(uploadUrl, file);
      if (isLayeredFormat(file.name)) {
        const { layers: found } = await client.inspectUpload({ key, filename: file.name });
        if (found.length > 1) {
          setUploadedKey(key);
          setLayers(found);
          setPhase("selecting-layer");
          return;
        }
        await startJob(key, found[0]?.name);
        return;
      }
      await startJob(key, undefined);
    } catch {
      setPhase("error");
      setError("Échec de l'import.");
    }
  }

  async function confirmLayer(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadedKey || !layerName) return;
    setPhase("uploading");
    setError("");
    try {
      await startJob(uploadedKey, layerName);
    } catch {
      setPhase("error");
      setError("Échec de l'import.");
    }
  }

  const busy = phase === "uploading" || phase === "polling";

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Importer un fichier
      </Button>
      <Drawer open={open} onOpenChange={(next) => !next && close()} title="Importer un fichier">
        {phase === "selecting-layer" ? (
          <form onSubmit={(e) => void confirmLayer(e)} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm text-ink">
              Couche à importer
              <select
                aria-label="Couche à importer"
                className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                value={layerName}
                onChange={(e) => setLayerName(e.target.value)}
              >
                <option value="">—</option>
                {layers.map((l) => (
                  <option key={l.name} value={l.name}>
                    {l.name} ({l.featureCount} entités)
                  </option>
                ))}
              </select>
            </label>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close}>
                Annuler
              </Button>
              <Button type="submit" size="sm" disabled={!layerName}>
                Continuer
              </Button>
            </div>
          </form>
        ) : (
          <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm text-ink">
              Fichier à importer
              <input
                aria-label="Fichier à importer"
                type="file"
                accept=".geojson,.json,.csv,.gpkg,.zip"
                onChange={(e) => void onFileChange(e)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-ink">
              Titre de la collection
              <Input
                aria-label="Titre de la collection"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            {needsManualLatLon && (
              <>
                <label className="flex flex-col gap-1 text-sm text-ink">
                  Colonne latitude
                  <select
                    aria-label="Colonne latitude"
                    className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                    value={latField}
                    onChange={(e) => setLatField(e.target.value)}
                  >
                    <option value="">—</option>
                    {csvHeaders!.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-sm text-ink">
                  Colonne longitude
                  <select
                    aria-label="Colonne longitude"
                    className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                    value={lonField}
                    onChange={(e) => setLonField(e.target.value)}
                  >
                    <option value="">—</option>
                    {csvHeaders!.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            {phase === "error" && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close}>
                Annuler
              </Button>
              <Button type="submit" size="sm" disabled={busy}>
                {phase === "uploading"
                  ? "Envoi…"
                  : phase === "polling"
                    ? "Import en cours…"
                    : "Importer"}
              </Button>
            </div>
          </form>
        )}
      </Drawer>
    </>
  );
}
```

- [ ] **Step 3: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/shell/ImportFileButton.test.tsx
```

Expected: PASS — 6 tests, sans modification du fichier de test (aucune
assertion existante ne dépend du rôle `dialog` ni du balisage interne de
`Dialog`/`Drawer`).

- [ ] **Step 4: Vérifier l'absence de couleur Tailwind en dur et d'ancien import**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/shell/ImportFileButton.tsx
grep -n 'ui/button"\|ui/input"\|ui/dialog"' shell/src/shell/ImportFileButton.tsx
```

Expected: aucune sortie pour les deux commandes.

- [ ] **Step 5: Suite E2E complète**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed, ou mieux.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/shell/ImportFileButton.tsx
git commit -m "feat(shell): importFileButton — dialogue converti en Drawer (kit)"
```

---

## Task 3: Shell — `Tileset3DUploadButton` : `Dialog` → `Drawer`, garde de fermeture préservée

**Files:**
- Modify: `shell/src/shell/Tileset3DUploadButton.tsx`
- Modify: `shell/src/shell/Tileset3DUploadButton.test.tsx`

**Interfaces:**
- Consumes: `Drawer`, `Button`/`Input` (`shell/src/ui/kit/`).
- Produces: `Tileset3DUploadButton({ pollTimeoutMs?: number })` — signature
  inchangée.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/shell/Tileset3DUploadButton.test.tsx
```

Expected: PASS — 4 tests, état actuel avant modification.

- [ ] **Step 2: Réécrire `Tileset3DUploadButton.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Drawer } from "../ui/kit/Drawer";

// S3 multipart accepts a single part of any size — the same chunking code
// path serves a tiny test fixture and a multi-GB tileset (design §4,
// Global Constraints). 100 MB keeps individual PUTs reasonable over a
// typical connection without adding meaningful per-part overhead.
const PART_SIZE_BYTES = 100 * 1024 * 1024;

// A finalize job that never reaches a terminal state (stuck/lost
// procrastinate job) must not leave the drawer permanently unclosable —
// the close-guard blocks Annuler/Escape/outside-pointerdown while busy, and
// "finalizing" counts as busy.
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

type Phase = "form" | "uploading" | "finalizing" | "error";

// pollTimeoutMs is injectable for tests only (this file's suite is MSW-based
// with real timers, where fake timers would fight userEvent's own scheduler).
export function Tileset3DUploadButton({
  pollTimeoutMs = POLL_TIMEOUT_MS,
}: { pollTimeoutMs?: number } = {}) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const client = useItemClient();

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setPhase("form");
    setError("");
    setProgress(null);
  }

  async function poll(jobId: string) {
    const deadline = Date.now() + pollTimeoutMs;
    for (;;) {
      const job = await client.getTileset3DUploadJob(jobId);
      if (job.status === "done") {
        close();
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? "Échec de la validation du tileset.");
        return;
      }
      if (Date.now() >= deadline) {
        setPhase("error");
        setError("La validation du tileset prend trop de temps. Réessayez plus tard.");
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    setPhase("uploading");
    setError("");
    try {
      const { jobId } = await client.createTileset3DUpload({
        filename: file.name,
        title: title.trim(),
      });
      const partCount = Math.max(1, Math.ceil(file.size / PART_SIZE_BYTES));
      setProgress({ done: 0, total: partCount });
      const parts: { partNumber: number; etag: string }[] = [];
      for (let i = 0; i < partCount; i++) {
        const partNumber = i + 1;
        const chunk = file.slice(i * PART_SIZE_BYTES, (i + 1) * PART_SIZE_BYTES);
        const { uploadUrl } = await client.presignTileset3DUploadPart(jobId, partNumber);
        const res = await fetch(uploadUrl, { method: "PUT", body: chunk });
        if (!res.ok) throw new Error(`Échec de l'envoi de la partie ${partNumber}.`);
        const etag = res.headers.get("ETag") ?? "";
        parts.push({ partNumber, etag });
        setProgress({ done: partNumber, total: partCount });
      }
      setPhase("finalizing");
      await client.completeTileset3DUpload(jobId, parts);
      await poll(jobId);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Échec de l'envoi du tileset.");
    }
  }

  const busy = phase === "uploading" || phase === "finalizing";

  // Closing mid-upload would leave the background submit()/poll() chain
  // running unabandoned: it would eventually call close() again (silently
  // discarding whatever the user started in a since-reopened drawer) or
  // setPhase("error") (overwriting that session's state). Block Escape,
  // outside pointerdown, and the Annuler button alike while busy —
  // Drawer's onOpenChange is the single funnel for Escape and outside
  // pointerdown (Radix calls it with `false` for both); the Annuler button
  // calls close() directly, which is why it also needs its own
  // disabled={busy} below.
  function requestClose() {
    if (busy) return;
    close();
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Nouveau tileset 3D
      </Button>
      <Drawer
        open={open}
        onOpenChange={(next) => !next && requestClose()}
        title="Nouveau tileset 3D"
      >
        <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm text-ink">
            Archive du tileset (.zip)
            <input
              aria-label="Archive du tileset (.zip)"
              type="file"
              accept=".zip"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink">
            Titre
            <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          {progress && (
            <p className="text-sm text-ink-2">
              Envoi de la partie {progress.done}/{progress.total}…
            </p>
          )}
          {phase === "finalizing" && <p className="text-sm text-ink-2">Validation du tileset…</p>}
          {phase === "error" && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close} disabled={busy}>
              Annuler
            </Button>
            <Button type="submit" size="sm" disabled={busy || !file || !title.trim()}>
              {busy ? "Envoi…" : "Importer"}
            </Button>
          </div>
        </form>
      </Drawer>
    </>
  );
}
```

- [ ] **Step 3: Réécrire le test « blocks closing » dans `Tileset3DUploadButton.test.tsx`**

Dans `shell/src/shell/Tileset3DUploadButton.test.tsx`, remplacer le dernier
test du fichier (« blocks closing (Annuler, Escape, backdrop) while an
upload is in progress ») par :

```tsx
test("blocks closing (Annuler, Escape, outside pointerdown) while an upload is in progress", async () => {
  let releaseCreate: () => void = () => {};
  const createGate = new Promise<void>((resolve) => {
    releaseCreate = resolve;
  });
  server.use(
    http.post("https://core.test/tileset3d/uploads", async () => {
      // Held open deliberately: keeps phase at "uploading" so the test can
      // assert the close guard while the request chain is still in flight.
      await createGate;
      return HttpResponse.json({ jobId: "job-1" }, { status: 201 });
    }),
    http.post("https://core.test/tileset3d/uploads/job-1/parts/1/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/part-1" }),
    ),
    http.put(
      "https://minio.test/part-1",
      () => new HttpResponse(null, { status: 200, headers: { ETag: '"etag-1"' } }),
    ),
    http.post(
      "https://core.test/tileset3d/uploads/job-1/complete",
      () => new HttpResponse(null, { status: 204 }),
    ),
    http.get("https://core.test/tileset3d/uploads/job-1", () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "item-1" }),
    ),
  );

  render(
    <Harness>
      <Tileset3DUploadButton />
    </Harness>,
  );
  await userEvent.click(screen.getByText("Nouveau tileset 3D"));
  await userEvent.upload(screen.getByLabelText("Archive du tileset (.zip)"), zipFile());
  await userEvent.type(screen.getByLabelText("Titre"), "Ville");
  await userEvent.click(screen.getByText("Importer"));

  const cancelButton = await screen.findByText("Annuler");
  await waitFor(() => expect(cancelButton).toBeDisabled());

  // Clicking a disabled button fires no onClick handler — this proves the
  // button itself can no longer trigger a close, not just that it looks
  // disabled.
  await userEvent.click(cancelButton);
  expect(screen.getByText("Nouveau tileset 3D", { selector: "h2" })).toBeInTheDocument();

  // Escape is wired through Drawer's onOpenChange, the same guarded handler.
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.getByText("Nouveau tileset 3D", { selector: "h2" })).toBeInTheDocument();

  // Outside pointerdown goes through the same funnel. Radix's
  // DialogPrimitive.Overlay (rendered by Drawer) does not carry
  // aria-hidden="true" — unlike the old hand-rolled ui/dialog.tsx backdrop
  // this test used to target — so it's located as the sibling immediately
  // before the role="dialog" content instead.
  const dialog = screen.getByRole("dialog", { name: "Nouveau tileset 3D" });
  const overlay = dialog.previousSibling as Element;
  await userEvent.click(overlay);
  expect(screen.getByText("Nouveau tileset 3D", { selector: "h2" })).toBeInTheDocument();

  // Let the held request settle so the upload completes normally and
  // doesn't leak a pending promise into the next test.
  releaseCreate();
  await waitFor(() =>
    expect(screen.queryByText("Nouveau tileset 3D", { selector: "h2" })).not.toBeInTheDocument(),
  );
});
```

Note : la signature de `render(...)` perd sa destructuration `{ container }`
(`const { container } = render(…)` → `render(…)`) — plus aucun test du
fichier n'a besoin de `container` après ce changement.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/shell/Tileset3DUploadButton.test.tsx
```

Expected: PASS — 4 tests (les trois premiers inchangés — leur sélecteur
`{ selector: "h2" }` matche `Drawer` à l'identique, `DialogPrimitive.Title`
rend un `<h2>` réel ; le quatrième réécrit à l'étape précédente).

- [ ] **Step 5: Vérifier l'absence de couleur Tailwind en dur et d'ancien import**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/shell/Tileset3DUploadButton.tsx
grep -n 'ui/button"\|ui/input"\|ui/dialog"' shell/src/shell/Tileset3DUploadButton.tsx
```

Expected: aucune sortie pour les deux commandes.

- [ ] **Step 6: Suite E2E complète**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed, ou mieux (couvre
`e2e/tileset3d.spec.ts`, qui exerce `Tileset3DUploadButton` derrière
`CORE_TILESET3D_ENABLED`).

- [ ] **Step 7: Commit**

```bash
cd shell && git add src/shell/Tileset3DUploadButton.tsx src/shell/Tileset3DUploadButton.test.tsx
git commit -m "feat(shell): tileset3DUploadButton — dialogue converti en Drawer (kit), garde de fermeture préservée"
```

---

## Task 4: Vérification finale

Ce plan ne se termine pas par un commit propre — c'est une tâche de
vérification. Si un des steps échoue, revenir à la tâche responsable
(identifiable par le fichier en cause) pour corriger, jamais par un
correctif générique ici.

- [ ] **Step 1: Suite Vitest complète**

```bash
cd shell && npx vitest run
```

Expected: PASS — 219 fichiers / 1833 tests (nombre de fichiers inchangé —
ce plan ne crée ni ne supprime aucun fichier ; nombre de tests inchangé lui
aussi : 17 `NewItemButton.test.tsx` + 6 `ImportFileButton.test.tsx` + 4
`Tileset3DUploadButton.test.tsx`, mêmes comptes qu'avant ce plan — chiffres
à confirmer par l'exécution réelle plutôt que recalculés à la main, cf.
verification-before-completion), aucune régression sur les fichiers non
touchés.

- [ ] **Step 2: Couverture**

```bash
rm -rf shell/dist shell/dist-export
cd shell && npm run build
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```

Expected: seuil 88 respecté (piège documenté quatre fois : nettoyer
`dist/`/`dist-export/` avant de mesurer).

- [ ] **Step 3: Suite E2E complète (dernière exécution, après tous les commits de ce plan)**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed, ou mieux.

- [ ] **Step 4: Lint + format + contrat de couches**

```bash
cd shell && npm run lint && npm run format:check
cd core && uv run lint-imports
```

Expected: PASS, aucune nouvelle entrée de contrat de couches (aucun
changement au cœur dans ce plan).

- [ ] **Step 5: Confirmer l'absence de tout changement côté cœur**

```bash
git status --short core/
```

Expected: aucune sortie.

- [ ] **Step 6: Confirmer que les seuls consommateurs restants de `ui/dialog.tsx` sont hors périmètre par doctrine**

```bash
grep -rln 'ui/dialog"' shell/src --include="*.tsx"
```

Expected : exactement deux fichiers — `shell/src/pages/AppRuntimePage.tsx`
(rendu public, spec §2.2, inchangé) et
`shell/src/builder/widgets/modal.tsx` (widget runtime « Modale », rendu par
`AppRenderer` à l'intérieur d'une app publiée, jamais un écran de
chrome/admin — voir « Ce que ce plan NE fait PAS »). Aucun des trois
fichiers de ce plan n'apparaît plus dans cette liste.

- [ ] **Step 7: Confirmer que `ui/button.tsx`/`ui/input.tsx` n'ont plus de consommateur dans `shell/src/shell/`**

```bash
grep -rln 'ui/button"\|ui/input"' shell/src/shell --include="*.tsx"
```

Expected: aucune sortie — tous les composants de `shell/src/shell/`
(chrome + admin) consomment désormais `ui/kit/*` exclusivement.

- [ ] **Step 8: Recherche exhaustive de couleurs Tailwind en dur résiduelles dans les trois fichiers touchés**

```bash
grep -rnE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/shell/NewItemButton.tsx \
  shell/src/shell/ImportFileButton.tsx \
  shell/src/shell/Tileset3DUploadButton.tsx
```

Expected: aucune sortie.
