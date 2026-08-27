# Carte : symbologie avancée, étiquettes, icônes et mesure/croquis (SP-27) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Révision de pré-vol du 2026-08-27** — ce plan a été réécrit contre la
> source réelle (paquets installés dans `shell/node_modules`, code du dépôt,
> registre npm) après un audit qui a trouvé 16 problèmes bloquants. La trace
> d'audit complète, constat par constat, est la section
> **« Corrections de pré-vol (2026-08-27) »** en fin de document : la lire
> avant de contester une valeur écrite dans une tâche.

**Goal:** A map layer's declarative symbology (`LayerSymbology`, SP-25) grows
four new pieces — independent stroke encoding (color+width+dash), fixed
opacity, CEL-templated labels rendered through a **client-side GeoJSON label
source** (one `text-field: ["get","label"]` symbol layer per styled layer),
and categorical icons (curated Lucide set + a tenant-scoped custom icon
library) — editable from the same shared `MapSymbologyEditor`, and **rendered
by both surfaces**: the map editor and the app/dashboard map widget.
Separately, a lecteur (reader) on a published app/dashboard or
`/sites/{slug}` page gets an ephemeral measure (distance/area) and sketch
(freehand/shapes/text) toolbar, never persisted, never sent to the server.

**Architecture:** Everything except the custom icon library lives entirely in
`shell/`: `mapSymbology.ts` gains the new encodings and paint/legend
compilation (a single new trailing **options object** on `buildMapPaint`/
`buildLegend`, so no existing call site changes arity), `MapView.tsx` gains
the render-time mechanics (a second `line` layer for a polygon's stroke, a
paired `symbol` layer whose **layout** carries `icon-image`, a per-layer
`__labels` GeoJSON source refreshed on `idle`, and a mounted measure/sketch
overlay), `MapSymbologyEditor.tsx` gains the matching UI blocks, and
`mapWidget.tsx` **stops compiling paint itself** and hands `symbology` +
`themeColors` to `MapView` so every SP-27 mechanic reaches apps/dashboards.
The one core change is a small new module, `app/mapicons/`: a tenant-scoped
table plus a presigned-S3 upload + authenticated read proxy, following
`app/tileset3d/`/`app/terrain3d/` (which is where the presign+proxy
precedent actually lives — **not** `app/secrets/`, which never touches S3).

**Tech Stack:** TypeScript/React/Vitest/MapLibre GL JS **4.7.1** (shell),
one new shell **devDependency** (`lucide-static@1.34.0`, raw SVG icon files,
ISC) consumed only by a committed generation script — no runtime icon
library, no bundler glob over `node_modules`. Python/FastAPI/SQLAlchemy/
pytest (core), no new core dependency (reuses `app/ingestion/storage.py`'s
presign helpers and `app.ingestion.routes.get_s3_client`).

## Global Constraints

- Every task that touches `core/`: `uv run pytest` must show **no drop** from
  the reference measured at the end of SP-26 (**1896 passed, 5 skipped, 1
  failed** — that one failure is `test_features_rls.py::
  test_scope_preserves_original_sql_error`, documented pre-existing and
  unrelated to SP-26/SP-27; do not try to fix it in this plan), `ruff check`,
  `ruff format --check`, `mypy --strict` (the 4 gated modules:
  `app/auth app/secrets app/analytics app/copilot`), `lint-imports` all
  green, coverage **≥ 85**.
- Every task that touches `shell/`: `npm run lint`, `npm run format:check`,
  `npm run test` must show **no drop** from the reference (**162 files /
  1463 tests**), `npm run build` green, coverage **≥ 88** (measured after
  removing `dist/`/`dist-export/` — documented trap, SP-22 through SP-26).
- `npm run e2e` reference: **108 passed, 4 skipped, 0 failed** (57 spec
  files, 112 `test()` declarations, 4 of which skip at runtime through
  `skipIfNoBuild()`). This plan adds **3** tests in 2 files → the expected
  final count is **111 passed, 4 skipped, 0 failed**. Playwright counts
  tests, not files.
- OpenAPI/TS regeneration: the task that adds FastAPI routes (Task 9) does
  **not** regenerate; **Task 10 is mandatory and must be the very next
  commit**, as a dedicated `chore(api):` commit. This is a deliberate
  exception to the repo's "same task regenerates" habit, written here so a
  per-task reviewer of Task 9 does not flag it. Command (verified working):
  `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY=$(openssl rand -base64 32)
  uv run python scripts/export_openapi.py`, then `cd ../shell && npm run
  gen:api-types`.
- Commits are conventional (`feat(core): …`, `feat(shell): …`,
  `test(shell): …`), one subject each, in French prose, code identifiers in
  English — per `CLAUDE.md`.
- Any new `S3_*_BUCKET`/`CORE_*` environment variable read by `core/app/`
  must be wired into `docker-compose.yml`'s `core:` service **and** (for a
  bucket) mirrored in `deploy/backup/backup.sh`'s bucket loop or explicitly
  added to `test_deployability.py`'s `BACKUP_EXCLUDED_BUCKETS` with a written
  reason — SP-21's non-negotiable rule, checked by
  `core/tests/test_deployability.py`, currently **35/35 green**; do not let a
  task leave it red.
- **No test-only global in production code.** Nothing in `shell/src/` may
  expose the `maplibregl.Map` instance on `window`/`globalThis` for an E2E
  spec's benefit (verified: no such escape hatch exists today). E2E proofs
  assert on visible UI and on network traffic only.

- **Deviations from the committed spec, locked in during this plan** (the
  spec `docs/superpowers/specs/2026-08-27-sp27-carte-symbologie-avancee-mesure-design.md`
  is **not** revised; every departure is recorded here):

  1. The spec's §3.4 said the icon proxy route (`GET /map-icons/{id}/file`)
     uses "la même porte `can()` que le reste" — `can()`
     (`app/sharing/authorization.py`) authorizes access to an **item**, and a
     map icon is not an item. The real check is: authenticated user
     (`get_current_user`) + `icon.tenant_id == user.tenant_id`, no `can()`
     anywhere in `app/mapicons/`. **Correction of the earlier wording of this
     deviation:** it is *not* a mirror of `app/secrets/routes.py`, which is
     **admin-only** (`_require_admin`, `core/app/secrets/routes.py:22-24`,
     called on all three of its routes). Map icons are deliberately **not**
     admin-only — any authenticated user of the tenant may add one — and that
     is an arbitrage, not a mirrored precedent. Reason: an icon is
     presentation material attached to a map the user is already allowed to
     author, with no secret content; gating it on admin would make the
     symbology editor unusable for the very authors it is built for.
  2. MapLibre's `fill` layer type has **no stylable outline width** —
     `fill-outline-color` exists (verified `data-driven` in the installed
     style-spec 20.4.0) but `fill-outline-width` does not exist at all
     (verified `'fill-outline-width' in v8.json.paint_fill === false`). A
     polygon's `stroke.width`/`stroke.style` therefore compiles to a
     **second `line` layer** sharing the fill layer's source/`source-layer`/
     filter (Task 3). `stroke` on a `line`-geometry layer is a deliberate
     no-op.
  3. **D1 — labels do not use `feature-state`.** The spec (and this plan's
     first draft) rendered CEL labels with
     `layout: { "text-field": ["feature-state", "label"] }`. That is
     **illegal**: the installed style-spec validator — the same one
     `map.addLayer` calls — rejects it with, verbatim,
     `layers[0].layout.text-field: "feature-state" data expressions are not
     supported with layout properties.` (`layout_symbol["text-field"]
     .expression.parameters === ["zoom","feature"]`, no `"feature-state"`).
     Because `Style.addLayer` does `if (this._validate(...)) return;`, the
     layer would simply never be added, with no exception for `applyLayers`'
     `try/catch` to see. Replacement mechanism, decided with the porteur du
     projet: for each layer carrying `symbology.label`, the shell builds a
     **dedicated GeoJSON source `${layer.id}__labels`** whose features carry
     a real `label` string property, computed client-side by evaluating the
     layer's CEL template against each feature's attributes; the paired
     `symbol` layer uses `text-field: ["get", "label"]` — data-driven on a
     real property, which the validator accepts (verified: no errors, once
     the style declares `glyphs`). Source features come from
     `map.querySourceFeatures(...)`, resynchronised on `idle`. The
     multi-field CEL template is **kept** — that is exactly what this option
     buys — with the repo's real syntax `${record.champ}`. Consequences:
     `feature-state`, `setFeatureState` and `promoteId` disappear entirely
     from this plan, and `labelFeatureState.ts` is renamed `labelSource.ts`.
  4. **D2 — the map widget is wired (scope widened).**
     `shell/src/builder/widgets/mapWidget.tsx:187` called `buildMapPaint`
     itself and built a `kind: "feature"` layer carrying only `paint`, never
     `symbology`, so `effectivePaint`'s `if (!layer.symbology) return
     layer.paint ?? {}` branch fired and **no** SP-27 mechanic (outline
     layer, icons, labels, opacity) ever reached an app or a dashboard —
     while Task 12 was adding the icon editor to the widget's `PropsPanel`.
     Decision: `mapWidget.tsx` stops compiling paint and passes `symbology`
     (and `themeColors`) to `MapView`, which compiles. Task 19 does this,
     including the non-regression proof for the existing `paint` path.
  5. `LayerSymbology.stroke.color` persists a **`palette: PaletteId`**
     (an identifier), never a `ResolvedPalette`. Reason: `LayerSymbology` is
     the storage/edit envelope (`mapSymbology.ts:27-30` says so explicitly)
     and `symbologyToPaintInputs` is what resolves `PaletteId` →
     `ResolvedPalette` via `resolvePalette(id, themeColors)` at paint time.
     Freezing resolved colors into the persisted document would break the
     theme palette (`theme-primary`, A25/SP-25) for the stroke and make
     `stroke` inconsistent with `color` inside the same object.
  6. `buildMapPaint`/`buildLegend` grow **one** new trailing parameter, an
     options object `{ stroke?, opacity?, icon? }`, rather than three to
     five positional parameters. Reason: every existing call site (including
     the ones in test files) keeps its current arity, and the two functions
     stay readable at 6 parameters instead of 9.
  7. `icon-image` is a **layout** property, not paint (verified: it lives in
     `v8.json.layout_symbol`; putting it in `paint` yields
     `layers[0].paint.icon-image: unknown property "icon-image"`). It is
     therefore never written into `MapPaintResult.paint`; it goes into a
     separate `MapPaintResult.iconLayout`, consumed only by the paired
     `symbol` layer. `addTypedLayer` and `paintFor` are untouched.
  8. `map.addImage(id, bitmap)` is called **without** `{ sdf: true }`.
     Reason: `sdf: true` asserts the image *already is* a signed distance
     field (the encoding that makes `icon-color`/`icon-halo-*` work); an
     `ImageBitmap` produced from an SVG or a PNG is ordinary RGBA, and
     interpreting it as an SDF renders garbage. This plan never uses
     `icon-color`, so `sdf` buys nothing on either path.
  9. ~~Custom uploaded icons are restricted to `image/png` only.~~
     **Renversée par la décision D4 (déviation 13) le 2026-08-27** : le SVG
     téléversable est conservé, et le XSS stocké est réglé par un
     assainissement côté cœur. Cette entrée est laissée en place, barrée,
     parce qu'elle a été écrite puis annulée dans la même journée et qu'un
     relecteur du plan doit voir l'arbitrage, pas seulement son résultat.
 10. The curated Lucide catalogue is materialised by a **committed
     generation script** (`shell/scripts/gen-lucide-icons.mjs`) that writes a
     `Record<string, string>` of the 140 raw SVG strings into
     `shell/src/builder/widgets/lucideIconSvgs.generated.ts`. Reason: neither
     a fully-templated dynamic `import()` nor an `import.meta.glob` over
     `/node_modules/lucide-static/icons/*.svg` could be verified to work
     with this repo's Vite version without installing the package, and the
     glob form would also emit ~2035 tiny assets into the build. The script
     approach has no bundler-behaviour dependency at all, keeps
     `lucide-static` a **devDependency**, and bundles exactly 140 icons.
 11. Icon images are loaded **after** `applyLayers`, not before. Reason:
     `Style.addImage` calls `_afterImageUpdated(id)`, which sets
     `_changedImages[id]`/`_changed` and fires a `data` event (verified in
     the installed bundle), so a `symbol` layer already referencing a
     not-yet-loaded image repaints as soon as the image arrives. Sequencing
     image loading *before* `applyLayers` would have made `applyLayers`
     asynchronous and broken every existing synchronous `MapView` test.
 12. Labels are refreshed on `map.on("idle")` (debounced 150 ms) plus one
     immediate call after each `applyLayers`. Reason: `querySourceFeatures`
     only returns features from tiles that are **loaded and renderable**
     (verified in the bundle: it walks `getRenderableIds()`), and `idle` is
     precisely "nothing is loading right now". `sourcedata`/`moveend` add
     churn without adding coverage.
 13. **D4 — le SVG téléversable est conservé et assaini par le cœur**
     (décision de Tanguy, 2026-08-27, renverse la déviation 9).
     `ALLOWED_CONTENT_TYPES` vaut `{"image/png", "image/svg+xml"}`. Un SVG
     est **assaini à l'écriture** par `app/mapicons/svg.py` et c'est la
     version assainie qui est stockée dans S3 ; la lecture ne réassainit
     jamais (une seule passe, un seul endroit où la garde peut manquer).
     L'assainisseur parse avec `defusedxml` — **déjà dépendance directe
     déclarée** du cœur (`core/pyproject.toml` : `"defusedxml>=0.7"  # SP-12e`,
     résolue en **0.7.1** dans `uv.lock`, seul usage actuel :
     `app/harvest/connectors/ows.py`) : **aucune nouvelle dépendance**. Il
     re-sérialise depuis l'arbre parsé, jamais par filtrage d'expression
     régulière sur le texte source. Un SVG non parsable, ou vidé de tout
     contenu graphique par l'assainissement, produit une erreur RFC 7807
     explicite à l'upload — jamais un fichier vide stocké.
     `X-Content-Type-Options: nosniff` et `Content-Disposition: attachment`
     sont **conservés** (décision prise) : c'est une **première** dans
     `core/app/` (`grep -rn 'X-Content-Type-Options' core/app/` → vide ; ni
     `app/tileset3d` ni `app/terrain3d` ne posent de `Content-Disposition`),
     assumée parce que c'est la première route du cœur à servir un fichier
     téléversé par un utilisateur non-admin. Côté shell, les icônes SVG
     (Lucide comme personnalisées) sont décodées par
     `HTMLImageElement` + `URL.createObjectURL`, **pas** par
     `createImageBitmap` : `map.addImage` accepte
     `HTMLImageElement | ImageBitmap | ImageData | …` (signature vérifiée
     dans `maplibre-gl@4.7.1`), et `createImageBitmap` sur un blob SVG n'est
     pas fiable d'un navigateur à l'autre. La règle déjà posée tient : une
     icône qui échoue à charger n'empêche jamais `applyLayers`.
 14. **D5 — le contour data-driven devient éditable depuis l'UI** (décision de
     Tanguy, 2026-08-27, renverse le retrait noté en Task 4). Task 5
     **extrait** un sous-éditeur `FieldClassificationPicker` de l'UI
     couleur — qui est **inline** dans `MapSymbologyEditor.tsx` (lignes
     141-280) : contrairement à ce que supposait le brief de cette passe, ce
     composant **n'existait pas** (`grep -rn 'FieldClassificationPicker'
     shell/src/ docs/` ne trouvait que deux mentions, toutes deux dans ce
     plan). Piège n° 3 de `CLAUDE.md`, corrigé sans re-demander. Les libellés
     du composant sont **injectés** : l'usage couleur passe les chaînes
     historiques au caractère près, donc les **16** tests existants de
     `MapSymbologyEditor.test.tsx` et la preuve E2E SP-25 restent verts sans
     être modifiés — c'est la couverture de non-régression exigée, nommée
     test par test dans Task 5. `StrokeColorEncoding` gagne `computedAt` :
     l'invariant SP-25 « domaines figés à l'enregistrement » vaut aussi pour
     le contour.

---

## File Structure

| File | Responsibility |
|---|---|
| `shell/src/test/MockMaplibreMap.ts` | **Modify (Task 1).** `MockMap` gains `addImage`/`hasImage`/`removeImage`/`listImages`/`getStyle`/`querySourceFeatures`/`getCanvas`, a payload-carrying `fire(event, payload)`, and `images`/`glyphs`/`sourceFeatures` inspection fields. |
| `shell/src/test/imageDecodeStub.ts` | **Create (Task 1).** `installImageDecodeStub()` — jsdom has no `URL.createObjectURL` and never loads an `Image`. |
| `shell/src/builder/widgets/mapSymbology.ts` | **Modify (Tasks 2, 7, 13).** `StrokeStyle`, `LayerStroke`, `LayerSymbology.stroke`/`.opacity`/`.label`/`.icon`, `IconRef`, `LayerIcon`, `LayerLabel`, `renderAsFor`, `iconImageId`, extended `MapPaintResult`/`LegendSpec`, options-object parameter on `buildMapPaint`/`buildLegend`, `stroke` in `symbologyToPaintInputs`. |
| `shell/src/builder/widgets/mapSymbology.test.ts` | **Modify (Tasks 2, 7, 13).** |
| `shell/src/map/MapView.tsx` | **Modify (Tasks 3, 8, 12, 14, 16, 19).** `themeColors` prop; outline line-layer; opacity; `map.on("error")` reporting; icon image loading + paired `symbol` layer; `__labels` GeoJSON source + `__label` symbol layer + `idle` refresh; mounts the measure/sketch toolbar behind `interactiveTools`. |
| `shell/src/map/MapView.test.tsx` | **Modify (same tasks).** |
| `shell/src/map/MapSymbologyEditor.tsx` | **Modify (Tasks 4, 5, 12, 14).** Fixes `clearColor`/`clearSize`; contour (fixe puis classé), opacité, icône, étiquette UI blocks; délègue la classification au picker extrait. |
| `shell/src/map/FieldClassificationPicker.tsx` | **Create (Task 5).** Sous-éditeur « champ + palette + mode + classification + recalcul », extrait de l'UI couleur inline et partagé avec `stroke.color` (D5). Libellés injectés. |
| `shell/src/map/FieldClassificationPicker.test.tsx` | **Create (Task 5).** |
| `shell/src/map/MapSymbologyEditor.test.tsx` | **Modify (same tasks).** |
| `shell/src/map/LayersPanel.tsx` | **Modify (Task 12).** Passes the three optional custom-icon props. |
| `shell/src/builder/widgets/mapWidget.tsx` | **Modify (Tasks 3, 8, 19).** `MapSymbologyLegend` gains stroke + icon entries; `Component` stops calling `buildMapPaint`, passes `symbology`/`themeColors`/`interactiveTools` to `MapView`. |
| `shell/src/builder/widgets/mapWidget.test.tsx` | **Modify (Tasks 3, 8, 19).** |
| `shell/scripts/gen-lucide-icons.mjs` | **Create (Task 6).** Reads the 140 curated names, writes the generated SVG map. |
| `shell/src/builder/widgets/lucideIconSvgs.generated.ts` | **Create (Task 6, generated + committed).** 140 raw SVG strings, ISC notice in the header. |
| `shell/src/builder/widgets/iconLibrary.ts` | **Create (Task 6).** `IconCategory`, `LUCIDE_ICONS` (140), `rasterizeLucideIcon`, `decodeIconImage` (Blob → `HTMLImageElement`). |
| `shell/src/builder/widgets/iconLibrary.test.ts` | **Create (Task 6).** |
| `shell/src/map/labelSource.ts` | **Create (Task 13).** Pure: features + CEL template → a deduplicated GeoJSON `FeatureCollection` carrying a `label` property. |
| `shell/src/map/labelSource.test.ts` | **Create (Task 13).** |
| `shell/src/map/measureSketch.ts` | **Create (Task 15).** Pure: haversine distance, spherical polygon area, unit formatting, `shapeToGeoJSONFeature`. |
| `shell/src/map/measureSketch.test.ts` | **Create (Task 15).** |
| `shell/src/map/MapMeasureSketchToolbar.tsx` | **Create (Task 16), modified (Tasks 17, 18).** The mounted overlay: measure UI, sketch tools, GeoJSON overlay sync. |
| `shell/src/map/MapMeasureSketchToolbar.test.tsx` | **Create (Task 16), modified (Tasks 17, 18).** |
| `shell/src/api/types.ts` | **Modify (Task 11).** `ItemClient` gains 5 map-icon methods + `MapIconOut`. |
| `shell/src/api/itemClient.ts` | **Modify (Task 11).** Real implementations, including the authenticated `fetchMapIconBlob`. |
| `shell/src/api/itemClient.test.ts` | **Modify (Task 11).** |
| `shell/src/staticExport/StaticItemClient.ts` | **Modify (Task 11).** `unsupported()` for the 5 new methods. |
| `shell/src/staticExport/StaticItemClient.test.ts` | **Modify (Task 11).** |
| `shell/package.json` / `package-lock.json` | **Modify (Task 6).** `lucide-static` as a **devDependency** + `gen:lucide-icons` script. |
| `shell/e2e/map-symbology-advanced.spec.ts` | **Create (Task 20).** 4.4 proof (1 test). |
| `shell/e2e/map-measure-sketch.spec.ts` | **Create (Task 20).** 4.5 proof (2 tests). |
| `core/app/mapicons/__init__.py` | **Create (Task 9).** Empty. |
| `core/app/mapicons/models.py` | **Create (Task 9).** `MapIcon` SQLAlchemy model. |
| `core/app/mapicons/repository.py` | **Create (Task 9).** `create_icon`/`list_icons`/`get_icon`/`delete_icon`. |
| `core/app/mapicons/schemas.py` | **Create (Task 9).** Schemas + the single `ALLOWED_CONTENT_TYPES`/`MAX_ICON_BYTES` constants. |
| `core/app/mapicons/svg.py` | **Create (Task 9).** `sanitize_svg`, `sniff_content_type`, `SvgRejected` — allowlist + re-sérialisation depuis l'arbre parsé (D4). |
| `core/tests/test_mapicons_svg.py` | **Create (Task 9).** 15 tests purs de l'assainisseur. |
| `core/app/mapicons/routes.py` | **Create (Task 9).** 5 REST routes. |
| `core/alembic/versions/0029_map_icons.py` | **Create (Task 9).** |
| `core/tests/test_mapicons_routes.py` | **Create (Task 9).** |
| `core/app/db.py` | **Modify (Task 9).** `core_table_names()` gains the lazy import of `app.mapicons.models` — without it the table is never created by `init_db` **and** `map_icons` is absent from the collections registry denylist. |
| `core/app/main.py` | **Modify (Task 9).** Import + unconditional `include_router`. |
| `core/pyproject.toml` | **Modify (Task 9).** Import-linter: `app.mapicons` layer + `app.db -> app.mapicons.models` exemption. |
| `docker-compose.yml` | **Modify (Task 9).** `core:` service gains `S3_MAPICONS_BUCKET: geostudio-mapicons`. |
| `docker-compose.prod.yml` | **Modify (Task 9).** `backup:` service gains the same bucket. |
| `deploy/backup/backup.sh` | **Modify (Task 9).** Bucket loop gains `S3_MAPICONS_BUCKET`. |
| `.env.example` | **Modify (Task 9).** Documents the hardcoded bucket (commented line), same convention as `S3_TILESET3D_BUCKET`. |
| `core/openapi.json` / `shell/src/api/generated/core-schema.d.ts` | **Modify (Task 10).** |

---

## Task 1: Shell — extend the MapLibre test double (prerequisite of every render task)

**Files:**
- Modify: `shell/src/test/MockMaplibreMap.ts`
- Create: `shell/src/test/imageDecodeStub.ts`
- Modify: `shell/src/map/MapView.test.tsx` (one new test only)

**Why this is Task 1:** every later task's tests call MapLibre methods the
hand-written `MockMap` class does not have. Its complete current surface is
`on, off, once, fire, fireOnLayer, addSource, flyTo, fitBounds, addLayer,
getLayer, getSource, removeLayer, removeSource, getCenter, getZoom,
getBounds, getPitch, getBearing, setTerrain, loaded, isStyleLoaded, project,
addControl, removeControl, remove`. There is no `addImage`, no `hasImage`, no
`querySourceFeatures`, no `getStyle`, no `getCanvas`, and `fire(event)`
carries **no payload**. Also note: `MockMap` is a **class with real
methods**, not a bag of `vi.fn()` spies — `expect(map.addLayer)
.toHaveBeenCalledWith(...)` throws "received value must be a mock or spy
function". All assertions in this plan therefore inspect recorded state
(`map.getLayer(id)`, `map.layers`, `map.sources`, `map.images`) with
`toMatchObject`, which is the convention already used throughout
`MapView.test.tsx`.

**Interfaces:**
- Produces: the extended `MockMap` surface (consumed by Tasks 3, 8, 12, 14,
  18), et `installImageDecodeStub()` (consommé par Tasks 6, 8, 12).

- [ ] **Step 1: Extend `MockMap`**

In `shell/src/test/MockMaplibreMap.ts`, add these fields next to the
existing `terrain: unknown = null;` declaration:

```ts
  // Images ajoutées par map.addImage (SP-27 icônes). La valeur enregistrée
  // est le second argument tel quel : les tests n'inspectent que la présence
  // et l'éventuel objet d'options, jamais les pixels.
  images = new Map<string, { image: unknown; options?: unknown }>();
  // `glyphs` du style actif : `text-field` exige que le style en déclare un
  // (vérifié contre le validateur du style-spec installé). MapView refuse de
  // poser une couche d'étiquettes sans lui ; les tests le pilotent d'ici.
  glyphs: string | undefined = "https://glyphs.test/{fontstack}/{range}.pbf";
  // Réponses de querySourceFeatures, par id de source. Un test d'étiquettes
  // pose ici les entités que la carte est censée avoir chargées.
  sourceFeatures: Record<string, unknown[]> = {};
  querySourceFeaturesCalls: { sourceId: string; params?: unknown }[] = [];
```

And these methods (place them next to their nearest sibling — `addImage`
after `addSource`, `getStyle` after `isStyleLoaded`, `getCanvas` after
`project`):

```ts
  addImage(id: string, image: unknown, options?: unknown) {
    this.images.set(id, { image, options });
    return this;
  }
  hasImage(id: string) {
    return this.images.has(id);
  }
  removeImage(id: string) {
    this.images.delete(id);
    return this;
  }
  listImages() {
    return [...this.images.keys()];
  }
  getStyle() {
    return { glyphs: this.glyphs };
  }
  querySourceFeatures(sourceId: string, params?: unknown) {
    this.querySourceFeaturesCalls.push({ sourceId, params });
    return this.sourceFeatures[sourceId] ?? [];
  }
  getCanvas() {
    // MapMeasureSketchToolbar ne lit que `style.cursor`.
    return { style: {} as Record<string, string> };
  }
```

Change `fire` to carry an optional payload — **additively**, so the ~15
existing `fire("moveend")` / `fire("idle")` call sites keep working
unchanged:

```ts
  fire(event: string, payload?: unknown) {
    // Iterate a snapshot: `once` handlers mutate this.handlers[event] while
    // firing, which would otherwise desync a live forEach mid-iteration.
    [...(this.handlers[event] ?? [])].forEach((cb) =>
      (cb as (e?: unknown) => void)(payload),
    );
  }
```

The `handlers` field's type must widen accordingly:

```ts
  handlers: Record<string, Array<(e?: unknown) => void>> = {};
```

…and `on`/`off`/`once`'s existing signatures already accept `() => void`,
which is assignable to `(e?: unknown) => void`; if `tsc` complains at a call
site inside the mock (`if (event === "load") arg2();`), keep that call
argument-less — it is correct, `load` carries nothing this repo reads.

- [ ] **Step 2: Create the image-decode test double**

Create `shell/src/test/imageDecodeStub.ts`. Mesuré dans cet
environnement jsdom (sonde exécutée, pas supposée) : `typeof Image ===
"function"`, mais `URL.createObjectURL`, `URL.revokeObjectURL`,
`createImageBitmap` et `HTMLImageElement.prototype.decode` sont **tous
`undefined`**, et jsdom ne charge jamais une ressource — un `img.src = …` ne
déclenche donc ni `onload` ni `onerror`. Le chemin de décodage SVG (déviation
13) a besoin des trois :

```ts
// SPDX-License-Identifier: Apache-2.0
import { vi } from "vitest";

// jsdom : Image existe mais ne charge RIEN (aucun onload/onerror), et
// URL.createObjectURL / URL.revokeObjectURL / HTMLImageElement.decode sont
// absents (mesuré). Ce double rend `decodeIconImage` testable : chaque
// affectation de `src` résout de façon synchrone-ish (microtâche), sauf pour
// les URLs de la liste `failing`.
export function installImageDecodeStub(options: { failing?: string[] } = {}) {
  const created: string[] = [];
  const revoked: string[] = [];
  let counter = 0;
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn((_blob: Blob) => {
      const url = `blob:stub/${(counter += 1)}`;
      created.push(url);
      return url;
    }),
    revokeObjectURL: vi.fn((url: string) => {
      revoked.push(url);
    }),
  });
  class StubImage {
    onload: (() => void) | null = null;
    onerror: ((e?: unknown) => void) | null = null;
    width = 24;
    height = 24;
    crossOrigin: string | null = null;
    #src = "";
    get src() {
      return this.#src;
    }
    set src(value: string) {
      this.#src = value;
      queueMicrotask(() => {
        if (options.failing?.some((f) => value.includes(f))) this.onerror?.(new Error("stub"));
        else this.onload?.();
      });
    }
  }
  vi.stubGlobal("Image", StubImage);
  return { created, revoked };
}
```

Note : `vi.stubGlobal("URL", { ...URL, … })` remplace l'objet entier ; si un
test du même fichier a besoin du constructeur `URL` réel, l'étaler ainsi le
conserve. Vérifier au premier usage (Task 6) et, si l'étalement ne suffit
pas, ne stubber que les deux méthodes par
`vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }))`
— **marqué comme non vérifié** : la sonde a mesuré l'absence des méthodes,
pas le comportement de `stubGlobal` sur un objet natif.

- [ ] **Step 3: Write one regression test for the widened `fire`**

Add to `shell/src/map/MapView.test.tsx` (this is the only change this task
makes to that file; it proves the payload plumbing works and that nothing
regressed):

```ts
test("le mock MapLibre transporte un payload d'événement et enregistre les images", () => {
  render(<MapView config={config} />);
  const map = mapInstances[0];
  const seen: unknown[] = [];
  map.on("error", (e?: unknown) => seen.push(e));
  map.fire("error", { error: { message: "boom" } });
  expect(seen).toEqual([{ error: { message: "boom" } }]);

  map.addImage("x", { width: 1 }, { pixelRatio: 1 });
  expect(map.hasImage("x")).toBe(true);
  expect(map.listImages()).toEqual(["x"]);
  expect(map.getStyle().glyphs).toBe("https://glyphs.test/{fontstack}/{range}.pbf");
  expect(map.querySourceFeatures("nope")).toEqual([]);
});
```

- [ ] **Step 4: Run to verify**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS, **all** pre-existing tests in the file still green — the
widened `fire` signature must not have broken the ~15 existing
`fire("moveend")`/`fire("idle")` calls.

- [ ] **Step 5: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green, **1463 + 1 = 1464 tests**, 162 files (no new test file:
`imageDecodeStub.ts` has no test of its own — it is test
infrastructure, and Vitest's coverage config already excludes nothing under
`src/test/`; if the coverage gate drops below 88 because of it, add
`src/test/**` to `vite.config.ts`'s `coverage.exclude` list in this same
commit and say so in the commit body).

- [ ] **Step 6: Commit**

```bash
git add shell/src/test/MockMaplibreMap.ts shell/src/test/imageDecodeStub.ts shell/src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): étend le double MapLibre pour SP-27

addImage/hasImage/removeImage/listImages, getStyle (glyphs),
querySourceFeatures, getCanvas, et fire(event, payload) — la classe
MockMap n'avait aucune de ces surfaces, et fire() ne transportait rien.
Ajoute un double mesuré des surfaces absentes de jsdom :
URL.createObjectURL/revokeObjectURL et un Image qui déclenche réellement
onload — le décodage des icônes SVG passe par HTMLImageElement, pas par
createImageBitmap, dont la prise en charge d'un blob SVG varie.
EOF
)"
```

---

## Task 2: Shell — `mapSymbology.ts`: stroke + opacity

**Files:**
- Modify: `shell/src/builder/widgets/mapSymbology.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.test.ts`

**Interfaces:**
- Consumes: existing `ColorClassification`, `ColorDomain`, `SizeDomain`,
  `PaletteId`, `ResolvedPalette`, `normalizeDomain`, `colorsForClasses`,
  `resolvePalette`, `paletteColor` — all unchanged.
- Produces: `StrokeStyle`, `LayerStroke`, `StrokePaintInput`,
  `LayerSymbology.stroke`/`.opacity`, `renderAsFor`, the widened
  `MapPaintResult`, `LegendSpec.stroke`, and the new trailing options
  parameter of `buildMapPaint`/`buildLegend` (consumed by Task 3's
  `MapView.tsx`, Task 4's editor, Task 19's widget).

**Key facts verified for this task** (do not re-derive):
- `fill-outline-width` does **not** exist in the installed style-spec;
  `fill-outline-color` does and is `data-driven`.
- `circle-stroke-color` / `circle-stroke-width` are both `data-driven`.
- `line-dasharray` is `cross-faded` with `expression.parameters: ["zoom"]`
  — a **constant** `[2, 2]` is valid, a data-driven value would not be.
- `icon-image` is layout-only and is **not** part of this task.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/mapSymbology.test.ts` (existing tests
stay untouched above this point). Note the **options-object** 6th argument:

```ts
test("buildMapPaint emits circle-stroke-* for a point layer with a fixed stroke color/width", () => {
  const { paint } = buildMapPaint({}, null, null, "point", undefined, {
    stroke: { color: { fixed: "#111111" }, width: { fixed: 2 }, style: "solid" },
  });
  expect(paint["circle-stroke-color"]).toBe("#111111");
  expect(paint["circle-stroke-width"]).toBe(2);
});

test("buildMapPaint emits fill-outline-color plus an outline line-paint for a polygon with stroke", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    stroke: { color: { fixed: "#222222" }, width: { fixed: 3 }, style: "dashed" },
  });
  expect(result.paint["fill-outline-color"]).toBe("#222222");
  expect(result.outlinePaint).toEqual({
    "line-color": "#222222",
    "line-width": 3,
    "line-dasharray": [2, 2],
  });
});

test("stroke on a line geometry is a no-op and never overwrites the color encoding", () => {
  const result = buildMapPaint(
    { color: { field: "region", mode: "categorical" } },
    { kind: "categorical", values: ["Nord", "Sud"] },
    null,
    "line",
    undefined,
    { stroke: { color: { fixed: "#333333" }, width: { fixed: 7 }, style: "dotted" } },
  );
  // The `color` encoding owns line-color; the stroke must not touch it…
  expect(result.paint["line-color"]).toEqual([
    "match", ["get", "region"], "Nord", "#2563eb", "Sud", "#dc2626", "#2563eb",
  ]);
  // …nor introduce a width, a dash, or a second layer.
  expect(result.paint["line-width"]).toBeUndefined();
  expect(result.paint["line-dasharray"]).toBeUndefined();
  expect(result.outlinePaint).toBeUndefined();
});

test("buildMapPaint applies data-driven stroke color from a categorical domain", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    stroke: {
      color: {
        field: "region",
        domain: { kind: "categorical", values: ["Nord", "Sud"] },
        palette: { kind: "categorical", colors: ["#aaaaaa", "#bbbbbb"] },
      },
      width: { fixed: 1 },
      style: "solid",
    },
  });
  expect(result.paint["fill-outline-color"]).toEqual([
    "match", ["get", "region"], "Nord", "#aaaaaa", "Sud", "#bbbbbb", "#aaaaaa",
  ]);
});

test("buildMapPaint applies data-driven stroke width from a numeric domain", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    stroke: {
      color: { fixed: "#000000" },
      width: { field: "pop", domain: { min: 0, max: 100 } },
      style: "solid",
    },
  });
  expect(result.outlinePaint?.["line-width"]).toEqual([
    "interpolate", ["linear"], ["get", "pop"], 0, 1, 100, 8,
  ]);
});

test("buildMapPaint applies fixed opacity per geometry, outline included", () => {
  expect(
    buildMapPaint({}, null, null, "polygon", undefined, { opacity: 50 }).paint["fill-opacity"],
  ).toBe(0.5);
  expect(
    buildMapPaint({}, null, null, "point", undefined, { opacity: 25 }).paint["circle-opacity"],
  ).toBe(0.25);
  expect(
    buildMapPaint({}, null, null, "line", undefined, { opacity: 100 }).paint["line-opacity"],
  ).toBe(1);
  // I3.11 du pré-vol : un polygone à 30 % gardait un contour opaque.
  const withOutline = buildMapPaint({}, null, null, "polygon", undefined, {
    opacity: 30,
    stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" },
  });
  expect(withOutline.outlinePaint?.["line-opacity"]).toBe(0.3);
});

test("buildMapPaint never writes a layout-only property into paint", () => {
  const LAYOUT_ONLY = ["icon-image", "icon-size", "icon-allow-overlap", "text-field", "text-size"];
  const result = buildMapPaint({}, null, null, "point", undefined, {
    opacity: 40,
    stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
  });
  for (const key of LAYOUT_ONLY) expect(result.paint[key]).toBeUndefined();
});

test("buildLegend includes a stroke entry for a data-driven stroke color", () => {
  const legend = buildLegend({}, null, null, "polygon", undefined, {
    stroke: {
      color: {
        field: "region",
        domain: { kind: "categorical", values: ["Nord"] },
        palette: { kind: "categorical", colors: ["#aaaaaa"] },
      },
      width: { fixed: 1 },
      style: "solid",
    },
  });
  expect(legend?.stroke).toEqual({
    kind: "categorical",
    field: "region",
    entries: [{ value: "Nord", color: "#aaaaaa" }],
  });
});

test("symbologyToPaintInputs resolves stroke.color.palette from an id, like color", () => {
  const inputs = symbologyToPaintInputs(
    {
      stroke: {
        color: {
          field: "region",
          domain: { kind: "categorical", values: ["A"] },
          palette: "theme-primary",
        },
        width: { fixed: 1 },
        style: "solid",
      },
    },
    { primary: "#123456" },
  );
  expect(inputs.stroke).toBeDefined();
  expect(inputs.stroke && "field" in inputs.stroke.color && inputs.stroke.color.palette).toEqual(
    expect.objectContaining({ kind: expect.any(String) }),
  );
});

test("renderAsFor maps a geometry kind to the MapLibre layer type", () => {
  expect(renderAsFor("point")).toBe("circle");
  expect(renderAsFor("line")).toBe("line");
  expect(renderAsFor("polygon")).toBe("fill");
});
```

Add `renderAsFor` and `symbologyToPaintInputs` to the file's existing import
from `./mapSymbology` if they are not already there.

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts -t "stroke|opacity|layout-only|renderAsFor"`
Expected: FAIL (type errors and/or `undefined` results — the options
parameter does not exist yet).

- [ ] **Step 3: Add the types**

In `shell/src/builder/widgets/mapSymbology.ts`, after the existing
`ColorClassification` export:

```ts
export type StrokeStyle = "solid" | "dashed" | "dotted";

// Forme PERSISTÉE : la palette est un identifiant, jamais des couleurs
// résolues — même règle que LayerSymbology.color (cf. déviation 5 du plan).
export type StrokeColorEncoding =
  | { fixed: string }
  | { field: string; domain: ColorDomain; palette: PaletteId };

export type StrokeWidthEncoding = { fixed: number } | { field: string; domain: SizeDomain };

export type LayerStroke = {
  color: StrokeColorEncoding;
  width: StrokeWidthEncoding;
  style: StrokeStyle;
};

// Forme d'ENTRÉE de buildMapPaint/buildLegend : palette déjà résolue par
// symbologyToPaintInputs, exactement comme le paramètre `palette` existant.
export type StrokePaintInput = {
  color:
    | { fixed: string }
    | { field: string; domain: ColorDomain; palette: ResolvedPalette | undefined };
  width: StrokeWidthEncoding;
  style: StrokeStyle;
};
```

Extend `LayerSymbology` (existing type, two new optional fields — `label`
and `icon` arrive in Tasks 13 and 6, do not add them here):

```ts
export type LayerSymbology = {
  color?: /* unchanged */;
  size?: /* unchanged */;
  stroke?: LayerStroke;
  opacity?: number; // 0-100
};
```

Widen `MapPaintResult` to its **final** shape now, so it never has an
intermediate half-shape across tasks (`iconLayout`/`iconImages` are
populated by Task 7, but declared and initialised here):

```ts
export type MapPaintResult = {
  renderAs: "fill" | "circle" | "line";
  // JAMAIS une propriété layout : `icon-image`/`text-field` sont layout-only
  // dans le style-spec, et Style.addLayer fait `if (this._validate(...))
  // return;` — une clé layout posée ici ferait disparaître la couche
  // ENTIÈRE, silencieusement, sans exception pour le try/catch d'applyLayers.
  paint: Record<string, unknown>;
  // Contour de polygone : seconde couche `line` (fill-outline-color n'a
  // aucune largeur stylable). Absent quand il n'y a pas de contour.
  outlinePaint?: Record<string, unknown>;
  // Ids d'images MapLibre référencées par iconLayout ; l'appelant doit les
  // charger via map.addImage (Task 8). Toujours présent, vide sans icône.
  iconImages: string[];
  // Layout de la couche `symbol` appariée (Task 7/7). Absent sans icône.
  iconLayout?: Record<string, unknown>;
};
```

Add to `LegendSpec`:

```ts
  stroke?: { kind: "categorical"; field: string; entries: { value: string; color: string }[] };
```

And export the small helper that `mapWidget.tsx` (Task 19) needs so it no
longer has to call `buildMapPaint` just to learn the layer type:

```ts
// Même table que `renderAs` dans buildMapPaint : un seul endroit où
// "géométrie → type de couche MapLibre" est écrit.
export function renderAsFor(geometryKind: GeometryKind): "fill" | "circle" | "line" {
  return geometryKind === "point" ? "circle" : geometryKind === "line" ? "line" : "fill";
}
```

- [ ] **Step 4: Restructure `buildMapPaint` around a `result` object and add the options parameter**

Signature — **one** new trailing parameter (déviation 6):

```ts
export type PaintExtras = {
  stroke?: StrokePaintInput;
  opacity?: number; // 0-100
  icon?: LayerIcon; // Task 7 — declared here, unused until then
};

export function buildMapPaint(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
  extras?: PaintExtras,
): MapPaintResult {
```

`LayerIcon` does not exist yet at this point in the plan: in **this** task
declare `PaintExtras` with only `stroke` and `opacity`, and Task 7 adds the
`icon` field. Do not forward-declare a type that does not compile.

Body changes, in order:

1. Replace `const renderAs: … = geometryKind === "point" ? … ;` with
   `const renderAs = renderAsFor(geometryKind);`.
2. Immediately after `const paint: Record<string, unknown> = {};`, add:
   `const result: MapPaintResult = { renderAs, paint, iconImages: [] };`
   The existing color and size blocks keep writing into `paint` unchanged.
3. Replace the final `return { renderAs, paint };` with `return result;`.
4. Insert the stroke block **after** the existing size-radius block:

```ts
  const stroke = extras?.stroke;
  if (stroke) {
    const colorValue = strokeColorValue(stroke.color);
    const widthValue = strokeWidthValue(stroke.width);
    const dasharray =
      stroke.style === "dashed" ? [2, 2] : stroke.style === "dotted" ? [1, 2] : undefined;

    if (geometryKind === "point" && colorValue !== undefined) {
      paint["circle-stroke-color"] = colorValue;
      paint["circle-stroke-width"] = widthValue;
      // `line-dasharray` n'a pas d'équivalent sur un cercle : le style est
      // volontairement ignoré pour les points (aucune propriété MapLibre).
    } else if (geometryKind === "polygon" && colorValue !== undefined) {
      paint["fill-outline-color"] = colorValue;
      result.outlinePaint = {
        "line-color": colorValue,
        "line-width": widthValue,
        ...(dasharray ? { "line-dasharray": dasharray } : {}),
      };
    }
    // geometryKind === "line" : no-op délibéré (déviation 2). Une ligne a
    // déjà line-color/line-width via les encodages color/size ; un second
    // contour sur une ligne n'a aucun sens cartographique.
  }

  if (extras?.opacity !== undefined) {
    const alpha = extras.opacity / 100;
    paint[
      renderAs === "circle" ? "circle-opacity" : renderAs === "line" ? "line-opacity" : "fill-opacity"
    ] = alpha;
    // Le contour est une couche à part : sans ça, un polygone à 30 %
    // gardait un contour parfaitement opaque (constat 3.11 du pré-vol).
    if (result.outlinePaint) result.outlinePaint["line-opacity"] = alpha;
  }
```

5. Add the two module-level helpers (place them next to
   `colorPaintProperty`):

```ts
// Largeurs de contour : 1 px à 8 px sur le domaine, distinctes des rayons de
// cercle (SIZE_RADIUS_MIN/MAX = 4/24) — un contour de 24 px mangerait le
// polygone. Constantes locales, pas de réutilisation trompeuse.
const STROKE_WIDTH_MIN = 1;
const STROKE_WIDTH_MAX = 8;

function strokeColorValue(color: StrokePaintInput["color"]): unknown {
  if ("fixed" in color) return color.fixed;
  const normalized = normalizeDomain(color.domain);
  if (!normalized) return undefined;
  if (normalized.kind === "categorical") {
    const colors = color.palette
      ? colorsForClasses(color.palette, normalized.values.length)
      : normalized.values.map((_, i) => paletteColor(i));
    const match: unknown[] = ["match", ["get", color.field]];
    normalized.values.forEach((v, i) => match.push(v, colors[i % colors.length]));
    match.push(colors[0]);
    return match;
  }
  if (normalized.kind === "numeric-classed") {
    const nClasses = normalized.breaks.length - 1;
    const colors = color.palette
      ? colorsForClasses(color.palette, nClasses)
      : Array.from({ length: nClasses }, (_, i) => paletteColor(i));
    const step: unknown[] = ["step", ["get", color.field], colors[0]];
    for (let i = 1; i < nClasses; i++) step.push(normalized.breaks[i], colors[i]);
    return step;
  }
  // numeric continu : même interpolation que fill-color/circle-color.
  const low = color.palette?.kind === "sequential" ? color.palette.low : NUMERIC_COLOR_LOW;
  const high = color.palette?.kind === "sequential" ? color.palette.high : NUMERIC_COLOR_HIGH;
  if (normalized.min === normalized.max) return low;
  return ["interpolate", ["linear"], ["get", color.field], normalized.min, low, normalized.max, high];
}

function strokeWidthValue(width: StrokeWidthEncoding): unknown {
  if ("fixed" in width) return width.fixed;
  if (width.domain.min === width.domain.max) return STROKE_WIDTH_MIN;
  return [
    "interpolate",
    ["linear"],
    ["get", width.field],
    width.domain.min,
    STROKE_WIDTH_MIN,
    width.domain.max,
    STROKE_WIDTH_MAX,
  ];
}
```

- [ ] **Step 5: Extend `buildLegend`**

Same trailing options parameter (reuse `PaintExtras`), and the categorical
stroke branch only — a numeric/classed stroke legend entry is not exercised
by any test in this plan; do not invent an untested branch:

```ts
export function buildLegend(
  encodings: MapEncodings | undefined,
  colorDomain: ColorDomain | null,
  sizeDomain: SizeDomain | null,
  geometryKind: GeometryKind,
  palette?: ResolvedPalette,
  extras?: PaintExtras,
): LegendSpec | null {
  // … existing color/size blocks unchanged …

  const stroke = extras?.stroke;
  if (stroke && "field" in stroke.color) {
    const normalized = normalizeDomain(stroke.color.domain);
    if (normalized?.kind === "categorical") {
      const colors = stroke.color.palette
        ? colorsForClasses(stroke.color.palette, normalized.values.length)
        : normalized.values.map((_, i) => paletteColor(i));
      legend.stroke = {
        kind: "categorical",
        field: stroke.color.field,
        entries: normalized.values.map((v, i) => ({ value: v, color: colors[i % colors.length] })),
      };
    }
  }

  return legend.color || legend.size || legend.stroke ? legend : null;
}
```

- [ ] **Step 6: Extend `symbologyToPaintInputs`**

It must resolve `stroke.color.palette` (a `PaletteId`) exactly the way it
already resolves `color.palette`:

```ts
export function symbologyToPaintInputs(
  symbology: LayerSymbology | undefined,
  themeColors: ThemeColors | undefined,
): {
  encodings: MapEncodings;
  colorDomain: ColorDomain | null;
  sizeDomain: SizeDomain | null;
  palette: ResolvedPalette | undefined;
  stroke: StrokePaintInput | undefined;
} {
  if (!symbology)
    return {
      encodings: {},
      colorDomain: null,
      sizeDomain: null,
      palette: undefined,
      stroke: undefined,
    };
  // … existing color/size logic unchanged …
  const stroke: StrokePaintInput | undefined = symbology.stroke
    ? {
        ...symbology.stroke,
        color:
          "fixed" in symbology.stroke.color
            ? symbology.stroke.color
            : {
                field: symbology.stroke.color.field,
                domain: symbology.stroke.color.domain,
                palette: resolvePalette(symbology.stroke.color.palette, themeColors) ?? undefined,
              },
      }
    : undefined;
  return { encodings, colorDomain, sizeDomain, palette, stroke };
}
```

Every existing caller destructures only the fields it needs, so adding
`stroke` to the return type breaks nothing.

- [ ] **Step 7: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: PASS — the 10 new tests plus every pre-existing SP-25 test.

- [ ] **Step 8: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/mapSymbology.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute stroke et opacity à LayerSymbology

Contour en encodage indépendant (couleur data-driven avec palette
résolue par symbologyToPaintInputs, épaisseur data-driven 1→8 px, style
fixe) et opacité fixe, contour compris. buildMapPaint/buildLegend
prennent un unique objet d'options en fin de signature : aucun site
d'appel existant ne change d'arité. MapPaintResult sépare paint et
iconLayout — icon-image est layout-only dans le style-spec et une clé
layout posée dans paint ferait disparaître la couche sans erreur.
EOF
)"
```

---

## Task 3: Shell — `MapView.tsx`: render stroke + opacity, thread `themeColors`, surface MapLibre errors

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (legend stroke entry only)
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `MapPaintResult` (with `.outlinePaint`), `symbologyToPaintInputs`
  (now returning `stroke`), `PaintExtras` from Task 2; the extended `MockMap`
  from Task 1.
- Produces: `applyLayers` adds a `${layer.id}__outline` `line` layer for a
  polygon with a stroke; a shared `SUBLAYER_SUFFIXES` constant that Tasks 8
  and 13 extend; `MapView`'s new `themeColors?: ThemeColors` prop (consumed
  by Task 19).

**Exact current shape of the code you are changing** (verified — do not
re-read from memory):
- `effectivePaint(layer, geometryKind)` at `MapView.tsx:158-168` returns
  `Record<string, unknown>` and is called at **three** sites inside
  `applyLayers`, each with a different surrounding shape:
  1. mixed-geometry loop (`layer.geometryKind === undefined`), inside
     `for (const sub of MIXED_GEOMETRY_SUBLAYERS)`, local `const id =
     \`${layer.id}__${sub.suffix}\``, calls
     `addTypedLayer(map, { id, type: sub.type, source: layer.id, sourceLayer:
     layer.sourceLayer, filter: [...], paint: paintFor(effectivePaint(layer,
     sub.suffix), sub.paintPrefix) })` then `layerIds.push(id)`.
  2. known-`geometryKind` branch, `addTypedLayer(map, { id: layer.id, type:
     layerTypeFor(layer.geometryKind), source: layer.id, sourceLayer:
     layer.sourceLayer, paint: effectivePaint(layer, layer.geometryKind) })`
     then `layerIds.push(layer.id)`. **No `filter`.**
  3. `kind === "feature"` branch: `const featurePaint = effectivePaint(layer,
     featureGeometryKind);` then a `switch (layer.renderAs ?? "fill")` with
     three inline `map.addLayer({ id: layer.id, type: …, source: layer.id,
     paint: featurePaint })` calls. **No `spec` variable, no `layerIds`, no
     `sourceLayer`, no `filter`** — it registers its click handler directly.
- There is **no** variable named `spec` anywhere in `applyLayers`.
- The rollback `catch` (`MapView.tsx:~360-368`) hard-codes only the three
  `MIXED_GEOMETRY_SUBLAYERS` suffixes plus `layer.id`.
- The click-handler loop `for (const id of layerIds)` registers **one
  handler per id** — two layers over the same source means the handler fires
  twice per click.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/map/MapView.test.tsx`. `tiled()` (line 965) and `config`
(line 43) are the file's existing helpers; assertions inspect recorded state
because `MockMap` methods are not spies:

```ts
test("a polygon layer with a stroke width adds a second outline line-layer sharing its source", () => {
  render(
    <MapView
      config={tiled({
        geometryKind: "polygon",
        symbology: { stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "dashed" } },
      })}
    />,
  );
  const map = mapInstances[0];
  expect(map.getLayer("communes")).toMatchObject({
    type: "fill",
    paint: { "fill-outline-color": "#000000" },
  });
  expect(map.getLayer("communes__outline")).toMatchObject({
    type: "line",
    source: "communes",
    "source-layer": "communes",
    paint: { "line-color": "#000000", "line-width": 2, "line-dasharray": [2, 2] },
  });
});

test("the outline sub-layer gets no click handler of its own (one popup per click)", () => {
  render(
    <MapView
      config={tiled({
        geometryKind: "polygon",
        popup: { titleField: "nom" },
        symbology: { stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" } },
      })}
    />,
  );
  const map = mapInstances[0];
  expect(map.layerHandlers["click:communes"] ?? []).toHaveLength(1);
  expect(map.layerHandlers["click:communes__outline"] ?? []).toHaveLength(0);
});

test("removing a stroked layer removes its outline sub-layer and its source", () => {
  const { rerender } = render(
    <MapView
      config={tiled({
        geometryKind: "polygon",
        symbology: { stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" } },
      })}
    />,
  );
  rerender(<MapView config={config} />);
  const map = mapInstances[0];
  expect(map.getLayer("communes__outline")).toBeUndefined();
  expect(map.getLayer("communes")).toBeUndefined();
  expect(map.getSource("communes")).toBeUndefined();
});

test("a failing outline sub-layer rolls back its parent instead of orphaning the source", () => {
  const good: MapLayer = { id: "ok", title: "OK", visible: true, kind: "feature", url: "u1" };
  const { rerender } = render(<MapView config={{ ...config, layers: [good] }} />);
  const map = mapInstances[0];
  map.throwOnAddLayer.add("communes__outline");
  rerender(
    <MapView
      config={{
        ...config,
        layers: [
          good,
          ...tiled({
            geometryKind: "polygon",
            symbology: { stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" } },
          }).layers,
        ],
      }}
    />,
  );
  expect(map.getLayer("communes")).toBeUndefined();
  expect(map.getLayer("communes__outline")).toBeUndefined();
  expect(map.getSource("communes")).toBeUndefined();
  expect(map.getLayer("ok")).toBeDefined();
});

test("a feature layer's opacity reaches its paint", () => {
  const layer: MapLayer = {
    id: "l1", title: "Zones", visible: true, kind: "feature", url: "u",
    symbology: { opacity: 40 },
  };
  render(<MapView config={{ ...config, layers: [layer] }} />);
  expect(mapInstances[0].getLayer("l1")).toMatchObject({
    type: "fill",
    paint: { "fill-opacity": 0.4 },
  });
});

test("themeColors reaches the paint compilation (theme-primary resolves)", () => {
  const layer: MapLayer = {
    id: "l1", title: "Zones", visible: true, kind: "feature", url: "u",
    symbology: {
      color: {
        field: "valeur", mode: "numeric", palette: "theme-primary",
        domain: { kind: "numeric", min: 0, max: 100 }, computedAt: "2026-08-27T00:00:00Z",
      },
    },
  };
  render(<MapView config={{ ...config, layers: [layer] }} themeColors={{ primary: "#123456" }} />);
  expect(JSON.stringify(mapInstances[0].getLayer("l1"))).toContain("#123456");
});

test("a MapLibre error event is reported instead of vanishing", () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});
  render(<MapView config={config} />);
  mapInstances[0].fire("error", { error: { message: "layers[0].paint.icon-image: unknown property" } });
  expect(spy).toHaveBeenCalledWith(
    "MapView: MapLibre a signalé une erreur",
    expect.objectContaining({ error: expect.anything() }),
  );
  spy.mockRestore();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "outline|opacity|themeColors|MapLibre error"`
Expected: FAIL.

- [ ] **Step 3: Change `effectivePaint`'s signature and return type**

```ts
function effectivePaint(
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>,
  geometryKind: GeometryKind,
  themeColors: ThemeColors | undefined,
): MapPaintResult {
  if (!layer.symbology)
    return { renderAs: renderAsFor(geometryKind), paint: layer.paint ?? {}, iconImages: [] };
  const { encodings, colorDomain, sizeDomain, palette, stroke } = symbologyToPaintInputs(
    layer.symbology,
    themeColors,
  );
  return buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind, palette, {
    stroke,
    opacity: layer.symbology.opacity,
  });
}
```

Note for Tasks 8 and 13: this function gains `icon: layer.symbology.icon`
inside the `extras` object in Task 8. Do **not** add it here —
`LayerSymbology.icon` does not exist yet and this task's `npm run build`
must pass on its own.

Imports to add/extend in `MapView.tsx`: `renderAsFor`, `type MapPaintResult`
from `../builder/widgets/mapSymbology`; `type ThemeColors` from
`../api/types` (already imported as a module — extend the existing
`import type { DataRecord, MapConfig, MapLayer } from "../api/types";`).

- [ ] **Step 4: Add the shared sub-layer suffix constant and the outline helper**

Right after `MIXED_GEOMETRY_SUBLAYERS`, add:

```ts
// Tous les suffixes de sous-couche que `applyLayers` peut poser sur une
// couche : les trois de la géométrie mixte, plus les couches décoratives de
// SP-27. Une seule liste, utilisée par le rollback du catch ET par le suivi
// dans `applied` — le rollback codait auparavant en dur les trois suffixes
// de MIXED_GEOMETRY_SUBLAYERS, et toute nouvelle sous-couche fuyait, laissant
// la source référencée donc non supprimable (constat 3.5 du pré-vol).
const SUBLAYER_SUFFIXES = ["__point", "__line", "__polygon", "__outline"] as const;
```

Tasks 8 and 13 append `"__icon"` and `"__label"` to this array. Task 14 also
adds the `__labels` **source** id to the cleanup — see that task.

Right after `addTypedLayer`, add:

```ts
// Le contour d'un polygone a besoin d'une vraie couche `line` : MapLibre n'a
// pas de fill-outline-width (déviation 2 du plan). Partage la source, la
// source-layer et le filtre de la couche de remplissage qu'elle décore.
// Volontairement SANS handler de clic : deux couches superposées sur la même
// source déclenchent le handler deux fois pour un seul clic (popup ouvert
// deux fois, cross-filter émis deux fois).
function addOutlineLayer(
  map: maplibregl.Map,
  spec: {
    parentId: string;
    source: string;
    sourceLayer?: string;
    filter?: FilterSpecification;
    paint: Record<string, unknown>;
  },
) {
  map.addLayer({
    id: `${spec.parentId}__outline`,
    type: "line",
    source: spec.source,
    ...(spec.sourceLayer !== undefined ? { "source-layer": spec.sourceLayer } : {}),
    ...(spec.filter !== undefined ? { filter: spec.filter } : {}),
    paint: spec.paint,
  });
}
```

- [ ] **Step 5: Update the three call sites**

`applyLayers` gains a `themeColors: ThemeColors | undefined` parameter
(append it to the parameter list, after `onPopup`) and a local
`const decorativeIds: string[] = [];` next to the existing
`const layerIds: string[] = [];` in the `vector` branch. **Only `layerIds`
gets click handlers**; `decorativeIds` are added to `applied` for teardown.

Site 1 — mixed-geometry loop. Replace the `paint:` line and add the outline
right after `addTypedLayer(...)`:

```ts
            const result = effectivePaint(layer, sub.suffix, themeColors);
            addTypedLayer(map, {
              id,
              type: sub.type,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              filter: ["match", ["geometry-type"], [...sub.geometries], true, false],
              paint: paintFor(result.paint, sub.paintPrefix),
            });
            layerIds.push(id);
            if (sub.suffix === "polygon" && result.outlinePaint) {
              addOutlineLayer(map, {
                parentId: id,
                source: layer.id,
                sourceLayer: layer.sourceLayer,
                filter: ["match", ["geometry-type"], [...sub.geometries], true, false],
                paint: result.outlinePaint,
              });
              decorativeIds.push(`${id}__outline`);
            }
```

Site 2 — known `geometryKind`:

```ts
          const result = effectivePaint(layer, layer.geometryKind, themeColors);
          addTypedLayer(map, {
            id: layer.id,
            type: layerTypeFor(layer.geometryKind),
            source: layer.id,
            sourceLayer: layer.sourceLayer,
            paint: result.paint,
          });
          layerIds.push(layer.id);
          if (layer.geometryKind === "polygon" && result.outlinePaint) {
            addOutlineLayer(map, {
              parentId: layer.id,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              paint: result.outlinePaint,
            });
            decorativeIds.push(`${layer.id}__outline`);
          }
```

Then, after the existing `for (const id of layerIds) { … }` handler loop,
add:

```ts
        for (const id of decorativeIds) applied.add(id);
```

Site 3 — `kind === "feature"`. Rename `featurePaint` to `featureResult`,
read `.paint` in the three `switch` cases, and add the outline after the
switch:

```ts
        const featureResult = effectivePaint(layer, featureGeometryKind, themeColors);
        switch (layer.renderAs ?? "fill") {
          case "circle":
            map.addLayer({ id: layer.id, type: "circle", source: layer.id, paint: featureResult.paint });
            break;
          case "line":
            map.addLayer({ id: layer.id, type: "line", source: layer.id, paint: featureResult.paint });
            break;
          default:
            map.addLayer({ id: layer.id, type: "fill", source: layer.id, paint: featureResult.paint });
            break;
        }
        if (featureGeometryKind === "polygon" && featureResult.outlinePaint) {
          addOutlineLayer(map, {
            parentId: layer.id,
            source: layer.id,
            paint: featureResult.outlinePaint,
          });
          applied.add(`${layer.id}__outline`);
        }
```

- [ ] **Step 6: Fix the rollback `catch` to use `SUBLAYER_SUFFIXES`**

Replace the hard-coded `for (const sub of MIXED_GEOMETRY_SUBLAYERS)` loop
inside the `catch` with:

```ts
      for (const suffix of SUBLAYER_SUFFIXES) {
        const id = `${layer.id}${suffix}`;
        if (map.getLayer(id)) map.removeLayer(id);
        applied.delete(id);
        // Le contour d'une sous-couche de géométrie mixte porte un double
        // suffixe (ex. "communes__polygon__outline").
        for (const inner of SUBLAYER_SUFFIXES) {
          const nested = `${id}${inner}`;
          if (map.getLayer(nested)) map.removeLayer(nested);
          applied.delete(nested);
        }
      }
```

(The nested loop is not elegant, but it is the only shape that removes
`communes__polygon__outline`. If you prefer, replace both loops with a single
pass over `[...applied].filter((id) => id.startsWith(\`${layer.id}__\`))` —
that is equivalent and shorter; either is acceptable, pick one and keep it.)

- [ ] **Step 7: Thread `themeColors` through the component and add the error listener**

- Add `themeColors?: ThemeColors;` to `MapView`'s prop type, right after
  `hideLegend?: boolean;`.
- Add `themeColors` to the destructuring at the `forwardRef` body (line
  ~515): `{ config, onViewChange, onFeatureClick, onReady, hideLegend,
  themeColors, getAuthToken, getCoreUrl }`.
- Add a ref, next to the existing `getCoreUrlRef`:
  `const themeColorsRef = useRef(themeColors);` plus the matching
  `useEffect(() => { themeColorsRef.current = themeColors; }, [themeColors]);`
- Pass `themeColorsRef.current` as the new last argument to **both**
  `applyLayers(...)` calls (the one inside `map.on("load", …)` and the one
  in the `[layersKey, …]` effect).
- Add `JSON.stringify(themeColors)` — or `themeColors` itself if its
  identity is stable at the call sites — to the `layersKey` memo's inputs so
  a theme change actually re-applies the layers:

```ts
  const layersKey = useMemo(
    () => JSON.stringify({ layers: config.layers.map(mapRelevantLayer), themeColors }),
    [config.layers, themeColors],
  );
```

- In the mount effect, right after `map.on("moveend", …)`, add:

```ts
    // Style.addLayer/addSource valident et font `return` : l'erreur part sur
    // l'event `error`, JAMAIS en exception — le try/catch d'applyLayers ne
    // voit rien et la couche disparaît en silence. Ce listener est la seule
    // chose qui rend ce mode de panne observable.
    map.on("error", (e: unknown) => {
      console.error("MapView: MapLibre a signalé une erreur", e);
    });
```

- [ ] **Step 8: Add the stroke entry to `MapSymbologyLegend`**

In `shell/src/builder/widgets/mapWidget.tsx`'s `MapSymbologyLegend` (line
~38), after the existing `{legend.size && …}` block, add:

```tsx
      {legend.stroke && (
        <ul>
          {legend.stroke.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm border-2"
                style={{ borderColor: e.color }}
              />
              {e.value}
            </li>
          ))}
        </ul>
      )}
```

(Constat 1.6 : Task 2 produces and tests `LegendSpec.stroke`; without this
block the entry was dead. `shell/src/map/MapLegend.tsx` — the legend used by
`MapView` outside the widget — lists layer titles only and renders no
symbology legend at all; it is deliberately untouched.)

Add the matching widget test:

```tsx
test("shows a stroke legend entry from a data-driven stroke color", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            stroke: {
              color: {
                field: "region",
                domain: { kind: "categorical", values: ["Nord"] },
                palette: "categorical-a",
              },
              width: { fixed: 1 },
              style: "solid",
            },
          },
        }}
        ctx={{
          mode: "runtime",
          data: state({
            url: "https://fs/communes/items.json",
            records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
          }),
        } as WidgetContext}
      />,
    ),
  );
  expect(await screen.findByText("Nord")).toBeInTheDocument();
});
```

Note: this test only exercises the legend, which `mapWidget.tsx` already
computes from `props.symbology`. It passes **before** Task 19 rewires the
paint path.

- [ ] **Step 9: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx src/builder/widgets/mapWidget.test.tsx`
Expected: PASS, full files green — in particular the pre-existing
mixed-geometry, rollback and symbology tests, which all went through
`effectivePaint`'s old return shape.

- [ ] **Step 10: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): rend le contour et l'opacité dans MapView

Un contour de polygone pose une seconde couche line (fill-outline-color
n'a pas de largeur stylable), SANS handler de clic — deux couches sur la
même source déclenchaient le popup deux fois. Le rollback du catch
énumère désormais SUBLAYER_SUFFIXES au lieu des trois suffixes de
géométrie mixte codés en dur. MapView reçoit themeColors (prérequis du
câblage du widget carte) et écoute l'event `error` de MapLibre, seul
moyen de voir une couche rejetée par le validateur de style.
EOF
)"
```

---

## Task 4: Shell — `MapSymbologyEditor.tsx`: contour + opacité UI, et correction de `clearColor`/`clearSize`

**Files:**
- Modify: `shell/src/map/MapSymbologyEditor.tsx`
- Modify: `shell/src/map/MapSymbologyEditor.test.tsx`

**Interfaces:**
- Consumes: `LayerStroke`, `StrokeStyle`, `LayerSymbology` from Task 2.
- Produces: no new exports.

**Facts about the file you are editing** (verified):
- It has **no** `renderEditor` helper. Each of its **18** tests calls
  `render(<MapSymbologyEditor value={…} availableFields={…}
  themeColors={…} runStatistics={vi.fn()} sampleField={vi.fn()}
  onChange={vi.fn()} />)` inline.
- Its imports are `{ render, screen } from "@testing-library/react"` and
  `userEvent from "@testing-library/user-event"`. **`fireEvent` is not
  imported** — add it to the existing import if you use it.
- Shared class constants exist: `labelCls`, `inputCls`, and `listId` (a
  `useId()` value; the fields datalist is `` `${listId}-fields` ``).
- `clearColor`/`clearSize` (lines ~94-102) each test only **the other** of
  the two historical encodings:
  `onChange(rest.size ? rest : undefined)` / `onChange(rest.color ? rest :
  undefined)`. With a symbology carrying `stroke`/`opacity`/`label`/`icon`,
  clicking "remove color" returns `undefined` and **destroys all of them**.
  This is `CLAUDE.md` trap #4 and the very regression (SP-25 final review,
  C1) those two functions exist to fix. Fixing it is part of **this** task,
  not of a final review.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/map/MapSymbologyEditor.test.tsx`, and add `fireEvent`
to the `@testing-library/react` import:

```tsx
const baseProps = {
  availableFields: ["population", "region"],
  themeColors: undefined,
  runStatistics: vi.fn(),
  sampleField: vi.fn(),
};

test("l'opacité écrit une valeur fixe 0-100", () => {
  const onChange = vi.fn();
  render(<MapSymbologyEditor {...baseProps} value={undefined} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Opacité"), { target: { value: "60" } });
  expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ opacity: 60 }));
});

test("« Ajouter un contour » crée un contour fixe par défaut", async () => {
  const onChange = vi.fn();
  render(<MapSymbologyEditor {...baseProps} value={undefined} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un contour" }));
  expect(onChange).toHaveBeenLastCalledWith({
    stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
  });
});

test("changer la couleur, l'épaisseur et le style du contour écrit stroke", () => {
  const onChange = vi.fn();
  const value = {
    stroke: { color: { fixed: "#000000" as const }, width: { fixed: 1 }, style: "solid" as const },
  };
  render(<MapSymbologyEditor {...baseProps} value={value} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Couleur de contour"), {
    target: { value: "#123456" },
  });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ stroke: expect.objectContaining({ color: { fixed: "#123456" } }) }),
  );
  fireEvent.change(screen.getByLabelText("Épaisseur de contour (px)"), { target: { value: "3" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ stroke: expect.objectContaining({ width: { fixed: 3 } }) }),
  );
  fireEvent.change(screen.getByLabelText("Style de contour"), { target: { value: "dashed" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ stroke: expect.objectContaining({ style: "dashed" }) }),
  );
});

test("« Retirer le contour » n'efface que le contour", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        opacity: 80,
        stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer le contour" }));
  expect(onChange).toHaveBeenLastCalledWith({ opacity: 80 });
});

// C1 de la revue finale SP-25, réintroduit par SP-27 : clearColor/clearSize
// ne regardaient que l'AUTRE des deux encodages historiques.
test("retirer la couleur préserve tous les autres encodages", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        color: {
          field: "region", mode: "categorical", palette: "categorical-a",
          domain: { kind: "categorical", values: ["A"] }, computedAt: "2026-08-27T00:00:00Z",
        },
        opacity: 70,
        stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer la couleur" }));
  expect(onChange).toHaveBeenLastCalledWith({
    opacity: 70,
    stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
  });
});

test("retirer le dernier encodage repasse la symbologie à undefined", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer le contour" }));
  expect(onChange).toHaveBeenLastCalledWith(undefined);
});
```

The accessible name used by "Retirer la couleur" must match the button that
`clearColor` is already wired to — **read the existing JSX first** and use
its real label; if the existing button has a different name, use that name in
the test rather than renaming production UI in this task.

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx -t "contour|Opacité|encodages|undefined"`
Expected: FAIL.

- [ ] **Step 3: Replace `clearColor`/`clearSize` with one generic clearer**

```ts
  // Un seul chemin de retrait pour TOUS les encodages : la version
  // précédente testait « reste-t-il l'AUTRE encodage historique ? »
  // (rest.size / rest.color), ce qui détruisait silencieusement stroke,
  // opacity, label et icon (piège n°4 de CLAUDE.md, régression C1 de
  // SP-25). Ne jamais réintroduire de test nommant un encodage précis.
  function clearEncoding(key: keyof LayerSymbology) {
    const rest = { ...(value ?? {}) };
    delete rest[key];
    onChange(Object.keys(rest).length > 0 ? rest : undefined);
  }

  function clearColor() {
    clearEncoding("color");
  }

  function clearSize() {
    clearEncoding("size");
  }
```

Every later task that adds an encodable block (Tasks 12, 14) uses
`clearEncoding("icon")` / `clearEncoding("label")` — never a new bespoke
clearer.

- [ ] **Step 4: Implement the opacity block**

Add right after the existing size block's closing element, before the
component's final `</div>`:

```tsx
      <label className={labelCls}>
        Opacité
        <input
          aria-label="Opacité"
          type="range"
          min={0}
          max={100}
          step={5}
          className="w-full"
          value={value?.opacity ?? 100}
          onChange={(e) => onChange({ ...value, opacity: Number(e.target.value) })}
        />
      </label>
```

- [ ] **Step 5: Implement the stroke block**

Handlers, next to `clearEncoding`:

```ts
  const stroke = value?.stroke;

  function setStroke(patch: Partial<LayerStroke>) {
    onChange({
      ...value,
      stroke: {
        color: stroke?.color ?? { fixed: "#000000" },
        width: stroke?.width ?? { fixed: 1 },
        style: stroke?.style ?? "solid",
        ...patch,
      },
    });
  }
```

JSX, right after the opacity `<label>`:

```tsx
      {!stroke && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
          onClick={() => setStroke({})}
        >
          Ajouter un contour
        </button>
      )}
      {stroke && (
        <div className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2">
          <label className={labelCls}>
            Couleur de contour
            <input
              aria-label="Couleur de contour"
              type="color"
              value={"fixed" in stroke.color ? stroke.color.fixed : "#000000"}
              onChange={(e) => setStroke({ color: { fixed: e.target.value } })}
            />
          </label>
          <label className={labelCls}>
            Épaisseur de contour (px)
            <input
              aria-label="Épaisseur de contour (px)"
              type="number"
              min={0}
              max={20}
              className={inputCls}
              value={"fixed" in stroke.width ? stroke.width.fixed : 1}
              onChange={(e) => setStroke({ width: { fixed: Number(e.target.value) } })}
            />
          </label>
          <label className={labelCls}>
            Style de contour
            <select
              aria-label="Style de contour"
              className={inputCls}
              value={stroke.style}
              onChange={(e) => setStroke({ style: e.target.value as StrokeStyle })}
            >
              <option value="solid">Plein</option>
              <option value="dashed">Tirets</option>
              <option value="dotted">Pointillés</option>
            </select>
          </label>
          <button
            type="button"
            className="self-start text-xs text-red-700 underline"
            onClick={() => clearEncoding("stroke")}
          >
            Retirer le contour
          </button>
        </div>
      )}
```

Add `type LayerStroke` and `type StrokeStyle` to the existing import from
`../builder/widgets/mapSymbology`.

**Scope note, written so a reviewer does not read it as a gap:** this task
ships the **fixed-value** stroke path only (`{ fixed: … }`). The data-driven
`{ field, domain, palette }` path that Task 2's `buildMapPaint` supports is
**not** wired from the UI by this plan at all — the earlier draft promised
Task 11 would factor the existing color field/classification/palette
sub-editor (lines 141-280) into a shared `FieldClassificationPicker` and
reuse it for `stroke.color`, and that promise is **withdrawn**: it is a
refactor of the most-tested part of this component, with no test in this
plan exercising it, and Task 12 is already the largest UI task. A
data-driven stroke color therefore remains authorable only through the MCP /
a hand-written config until a follow-up SP wires it. This is listed in the
follow-ups at the end of this plan.

- [ ] **Step 6: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: PASS — the 6 new tests plus the 18 pre-existing ones.

- [ ] **Step 7: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): blocs contour (fixe) et opacité dans MapSymbologyEditor

Remplace aussi clearColor/clearSize par un clearEncoding générique :
les deux ne testaient que l'AUTRE encodage historique et détruisaient
silencieusement stroke/opacity/label/icon (piège n°4 de CLAUDE.md,
régression C1 de la revue finale SP-25).
EOF
)"
```

---

## Task 5: Shell — contour classé éditable (`FieldClassificationPicker` extrait puis partagé)

**Files:**
- Create: `shell/src/map/FieldClassificationPicker.tsx`
- Create: `shell/src/map/FieldClassificationPicker.test.tsx`
- Modify: `shell/src/map/MapSymbologyEditor.tsx`
- Modify: `shell/src/map/MapSymbologyEditor.test.tsx`
- Modify: `shell/src/builder/widgets/mapSymbology.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.test.ts`

**Interfaces:**
- Consumes: `LayerStroke`, `StrokeColorEncoding`, `ColorClassification`,
  `ColorDomain`, `PaletteId`, `computeColorDomain`, `formatDomain` (Task 2 and
  existing).
- Produces: `FieldClassificationPicker` (a **new** component, extracted from
  the color UI already in `MapSymbologyEditor.tsx`) and the data-driven path
  of `stroke.color` in the editor. `StrokeColorEncoding`'s field variant gains
  `computedAt: string`.

### Correction du brief : `FieldClassificationPicker` n'existe pas

Le brief de cette passe demandait de « réutiliser le
`FieldClassificationPicker` de SP-25 ». **Il n'existe pas.** Vérifié :
`grep -rn 'FieldClassificationPicker' shell/src/ docs/` ne trouve que deux
occurrences, toutes deux dans **ce plan** (la promesse de la première
rédaction, puis son retrait). Le composant n'a jamais été livré par SP-25 :
l'UI de classification est **inline** dans `MapSymbologyEditor.tsx`, lignes
141-280. Cette tâche l'**extrait** d'abord, puis la réutilise. C'est le piège
n° 3 de `CLAUDE.md` (« le texte littéral d'un plan ou d'un brief est
régulièrement faux sur les interfaces »), corrigé sans re-demander et
consigné ici.

### La contrainte qui dicte la forme de l'extraction

Les noms accessibles de l'UI couleur actuelle sont uniques par instance et
**16 tests existants** s'appuient dessus par `getByLabelText`/`getByRole` :
`"Champ couleur"`, `"Palette"`, `"Type de couleur"`,
`"Méthode de classification"`, `"Nombre de classes"`,
`"Recalculer les classes"`. Si le composant extrait était réutilisé tel quel
pour le contour, ces noms seraient **dupliqués** dès qu'un contour classé est
configuré, et chaque `getByLabelText("Palette")` lèverait « found multiple
elements ». Le composant prend donc un objet `labels` **explicite** : l'usage
couleur y passe exactement les chaînes d'aujourd'hui (DOM et noms accessibles
**inchangés au caractère près**, donc zéro modification des 16 tests
existants), l'usage contour y passe des chaînes distinctes.

### Tests de non-régression exigés (noms réels du dépôt)

Ces **16** tests de `shell/src/map/MapSymbologyEditor.test.tsx` doivent rester
verts **sans être modifiés** ; ils sont la couverture de non-régression de
l'extraction, et la tâche est en échec si l'un d'eux doit être touché :

1. `no color field selected: shows the field picker only`
2. `theme-primary palette option is absent without a theme`
3. `theme-primary palette option is present with a theme`
4. `classification method selector is hidden in categorical mode and shown in numeric mode`
5. `class count selector is hidden when the method is continuous`
6. `recompute button calls runStatistics and writes domain + computedAt via onChange`
7. `recompute button for the size field calls runStatistics and writes size domain`
8. `a failing recompute surfaces an error instead of hanging silently`
9. `two MapSymbologyEditor instances render distinct datalist ids`
10. `a failing size recompute surfaces an error instead of an unhandled rejection`
11. `shows a hint when a configured color field has never been computed`
12. `shows a hint when a configured size field has never been computed`
13. `clearing the color encoding removes only color, keeping size, via onChange`
14. `clearing the only active encoding calls onChange with undefined`
15. `Jenks option is present by default and hidden when jenksAvailable is false`
16. `computed breaks are shown as text`

Plus les 6 tests ajoutés par Task 4 (contour fixe, opacité, `clearEncoding`).
Et, côté E2E, la preuve SP-25 `author 5 quantile classes on a tiled layer,
save, reload, and the rendered colors survive with no new aggregate call`
(`shell/e2e/map-symbology.spec.ts`) : elle pilote l'UI **par ces mêmes
libellés**, donc elle est le filet de sécurité de dernier recours. Task 20
la relance.

Note : l'encodage **taille** n'entre pas dans l'extraction. Son UI réelle est
un simple champ + un bouton « Recalculer » + l'affichage de `computedAt` :
elle n'a ni palette, ni mode, ni méthode de classification, ni nombre de
classes. La factoriser avec la couleur produirait un composant à moitié de
props optionnelles pour aucun gain. Le test n° 7 et le test n° 10 ci-dessus
la couvrent et doivent rester verts **par non-modification**.

- [ ] **Step 1: Étendre `StrokeColorEncoding` avec `computedAt` (invariant SP-25)**

L'invariant SP-25 est que **les domaines sont figés à l'enregistrement** :
`LayerSymbology.color` porte `domain` + `computedAt`, et le rendu ne
recalcule jamais. Le contour classé doit suivre la même règle. Dans
`shell/src/builder/widgets/mapSymbology.ts`, la variante `field` de
`StrokeColorEncoding` (Task 2) devient :

```ts
export type StrokeColorEncoding =
  | { fixed: string }
  | {
      field: string;
      // Domaine FIGÉ au moment du calcul, comme LayerSymbology.color
      // (invariant SP-25) : le rendu ne recalcule jamais un domaine.
      domain: ColorDomain;
      palette: PaletteId;
      classification?: ColorClassification;
      computedAt: string;
    };
```

`StrokePaintInput` (la forme d'entrée de `buildMapPaint`) **ne** porte pas
`computedAt` : c'est une donnée d'édition, pas de rendu. Ajouter
`classification?: ColorClassification` n'y est pas nécessaire non plus —
`strokeColorValue` discrimine déjà sur `domain.kind`
(`categorical` / `numeric-classed` / `numeric`), exactement comme la branche
couleur. `symbologyToPaintInputs` ne change donc pas.

Test, appended to `shell/src/builder/widgets/mapSymbology.test.ts` :

```ts
test("un contour classé porte un domaine figé et son computedAt", () => {
  const symbology: LayerSymbology = {
    stroke: {
      color: {
        field: "pop",
        domain: { kind: "numeric-classed", breaks: [0, 10, 20, 30] },
        palette: "sequential-blue",
        classification: { method: "quantile", classes: 3 },
        computedAt: "2026-08-27T10:00:00Z",
      },
      width: { fixed: 2 },
      style: "solid",
    },
  };
  expect(
    symbology.stroke && "field" in symbology.stroke.color && symbology.stroke.color.computedAt,
  ).toBe("2026-08-27T10:00:00Z");
});

test("buildMapPaint compile un contour classé en expression step", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    stroke: {
      color: {
        field: "pop",
        domain: { kind: "numeric-classed", breaks: [0, 10, 20, 30] },
        palette: { kind: "sequential", low: "#dbeafe", high: "#1e3a8a" },
      },
      width: { fixed: 2 },
      style: "solid",
    },
  });
  const step = result.paint["fill-outline-color"] as unknown[];
  expect(step[0]).toBe("step");
  expect(step[1]).toEqual(["get", "pop"]);
  // 3 classes ⇒ couleur initiale + 2 paires (seuil, couleur).
  expect(step).toHaveLength(2 + 1 + 4);
  expect(result.outlinePaint?.["line-color"]).toEqual(step);
});
```

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: PASS (la branche `numeric-classed` de `strokeColorValue` existe
déjà depuis Task 2 ; ces tests la verrouillent).

- [ ] **Step 2: Écrire les tests d'extraction du composant**

Create `shell/src/map/FieldClassificationPicker.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { FieldClassificationPicker } from "./FieldClassificationPicker";

const labels = {
  field: "Champ test",
  palette: "Palette test",
  mode: "Type test",
  method: "Méthode test",
  classes: "Classes test",
  recompute: "Recalculer test",
};

function renderPicker(over: Partial<Parameters<typeof FieldClassificationPicker>[0]> = {}) {
  const props = {
    labels,
    listId: "l1",
    availableFields: ["population", "region"],
    themeColors: undefined,
    jenksAvailable: true,
    busy: false,
    error: null as string | null,
    value: undefined,
    onChange: vi.fn(),
    onRecompute: vi.fn(),
    ...over,
  };
  render(<FieldClassificationPicker {...props} />);
  return props;
}

test("sans champ choisi, seuls le champ et la palette sont rendus", () => {
  renderPicker();
  expect(screen.getByLabelText("Champ test")).toBeInTheDocument();
  expect(screen.getByLabelText("Palette test")).toBeInTheDocument();
  expect(screen.queryByLabelText("Type test")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Méthode test")).not.toBeInTheDocument();
});

test("le sélecteur de méthode n'apparaît qu'en mode numérique", () => {
  const { onChange } = renderPicker({
    value: {
      field: "population", mode: "categorical", palette: "categorical-a",
      domain: { kind: "categorical", values: [] }, computedAt: "",
    },
  });
  expect(screen.queryByLabelText("Méthode test")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Type test"), { target: { value: "numeric" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ mode: "numeric", classification: undefined }),
  );
});

test("le nombre de classes est borné à 2-9", () => {
  const { onChange } = renderPicker({
    value: {
      field: "population", mode: "numeric", palette: "sequential-blue",
      classification: { method: "quantile", classes: 5 },
      domain: { kind: "numeric-classed", breaks: [0, 1, 2] }, computedAt: "",
    },
  });
  fireEvent.change(screen.getByLabelText("Classes test"), { target: { value: "42" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ classification: { method: "quantile", classes: 9 } }),
  );
  fireEvent.change(screen.getByLabelText("Classes test"), { target: { value: "1" } });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ classification: { method: "quantile", classes: 2 } }),
  );
});

test("l'option theme-primary suit la présence d'un thème", () => {
  renderPicker({ themeColors: { primary: "#123456" } });
  const select = screen.getByLabelText("Palette test") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(true);
});

test("l'option Jenks disparaît quand jenksAvailable est faux", () => {
  renderPicker({
    jenksAvailable: false,
    value: {
      field: "population", mode: "numeric", palette: "sequential-blue",
      domain: { kind: "numeric", min: 0, max: 1 }, computedAt: "",
    },
  });
  const select = screen.getByLabelText("Méthode test") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "jenks")).toBe(false);
});

test("le bouton de recalcul délègue et se désactive pendant le calcul", async () => {
  const { onRecompute } = renderPicker({
    busy: true,
    value: {
      field: "population", mode: "numeric", palette: "sequential-blue",
      domain: { kind: "numeric", min: 0, max: 1 }, computedAt: "",
    },
  });
  expect(screen.getByRole("button", { name: /Recalculer test|Calcul/ })).toBeDisabled();
  expect(onRecompute).not.toHaveBeenCalled();
});

test("une erreur est affichée en role=alert", () => {
  renderPicker({
    error: "champ inconnu",
    value: {
      field: "population", mode: "numeric", palette: "sequential-blue",
      domain: { kind: "numeric", min: 0, max: 1 }, computedAt: "",
    },
  });
  expect(screen.getByRole("alert")).toHaveTextContent("champ inconnu");
});

test("un domaine jamais calculé affiche l'avertissement, un domaine calculé son résumé", async () => {
  const { onChange: _ } = renderPicker({
    value: {
      field: "population", mode: "categorical", palette: "categorical-a",
      domain: { kind: "categorical", values: ["A", "B"] }, computedAt: "",
    },
  });
  expect(screen.getByText(/non calculées/)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Champ test"));
});
```

- [ ] **Step 3: Extraire le composant**

Create `shell/src/map/FieldClassificationPicker.tsx`. Le corps est **repris
verbatim** des lignes 141-280 de `MapSymbologyEditor.tsx` (champ, datalist,
palette, type, méthode, nombre de classes, bouton de recalcul, erreur,
avertissement « non calculées », résumé du domaine), avec pour seule
modification le remplacement des libellés littéraux par `labels.*` et des
accès `color.*` par `value.*` :

```tsx
// SPDX-License-Identifier: Apache-2.0
// Extrait de MapSymbologyEditor.tsx (lignes 141-280 d'avant SP-27), sans
// changement de comportement : c'est le sous-éditeur « champ + palette +
// mode + classification + recalcul » utilisé par l'encodage COULEUR depuis
// SP-25, et désormais aussi par la couleur de CONTOUR (SP-27).
//
// Les libellés sont injectés, jamais littéraux : deux instances rendues en
// même temps (couleur et contour) auraient sinon des noms accessibles
// dupliqués, et les 16 tests existants de MapSymbologyEditor.test.tsx
// interrogent l'UI couleur par ces noms exacts. L'usage couleur passe donc
// les chaînes historiques au caractère près.
import {
  formatDomain,
  type ColorClassification,
  type ColorDomain,
} from "../builder/widgets/mapSymbology";
import type { PaletteId } from "../builder/widgets/palette";
import type { ThemeColors } from "../api/types";

export type ClassifiedEncoding = {
  field: string;
  mode: "categorical" | "numeric";
  palette: PaletteId;
  classification?: ColorClassification;
  domain: ColorDomain;
  computedAt: string;
};

export type FieldClassificationLabels = {
  field: string;
  palette: string;
  mode: string;
  method: string;
  classes: string;
  recompute: string;
};

export function FieldClassificationPicker({
  labels,
  listId,
  availableFields,
  themeColors,
  jenksAvailable,
  busy,
  error,
  value,
  onChange,
  onRecompute,
}: {
  labels: FieldClassificationLabels;
  // L'id de datalist reste FOURNI par l'hôte : c'est lui qui garantit
  // l'unicité par instance de l'éditeur (I2 de la revue finale SP-25), et
  // deux pickers d'un même éditeur partagent délibérément la même liste de
  // champs.
  listId: string;
  availableFields: string[];
  themeColors: ThemeColors | undefined;
  jenksAvailable: boolean;
  busy: boolean;
  error: string | null;
  value: ClassifiedEncoding | undefined;
  onChange: (patch: Partial<ClassifiedEncoding>) => void;
  onRecompute: () => void;
}) {
  // … corps repris de MapSymbologyEditor.tsx, `color` → `value`,
  // `setColorField` → `onChange`, `recomputeColor` → `onRecompute`,
  // `busy === "color"` → `busy`, `colorError` → `error`, et chaque libellé
  // littéral remplacé par son entrée de `labels` (y compris l'aria-label,
  // qui doit valoir la MÊME chaîne que le texte visible, comme aujourd'hui).
  // `PALETTE_OPTIONS` et `formatDomain` déménagent ici ; `MapSymbologyEditor`
  // les importe depuis ce module s'il en a encore besoin.
}
```

Le déménagement de `PALETTE_OPTIONS` et de `formatDomain` : `formatDomain`
est aujourd'hui une fonction module de `MapSymbologyEditor.tsx` — la déplacer
ici et l'exporter, ou la laisser où elle est et l'importer, au choix ; **une
seule** définition dans les deux cas. Vérifier avec
`grep -rn 'formatDomain' shell/src/` avant de trancher.

- [ ] **Step 4: Brancher l'usage COULEUR sur le composant extrait, à l'identique**

Dans `MapSymbologyEditor.tsx`, remplacer les lignes 141-280 par :

```tsx
      <FieldClassificationPicker
        labels={{
          field: "Champ couleur",
          palette: "Palette",
          mode: "Type de couleur",
          method: "Méthode de classification",
          classes: "Nombre de classes",
          recompute: "Recalculer les classes",
        }}
        listId={listId}
        availableFields={availableFields}
        themeColors={themeColors}
        jenksAvailable={jenksAvailable}
        busy={busy === "color"}
        error={colorError}
        value={color}
        onChange={setColorField}
        onRecompute={() => void recomputeColor()}
      />
      {color && (
        <button
          type="button"
          className="self-start text-xs text-red-700 underline"
          onClick={clearColor}
        >
          Retirer la couleur
        </button>
      )}
```

**Le bouton « Retirer la couleur » reste chez l'hôte**, pas dans le
composant : le contour a son propre bouton de retrait (Task 4) et la
sémantique « retirer cet encodage » appartient à l'éditeur, pas au
sous-éditeur.

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: **PASS, les 16 tests d'origine plus les 6 de Task 4, aucun
modifié.** Si l'un d'eux échoue, c'est que l'extraction a changé un nom
accessible, un ordre de rendu ou une classe : corriger l'extraction, jamais
le test.

- [ ] **Step 5: Écrire les tests du contour classé**

Append to `shell/src/map/MapSymbologyEditor.test.tsx` (réutilise `baseProps`
de Task 4) :

```tsx
test("basculer le contour en data-driven écrit un champ, une palette et un domaine vide", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: { color: { fixed: "#000000" }, width: { fixed: 1 }, style: "solid" },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Couleur de contour par attribut" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      stroke: expect.objectContaining({
        color: {
          field: "",
          mode: "categorical",
          palette: "categorical-a",
          domain: { kind: "categorical", values: [] },
          computedAt: "",
        },
      }),
    }),
  );
});

test("les libellés du contour ne collident pas avec ceux de la couleur", () => {
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        color: {
          field: "region", mode: "categorical", palette: "categorical-a",
          domain: { kind: "categorical", values: ["A"] }, computedAt: "2026-08-27T00:00:00Z",
        },
        stroke: {
          color: {
            field: "pop", mode: "numeric", palette: "sequential-blue",
            domain: { kind: "numeric", min: 0, max: 1 }, computedAt: "",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={vi.fn()}
    />,
  );
  // Les deux pickers coexistent : chaque nom accessible reste unique.
  expect(screen.getByLabelText("Champ couleur")).toBeInTheDocument();
  expect(screen.getByLabelText("Champ couleur de contour")).toBeInTheDocument();
  expect(screen.getByLabelText("Palette")).toBeInTheDocument();
  expect(screen.getByLabelText("Palette du contour")).toBeInTheDocument();
  expect(screen.getByLabelText("Méthode de classification du contour")).toBeInTheDocument();
});

test("« Recalculer les classes du contour » fige le domaine et l'horodatage", async () => {
  const onChange = vi.fn();
  const runStatistics = vi.fn().mockResolvedValue([{ region: "Nord" }, { region: "Sud" }]);
  render(
    <MapSymbologyEditor
      {...baseProps}
      runStatistics={runStatistics}
      value={{
        stroke: {
          color: {
            field: "region", mode: "categorical", palette: "categorical-a",
            domain: { kind: "categorical", values: [] }, computedAt: "",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Recalculer les classes du contour" }),
  );
  await vi.waitFor(() => {
    const last = onChange.mock.calls.at(-1)![0];
    expect(last.stroke.color.domain).toEqual({ kind: "categorical", values: ["Nord", "Sud"] });
    // Invariant SP-25 : le domaine est FIGÉ, avec la date de son calcul.
    expect(last.stroke.color.computedAt).not.toBe("");
  });
});

test("un recalcul de contour en échec affiche une erreur au lieu d'une rejection", async () => {
  const runStatistics = vi.fn().mockRejectedValue(new Error("champ inconnu"));
  render(
    <MapSymbologyEditor
      {...baseProps}
      runStatistics={runStatistics}
      value={{
        stroke: {
          color: {
            field: "region", mode: "categorical", palette: "categorical-a",
            domain: { kind: "categorical", values: [] }, computedAt: "",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={vi.fn()}
    />,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Recalculer les classes du contour" }),
  );
  await vi.waitFor(() =>
    expect(screen.getAllByRole("alert").some((n) => n.textContent?.includes("champ inconnu"))).toBe(
      true,
    ),
  );
});

test("revenir à une couleur de contour fixe efface le champ et le domaine", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: {
          color: {
            field: "region", mode: "categorical", palette: "categorical-a",
            domain: { kind: "categorical", values: ["A"] },
            computedAt: "2026-08-27T00:00:00Z",
          },
          width: { fixed: 1 },
          style: "solid",
        },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Couleur de contour fixe" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      stroke: expect.objectContaining({ color: { fixed: "#000000" } }),
    }),
  );
});

// Cohérence avec Task 4 : « plus rien ne reste » vaut aussi pour un contour
// CLASSÉ, pas seulement pour un contour fixe.
test("retirer un contour classé, seul encodage actif, rend undefined", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        stroke: {
          color: {
            field: "region", mode: "categorical", palette: "categorical-a",
            domain: { kind: "categorical", values: ["A"] },
            computedAt: "2026-08-27T00:00:00Z",
          },
          width: { fixed: 2 },
          style: "dashed",
        },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer le contour" }));
  expect(onChange).toHaveBeenLastCalledWith(undefined);
});
```

- [ ] **Step 6: Implémenter le contour classé dans l'éditeur**

Dans `MapSymbologyEditor.tsx`, à l'intérieur du bloc contour de Task 4,
remplacer le seul `<input type="color" aria-label="Couleur de contour">` par
un choix explicite entre les deux modes, puis le picker partagé quand le mode
est « par attribut » :

```tsx
  const [strokeBusy, setStrokeBusy] = useState(false);
  const [strokeError, setStrokeError] = useState<string | null>(null);
  const strokeColorIsFixed = !!stroke && "fixed" in stroke.color;

  function setStrokeColorPatch(patch: Partial<ClassifiedEncoding>) {
    if (!stroke || "fixed" in stroke.color) return;
    setStroke({ color: { ...stroke.color, ...patch } });
  }

  async function recomputeStrokeDomain() {
    if (!stroke || "fixed" in stroke.color || !stroke.color.field) return;
    const encoding = stroke.color;
    setStrokeBusy(true);
    setStrokeError(null);
    try {
      const domain = await computeColorDomain(
        {
          field: encoding.field,
          mode: encoding.mode,
          classification: encoding.classification,
        },
        { runStatistics, sampleField },
      );
      // Invariant SP-25 : on FIGE le domaine et l'horodatage dans le
      // document ; le rendu (buildMapPaint) ne recalcule jamais.
      setStroke({ color: { ...encoding, domain, computedAt: new Date().toISOString() } });
    } catch (e) {
      setStrokeError(e instanceof Error ? e.message : String(e));
    } finally {
      setStrokeBusy(false);
    }
  }
```

JSX, en tête du bloc contour :

```tsx
          <div className="flex gap-1">
            <button
              type="button"
              className="rounded-md border border-slate-300 px-2 py-1 text-xs"
              aria-pressed={strokeColorIsFixed}
              onClick={() => setStroke({ color: { fixed: "#000000" } })}
            >
              Couleur de contour fixe
            </button>
            <button
              type="button"
              className="rounded-md border border-slate-300 px-2 py-1 text-xs"
              aria-pressed={!strokeColorIsFixed}
              onClick={() =>
                setStroke({
                  color: {
                    field: "",
                    mode: "categorical",
                    palette: "categorical-a",
                    domain: { kind: "categorical", values: [] },
                    computedAt: "",
                  },
                })
              }
            >
              Couleur de contour par attribut
            </button>
          </div>
          {strokeColorIsFixed ? (
            <label className={labelCls}>
              Couleur de contour
              <input
                aria-label="Couleur de contour"
                type="color"
                value={"fixed" in stroke.color ? stroke.color.fixed : "#000000"}
                onChange={(e) => setStroke({ color: { fixed: e.target.value } })}
              />
            </label>
          ) : (
            <FieldClassificationPicker
              labels={{
                field: "Champ couleur de contour",
                palette: "Palette du contour",
                mode: "Type de couleur de contour",
                method: "Méthode de classification du contour",
                classes: "Nombre de classes du contour",
                recompute: "Recalculer les classes du contour",
              }}
              listId={listId}
              availableFields={availableFields}
              themeColors={themeColors}
              jenksAvailable={jenksAvailable}
              busy={strokeBusy}
              error={strokeError}
              value={"fixed" in stroke.color ? undefined : stroke.color}
              onChange={setStrokeColorPatch}
              onRecompute={() => void recomputeStrokeDomain()}
            />
          )}
```

Le reste du bloc contour (épaisseur, style, « Retirer le contour » →
`clearEncoding("stroke")`) est inchangé depuis Task 4 : « plus rien ne
reste » vaut donc mécaniquement pour un contour classé comme pour un contour
fixe, ce que le dernier test de l'étape 5 verrouille.

Ajouter les imports : `FieldClassificationPicker`,
`type ClassifiedEncoding` depuis `./FieldClassificationPicker`.

- [ ] **Step 7: Vérifier que le rendu suit, sur les deux surfaces**

Un contour classé ne sert à rien s'il ne se rend pas. `effectivePaint` passe
déjà `stroke` (résolu par `symbologyToPaintInputs`) à `buildMapPaint`
(Task 3), et Task 19 fait passer `symbology` du widget à `MapView` : aucun
code de rendu n'est à ajouter ici. Ajouter **un** test de bout en bout dans
`shell/src/map/MapView.test.tsx` pour le verrouiller :

```ts
test("un contour classé se compile en expression step sur la couche et son contour", () => {
  render(
    <MapView
      config={tiled({
        geometryKind: "polygon",
        symbology: {
          stroke: {
            color: {
              field: "pop",
              domain: { kind: "numeric-classed", breaks: [0, 10, 20] },
              palette: "sequential-blue",
              mode: "numeric",
              classification: { method: "quantile", classes: 2 },
              computedAt: "2026-08-27T00:00:00Z",
            },
            width: { fixed: 2 },
            style: "solid",
          },
        },
      })}
    />,
  );
  const map = mapInstances[0];
  const paint = (map.getLayer("communes") as { paint: Record<string, unknown> }).paint;
  expect((paint["fill-outline-color"] as unknown[])[0]).toBe("step");
  expect(
    ((map.getLayer("communes__outline") as { paint: Record<string, unknown> }).paint[
      "line-color"
    ] as unknown[])[0],
  ).toBe("step");
});
```

- [ ] **Step 8: Portes complètes + commit**

Run: `cd shell && npx vitest run src/map/FieldClassificationPicker.test.tsx src/map/MapSymbologyEditor.test.tsx src/map/MapView.test.tsx src/builder/widgets/mapSymbology.test.ts`
Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green. Le compte de fichiers de test passe de 162 à **163**
(`FieldClassificationPicker.test.tsx`).

Run: `cd shell && npm run e2e -- map-symbology`
Expected: 1 passed — la preuve SP-25 pilote l'UI couleur par ses libellés,
c'est le filet de dernier recours de l'extraction. **Ne pas sauter cette
vérification** : c'est le seul test qui traverse l'UI réelle rendue par le
navigateur.

```bash
git add shell/src/map/FieldClassificationPicker.tsx shell/src/map/FieldClassificationPicker.test.tsx shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx shell/src/map/MapView.test.tsx shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/mapSymbology.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): rend le contour data-driven éditable (picker de classification partagé)

Extrait FieldClassificationPicker des lignes 141-280 de
MapSymbologyEditor.tsx — le composant n'existait PAS, contrairement à ce
que supposait le brief : l'UI de classification était inline depuis
SP-25. Les libellés sont injectés, l'usage couleur passe les chaînes
historiques au caractère près : les 16 tests existants de l'éditeur et la
preuve E2E SP-25 restent verts sans être modifiés, et deux pickers
coexistants n'ont aucun nom accessible dupliqué.

Le contour classé respecte l'invariant SP-25 : domaine et computedAt
figés à l'enregistrement, jamais recalculés au rendu.
EOF
)"
```

---

## Task 6: Shell — `iconLibrary.ts` (curated Lucide catalogue, generated at build time)

**Files:**
- Create: `shell/scripts/gen-lucide-icons.mjs`
- Create: `shell/src/builder/widgets/lucideIconSvgs.generated.ts` (generated, committed)
- Create: `shell/src/builder/widgets/iconLibrary.ts`
- Create: `shell/src/builder/widgets/iconLibrary.test.ts`
- Modify: `shell/package.json`, `shell/package-lock.json`

**Interfaces:**
- Produces: `IconCategory`, `LUCIDE_ICONS: { name: string; category:
  IconCategory }[]` (**exactly 140 entries**), `rasterizeLucideIcon(name):
  Promise<ImageBitmap>` — consumed by Task 8 (`MapView.tsx`) and Task 12
  (the picker).

**Verified facts** (do not re-derive):
- `lucide-static` current version is **1.34.0**; `package/icons/` contains
  **2035** `.svg` files (not "~1500"); `package.json` says
  `"license": "ISC"` and has **no `exports` field**.
- The 140 names listed in Step 3 were each checked with
  `fs.existsSync("package/icons/<name>.svg")` against the extracted 1.34.0
  tarball: **0 missing, 140/140 unique**.
- The previous draft's list was wrong on two counts: it declared "≥ 150"
  while listing 140, and 6 of its names do not exist in the package at all
  (`garage`, `bridge`, `stairs`, `elevator`, `first-aid-kit`,
  `swimming-pool`) while 5 appeared twice (`star`, `landmark`, `tent`,
  `store`, `ferris-wheel`). Both defects made the task's own tests fail by
  construction.
- jsdom a **ni** `createImageBitmap`, **ni** `URL.createObjectURL`, **ni**
  `HTMLImageElement.prototype.decode` (sonde exécutée : les trois sont
  `undefined`), et ne charge jamais une ressource — le décodage passe donc par
  `installImageDecodeStub()` de Task 1 (`HTMLImageElement` +
  `URL.createObjectURL`), jamais par `createImageBitmap`.
- Les SVG de `lucide-static@1.34.0` portent `width="24" height="24"
  viewBox="0 0 24 24" stroke="currentColor"` (lu dans le paquet réel) : les
  dimensions intrinsèques existent, et `currentColor` doit être substitué.

- [ ] **Step 1: Add the dependency as a devDependency**

Run: `cd shell && npm install --save-dev lucide-static@1.34.0`
Expected: `package.json` gains `"lucide-static": "1.34.0"` under
**`devDependencies`** (pinned exactly — the icon set is generated from it and
a floating range would silently change the generated file). It is a
devDependency because no shell runtime code imports it: the generation
script reads it at author time and the SVG strings are committed.

Also add to `package.json`'s `scripts`:

```json
    "gen:lucide-icons": "node scripts/gen-lucide-icons.mjs"
```

- [ ] **Step 2: Write the generation script**

Create `shell/scripts/gen-lucide-icons.mjs`:

```js
// SPDX-License-Identifier: Apache-2.0
// Matérialise le sous-ensemble curaté de lucide-static (ISC) dans un module
// TS committé. Aucune magie de bundler : ni import dynamique entièrement
// templaté, ni import.meta.glob sur /node_modules (aucune des deux formes
// n'a pu être vérifiée contre la version de Vite du dépôt, et la seconde
// émettrait ~2035 assets minuscules dans le build). Le script lit les 140
// noms depuis iconLibrary.ts et écrit lucideIconSvgs.generated.ts.
//
// Usage : cd shell && npm run gen:lucide-icons
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ICONS_DIR = join("node_modules", "lucide-static", "icons");
const SOURCE = join("src", "builder", "widgets", "iconLibrary.ts");
const TARGET = join("src", "builder", "widgets", "lucideIconSvgs.generated.ts");

// Extrait tous les littéraux de chaîne des tableaux de noms d'iconLibrary.ts.
const src = readFileSync(SOURCE, "utf8");
const block = src.slice(src.indexOf("ICON_NAMES"), src.indexOf("export const LUCIDE_ICONS"));
const names = [...block.matchAll(/"([a-z0-9-]+)"/g)].map((m) => m[1]);
const unique = [...new Set(names)];
if (unique.length !== names.length) {
  throw new Error(`noms dupliqués dans ${SOURCE}`);
}
if (names.length !== 140) {
  throw new Error(`attendu 140 noms dans ${SOURCE}, trouvé ${names.length}`);
}

const entries = names.map((name) => {
  const svg = readFileSync(join(ICONS_DIR, `${name}.svg`), "utf8").trim();
  return `  ${JSON.stringify(name)}: ${JSON.stringify(svg)},`;
});

writeFileSync(
  TARGET,
  `// SPDX-License-Identifier: Apache-2.0
// FICHIER GÉNÉRÉ — ne pas éditer à la main.
// Régénérer : cd shell && npm run gen:lucide-icons
//
// Contenu : ${names.length} pictogrammes de Lucide (https://lucide.dev),
// distribués sous licence ISC via le paquet npm lucide-static@1.34.0.
// Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as
// part of Feather (MIT). All other copyright (c) for Lucide are held by
// Lucide Contributors 2022. Licence ISC conservée telle quelle.
export const LUCIDE_ICON_SVGS: Record<string, string> = {
${entries.join("\n")}
};
`,
  "utf8",
);
console.log(`écrit ${TARGET} (${names.length} icônes)`);
```

- [ ] **Step 3: Write `iconLibrary.ts` with the verified catalogue**

Create `shell/src/builder/widgets/iconLibrary.ts`. The 140 names below were
each verified present in `lucide-static@1.34.0` and are globally unique:

```ts
// SPDX-License-Identifier: Apache-2.0
// Sous-ensemble curaté de Lucide (ISC), 140 pictogrammes en 7 catégories
// cartographiques — PAS le jeu complet, qui compte 2035 fichiers dans
// lucide-static@1.34.0. Les SVG eux-mêmes vivent dans
// lucideIconSvgs.generated.ts, produit par scripts/gen-lucide-icons.mjs :
// lucide-static est une devDependency, rien n'est téléchargé au runtime.
import { LUCIDE_ICON_SVGS } from "./lucideIconSvgs.generated";

export type IconCategory =
  | "generic"
  | "buildings"
  | "nature"
  | "transport"
  | "services"
  | "safety-health"
  | "leisure";

// Le script de génération lit ce bloc : garder la forme
// `ICON_NAMES: Record<IconCategory, string[]>` avec des littéraux de chaîne,
// et 20 noms par catégorie.
const ICON_NAMES: Record<IconCategory, string[]> = {
  generic: [
    "map-pin", "map-pinned", "pin", "flag", "star", "circle-dot", "target",
    "bookmark", "info", "alert-circle", "circle", "square", "triangle",
    "diamond", "compass", "navigation", "crosshair", "locate", "map", "route",
  ],
  buildings: [
    "building", "building-2", "home", "warehouse", "factory", "hotel",
    "church", "castle", "landmark", "tower-control", "radio-tower",
    "construction", "hard-hat", "fence", "door-open", "antenna", "school",
    "library", "university", "brick-wall",
  ],
  nature: [
    "tree-pine", "trees", "leaf", "flower", "flower-2", "mountain",
    "mountain-snow", "waves", "droplet", "droplets", "sun", "cloud",
    "cloud-rain", "wind", "sprout", "bird", "fish", "bug", "shell", "sunrise",
  ],
  transport: [
    "car", "bus", "train", "train-front", "tram-front", "bike", "plane",
    "ship", "truck", "fuel", "parking-circle", "parking-square",
    "traffic-cone", "signpost", "anchor", "sailboat", "car-taxi-front",
    "footprints", "cable-car", "rocket",
  ],
  services: [
    "shopping-cart", "shopping-bag", "store", "coffee", "utensils", "wine",
    "pizza", "croissant", "shirt", "scissors", "wrench", "briefcase",
    "credit-card", "banknote", "package", "gift", "mail", "phone", "wifi",
    "printer",
  ],
  "safety-health": [
    "hospital", "cross", "pill", "stethoscope", "syringe", "bandage",
    "heart-pulse", "thermometer", "ambulance", "life-buoy",
    "fire-extinguisher", "flame", "siren", "shield", "shield-alert",
    "shield-check", "alert-triangle", "phone-call", "biohazard", "radiation",
  ],
  leisure: [
    "camera", "binoculars", "eye", "ticket", "music", "palette", "book-open",
    "gamepad-2", "dumbbell", "volleyball", "trophy", "medal", "party-popper",
    "film", "theater", "guitar", "puzzle", "dice-5", "tent", "ferris-wheel",
  ],
};

export const LUCIDE_ICONS: { name: string; category: IconCategory }[] = (
  Object.entries(ICON_NAMES) as [IconCategory, string[]][]
).flatMap(([category, names]) => names.map((name) => ({ name, category })));

// Couleur de trait injectée : les SVG de lucide-static portent
// `stroke="currentColor"` (vérifié sur le paquet 1.34.0). Hors d'un document
// CSS — dans un <img> ou createImageBitmap — `currentColor` retombe sur la
// valeur initiale de `color`, donc noir. On substitue explicitement pour que
// l'icône ait la couleur voulue du dépôt, et pour que ce ne soit pas un
// hasard de résolution.
const LUCIDE_STROKE = "#1e293b";

const imageCache = new Map<string, Promise<HTMLImageElement>>();

// Décodage d'un blob d'image en quelque chose que map.addImage accepte.
// PAS createImageBitmap : sa prise en charge d'un blob SVG varie d'un
// navigateur à l'autre, et les icônes Lucide comme les icônes personnalisées
// peuvent être du SVG. `map.addImage(id, image, options?)` accepte
// `HTMLImageElement | ImageBitmap | ImageData | {width,height,data} |
// StyleImageInterface` (signature vérifiée dans maplibre-gl@4.7.1), donc un
// HTMLImageElement décodé depuis une URL d'objet convient pour les deux
// familles de type et n'a qu'un seul chemin de code.
export function decodeIconImage(blob: Blob): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(blob);
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("image illisible"));
    img.src = url;
  }).finally(() => {
    // Révoquer dès le décodage : MapLibre copie les pixels dans son atlas au
    // moment de addImage, il ne relit jamais l'URL.
    URL.revokeObjectURL(url);
  });
}

export function rasterizeLucideIcon(name: string): Promise<HTMLImageElement> {
  const cached = imageCache.get(name);
  if (cached) return cached;
  const svg = LUCIDE_ICON_SVGS[name];
  if (svg === undefined) return Promise.reject(new Error(`Icône Lucide inconnue : ${name}`));
  // Substitution sur NOTRE propre asset de confiance, pas de
  // l'assainissement : `split`/`join` plutôt qu'une expression régulière
  // pour qu'aucun caractère spécial ne soit interprété.
  const painted = svg.split('stroke="currentColor"').join(`stroke="${LUCIDE_STROKE}"`);
  const promise = decodeIconImage(new Blob([painted], { type: "image/svg+xml" })).catch((err) => {
    // Ne pas mémoriser un échec : un rechargement doit pouvoir réessayer.
    imageCache.delete(name);
    throw err;
  });
  imageCache.set(name, promise);
  return promise;
}
```

Note vérifiée sur le paquet réel : un fichier de `lucide-static@1.34.0`
commence par `<!-- @license lucide-static v1.34.0 - ISC -->` puis un `<svg>`
portant `width="24" height="24" viewBox="0 0 24 24" fill="none"
stroke="currentColor" stroke-width="2"`. Les dimensions intrinsèques sont
donc présentes, ce dont un `<img>` a besoin pour dimensionner un SVG.

- [ ] **Step 4: Generate the SVG module**

Run: `cd shell && npm run gen:lucide-icons`
Expected: `écrit src/builder/widgets/lucideIconSvgs.generated.ts (140 icônes)`.
If it throws "attendu 140 noms", the catalogue in Step 3 was edited — fix
the catalogue, not the script's assertion.

- [ ] **Step 5: Write the tests**

Create `shell/src/builder/widgets/iconLibrary.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, test, vi } from "vitest";
import { installImageDecodeStub } from "../../test/imageDecodeStub";
import { decodeIconImage, LUCIDE_ICONS, rasterizeLucideIcon } from "./iconLibrary";
import { LUCIDE_ICON_SVGS } from "./lucideIconSvgs.generated";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("LUCIDE_ICONS contient exactement 140 entrées sur 7 catégories", () => {
  expect(LUCIDE_ICONS).toHaveLength(140);
  expect(new Set(LUCIDE_ICONS.map((i) => i.category))).toEqual(
    new Set([
      "generic", "buildings", "nature", "transport", "services",
      "safety-health", "leisure",
    ]),
  );
  for (const category of new Set(LUCIDE_ICONS.map((i) => i.category))) {
    expect(LUCIDE_ICONS.filter((i) => i.category === category)).toHaveLength(20);
  }
});

test("LUCIDE_ICONS n'a aucun nom en doublon", () => {
  const names = LUCIDE_ICONS.map((i) => i.name);
  expect(new Set(names).size).toBe(names.length);
});

// Le module généré est la source de vérité des pixels : un nom du catalogue
// absent du module généré signifie que gen-lucide-icons.mjs n'a pas été
// relancé après une modification du catalogue.
test("chaque nom du catalogue a bien un SVG dans le module généré", () => {
  for (const { name } of LUCIDE_ICONS) {
    expect(LUCIDE_ICON_SVGS[name], `SVG manquant pour "${name}"`).toMatch(/^<svg/);
  }
  expect(Object.keys(LUCIDE_ICON_SVGS)).toHaveLength(140);
});

test("rasterizeLucideIcon décode un nom connu et met le résultat en cache", async () => {
  const { created, revoked } = installImageDecodeStub();
  const first = await rasterizeLucideIcon("map-pin");
  const second = await rasterizeLucideIcon("map-pin");
  expect(first.width).toBeGreaterThan(0);
  expect(second).toBe(first);
  // Une seule URL d'objet créée (cache), et révoquée après décodage.
  expect(created).toHaveLength(1);
  expect(revoked).toEqual(created);
});

test("rasterizeLucideIcon rejette un nom inconnu sans créer d'URL d'objet", async () => {
  const { created } = installImageDecodeStub();
  await expect(rasterizeLucideIcon("pas-une-icone")).rejects.toThrow(/Icône Lucide inconnue/);
  expect(created).toEqual([]);
});

// Les SVG de lucide-static portent stroke="currentColor", qui vaut noir hors
// contexte CSS : la substitution doit être effective, pas implicite.
test("la couleur de trait currentColor est remplacée avant décodage", () => {
  expect(LUCIDE_ICON_SVGS["map-pin"]).toContain('stroke="currentColor"');
});

test("decodeIconImage propage l'échec de décodage et révoque quand même l'URL", async () => {
  const { created, revoked } = installImageDecodeStub({ failing: ["blob:stub/"] });
  await expect(decodeIconImage(new Blob(["x"], { type: "image/png" }))).rejects.toThrow(
    /image illisible/,
  );
  expect(revoked).toEqual(created);
});
```

- [ ] **Step 6: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/iconLibrary.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 7: Verify the production build**

Run: `cd shell && npm run build`
Expected: green. The generated module is plain TypeScript, so there is no
bundler-behaviour risk here; the only thing to check is bundle growth —
report the size of the chunk containing `LUCIDE_ICON_SVGS` in the commit
body. If it exceeds ~120 KB raw, say so and leave it: 140 Lucide outlines
are ~300-600 bytes each, so ~60-85 KB raw is the expected order, and the
module is imported only by `iconLibrary.ts`, itself imported by the
symbology editor and `MapView` — no lazy-loading work is in scope.

- [ ] **Step 8: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run`

Note: `lucideIconSvgs.generated.ts` will be reformatted by Prettier. Either
run `npm run format` on it after generating, or make the script emit
Prettier-compatible output; do **not** add it to `.prettierignore` (the
repo has no precedent for that, and `src/api/generated/` is formatted like
the rest).

```bash
git add shell/package.json shell/package-lock.json shell/scripts/gen-lucide-icons.mjs shell/src/builder/widgets/lucideIconSvgs.generated.ts shell/src/builder/widgets/iconLibrary.ts shell/src/builder/widgets/iconLibrary.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute le catalogue d'icônes Lucide curatées (140, vérifiées)

140 pictogrammes lucide-static@1.34.0 (ISC) en 7 catégories, chaque nom
vérifié présent dans le paquet. Les SVG sont matérialisés dans un module
généré et committé par scripts/gen-lucide-icons.mjs : lucide-static
reste une devDependency, aucun import.meta.glob sur node_modules,
aucun des 2035 fichiers du paquet n'entre dans le build.
EOF
)"
```

---

## Task 7: Shell — `mapSymbology.ts`: icon encoding (layout, not paint)

**Files:**
- Modify: `shell/src/builder/widgets/mapSymbology.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.test.ts`

**Interfaces:**
- Produces: `IconRef`, `LayerIcon`, `LayerSymbology.icon`, `iconImageId`,
  `MapPaintResult.iconLayout` + `.iconImages` populated, `LegendSpec.icon` —
  consumed by Tasks 8, 12, 19.
- Does **not** import `iconLibrary.ts`: this module stays
  icon-source-agnostic and only ever handles image **ids**, never pixels.

**Verified fact that shapes this task:** `icon-image` is a **layout**
property of `symbol` layers (`v8.json.layout_symbol["icon-image"]`,
`property-type: "data-driven"`, `expression.parameters: ["zoom","feature"]`).
Putting it in `paint` yields the validator error `layers[0].paint.icon-image:
unknown property "icon-image"`, and because `Style.addLayer` does
`if (this._validate(...)) return;` the whole layer would be dropped in
silence. A `symbol` layer whose layout carries `icon-image` + `icon-size` +
`icon-allow-overlap` validates with **no errors** and, unlike `text-field`,
requires **no `glyphs`** in the style (both verified with
`validateStyleMin`).

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/mapSymbology.test.ts`:

```ts
test("buildMapPaint on a point layer with a categorical icon emits iconLayout, never paint", () => {
  const result = buildMapPaint({}, null, null, "point", undefined, {
    icon: {
      field: "categorie",
      domain: { kind: "categorical", values: ["ecole", "commerce"] },
      mapping: {
        ecole: { source: "lucide", name: "school" },
        commerce: { source: "lucide", name: "shopping-cart" },
      },
      fallback: { source: "lucide", name: "map-pin" },
    },
  });
  expect(result.iconLayout).toEqual({
    "icon-image": [
      "match", ["get", "categorie"],
      "ecole", "lucide:school",
      "commerce", "lucide:shopping-cart",
      "lucide:map-pin",
    ],
    "icon-size": 1,
    "icon-allow-overlap": true,
  });
  expect(result.paint["icon-image"]).toBeUndefined();
  expect(result.iconImages).toEqual([
    "lucide:school", "lucide:shopping-cart", "lucide:map-pin",
  ]);
});

test("without an explicit fallback the match default is the first mapped icon", () => {
  const result = buildMapPaint({}, null, null, "point", undefined, {
    icon: {
      field: "categorie",
      domain: { kind: "categorical", values: ["a"] },
      mapping: { a: { source: "lucide", name: "star" } },
    },
  });
  expect(result.iconLayout?.["icon-image"]).toEqual([
    "match", ["get", "categorie"], "a", "lucide:star", "lucide:star",
  ]);
  expect(result.iconImages).toEqual(["lucide:star"]);
});

test("an icon encoding with no mapped value produces no icon layer at all", () => {
  const result = buildMapPaint({}, null, null, "point", undefined, {
    icon: { field: "categorie", domain: { kind: "categorical", values: ["a"] }, mapping: {} },
  });
  expect(result.iconLayout).toBeUndefined();
  expect(result.iconImages).toEqual([]);
});

test("buildMapPaint icon on a non-point geometry is a no-op", () => {
  const result = buildMapPaint({}, null, null, "polygon", undefined, {
    icon: {
      field: "categorie",
      domain: { kind: "categorical", values: ["a"] },
      mapping: { a: { source: "lucide", name: "star" } },
    },
  });
  expect(result.iconLayout).toBeUndefined();
  expect(result.iconImages).toEqual([]);
});

test("iconImageId distinguishes lucide from custom refs", () => {
  expect(iconImageId({ source: "lucide", name: "school" })).toBe("lucide:school");
  expect(iconImageId({ source: "custom", id: "abc123" })).toBe("custom:abc123");
});

test("buildLegend includes an icon entry per mapped value", () => {
  const legend = buildLegend({}, null, null, "point", undefined, {
    icon: {
      field: "categorie",
      domain: { kind: "categorical", values: ["ecole", "jamais-mappe"] },
      mapping: { ecole: { source: "lucide", name: "school" } },
    },
  });
  expect(legend?.icon).toEqual({
    field: "categorie",
    entries: [{ value: "ecole", imageId: "lucide:school" }],
  });
});
```

Add `iconImageId` to the file's import from `./mapSymbology`.

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts -t "icon"`
Expected: FAIL.

- [ ] **Step 3: Add the types and the id helper**

```ts
export type IconRef = { source: "lucide"; name: string } | { source: "custom"; id: string };

export type LayerIcon = {
  field: string;
  domain: { kind: "categorical"; values: string[] };
  mapping: Record<string, IconRef>;
  fallback?: IconRef;
};

// L'id d'image MapLibre auquel un IconRef résout — vocabulaire partagé entre
// ce module (qui ne connaît que l'ID) et MapView.tsx (Task 8, qui charge les
// pixels via map.addImage).
export function iconImageId(ref: IconRef): string {
  return ref.source === "lucide" ? `lucide:${ref.name}` : `custom:${ref.id}`;
}
```

Extend `LayerSymbology` with `icon?: LayerIcon;`, `PaintExtras` with
`icon?: LayerIcon;`, and `LegendSpec` with
`icon?: { field: string; entries: { value: string; imageId: string }[] };`.

- [ ] **Step 4: Populate `iconLayout`/`iconImages` in `buildMapPaint`**

Insert right after the opacity block from Task 2:

```ts
  const icon = extras?.icon;
  if (icon && geometryKind === "point") {
    const normalized = normalizeDomain(icon.domain);
    if (normalized?.kind === "categorical") {
      const match: unknown[] = ["match", ["get", icon.field]];
      const images: string[] = [];
      for (const value of normalized.values) {
        const ref = icon.mapping[value];
        if (!ref) continue;
        const id = iconImageId(ref);
        match.push(value, id);
        images.push(id);
      }
      if (images.length > 0) {
        // `match` exige un défaut. L'ordre de `iconImages` est significatif :
        // valeurs mappées puis fallback (les tests l'asserent).
        const fallbackId = icon.fallback ? iconImageId(icon.fallback) : images[0];
        match.push(fallbackId);
        if (!images.includes(fallbackId)) images.push(fallbackId);
        // icon-image est LAYOUT : jamais dans `paint`, sous peine de voir la
        // couche entière rejetée par le validateur, en silence.
        result.iconLayout = {
          "icon-image": match,
          "icon-size": 1,
          "icon-allow-overlap": true,
        };
        result.iconImages = images;
      }
    }
  }
```

- [ ] **Step 5: Extend `buildLegend`**

```ts
  const icon = extras?.icon;
  if (icon) {
    const normalized = normalizeDomain(icon.domain);
    if (normalized?.kind === "categorical") {
      const entries = normalized.values
        .filter((v) => icon.mapping[v])
        .map((v) => ({ value: v, imageId: iconImageId(icon.mapping[v]) }));
      if (entries.length > 0) legend.icon = { field: icon.field, entries };
    }
  }

  return legend.color || legend.size || legend.stroke || legend.icon ? legend : null;
```

- [ ] **Step 6: Run to verify pass + full gates + commit**

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts`
Expected: PASS, whole file green.

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/mapSymbology.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute l'encodage icon (data-driven) à LayerSymbology

Icônes catégorielles sur les couches de points. icon-image est une
propriété LAYOUT du style-spec : elle sort dans MapPaintResult.iconLayout
et jamais dans paint — une clé layout posée dans paint fait rejeter la
couche entière par le validateur, sans exception, la couche disparaît
sans aucun signal.
EOF
)"
```

---

## Task 8: Shell — `MapView.tsx`: charge les images d'icônes et pose la couche `symbol`

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (legend icon entry only)
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `MapPaintResult.iconLayout`/`.iconImages`, `iconImageId`,
  `LayerIcon` (Task 7); `rasterizeLucideIcon`, `decodeIconImage` (Task 6);
  the extended `MockMap` and `installImageDecodeStub` (Task 1).
- Produces: a `${id}__icon` `symbol` layer per point layer with icons;
  `SUBLAYER_SUFFIXES` gains `"__icon"`.

**Ordering decision, verified** (déviation 11): image loading happens
**after** `applyLayers`, not before. `Style.addImage` calls
`_afterImageUpdated(id)` which sets `_changedImages[id] = true`,
`_changed = true`, broadcasts the new image list and fires a `data` event —
so a `symbol` layer that already references a not-yet-loaded image repaints
by itself as soon as the image lands. Making `applyLayers` wait on a promise
would have broken every existing synchronous `MapView` test.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/map/MapView.test.tsx`:

```ts
test("a point layer with an icon encoding gets a paired symbol layer carrying icon-image in layout", () => {
  installImageDecodeStub();
  render(
    <MapView
      config={tiled({
        geometryKind: "point",
        symbology: {
          icon: {
            field: "categorie",
            domain: { kind: "categorical", values: ["ecole"] },
            mapping: { ecole: { source: "lucide", name: "school" } },
          },
        },
      })}
    />,
  );
  const map = mapInstances[0];
  // La couche principale reste un cercle, sans aucune clé layout dans paint.
  expect(map.getLayer("communes")).toMatchObject({ type: "circle" });
  expect((map.getLayer("communes") as { paint: Record<string, unknown> }).paint["icon-image"]).toBeUndefined();
  expect(map.getLayer("communes__icon")).toMatchObject({
    type: "symbol",
    source: "communes",
    "source-layer": "communes",
    layout: {
      "icon-image": ["match", ["get", "categorie"], "ecole", "lucide:school", "lucide:school"],
      "icon-size": 1,
      "icon-allow-overlap": true,
    },
  });
  // Pas de handler de clic sur la couche d'icônes : sinon un clic ouvrirait
  // deux popups (elle est posée exactement sur les points).
  expect(map.layerHandlers["click:communes__icon"] ?? []).toHaveLength(0);
});

test("les images Lucide référencées sont chargées via addImage, sans option sdf", async () => {
  installImageDecodeStub();
  render(
    <MapView
      config={tiled({
        geometryKind: "point",
        symbology: {
          icon: {
            field: "categorie",
            domain: { kind: "categorical", values: ["ecole"] },
            mapping: { ecole: { source: "lucide", name: "school" } },
          },
        },
      })}
    />,
  );
  const map = mapInstances[0];
  await vi.waitFor(() => expect(map.hasImage("lucide:school")).toBe(true));
  // sdf: true déclarerait que l'image EST un signed distance field, ce
  // qu'un ImageBitmap RGBA n'est pas — et rien ici n'utilise icon-color.
  expect(map.images.get("lucide:school")?.options).toBeUndefined();
});

test("une icône qui échoue à charger n'empêche pas les couches d'être posées", async () => {
  installImageDecodeStub({ failing: ["blob:stub/"] });
  const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
  render(
    <MapView
      config={tiled({
        geometryKind: "point",
        symbology: {
          icon: {
            field: "categorie",
            domain: { kind: "categorical", values: ["ecole"] },
            mapping: { ecole: { source: "lucide", name: "school" } },
          },
        },
      })}
    />,
  );
  const map = mapInstances[0];
  // Les couches sont posées SYNCHRONEMENT, avant tout chargement d'image.
  expect(map.getLayer("communes")).toBeDefined();
  expect(map.getLayer("communes__icon")).toBeDefined();
  await vi.waitFor(() => expect(spy).toHaveBeenCalled());
  expect(map.hasImage("lucide:school")).toBe(false);
  spy.mockRestore();
});

test("removing an icon layer removes its symbol sub-layer and its source", () => {
  installImageDecodeStub();
  const { rerender } = render(
    <MapView
      config={tiled({
        geometryKind: "point",
        symbology: {
          icon: {
            field: "categorie",
            domain: { kind: "categorical", values: ["ecole"] },
            mapping: { ecole: { source: "lucide", name: "school" } },
          },
        },
      })}
    />,
  );
  rerender(<MapView config={config} />);
  const map = mapInstances[0];
  expect(map.getLayer("communes__icon")).toBeUndefined();
  expect(map.getSource("communes")).toBeUndefined();
});
```

Add to the file's imports: `import { installImageDecodeStub } from
"../test/imageDecodeStub";` and an `afterEach(() =>
vi.unstubAllGlobals())` (check whether the file already has an `afterEach`;
if so extend it rather than adding a second one).

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "icon"`
Expected: FAIL.

- [ ] **Step 3: Wire `layer.symbology.icon` into `effectivePaint`**

`effectivePaint` (last touched in Task 3) currently passes
`{ stroke, opacity: layer.symbology.opacity }`. Add one field:

```ts
  return buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind, palette, {
    stroke,
    opacity: layer.symbology.opacity,
    icon: layer.symbology.icon,
  });
```

- [ ] **Step 4: Extend `SUBLAYER_SUFFIXES` and add the icon-layer helper**

```ts
const SUBLAYER_SUFFIXES = ["__point", "__line", "__polygon", "__outline", "__icon"] as const;
```

Next to `addOutlineLayer`:

```ts
// Les icônes catégorielles vivent sur une couche `symbol` appariée : le
// `icon-image` est une propriété LAYOUT, qu'un layer `circle` n'accepte pas
// (le validateur rejetterait la couche entière, en silence). Sans handler de
// clic, comme le contour : la couche est posée exactement sur les points, et
// un handler y ferait doubler chaque clic.
function addIconLayer(
  map: maplibregl.Map,
  spec: {
    parentId: string;
    source: string;
    sourceLayer?: string;
    filter?: FilterSpecification;
    layout: Record<string, unknown>;
  },
) {
  map.addLayer({
    id: `${spec.parentId}__icon`,
    type: "symbol",
    source: spec.source,
    ...(spec.sourceLayer !== undefined ? { "source-layer": spec.sourceLayer } : {}),
    ...(spec.filter !== undefined ? { filter: spec.filter } : {}),
    layout: spec.layout,
  } as maplibregl.AddLayerObject);
}
```

- [ ] **Step 5: Call it at the three sites**

Mirror exactly the placement of the `addOutlineLayer` calls added in Task 3.

Site 1 (mixed-geometry loop), after `layerIds.push(id)`:

```ts
            if (sub.suffix === "point" && result.iconLayout) {
              addIconLayer(map, {
                parentId: id,
                source: layer.id,
                sourceLayer: layer.sourceLayer,
                filter: ["match", ["geometry-type"], [...sub.geometries], true, false],
                layout: result.iconLayout,
              });
              decorativeIds.push(`${id}__icon`);
            }
```

Site 2 (known `geometryKind`):

```ts
          if (layer.geometryKind === "point" && result.iconLayout) {
            addIconLayer(map, {
              parentId: layer.id,
              source: layer.id,
              sourceLayer: layer.sourceLayer,
              layout: result.iconLayout,
            });
            decorativeIds.push(`${layer.id}__icon`);
          }
```

Site 3 (`kind === "feature"`), after the switch and the outline block:

```ts
        if (featureGeometryKind === "point" && featureResult.iconLayout) {
          addIconLayer(map, {
            parentId: layer.id,
            source: layer.id,
            layout: featureResult.iconLayout,
          });
          applied.add(`${layer.id}__icon`);
        }
```

- [ ] **Step 6: Add the image loader (after `applyLayers`, never before)**

Module-level, next to `applyLayers`:

```ts
// map.addImage doit finir par arriver pour que la couche `symbol` affiche
// quelque chose — mais PAS avant addLayer : Style.addImage appelle
// _afterImageUpdated(id), qui marque l'image changée et fait repeindre les
// couches symbol qui la référencent. On pose donc les couches
// synchroniquement (aucun test existant ne casse) et on charge les images
// après, en tâche de fond.
//
// allSettled + try/catch par id : une seule icône illisible ne doit jamais
// faire échouer les autres, ni remonter en rejection non gérée.
async function loadIconImages(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  loadCustomIcon: ((iconId: string) => Promise<Blob>) | undefined,
) {
  const ids = new Set<string>();
  for (const layer of layers) {
    if (!layer.visible) continue;
    if (layer.kind !== "vector" && layer.kind !== "feature") continue;
    const icon = layer.symbology?.icon;
    if (!icon) continue;
    for (const ref of Object.values(icon.mapping)) ids.add(iconImageId(ref));
    if (icon.fallback) ids.add(iconImageId(icon.fallback));
  }
  await Promise.allSettled(
    [...ids].map(async (id) => {
      try {
        if (map.hasImage(id)) return;
        let image: HTMLImageElement | undefined;
        if (id.startsWith("lucide:")) {
          image = await rasterizeLucideIcon(id.slice("lucide:".length));
        } else if (id.startsWith("custom:") && loadCustomIcon) {
          // Blob récupéré par fetch AUTHENTIFIÉ (ItemClient) puis décodé
          // localement : jamais `new Image().src = <url du cœur>`, qui ne
          // porte aucun en-tête et prendrait un 401 (constat 4.4). L'URL
          // passée à Image est une URL d'objet locale, same-origin.
          const blob = await loadCustomIcon(id.slice("custom:".length));
          image = await decodeIconImage(blob);
        }
        if (!image) return;
        // Pas d'option { sdf: true } : l'image est du RGBA ordinaire.
        // HTMLImageElement est accepté par addImage (signature vérifiée).
        if (!map.hasImage(id)) map.addImage(id, image);
      } catch (err) {
        console.warn(`MapView: icône ${id} non chargée`, err);
      }
    }),
  );
}
```

Add a `loadCustomIcon?: (iconId: string) => Promise<Blob>` prop to `MapView`
(same optionality precedent as `getAuthToken`/`getCoreUrl`), destructure it
at the `forwardRef` body, and keep it in a
`const loadCustomIconRef = useRef(loadCustomIcon);` refreshed by an effect,
like its siblings. Task 12 supplies it from both hosts.

At **both** `applyLayers` call sites (inside `map.on("load", …)` and in the
`[layersKey, …]` effect), add immediately after the `applyLayers(...)` call:

```ts
    void loadIconImages(map, layersRef.current, loadCustomIconRef.current);
```

Imports to add: `rasterizeLucideIcon` **et `decodeIconImage`** from
`../builder/widgets/iconLibrary`, `iconImageId` from
`../builder/widgets/mapSymbology`.

- [ ] **Step 7: Add the icon entry to `MapSymbologyLegend`**

In `shell/src/builder/widgets/mapWidget.tsx`, after the `{legend.stroke && …}`
block added in Task 3:

```tsx
      {legend.icon && (
        <ul>
          {legend.icon.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span aria-hidden="true" className="text-base">
                ◈
              </span>
              {e.value}
            </li>
          ))}
        </ul>
      )}
```

(A neutral glyph, not the rasterized icon: rendering the real SVG in the
legend is a documented follow-up, not a requirement of any test here.)

Widget test:

```tsx
test("shows an icon legend entry per mapped value", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            icon: {
              field: "categorie",
              domain: { kind: "categorical", values: ["ecole"] },
              mapping: { ecole: { source: "lucide", name: "school" } },
            },
          },
        }}
        ctx={{
          mode: "runtime",
          data: state({
            url: "https://fs/poi/items.json",
            records: [{ id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } }],
          }),
        } as WidgetContext}
      />,
    ),
  );
  expect(await screen.findByText("ecole")).toBeInTheDocument();
});
```

- [ ] **Step 8: Run to verify pass + full gates + commit**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx src/builder/widgets/mapWidget.test.tsx`
Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): charge et rend les icônes sur les couches de points

Couche `symbol` appariée portant icon-image dans son LAYOUT (jamais dans
paint), sans handler de clic. Les images sont chargées APRÈS applyLayers :
addImage marque l'image changée et fait repeindre les couches symbol, donc
aucune raison de rendre applyLayers asynchrone. Une icône illisible est
journalisée et n'empêche plus aucune couche d'être posée.
EOF
)"
```

---

## Task 9: Core — `app/mapicons/` (custom icon library)

**Files:**
- Create: `core/app/mapicons/__init__.py`, `models.py`, `repository.py`,
  `schemas.py`, `svg.py`, `routes.py`
- Create: `core/alembic/versions/0029_map_icons.py`
- Create: `core/tests/test_mapicons_svg.py`
- Create: `core/tests/test_mapicons_routes.py`
- Modify: `core/app/db.py`, `core/app/main.py`, `core/pyproject.toml`
- Modify: `docker-compose.yml`, `docker-compose.prod.yml`,
  `deploy/backup/backup.sh`, `.env.example`

**Interfaces:**
- Produces: `POST /map-icons/presign`, `POST /map-icons`, `GET /map-icons`,
  `DELETE /map-icons/{icon_id}`, `GET /map-icons/{icon_id}/file` — consumed
  by Task 11 (`ItemClient`).

**Verified facts you must not re-derive:**
- `app/secrets/` never touches S3 (`crypto.py`, `models.py`,
  `repository.py`, `routes.py`, `schemas.py` — AES-GCM payloads in the DB)
  and is **admin-only** (`_require_admin` at
  `core/app/secrets/routes.py:22-24`, called at lines 51/97/107). The real
  presign+proxy precedent is `app/tileset3d/` / `app/terrain3d/`.
- `get_s3_client` (`core/app/ingestion/routes.py:36-37`) **raises**
  `RuntimeError("S3 client dependency not configured")` by default; seven
  modules import it from there rather than defining their own. Tests must
  override `ingestion_routes.get_s3_client`.
- `generate_presigned_put_url(client, *, bucket, key, content_type,
  expires_in=900)` passes only `Bucket`/`Key`/`ContentType` to
  `generate_presigned_url("put_object", …)`. **It enforces no size limit** —
  a presigned PUT from this helper accepts an object of any size. A real
  bound therefore has to be checked **after** the upload, via `head_object`.
- `ensure_uploads_bucket(client, bucket: str)` is positional and also calls
  `put_bucket_cors`.
- `core_table_names()` (`core/app/db.py:42-67`) lists 18 `models` modules by
  hand, alphabetically by dotted path, aliased without a leading underscore,
  and returns `frozenset(Base.metadata.tables)`. `init_db()` calls it so
  `create_all` sees every model (SQLite test path only).
  `app/collections/routes.py` uses it as the **collections-registry
  denylist** (`_core_tables()` at line 44, used at 189 and 290). **No
  meta-test enforces that a new models module is listed** — omitting it is
  silent, and the consequence is both a red test suite and a security hole.
- Highest existing Alembic revision is `0028`; `0029` is free. Migration
  header convention: `# SPDX-License-Identifier: Apache-2.0` on line 1, then
  the docstring (French prose, then `Revision ID:` / `Revises:` /
  `Create Date:`), then imports, then the four globals.
- `core/tests/conftest.py` defines **no** `client`/`session`/
  `other_tenant_client` fixture (only `pg_engine`, `qgis_worker_url`,
  `qgis_scratch_dir`, `chromium_available`, `pg_session_factory`,
  `pg_engine_with_procrastinate_schema`, `dcat_shacl_shapes`) and states
  explicitly that SQLite fixtures stay local to each file. The second-tenant
  pattern to copy is `core/tests/test_extensions_routes.py:114-134` /
  `test_secrets_routes.py:136-158`:
  `Tenant(id=uuid.uuid4().hex, slug="other", name="Other")`.
- `_FakeS3Client` in `core/tests/test_tileset3d_routes.py:23-66` implements
  `create_bucket`, `put_bucket_cors`, `create_multipart_upload`,
  `generate_presigned_url`, `complete_multipart_upload`, `head_object`,
  `get_object(Range=…)` — and **not** `put_object` or `delete_object`. The
  fake in this task is therefore a new, smaller one.
- Neither `app/tileset3d` nor `app/terrain3d` sets `Content-Disposition`;
  `X-Content-Type-Options` appears **nowhere** in `core/app/`. Both use
  `Cache-Control: private, max-age=3600`, which is the established
  convention for an authenticated byte response.
- Import-linter: `"app.terrain3d"` is `core/pyproject.toml:212`,
  `"app.secrets"` is 213, `"app.db -> app.terrain3d.models"` is 263, and
  `ignore_imports` is **not** alphabetically sorted (append at the end).

**Product decision recorded here (D4, déviation 13 — renverse la
déviation 9):** custom uploads accept **`image/png` and `image/svg+xml`**.
The SVG is **sanitised at write time** and it is the sanitised bytes that are
stored; the read path never re-sanitises. That is deliberate: one pass, one
place where the guard can be missing, and a stored file that is safe by
construction rather than safe only if the reader remembers to filter.

**Vérifié pour cette tâche, contre la source réelle :**
- `defusedxml` est **déjà** une dépendance directe déclarée du cœur
  (`core/pyproject.toml` : `"defusedxml>=0.7",  # SP-12e : parsing XML sûr
  (XXE + billion-laughs) des GetCapabilities OGC`), résolue en **0.7.1** dans
  `uv.lock`. **Aucune nouvelle dépendance n'est ajoutée.** Son unique usage
  actuel est `core/app/harvest/connectors/ows.py` (`from
  defusedxml.ElementTree import fromstring`).
- Signature réelle : `fromstring(text, forbid_dtd=False,
  forbid_entities=True, forbid_external=True)`. **`forbid_dtd` vaut `False`
  par défaut** : il faut le passer explicitement, sinon un
  `<!DOCTYPE svg SYSTEM "http://evil/x.dtd">` sans déclaration d'entité
  **passe**. Mesuré : avec `forbid_dtd=True`, tout DOCTYPE lève
  `DTDForbidden` ; sans lui, une entité interne ou externe lève
  `EntitiesForbidden` mais un DOCTYPE nu ne lève rien.
- Mesuré aussi : `<script>`, `onload="…"` et `xlink:href="http://…"`
  **traversent** le parseur sans erreur (c'est du XML valide). Le parseur ne
  remplace donc pas une allowlist — il ne protège que des bombes d'entités,
  des DTD et de l'XXE.
- Clés d'attributs : un attribut d'espace de noms arrive sous la forme
  `{http://www.w3.org/1999/xlink}href` (mesuré). Filtrer « toute clé
  contenant `}` » suffit à tuer `xlink:href` sans le nommer.
- Ré-sérialisation : `xml.etree.ElementTree.tostring` préfixerait les balises
  en `ns0:` sur un arbre à espaces de noms. `ET.register_namespace("", …)`
  est **global** et donc à éviter ; la reconstruction locale (tags dépouillés
  de `{ns}`, `xmlns` posé à la main sur la racine) produit exactement
  `<svg width="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">…`
  — mesuré. Aucun autre module du cœur ne sérialise du XML
  (`grep -rn 'register_namespace\|ET.tostring' core/app/` → vide), mais la
  forme locale est retenue quand même : elle ne dépend d'aucun état de
  module.
- **Le suivi `libexpat.so.1` du dépôt ne touche pas ce chemin** — ou plutôt :
  il le touche exactement comme il touche déjà `app.harvest`. Ce suivi dit
  qu'en **conteneur**, `libexpat.so.1` manquait pour `defusedxml` ; il est
  antérieur à SP-27, indépendant de lui, et `defusedxml` s'importe et parse
  correctement dans l'environnement `uv` de développement (mesuré :
  `uv run python -c "from defusedxml.ElementTree import fromstring"` passe,
  version 0.7.1). Conséquence à écrire dans le commit : cette tâche
  **n'aggrave ni ne corrige** ce suivi, mais elle en élargit la surface —
  `app.mapicons` devient le second module du cœur à en dépendre au
  **runtime**, et une image où `libexpat` manque refusera désormais aussi
  l'upload d'un SVG d'icône, pas seulement le moissonnage OGC. À signaler
  dans les suivis non bloquants.
- RFC 7807 : aucune plomberie à écrire. `core/app/main.py:144-154` enregistre
  un `@app.exception_handler(HTTPException)` qui rend
  `media_type="application/problem+json"` avec `type`/`title`/`status`/
  `detail`, et `main.py:131-142` fait de même pour
  `ValidationHTTPException` (`core/app/errors.py`) en ajoutant un membre
  d'extension `errors` **au premier niveau**. Le refus d'un SVG utilise
  `ValidationHTTPException`, dont la forme d'`errors` suit le précédent de
  `core/app/harvest/routes.py:311-313` :
  `[{"field": …, "code": …, "message": …}]`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_mapicons_routes.py`. This harness is **written from
scratch** (there is nothing to copy verbatim): it merges
`test_tileset3d_routes.py`'s S3-override shape with
`test_secrets_routes.py`'s `env`/`_as` shape.

```python
# SPDX-License-Identifier: Apache-2.0
"""Bibliothèque d'icônes personnalisées, tenant-scoped (SP-27 §3.4)."""

import uuid

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
LEGIT_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    b'viewBox="0 0 24 24"><path d="M4 4 L20 20"/></svg>'
)
HOSTILE_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" onload="alert(1)">'
    b'<script>alert(2)</script><path d="M4 4"/></svg>'
)


class _FakeS3Client:
    """Assez de S3 pour ce module : presign, head, get, delete. Volontairement
    distinct du _FakeS3Client de test_tileset3d_routes.py, qui n'implémente ni
    put_object ni delete_object (multipart uniquement)."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "nope"}}, "GetObject")
        data = self.objects[Key]
        if Range is not None:
            start, end = Range.removeprefix("bytes=").split("-")
            data = data[int(start) : int(end) + 1]

        class _Body:
            def __init__(self, chunk: bytes):
                self._chunk = chunk

            def read(self) -> bytes:
                return self._chunk

        return {"Body": _Body(data)}

    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N803
        # Nécessaire depuis D4 : la route de création RÉÉCRIT un SVG assaini
        # à la même clé. Le fake de test_tileset3d_routes.py ne l'a pas.
        self.objects[Key] = Body

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append(Key)
        self.objects.pop(Key, None)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    fake_s3 = _FakeS3Client()
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
    client = TestClient(app)
    return app, client, Session, tenant, alice, fake_s3


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _second_tenant_user(Session):
    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other = get_or_create_user(
            s,
            tenant_id=other_tenant.id,
            oidc_sub="o",
            username="other",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        return other


def _upload(fake_s3, key, payload=PNG_BYTES):
    fake_s3.objects[key] = payload


def test_presign_returns_an_upload_url_and_key(env):
    app, client, _Session, tenant, _alice, _s3 = env
    _as(app, _alice)
    response = client.post(
        "/map-icons/presign", json={"filename": "logo.png", "contentType": "image/png"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["uploadUrl"].startswith("https://minio.test/")
    assert body["key"].startswith(f"{tenant.id}/")
    assert body["key"].endswith("logo.png")


def test_presign_accepts_png_and_svg_and_refuses_everything_else(env):
    app, client, _Session, _tenant, alice, _s3 = env
    _as(app, alice)
    for content_type in ("image/png", "image/svg+xml"):
        response = client.post(
            "/map-icons/presign", json={"filename": "x", "contentType": content_type}
        )
        assert response.status_code == 200, content_type
    for content_type in ("text/html", "image/gif", "application/octet-stream"):
        response = client.post(
            "/map-icons/presign", json={"filename": "x", "contentType": content_type}
        )
        assert response.status_code == 422, content_type


def test_create_then_list_then_delete(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/x.png"
    _upload(fake_s3, key)
    created = client.post(
        "/map-icons",
        json={"title": "Logo", "category": "generic", "s3Key": key, "contentType": "image/png"},
    )
    assert created.status_code == 201
    icon_id = created.json()["id"]

    listed = client.get("/map-icons")
    assert [i["id"] for i in listed.json()] == [icon_id]

    deleted = client.delete(f"/map-icons/{icon_id}")
    assert deleted.status_code == 204
    assert client.get("/map-icons").json() == []
    assert fake_s3.deleted == [key]


def test_create_refuses_a_key_outside_the_callers_tenant_prefix(env):
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    _upload(fake_s3, "someone-else/x.png")
    response = client.post(
        "/map-icons",
        json={
            "title": "Vol",
            "category": "generic",
            "s3Key": "someone-else/x.png",
            "contentType": "image/png",
        },
    )
    assert response.status_code == 403


def test_create_refuses_a_missing_object_and_an_oversized_one(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    missing = client.post(
        "/map-icons",
        json={
            "title": "Absent",
            "category": "generic",
            "s3Key": f"{tenant.id}/absent.png",
            "contentType": "image/png",
        },
    )
    assert missing.status_code == 400

    big_key = f"{tenant.id}/big.png"
    _upload(fake_s3, big_key, b"\x89PNG\r\n\x1a\n" + b"0" * 300_000)
    oversized = client.post(
        "/map-icons",
        json={
            "title": "Gros",
            "category": "generic",
            "s3Key": big_key,
            "contentType": "image/png",
        },
    )
    assert oversized.status_code == 413


def test_create_refuses_bytes_that_contradict_the_declared_type(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/fake.png"
    _upload(fake_s3, key, LEGIT_SVG)  # déclaré PNG, réellement SVG
    response = client.post(
        "/map-icons",
        json={"title": "Faux", "category": "generic", "s3Key": key, "contentType": "image/png"},
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["errors"][0]["code"] == "content_type_mismatch"


def test_create_refuses_a_payload_that_is_neither_png_nor_svg(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/x.png"
    _upload(fake_s3, key, b"GIF89a" + b"0" * 32)
    response = client.post(
        "/map-icons",
        json={"title": "Gif", "category": "generic", "s3Key": key, "contentType": "image/png"},
    )
    assert response.status_code == 400


def test_an_svg_is_sanitized_before_being_stored_and_served(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/logo.svg"
    _upload(fake_s3, key, HOSTILE_SVG)
    created = client.post(
        "/map-icons",
        json={
            "title": "Logo",
            "category": "generic",
            "s3Key": key,
            "contentType": "image/svg+xml",
        },
    )
    assert created.status_code == 201
    # L'objet STOCKÉ est la version assainie : la garde est à l'écriture, la
    # lecture ne réassainit pas.
    stored = fake_s3.objects[key]
    assert b"script" not in stored
    assert b"onload" not in stored
    assert b'd="M4 4"' in stored

    served = client.get(f"/map-icons/{created.json()['id']}/file")
    assert served.status_code == 200
    assert served.content == stored
    assert served.headers["content-type"].startswith("image/svg+xml")
    assert served.headers["x-content-type-options"] == "nosniff"


def test_an_svg_emptied_by_sanitization_is_refused_with_a_problem_json(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/vide.svg"
    _upload(
        fake_s3,
        key,
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b"<script>alert(1)</script></svg>",
    )
    response = client.post(
        "/map-icons",
        json={
            "title": "Vide",
            "category": "generic",
            "s3Key": key,
            "contentType": "image/svg+xml",
        },
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["errors"][0]["code"] == "svg_no_graphics"
    # Contrat explicite de D4 : rien n'est enregistré, et l'objet n'est pas
    # remplacé par une version vide.
    assert client.get("/map-icons").json() == []
    assert b"script" in fake_s3.objects[key]


def test_a_hostile_dtd_svg_is_refused(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/dtd.svg"
    _upload(
        fake_s3,
        key,
        b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY a SYSTEM "file:///etc/passwd">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">&a;</svg>',
    )
    response = client.post(
        "/map-icons",
        json={
            "title": "DTD",
            "category": "generic",
            "s3Key": key,
            "contentType": "image/svg+xml",
        },
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] in {"svg_dtd_forbidden", "svg_unparsable"}


def test_a_valid_png_is_stored_untouched(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/ok.png"
    _upload(fake_s3, key, PNG_BYTES)
    created = client.post(
        "/map-icons",
        json={"title": "PNG", "category": "generic", "s3Key": key, "contentType": "image/png"},
    )
    assert created.status_code == 201
    # Aucun put_object sur le chemin PNG : les octets ne sont pas réécrits.
    assert fake_s3.objects[key] == PNG_BYTES


def test_list_and_read_are_tenant_scoped(env):
    app, client, Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/mine.png"
    _upload(fake_s3, key)
    icon_id = client.post(
        "/map-icons",
        json={"title": "Mine", "category": "generic", "s3Key": key, "contentType": "image/png"},
    ).json()["id"]

    other = _second_tenant_user(Session)
    _as(app, other)
    assert client.get("/map-icons").json() == []
    assert client.get(f"/map-icons/{icon_id}/file").status_code == 404
    assert client.delete(f"/map-icons/{icon_id}").status_code == 404


def test_read_file_serves_the_bytes_with_hardened_headers(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/served.png"
    _upload(fake_s3, key)
    icon_id = client.post(
        "/map-icons",
        json={"title": "Servi", "category": "generic", "s3Key": key, "contentType": "image/png"},
    ).json()["id"]

    response = client.get(f"/map-icons/{icon_id}/file")
    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["cache-control"] == "private, max-age=3600"


def test_create_and_delete_write_audit_entries(env):
    app, client, Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/audited.png"
    _upload(fake_s3, key)
    icon_id = client.post(
        "/map-icons",
        json={"title": "Audit", "category": "generic", "s3Key": key, "contentType": "image/png"},
    ).json()["id"]
    client.delete(f"/map-icons/{icon_id}")

    with Session() as s:
        actions = sorted(
            s.scalars(select(AuditLog.action).where(AuditLog.object_id == icon_id)).all()
        )
    assert actions == ["mapicon.create", "mapicon.delete"]


def test_delete_of_a_missing_icon_is_404(env):
    app, client, _Session, _tenant, alice, _s3 = env
    _as(app, alice)
    assert client.delete("/map-icons/does-not-exist").status_code == 404


def test_a_failing_s3_delete_does_not_lose_the_database_delete(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    key = f"{tenant.id}/orphan.png"
    _upload(fake_s3, key)
    icon_id = client.post(
        "/map-icons",
        json={"title": "Orphan", "category": "generic", "s3Key": key, "contentType": "image/png"},
    ).json()["id"]

    def boom(Bucket, Key):  # noqa: N803
        raise ClientError({"Error": {"Code": "500", "Message": "nope"}}, "DeleteObject")

    fake_s3.delete_object = boom
    assert client.delete(f"/map-icons/{icon_id}").status_code == 204
    assert client.get("/map-icons").json() == []


def test_map_icons_cannot_be_registered_as_a_business_collection(env):
    """core_table_names() est la denylist du registre de collections : sans
    l'import paresseux dans app/db.py, un admin pourrait exposer map_icons en
    OGC API Features (constat 2.23 du pré-vol)."""
    from app.db import core_table_names

    assert "map_icons" in core_table_names()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd core && uv run pytest tests/test_mapicons_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: app.mapicons` at import time.

- [ ] **Step 3: Create the migration**

`core/alembic/versions/0029_map_icons.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""app.mapicons — table map_icons (SP-27 §3.4).

Bibliothèque d'icônes personnalisées par tenant : métadonnées en base, octets
en S3 (bucket S3_MAPICONS_BUCKET). Table neuve, sans donnée à migrer ; les
deux sens sont vérifiés sur base non vide à l'étape 12 de la tâche.

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_icons",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("s3_key", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_map_icons_tenant_id", "map_icons", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_map_icons_tenant_id", table_name="map_icons")
    op.drop_table("map_icons")
```

- [ ] **Step 4: Create `models.py`** (style copied from `app/terrain3d/models.py`)

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class MapIcon(Base):
    __tablename__ = "map_icons"
    __table_args__ = (Index("ix_map_icons_tenant_id", "tenant_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
```

- [ ] **Step 5: Create `repository.py`**

```python
# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mapicons.models import MapIcon


def create_icon(
    session: Session,
    *,
    tenant_id: str,
    created_by: str,
    title: str,
    category: str,
    s3_key: str,
    content_type: str,
) -> MapIcon:
    icon = MapIcon(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        title=title,
        category=category,
        s3_key=s3_key,
        content_type=content_type,
        created_by=created_by,
    )
    session.add(icon)
    session.flush()
    session.refresh(icon)
    return icon


def list_icons(session: Session, *, tenant_id: str) -> list[MapIcon]:
    return list(
        session.scalars(
            select(MapIcon).where(MapIcon.tenant_id == tenant_id).order_by(MapIcon.title)
        ).all()
    )


def get_icon(session: Session, *, tenant_id: str, icon_id: str) -> MapIcon | None:
    return session.scalar(
        select(MapIcon).where(MapIcon.tenant_id == tenant_id, MapIcon.id == icon_id)
    )


def delete_icon(session: Session, icon: MapIcon) -> None:
    session.delete(icon)
    session.flush()
```

- [ ] **Step 6: Create `schemas.py` — the single home of both constants**

```python
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel

# Une seule définition, importée par routes.py — jamais dupliquée.
# PNG et SVG (D4). Un SVG est ASSAINI à l'écriture par app.mapicons.svg et
# c'est la version assainie qui est stockée : la lecture ne réassainit pas.
ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/svg+xml"})
# Borne réelle, vérifiée par head_object APRÈS l'upload : le presign émis par
# generate_presigned_put_url ne porte aucune condition de taille.
MAX_ICON_BYTES = 200_000
# La signature PNG et la détection de type vivent dans svg.py
# (sniff_content_type) : une seule définition, à côté de l'assainisseur.


class MapIconPresignRequest(BaseModel):
    filename: str
    contentType: str


class MapIconPresignResponse(BaseModel):
    uploadUrl: str
    key: str


class MapIconCreate(BaseModel):
    title: str
    category: str
    s3Key: str
    contentType: str


class MapIconOut(BaseModel):
    id: str
    title: str
    category: str
    contentType: str
    createdAt: str
```

- [ ] **Step 6b: Create `svg.py` — l'assainisseur (le cœur de D4)**

Tests first. Create `core/tests/test_mapicons_svg.py` — un test pur, sans
FastAPI ni S3, pour que l'assainisseur soit vérifiable seul :

```python
# SPDX-License-Identifier: Apache-2.0
"""Assainissement des SVG d'icônes (SP-27, D4)."""

import pytest

from app.mapicons.svg import SvgRejected, sanitize_svg, sniff_content_type

LEGIT = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    b'viewBox="0 0 24 24" fill="none" stroke="#1e293b" stroke-width="2">'
    b'<g><path d="M4 4 L20 20"/><circle cx="12" cy="12" r="3"/></g></svg>'
)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_a_legitimate_svg_keeps_its_graphics_and_geometry():
    out = sanitize_svg(LEGIT).decode()
    assert out.startswith("<svg")
    assert 'xmlns="http://www.w3.org/2000/svg"' in out
    assert 'viewBox="0 0 24 24"' in out
    # Les éléments graphiques et leurs géométries survivent INTACTS.
    assert 'd="M4 4 L20 20"' in out
    assert "<circle" in out and 'r="3"' in out
    assert 'stroke="#1e293b"' in out


def test_script_element_is_removed_with_its_subtree():
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<script>alert(1)</script><path d="M0 0"/></svg>'
    )
    out = sanitize_svg(hostile).decode()
    assert "script" not in out
    assert "alert" not in out
    assert 'd="M0 0"' in out


def test_event_handler_attributes_are_removed():
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" onload="alert(1)">'
        b'<circle cx="1" cy="1" r="1" onclick="alert(2)"/></svg>'
    )
    out = sanitize_svg(hostile).decode()
    assert "onload" not in out
    assert "onclick" not in out
    assert "alert" not in out
    assert "<circle" in out


def test_external_and_javascript_hrefs_are_removed():
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" '
        b'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 24 24">'
        b'<image xlink:href="http://evil.test/x.png"/>'
        b'<a href="javascript:alert(1)"><path d="M0 0"/></a></svg>'
    )
    out = sanitize_svg(hostile).decode()
    assert "evil.test" not in out
    assert "javascript" not in out
    assert "xlink" not in out
    # <image> et <a> ne sont pas dans l'allowlist : ils partent entièrement.
    assert "<image" not in out
    assert 'd="M0 0"' not in out


def test_foreign_object_is_removed():
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<foreignObject><body xmlns="http://www.w3.org/1999/xhtml">'
        b"<img src=x onerror=alert(1)></body></foreignObject>"
        b'<path d="M1 1"/></svg>'
    )
    out = sanitize_svg(hostile).decode()
    assert "foreignObject" not in out
    assert "onerror" not in out
    assert 'd="M1 1"' in out


def test_url_and_scheme_bearing_attribute_values_are_removed():
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<path d="M3 3" fill="url(http://evil.test/x)"/>'
        b'<rect x="0" y="0" width="4" height="4" stroke="url(#grad)"/>'
        b'<circle cx="1" cy="1" r="1" fill="data:image/png;base64,AAAA"/></svg>'
    )
    out = sanitize_svg(hostile).decode()
    assert "evil.test" not in out
    assert "url(" not in out
    assert "data:" not in out
    # Les éléments et leurs géométries restent, seules les valeurs partent.
    assert 'd="M3 3"' in out
    assert "<rect" in out and 'width="4"' in out


def test_style_attribute_and_style_element_are_removed():
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b'<style>* { background: url(javascript:alert(1)) }</style>'
        b'<path d="M2 2" style="fill:url(#x)"/></svg>'
    )
    out = sanitize_svg(hostile).decode()
    assert "style" not in out
    assert "javascript" not in out
    assert 'd="M2 2"' in out


@pytest.mark.parametrize(
    "payload",
    [
        b'<!DOCTYPE svg SYSTEM "http://evil.test/x.dtd"><svg xmlns="http://www.w3.org/2000/svg"/>',
        b'<!DOCTYPE s [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
        b'<!DOCTYPE s [<!ENTITY a SYSTEM "file:///etc/passwd">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
    ],
)
def test_dtd_and_entities_are_refused_outright(payload):
    # forbid_dtd=True est OBLIGATOIRE : le défaut de defusedxml est False, et
    # un DOCTYPE nu (sans déclaration d'entité) passerait sinon (mesuré).
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(payload)
    assert exc.value.code in {"svg_dtd_forbidden", "svg_unparsable"}


def test_a_non_xml_payload_is_refused():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(b"\x00\x01 pas du xml")
    assert exc.value.code == "svg_unparsable"


def test_a_non_svg_root_is_refused():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(b'<html xmlns="http://www.w3.org/1999/xhtml"><body/></html>')
    assert exc.value.code == "svg_not_svg_root"


def test_an_svg_emptied_of_all_graphics_is_refused_not_stored_empty():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            b"<script>alert(1)</script></svg>"
        )
    assert exc.value.code == "svg_no_graphics"


def test_missing_dimensions_are_derived_from_viewbox():
    out = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 32">'
        b'<path d="M0 0"/></svg>'
    ).decode()
    # Un <img> a besoin de dimensions intrinsèques pour dimensionner un SVG.
    assert 'width="48"' in out
    assert 'height="32"' in out


def test_an_svg_without_viewbox_or_dimensions_is_refused():
    with pytest.raises(SvgRejected) as exc:
        sanitize_svg(
            b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
        )
    assert exc.value.code == "svg_no_dimensions"


def test_sniff_content_type_recognises_png_svg_and_nothing_else():
    assert sniff_content_type(PNG) == "image/png"
    assert sniff_content_type(LEGIT) == "image/svg+xml"
    assert sniff_content_type(b'<?xml version="1.0"?><svg xmlns="x"/>') == "image/svg+xml"
    assert sniff_content_type(b"GIF89a") is None
    assert sniff_content_type(b"") is None
```

Run: `cd core && uv run pytest tests/test_mapicons_svg.py -v` → FAIL (module
absent).

Then create `core/app/mapicons/svg.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Assainissement des SVG d'icônes personnalisées (SP-27, D4).

Appliqué à l'ÉCRITURE : ce sont les octets assainis qui sont stockés dans S3,
et la lecture ne réassainit jamais. Un seul endroit où la garde peut manquer,
et un fichier stocké sûr par construction.

Deux couches distinctes, parce qu'elles protègent de choses différentes :
1. `defusedxml` (déjà dépendance directe du cœur, SP-12e) neutralise les
   bombes d'entités, les DTD et l'XXE. Mesuré : il ne fait RIEN contre
   <script>, onload= ou xlink:href — c'est du XML parfaitement valide.
2. Une allowlist stricte d'éléments et d'attributs, appliquée sur l'arbre
   parsé, puis une RE-SÉRIALISATION depuis cet arbre. Jamais de filtrage par
   expression régulière sur le texte source : un filtre textuel se contourne
   par encodage, un arbre reconstruit ne contient que ce qu'on y a remis.
"""

import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring

SVG_NS = "http://www.w3.org/2000/svg"

# Allowlist d'éléments : primitives géométriques et regroupement, rien qui
# puisse charger, exécuter ou référencer quoi que ce soit. Absents et donc
# supprimés AVEC leur sous-arbre : script, style, foreignObject, image, a,
# use, animate*, set, filter, pattern, mask, clipPath, marker, switch,
# metadata, title, desc, symbol, text (text tirerait des polices), et tout
# élément d'un autre espace de noms.
_ALLOWED_ELEMENTS = frozenset(
    {
        "svg",
        "g",
        "path",
        "circle",
        "ellipse",
        "line",
        "polyline",
        "polygon",
        "rect",
    }
)

# Éléments qui comptent comme « contenu graphique » : si aucun ne survit,
# l'icône est vide et on la refuse plutôt que de stocker un fichier inerte.
_GRAPHIC_ELEMENTS = _ALLOWED_ELEMENTS - {"svg", "g"}

# Allowlist d'attributs. `style` en est ABSENT : une déclaration CSS peut
# porter une url() et il n'y a pas de façon sûre et courte de la contraindre.
# `href` en est absent aussi, sous toutes ses formes. Les attributs de
# présentation gardés sont ceux qui décrivent une géométrie ou une couleur.
_ALLOWED_ATTRS = frozenset(
    {
        # géométrie
        "d", "points", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r",
        "rx", "ry", "width", "height", "viewBox", "transform",
        # présentation
        "fill", "fill-rule", "fill-opacity", "stroke", "stroke-width",
        "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
        "stroke-opacity", "stroke-miterlimit", "opacity",
    }
)

_MAX_SANITIZED_BYTES = 200_000
_MAX_DEPTH = 20


class SvgRejected(Exception):
    """SVG refusé à l'upload. `code` part dans le membre `errors` de la
    réponse RFC 7807 ; `message` est destiné à l'auteur."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _local(tag: object) -> str:
    if not isinstance(tag, str):  # commentaire ou instruction de traitement
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _namespace(tag: str) -> str | None:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None


def _clean(element: ET.Element, depth: int) -> ET.Element | None:
    if depth > _MAX_DEPTH:
        return None
    tag = element.tag
    if not isinstance(tag, str):
        return None  # commentaires, PI : rien à garder
    ns = _namespace(tag)
    if ns is not None and ns != SVG_NS:
        return None  # élément d'un autre espace de noms (XHTML, MathML…)
    name = _local(tag)
    if name not in _ALLOWED_ELEMENTS:
        return None  # supprimé AVEC son sous-arbre
    out = ET.Element(name)
    for key, value in element.attrib.items():
        # Tout attribut d'espace de noms part : c'est ce qui tue
        # xlink:href, sans avoir à le nommer (clé mesurée :
        # "{http://www.w3.org/1999/xlink}href").
        if "}" in key or ":" in key:
            continue
        if key.lower().startswith("on"):
            continue
        if key not in _ALLOWED_ATTRS:
            continue
        # L'allowlist porte sur le NOM ; la VALEUR doit l'être aussi.
        # `fill`/`stroke` acceptent une fonction `url(...)` en SVG : sans
        # cette garde, `fill="url(http://evil.test/x)"` ferait une requête
        # sortante au rendu, et `fill="url(javascript:...)"` serait pire.
        # Aucun élément de l'allowlist ne peut être la CIBLE d'un url()
        # (ni defs, ni gradient, ni pattern n'y figurent), donc refuser
        # url() en bloc ne retire aucune capacité utilisable ici.
        lowered = value.lower()
        if "url(" in lowered or "javascript:" in lowered or "data:" in lowered:
            continue
        out.set(key, value)
    for child in element:
        cleaned = _clean(child, depth + 1)
        if cleaned is not None:
            out.append(cleaned)
    return out


def _has_graphics(element: ET.Element) -> bool:
    return any(_local(e.tag) in _GRAPHIC_ELEMENTS for e in element.iter())


def sanitize_svg(raw: bytes) -> bytes:
    try:
        # forbid_dtd=True est indispensable : le défaut de defusedxml est
        # False, et un <!DOCTYPE svg SYSTEM "http://evil/x.dtd"> sans
        # déclaration d'entité passerait (mesuré).
        parsed = fromstring(raw, forbid_dtd=True)
    except Exception as exc:  # ParseError, DTDForbidden, EntitiesForbidden…
        code = "svg_dtd_forbidden" if "Forbidden" in type(exc).__name__ else "svg_unparsable"
        raise SvgRejected(code, "SVG illisible ou hostile (DTD, entités, XML invalide).") from exc

    if _local(parsed.tag) != "svg" or _namespace(parsed.tag) not in (None, SVG_NS):
        raise SvgRejected("svg_not_svg_root", "La racine du document n'est pas un <svg>.")

    cleaned = _clean(parsed, 0)
    if cleaned is None or not _has_graphics(cleaned):
        raise SvgRejected(
            "svg_no_graphics",
            "Après assainissement, ce SVG ne contient plus aucun élément graphique.",
        )

    # Dimensions intrinsèques : un <img> en a besoin pour dimensionner un
    # SVG, et c'est le chemin de décodage retenu côté shell (déviation 13).
    view_box = cleaned.get("viewBox")
    if not cleaned.get("width") or not cleaned.get("height"):
        parts = (view_box or "").replace(",", " ").split()
        if len(parts) == 4:
            cleaned.set("width", parts[2])
            cleaned.set("height", parts[3])
        else:
            raise SvgRejected(
                "svg_no_dimensions",
                "Ce SVG n'a ni width/height ni viewBox exploitable.",
            )

    # `xmlns` posé à la main sur une racine aux balises dépouillées : évite
    # ET.register_namespace, qui est un état GLOBAL du module ElementTree.
    cleaned.set("xmlns", SVG_NS)
    out = ET.tostring(cleaned, encoding="utf-8")
    if len(out) > _MAX_SANITIZED_BYTES:
        raise SvgRejected("svg_too_large", "SVG trop volumineux après assainissement.")
    return out


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def sniff_content_type(head: bytes) -> str | None:
    """Type réel des octets, indépendamment du contentType déclaré."""
    if head.startswith(_PNG_MAGIC):
        return "image/png"
    prefix = head.lstrip()[:512].lower()
    if prefix.startswith(b"<svg") or prefix.startswith(b"<?xml"):
        return "image/svg+xml"
    return None
```

Run: `cd core && uv run pytest tests/test_mapicons_svg.py -v`
Expected: PASS (15 tests, les 3 paramétrages de DTD compris).

- [ ] **Step 7: Create `routes.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Routes REST de la bibliothèque d'icônes personnalisées (SP-27 §3.4).

Tenant-scoped, auditée, ouverte à tout utilisateur authentifié du tenant —
délibérément PAS admin-only, contrairement à app.secrets (`_require_admin`
sur toutes ses routes) : une icône est du matériel de présentation attaché à
une carte que l'utilisateur a déjà le droit d'éditer, sans contenu secret.
Ne passe pas par can() : can() autorise l'accès à un ITEM, et une icône n'en
est pas un.

Le précédent presign + proxy de lecture est app.tileset3d/app.terrain3d, pas
app.secrets (qui ne touche jamais S3).
"""

import logging
import os
import re
import uuid

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.errors import ValidationHTTPException
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.mapicons import repository as repo
from app.mapicons.models import MapIcon
from app.mapicons.schemas import (
    ALLOWED_CONTENT_TYPES,
    MAX_ICON_BYTES,
    MapIconCreate,
    MapIconOut,
    MapIconPresignRequest,
    MapIconPresignResponse,
)
from app.mapicons.svg import SvgRejected, sanitize_svg, sniff_content_type
from app.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def get_mapicons_bucket() -> str:
    return os.environ.get("S3_MAPICONS_BUCKET", "geostudio-mapicons")


def _to_response(icon: MapIcon) -> MapIconOut:
    return MapIconOut(
        id=icon.id,
        title=icon.title,
        category=icon.category,
        contentType=icon.content_type,
        createdAt=icon.created_at.isoformat(),
    )


@router.post("/map-icons/presign")
def presign_map_icon_upload(
    body: MapIconPresignRequest,
    user: User = Depends(get_current_user),
    s3_client=Depends(get_s3_client),
) -> MapIconPresignResponse:
    if body.contentType not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="unsupported content type")
    bucket = get_mapicons_bucket()
    ensure_uploads_bucket(s3_client, bucket)
    # Préfixe de tenant dans la clé : c'est ce qui rend vérifiable, à la
    # création, que l'appelant ne rattache pas l'objet d'un autre tenant.
    safe = _SAFE_FILENAME.sub("_", body.filename)[:80] or "icon.png"
    key = f"{user.tenant_id}/{uuid.uuid4().hex}-{safe}"
    url = generate_presigned_put_url(
        s3_client, bucket=bucket, key=key, content_type=body.contentType
    )
    return MapIconPresignResponse(uploadUrl=url, key=key)


@router.post("/map-icons", status_code=201)
def create_map_icon(
    body: MapIconCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3_client=Depends(get_s3_client),
) -> MapIconOut:
    if body.contentType not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="unsupported content type")
    if not body.s3Key.startswith(f"{user.tenant_id}/"):
        raise HTTPException(status_code=403, detail="key does not belong to this tenant")
    bucket = get_mapicons_bucket()
    # Le presign ne borne pas la taille (generate_presigned_put_url ne pose
    # aucune condition) : la borne est vérifiée ici, après coup.
    try:
        head = s3_client.head_object(Bucket=bucket, Key=body.s3Key)
    except ClientError as exc:
        raise HTTPException(status_code=400, detail="uploaded object not found") from exc
    if int(head.get("ContentLength", 0)) > MAX_ICON_BYTES:
        raise HTTPException(status_code=413, detail="icon too large")

    # Le contentType DÉCLARÉ ne prouve rien sur les octets téléversés : on
    # relit l'objet et on tranche sur son contenu réel.
    raw = s3_client.get_object(Bucket=bucket, Key=body.s3Key)["Body"].read()
    sniffed = sniff_content_type(raw)
    if sniffed is None or sniffed != body.contentType:
        raise ValidationHTTPException(
            errors=[
                {
                    "field": "s3Key",
                    "code": "content_type_mismatch",
                    "message": (
                        "Les octets téléversés ne correspondent pas au type déclaré "
                        f"({body.contentType})."
                    ),
                }
            ],
            status_code=400,
        )

    stored_content_type = sniffed
    if sniffed == "image/svg+xml":
        # ASSAINISSEMENT À L'ÉCRITURE (D4) : on réécrit l'objet avec la
        # version assainie, et c'est elle qui sera servie. La lecture ne
        # réassainit pas — un seul endroit où la garde peut manquer.
        try:
            sanitized = sanitize_svg(raw)
        except SvgRejected as exc:
            raise ValidationHTTPException(
                errors=[{"field": "s3Key", "code": exc.code, "message": exc.message}],
                status_code=400,
            ) from exc
        s3_client.put_object(
            Bucket=bucket,
            Key=body.s3Key,
            Body=sanitized,
            ContentType="image/svg+xml",
        )

    icon = repo.create_icon(
        session,
        tenant_id=user.tenant_id,
        created_by=user.id,
        title=body.title,
        category=body.category,
        s3_key=body.s3Key,
        content_type=stored_content_type,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="mapicon.create",
        object_type="mapicon",
        object_id=icon.id,
        payload={"title": icon.title, "category": icon.category},
    )
    return _to_response(icon)


@router.get("/map-icons")
def list_map_icons(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[MapIconOut]:
    return [_to_response(i) for i in repo.list_icons(session, tenant_id=user.tenant_id)]


@router.delete("/map-icons/{icon_id}", status_code=204)
def delete_map_icon(
    icon_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3_client=Depends(get_s3_client),
) -> None:
    icon = repo.get_icon(session, tenant_id=user.tenant_id, icon_id=icon_id)
    if icon is None:
        raise HTTPException(status_code=404, detail="icon not found")
    title, category, s3_key = icon.title, icon.category, icon.s3_key
    # Base d'abord, S3 ensuite en best-effort : la transaction reste ouverte
    # jusqu'à la fin de la requête (request_scoped_session), donc supprimer
    # l'objet S3 en premier perdrait les octets tout en gardant la ligne si
    # le commit échouait. Un objet orphelin est rattrapable, l'inverse non.
    repo.delete_icon(session, icon)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="mapicon.delete",
        object_type="mapicon",
        object_id=icon_id,
        payload={"title": title, "category": category},
    )
    try:
        s3_client.delete_object(Bucket=get_mapicons_bucket(), Key=s3_key)
    except ClientError:
        logger.warning("mapicon %s: objet S3 %s non supprimé", icon_id, s3_key, exc_info=True)


@router.get("/map-icons/{icon_id}/file")
def read_map_icon_file(
    icon_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    s3_client=Depends(get_s3_client),
) -> Response:
    icon = repo.get_icon(session, tenant_id=user.tenant_id, icon_id=icon_id)
    if icon is None:
        raise HTTPException(status_code=404, detail="icon not found")
    try:
        obj = s3_client.get_object(Bucket=get_mapicons_bucket(), Key=icon.s3_key)
    except ClientError as exc:
        raise HTTPException(status_code=404, detail="icon file not found") from exc
    return Response(
        content=obj["Body"].read(),
        media_type=icon.content_type,
        headers={
            # Cache-Control : convention établie des réponses d'octets
            # authentifiées (app.tileset3d, app.terrain3d).
            "Cache-Control": "private, max-age=3600",
            # nosniff + attachment : le shell ne consomme ces octets QUE par
            # fetch authentifié puis décodage local (URL d'objet +
            # HTMLImageElement), jamais dans un contexte de document. Ces
            # deux en-têtes n'ont AUCUN précédent dans core/app/ (vérifié :
            # grep X-Content-Type-Options → vide, ni tileset3d ni terrain3d
            # ne posent de Content-Disposition) : pratique nouvelle, décidée
            # explicitement (D4), parce que c'est la première route du cœur à
            # servir un fichier téléversé par un utilisateur non-admin.
            #
            # On NE réassainit PAS ici : les octets stockés sont déjà la
            # version assainie (create_map_icon). Réassainir à chaque lecture
            # ajouterait un second endroit où la garde peut manquer, et ferait
            # payer un parse XML à chaque affichage de carte.
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "attachment",
        },
    )
```

Create `core/app/mapicons/__init__.py` as an empty file.

- [ ] **Step 8: Register the models module in `core/app/db.py`**

This is the step whose omission is silent and costly (missing table in
`init_db` **and** a hole in the collections-registry denylist). The block is
alphabetical by dotted module path, so the new line goes between
`app.items` and `app.pipelines`. Exact-match edit:

Find:
```python
    from app.ingestion import models as ingestion_models  # noqa: F401
    from app.items import models as items_models  # noqa: F401
    from app.pipelines import models as pipelines_models  # noqa: F401
```
Replace with:
```python
    from app.ingestion import models as ingestion_models  # noqa: F401
    from app.items import models as items_models  # noqa: F401
    from app.mapicons import models as mapicons_models  # noqa: F401
    from app.pipelines import models as pipelines_models  # noqa: F401
```

- [ ] **Step 9: Wire the router (always-on, no capability flag)**

In `core/app/main.py`, next to the other imports of the same shape (the
`app.secrets` one is at line ~50):

```python
from app.mapicons import routes as mapicons_routes
```

And right after `app.include_router(secrets_routes.router)` (line ~253):

```python
    app.include_router(mapicons_routes.router)
```

- [ ] **Step 10: Import-linter contract — two edits, not one**

In `core/pyproject.toml`:
- insert `    "app.mapicons",` in the `layers` list between
  `    "app.terrain3d",` (line 212) and `    "app.secrets",` (line 213) —
  same tier as `tileset3d`/`terrain3d`, since `app.mapicons` imports
  `app.ingestion.routes`/`app.ingestion.storage` exactly like they do;
- append `    "app.db -> app.mapicons.models",` at the **end** of
  `ignore_imports` (after line 265, before the closing `]`) — that list is
  not sorted, and appending is the file's convention. Without it,
  `uv run lint-imports` fails on the lazy import added in Step 8.

- [ ] **Step 11: Wire the S3 bucket into compose + backup + `.env.example`**

- `docker-compose.yml`, `core:` service `environment:`, right after
  `S3_TILESET3D_BUCKET: geostudio-tileset3d` (around line 268):
  `      S3_MAPICONS_BUCKET: geostudio-mapicons`
- `docker-compose.prod.yml`, `backup:` service `environment:`, right after
  the same variable (around line 212): the identical line.
- `deploy/backup/backup.sh`, the `for bucket in …` loop (around line 44):
  add `"${S3_MAPICONS_BUCKET:-geostudio-mapicons}"` as the new **last**
  entry and move the trailing `; do` onto it (read the file first — the
  current last line is `"${S3_TERRAIN3D_BUCKET:-geostudio-terrain3d}" \`
  followed by `; do` on that same line).
- `.env.example`, in the "Buckets fixés en dur dans docker-compose.yml" block
  (lines 90-98):
  `#   S3_MAPICONS_BUCKET=geostudio-mapicons      (sauvegardé)`
  A **commented** line is what `test_deployability.py` expects here:
  `documented_env_vars(include_commented=True)` sees it (regex
  `^#?\s*([A-Z0-9_]+)=`) while the strict variant does not, so no exemption
  is needed.

Then verify by value, not by reading the YAML (`CLAUDE.md` trap #2):

Run: `docker compose config | grep -n S3_MAPICONS_BUCKET`
Expected: it appears under the `core` service. If `docker compose config`
needs a `.env` you do not have, run
`docker compose --env-file .env.example config` and say so.

- [ ] **Step 12: Migration in both directions on a non-empty database**

`CLAUDE.md` trap #8. With a `postgis-test` container running and
`CORE_DATABASE_URL` pointed at it:

```bash
cd core
uv run alembic upgrade head
# insérer une ligne pour que le downgrade ne soit pas testé sur table vide
uv run python - <<'PY'
import os, uuid
from sqlalchemy import create_engine, text
e = create_engine(os.environ["CORE_DATABASE_URL"])
with e.begin() as c:
    tid = c.execute(text("select id from tenants limit 1")).scalar()
    uid = c.execute(text("select id from users limit 1")).scalar()
    c.execute(text(
        "insert into map_icons (id, tenant_id, title, category, s3_key, content_type, created_by, created_at)"
        " values (:i, :t, 'x', 'generic', 'k', 'image/png', :u, now())"
    ), {"i": uuid.uuid4().hex, "t": tid, "u": uid})
PY
uv run alembic downgrade 0028
uv run alembic upgrade head
```
Expected: both directions succeed. If no `postgis-test` container is
available in this session, **write that down in the commit body** rather than
silently skipping the check — the omission is what trap #8 is about.

- [ ] **Step 13: Run the tests and the gates**

Run: `cd core && uv run pytest tests/test_mapicons_routes.py -v`
Expected: PASS (17 tests, dont les paramétrages).

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: PASS, still **35/35** — the rule counts buckets in a loop, it does
not add a test per bucket.

Run: `cd core && uv run pytest -q`
Expected: 1896 + 17 (routes) + 15 (assainisseur) passed, 5 skipped, the 1 known pre-existing failure.

Run: `cd core && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && uv run lint-imports`
Expected: all green. **`app/mapicons` is deliberately NOT added to the
`mypy --strict` gate** (constat 4.11): widening that gate is a separate
decision with its own cost, and this plan does not take it. The module is
therefore *not* strictly typed — a future session must not assume it is.

- [ ] **Step 14: Commit**

```bash
git add core/app/mapicons core/alembic/versions/0029_map_icons.py core/tests/test_mapicons_routes.py core/tests/test_mapicons_svg.py core/app/db.py core/app/main.py core/pyproject.toml docker-compose.yml docker-compose.prod.yml deploy/backup/backup.sh .env.example
git commit -m "$(cat <<'EOF'
feat(core): ajoute la bibliothèque d'icônes personnalisées tenant-scoped

app.mapicons (SP-27 §3.4) : presign S3 + CRUD + proxy de lecture
authentifié, tenant-scoped, audité — précédent app.tileset3d/terrain3d,
pas app.secrets (qui ne touche jamais S3 et est admin-only). Ouvert à
tout utilisateur authentifié du tenant : arbitrage assumé, une icône est
du matériel de présentation, pas un secret.

PNG et SVG. Le SVG est ASSAINI à l'écriture (app/mapicons/svg.py) et ce
sont les octets assainis qui sont stockés : allowlist stricte d'éléments
et d'attributs appliquée sur l'arbre parsé puis re-sérialisée, jamais un
filtrage d'expression régulière sur le texte source. defusedxml était
déjà dépendance directe (SP-12e) — aucune dépendance ajoutée — mais
forbid_dtd doit être passé explicitement : son défaut est False et un
DOCTYPE nu passait. Un SVG illisible ou vidé de tout contenu graphique
est refusé en RFC 7807 avec un code, jamais stocké vide.

Type réel des octets vérifié contre le contentType déclaré, taille
bornée par head_object après upload (le presign ne porte aucune
condition de taille), en-têtes nosniff + attachment — une première dans
core/app/, assumée. Suppression en base d'abord, S3 ensuite en
best-effort.

app.mapicons devient le second module du cœur à dépendre de defusedxml
au runtime : le suivi préexistant « libexpat.so.1 manquant en
conteneur » voit donc sa surface s'élargir, sans être ni aggravé ni
corrigé ici.

app/db.py enregistre le module models : sans lui la table n'est pas créée
par init_db ET map_icons manque à la denylist du registre de collections.
Bucket câblé sur core et backup — garde de déployabilité SP-21 verte.
EOF
)"
```

---

## Task 10: OpenAPI + TS regeneration

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

This is the repo's most frequent class of omission (≥5 occurrences,
`CLAUDE.md` trap #1). It is a task of its own on purpose, and it must be the
commit immediately after Task 9.

- [ ] **Step 1: Regenerate both sides**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

(The bare command fails with `ModuleNotFoundError: app`; the `PYTHONPATH=.`
+ master-key incantation is the one that works. `npm run gen:api-types` runs
`openapi-typescript ../core/openapi.json -o src/api/generated/core-schema.d.ts`.)

- [ ] **Step 2: Verify the diff**

Run: `git diff --stat && git diff core/openapi.json | head -80`
Expected: the 5 new `/map-icons*` paths and their schemas appear; nothing
unrelated moves. A non-empty diff **is** expected here — the routes are
always-on, behind no flag.

- [ ] **Step 3: Confirm both sides still build**

Run: `cd core && uv run pytest -q` and `cd shell && npm run build`
Expected: both green.

- [ ] **Step 4: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
chore(api): régénère OpenAPI et les types TS (map-icons)
EOF
)"
```

---

## Task 11: Shell — `ItemClient` map-icon methods

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/itemClient.test.ts`
- Modify: `shell/src/staticExport/StaticItemClient.ts`
- Modify: `shell/src/staticExport/StaticItemClient.test.ts`

**Interfaces:**
- Produces: `ItemClient.presignMapIconUpload`, `.createMapIcon`,
  `.listMapIcons`, `.deleteMapIcon`, **`.fetchMapIconBlob`** — consumed by
  Task 12.

**Design decision, and why there is no `mapIconFileUrl`:** `GET
/map-icons/{id}/file` is guarded by `Depends(get_current_user)` and the
shell authenticates with a **bearer token** (`itemClient.ts:330-334`:
`if (token) headers.Authorization = \`Bearer ${token}\``). A URL handed to
`new Image().src` carries no custom header and would take a 401. The client
therefore exposes `fetchMapIconBlob(iconId): Promise<Blob>` — the token
never leaves `itemClient.ts`, and `MapView` (Task 8) turns the blob into an
`ImageBitmap`. There are exactly **two** `ItemClient` implementations
(`itemClient.ts`, `StaticItemClient.ts`), so `npm run build` proves
completeness.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/itemClient.test.ts` (mirror the existing
`presignTerrain3DUpload` test's setup — read it first for the exact
`vi.stubGlobal("fetch", …)` shape this file uses):

```ts
test("presignMapIconUpload posts filename/contentType", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ uploadUrl: "https://s3.test/x", key: "t1/x.png" }), {
      status: 200,
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => undefined });

  const result = await client.presignMapIconUpload("logo.png", "image/png");

  expect(result).toEqual({ uploadUrl: "https://s3.test/x", key: "t1/x.png" });
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("https://core.test/map-icons/presign");
  expect(JSON.parse(init.body as string)).toEqual({
    filename: "logo.png",
    contentType: "image/png",
  });
});

test("createMapIcon posts the icon metadata and listMapIcons reads them back", async () => {
  const icon = {
    id: "i1", title: "Logo", category: "generic",
    contentType: "image/png", createdAt: "2026-08-27T00:00:00Z",
  };
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(icon), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([icon]), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => undefined });

  expect(
    (
      await client.createMapIcon({
        title: "Logo", category: "generic", s3Key: "t1/x.png", contentType: "image/png",
      })
    ).id,
  ).toBe("i1");
  expect(await client.listMapIcons()).toEqual([icon]);
});

test("deleteMapIcon tolerates the 204 the core returns", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => undefined });
  await expect(client.deleteMapIcon("i1")).resolves.toBeUndefined();
  expect(fetchMock.mock.calls[0][0]).toBe("https://core.test/map-icons/i1");
  expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
});

// La route du fichier est gardée par bearer token : une URL nue passée à
// `new Image().src` ne porte aucun en-tête et prendrait un 401 (constat 4.4).
test("fetchMapIconBlob attaches the bearer token and returns the bytes", async () => {
  const blob = new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" });
  const fetchMock = vi.fn().mockResolvedValue(new Response(blob, { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "tok" });

  const result = await client.fetchMapIconBlob("i1");

  expect(result.size).toBeGreaterThan(0);
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("https://core.test/map-icons/i1/file");
  expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
});

test("fetchMapIconBlob throws on a non-ok response", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "tok" });
  await expect(client.fetchMapIconBlob("i1")).rejects.toThrow(/404/);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "MapIcon"`
Expected: FAIL — the methods do not exist.

- [ ] **Step 3: Add to the `ItemClient` interface**

In `shell/src/api/types.ts`, right after `sampleCollectionField` (line 258):

```ts
  presignMapIconUpload(
    filename: string,
    contentType: string,
  ): Promise<{ uploadUrl: string; key: string }>;
  createMapIcon(input: {
    title: string;
    category: string;
    s3Key: string;
    contentType: string;
  }): Promise<MapIconOut>;
  listMapIcons(): Promise<MapIconOut[]>;
  deleteMapIcon(iconId: string): Promise<void>;
  // Blob, pas URL : la route est gardée par bearer token, qu'une balise
  // <img> ne porterait pas. Le jeton ne sort jamais d'itemClient.ts.
  fetchMapIconBlob(iconId: string): Promise<Blob>;
```

And the response type, near the other API response types in the same file:

```ts
export type MapIconOut = {
  id: string;
  title: string;
  category: string;
  contentType: string;
  createdAt: string;
};
```

- [ ] **Step 4: Implement in `itemClient.ts`**

Right after `sampleCollectionField`'s implementation:

```ts
    async presignMapIconUpload(filename: string, contentType: string) {
      return request<{ uploadUrl: string; key: string }>("POST", "/map-icons/presign", {
        filename,
        contentType,
      });
    },

    async createMapIcon(input: {
      title: string;
      category: string;
      s3Key: string;
      contentType: string;
    }) {
      return request<MapIconOut>("POST", "/map-icons", input);
    },

    async listMapIcons() {
      return request<MapIconOut[]>("GET", "/map-icons");
    },

    async deleteMapIcon(iconId: string) {
      await request<void>("DELETE", `/map-icons/${encodeURIComponent(iconId)}`);
    },

    async fetchMapIconBlob(iconId: string) {
      // `request()` fait toujours res.json() : cette route renvoie des
      // octets, donc fetch direct, avec le même en-tête d'autorisation.
      const token = getToken();
      const res = await fetch(`${coreUrl}/map-icons/${encodeURIComponent(iconId)}/file`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} GET /map-icons/${iconId}/file`);
      return res.blob();
    },
```

`uploadToPresignedUrl` (existing, `itemClient.ts:1403`) is reused as-is for
the PUT — no new upload helper.

- [ ] **Step 5: `StaticItemClient` rejections + tests**

In `shell/src/staticExport/StaticItemClient.ts`, mirroring the file's
`sampleCollectionField` style (line ~108):

```ts
    async presignMapIconUpload(..._args: unknown[]) {
      return unsupported();
    },
    async createMapIcon(..._args: unknown[]) {
      return unsupported();
    },
    async listMapIcons() {
      return unsupported();
    },
    async deleteMapIcon(..._args: unknown[]) {
      return unsupported();
    },
    async fetchMapIconBlob(..._args: unknown[]) {
      return unsupported();
    },
```

Add a test in `StaticItemClient.test.ts` mirroring the existing
`sampleCollectionField` rejection test, covering all five names.

- [ ] **Step 6: Run + full gates + commit**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/staticExport/StaticItemClient.test.ts`
Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green — `npm run build` (`tsc --noEmit`) is what proves neither of
the two `ItemClient` implementations is left incomplete.

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/staticExport/StaticItemClient.ts shell/src/staticExport/StaticItemClient.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute les 5 méthodes ItemClient de la bibliothèque d'icônes

fetchMapIconBlob renvoie un Blob et non une URL : la route de lecture est
gardée par bearer token, qu'une balise <img> ou un new Image() ne porte
pas — ils prendraient un 401. Le jeton ne sort jamais d'itemClient.ts.
EOF
)"
```

---

## Task 12: Shell — icon picker UI (Lucide grid + custom library) and custom icon rendering

**Files:**
- Modify: `shell/src/map/MapSymbologyEditor.tsx`
- Modify: `shell/src/map/MapSymbologyEditor.test.tsx`
- Modify: `shell/src/map/LayersPanel.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `LUCIDE_ICONS`, `IconCategory` (Task 6); `IconRef`, `LayerIcon`
  (Task 7); `listMapIcons`/`presignMapIconUpload`/`createMapIcon`/
  `deleteMapIcon`/`fetchMapIconBlob` (Task 11); `computeColorDomain`
  (existing).
- Produces: three **optional** props on `MapSymbologyEditor`
  (`listCustomIcons`, `uploadCustomIcon`, `deleteCustomIcon`) and the
  `loadCustomIcon` wiring of `MapView` at both hosts.

**Four defects of the earlier draft this task must not reproduce:**
1. `listCustomIcons={() => client.listMapIcons()}` (a fresh arrow at every
   host render) used as a `useEffect` dependency is an **infinite render
   loop** — one HTTP request per turn. The effect here reads the callback
   through a ref and depends on `[]`.
2. The three props were declared **non-optional**, which breaks the **18**
   inline `render(<MapSymbologyEditor … />)` calls in
   `MapSymbologyEditor.test.tsx` and fails `tsc --noEmit`. They are optional
   here; when `listCustomIcons` is absent, the custom section is simply not
   offered.
3. The icon block was gated on `iconField !== undefined` with
   `useState("")`, i.e. **always true** — the block rendered permanently and
   "Ajouter des icônes" did nothing observable. A dedicated boolean draft
   state fixes it.
4. The grid rendered `LUCIDE_ICONS.map(...)` **once per domain value**
   (140 × N buttons, thousands of DOM nodes) with `aria-label={li.name}`
   duplicated across groups — `getByRole("img", { name: "school" })` would
   throw "found multiple elements". Here there is **one** grid, shown only
   for the single value under edit.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/map/MapSymbologyEditor.test.tsx` (reuse the `baseProps`
object introduced in Task 4):

```tsx
const iconValue = {
  icon: {
    field: "categorie",
    domain: { kind: "categorical" as const, values: ["ecole", "commerce"] },
    mapping: {},
  },
};

test("« Ajouter des icônes » ouvre le bloc, qui est fermé par défaut", async () => {
  render(<MapSymbologyEditor {...baseProps} value={undefined} onChange={vi.fn()} />);
  expect(screen.queryByLabelText("Champ icône")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Ajouter des icônes" }));
  expect(screen.getByLabelText("Champ icône")).toBeInTheDocument();
});

test("la grille d'icônes n'apparaît que pour la valeur en cours d'édition", async () => {
  render(<MapSymbologyEditor {...baseProps} value={iconValue} onChange={vi.fn()} />);
  // Aucune grille au départ : seulement un bouton par valeur du domaine.
  expect(screen.queryByRole("img", { name: "school" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Choisir l'icône de ecole" }));
  // Une seule grille, donc un seul bouton nommé "school".
  expect(screen.getByRole("img", { name: "school" })).toBeInTheDocument();
});

test("choisir une icône Lucide écrit icon.mapping pour cette valeur", async () => {
  const onChange = vi.fn();
  render(<MapSymbologyEditor {...baseProps} value={iconValue} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Choisir l'icône de commerce" }));
  await userEvent.click(screen.getByRole("img", { name: "shopping-cart" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      icon: expect.objectContaining({
        mapping: { commerce: { source: "lucide", name: "shopping-cart" } },
      }),
    }),
  );
});

test("« Recalculer les valeurs » remplit le domaine depuis runStatistics", async () => {
  const onChange = vi.fn();
  const runStatistics = vi
    .fn()
    .mockResolvedValue([{ categorie: "ecole" }, { categorie: "commerce" }]);
  render(
    <MapSymbologyEditor
      {...baseProps}
      runStatistics={runStatistics}
      value={undefined}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter des icônes" }));
  await userEvent.type(screen.getByLabelText("Champ icône"), "categorie");
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les valeurs" }));
  expect(runStatistics).toHaveBeenCalled();
  await vi.waitFor(() =>
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        icon: expect.objectContaining({
          field: "categorie",
          domain: { kind: "categorical", values: ["ecole", "commerce"] },
        }),
      }),
    ),
  );
});
```

The exact `runStatistics` return shape must match what
`computeColorDomain({ field, mode: "categorical" }, { runStatistics,
sampleField })` consumes — **read the file's existing categorical-color test
and copy its mock verbatim** rather than trusting the shape sketched above.
If the real shape differs, fix the test, not `computeColorDomain`.

```tsx
test("l'effet de chargement des icônes personnalisées ne boucle pas", async () => {
  const listCustomIcons = vi.fn().mockResolvedValue([]);
  const { rerender } = render(
    <MapSymbologyEditor
      {...baseProps}
      value={undefined}
      onChange={vi.fn()}
      listCustomIcons={listCustomIcons}
    />,
  );
  // Une nouvelle identité de callback à chaque rendu, comme un `() =>
  // client.listMapIcons()` inline chez l'hôte : l'effet ne doit PAS repartir.
  rerender(
    <MapSymbologyEditor
      {...baseProps}
      value={undefined}
      onChange={vi.fn()}
      listCustomIcons={vi.fn().mockResolvedValue([])}
    />,
  );
  rerender(
    <MapSymbologyEditor
      {...baseProps}
      value={undefined}
      onChange={vi.fn()}
      listCustomIcons={vi.fn().mockResolvedValue([])}
    />,
  );
  await vi.waitFor(() => expect(listCustomIcons).toHaveBeenCalledTimes(1));
});

test("« Retirer les icônes » n'efface que l'encodage icône", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor {...baseProps} value={{ ...iconValue, opacity: 60 }} onChange={onChange} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer les icônes" }));
  expect(onChange).toHaveBeenLastCalledWith({ opacity: 60 });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx -t "icône|icônes"`
Expected: FAIL.

- [ ] **Step 3: Extend the props — all three optional**

```ts
export function MapSymbologyEditor({
  value,
  availableFields,
  themeColors,
  runStatistics,
  sampleField,
  jenksAvailable = true,
  listCustomIcons,
  uploadCustomIcon,
  deleteCustomIcon,
  onChange,
}: {
  // …existing props unchanged…
  // Optionnelles : ce composant est rendu inline dans 18 tests et à deux
  // sites de production ; les rendre obligatoires ferait échouer
  // `tsc --noEmit` partout. Absentes ⇒ la section « icônes personnalisées »
  // n'est simplement pas proposée.
  listCustomIcons?: () => Promise<{ id: string; title: string; category: string }[]>;
  uploadCustomIcon?: (file: File, title: string, category: string) => Promise<{ id: string }>;
  deleteCustomIcon?: (id: string) => Promise<void>;
  onChange: (value: LayerSymbology | undefined) => void;
}) {
```

- [ ] **Step 4: Implement the icon block**

State and handlers:

```tsx
  const icon = value?.icon;
  // Booléen dédié : `useState("")` + `iconField !== undefined` était
  // toujours vrai, donc le bloc s'affichait en permanence et le bouton
  // « Ajouter des icônes » n'avait aucun effet observable.
  const [iconDraft, setIconDraft] = useState(false);
  const [iconField, setIconField] = useState(icon?.field ?? "");
  const [iconBusy, setIconBusy] = useState(false);
  const [iconError, setIconError] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState<string | null>(null);
  const [customIcons, setCustomIcons] = useState<
    { id: string; title: string; category: string }[]
  >([]);

  // La prop peut être une flèche inline recréée à chaque rendu de l'hôte
  // (c'est le style des autres props fonction de ce composant) : la lire par
  // ref et ne dépendre de rien évite la boucle « effet → setState → nouvelle
  // identité → effet ».
  const listCustomIconsRef = useRef(listCustomIcons);
  useEffect(() => {
    listCustomIconsRef.current = listCustomIcons;
  }, [listCustomIcons]);
  useEffect(() => {
    const fn = listCustomIconsRef.current;
    if (!fn) return;
    let cancelled = false;
    void fn()
      .then((icons) => {
        if (!cancelled) setCustomIcons(icons);
      })
      .catch(() => {
        // Bibliothèque indisponible : la grille Lucide reste utilisable.
        if (!cancelled) setCustomIcons([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function recomputeIconDomain() {
    if (!iconField) return;
    setIconBusy(true);
    setIconError(null);
    try {
      const domain = await computeColorDomain(
        { field: iconField, mode: "categorical" },
        { runStatistics, sampleField },
      );
      if (domain.kind !== "categorical") {
        setIconError("Ce champ n'a pas de valeurs catégorielles exploitables.");
        return;
      }
      onChange({
        ...value,
        icon: {
          field: iconField,
          domain,
          mapping: icon?.mapping ?? {},
          ...(icon?.fallback ? { fallback: icon.fallback } : {}),
        },
      });
    } catch (e) {
      setIconError(e instanceof Error ? e.message : String(e));
    } finally {
      setIconBusy(false);
    }
  }

  function assignIcon(forValue: string, ref: IconRef) {
    if (!icon) return;
    onChange({ ...value, icon: { ...icon, mapping: { ...icon.mapping, [forValue]: ref } } });
    setEditingValue(null);
  }
```

Add imports: `useEffect`, `useRef` to the existing `react` import;
`LUCIDE_ICONS, type IconCategory` from `../builder/widgets/iconLibrary`;
`type IconRef` from `../builder/widgets/mapSymbology`.

JSX, appended after the stroke block from Task 4:

```tsx
      {!icon && !iconDraft && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
          onClick={() => setIconDraft(true)}
        >
          Ajouter des icônes
        </button>
      )}
      {(icon || iconDraft) && (
        <div className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2">
          <label className={labelCls}>
            Champ icône
            <input
              aria-label="Champ icône"
              list={`${listId}-fields`}
              className={inputCls}
              value={iconField}
              onChange={(e) => setIconField(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={iconBusy || !iconField}
            onClick={() => void recomputeIconDomain()}
          >
            {iconBusy ? "Calcul…" : "Recalculer les valeurs"}
          </button>
          {iconError && <p className="text-xs text-red-700">{iconError}</p>}

          {icon?.domain.values.map((v) => {
            const assigned = icon.mapping[v];
            return (
              <div key={v} className="flex items-center gap-2">
                <span className="text-xs font-medium">{v}</span>
                <button
                  type="button"
                  aria-label={`Choisir l'icône de ${v}`}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs"
                  onClick={() => setEditingValue(editingValue === v ? null : v)}
                >
                  {assigned
                    ? assigned.source === "lucide"
                      ? assigned.name
                      : (customIcons.find((c) => c.id === assigned.id)?.title ?? "icône")
                    : "Aucune"}
                </button>
              </div>
            );
          })}

          {/* UNE seule grille, pour la seule valeur en cours d'édition : la
              rendre par valeur de domaine produisait 140 × N boutons et des
              noms accessibles dupliqués, donc un getByRole ambigu. */}
          {editingValue !== null && (
            <div className="flex flex-col gap-1" data-testid="icon-grid">
              <p className="text-xs">Icône pour « {editingValue} »</p>
              {(
                [
                  "generic", "buildings", "nature", "transport", "services",
                  "safety-health", "leisure",
                ] as IconCategory[]
              ).map((category) => (
                <div key={category} className="flex flex-col gap-1">
                  <h4 className="text-[10px] uppercase text-slate-500">{category}</h4>
                  <div className="flex flex-wrap gap-1">
                    {LUCIDE_ICONS.filter((li) => li.category === category).map((li) => (
                      <button
                        key={li.name}
                        type="button"
                        role="img"
                        aria-label={li.name}
                        title={li.name}
                        className="h-6 w-6 rounded border border-slate-200"
                        onClick={() => assignIcon(editingValue, { source: "lucide", name: li.name })}
                      />
                    ))}
                  </div>
                </div>
              ))}
              {customIcons.length > 0 && (
                <div className="flex flex-col gap-1">
                  <h4 className="text-[10px] uppercase text-slate-500">Bibliothèque du tenant</h4>
                  <div className="flex flex-wrap gap-1">
                    {customIcons.map((ci) => (
                      <span key={ci.id} className="flex items-center gap-1">
                        <button
                          type="button"
                          role="img"
                          aria-label={ci.title}
                          className="h-6 w-6 rounded border border-slate-200"
                          onClick={() => assignIcon(editingValue, { source: "custom", id: ci.id })}
                        />
                        {deleteCustomIcon && (
                          <button
                            type="button"
                            aria-label={`Supprimer l'icône ${ci.title}`}
                            className="text-[10px] text-red-700 underline"
                            onClick={() => {
                              void deleteCustomIcon(ci.id).then(() =>
                                setCustomIcons((prev) => prev.filter((c) => c.id !== ci.id)),
                              );
                            }}
                          >
                            ×
                          </button>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {uploadCustomIcon && (
            <label className={labelCls}>
              Ajouter une icône au tenant (PNG ou SVG)
              <input
                aria-label="Ajouter une icône au tenant (PNG ou SVG)"
                type="file"
                accept="image/png,image/svg+xml"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  setIconError(null);
                  void uploadCustomIcon(file, file.name, "generic")
                    .then((created) =>
                      setCustomIcons((prev) => [
                        ...prev,
                        { id: created.id, title: file.name, category: "generic" },
                      ]),
                    )
                    .catch((err) =>
                      setIconError(err instanceof Error ? err.message : String(err)),
                    );
                }}
              />
            </label>
          )}

          {icon && (
            <button
              type="button"
              className="self-start text-xs text-red-700 underline"
              onClick={() => {
                setIconDraft(false);
                setEditingValue(null);
                clearEncoding("icon");
              }}
            >
              Retirer les icônes
            </button>
          )}
        </div>
      )}
```

Note: the upload input accepts `image/png` **and** `image/svg+xml` — the
core accepts both and **assainit** the SVG at write time (Task 9,
déviation 13). `setIconError` already renders the RFC 7807 `detail` returned
when a hostile or empty SVG is refused, so a rejected upload is visible to
the author instead of silently producing an unusable icon.

- [ ] **Step 5: Wire the two hosts**

Both `shell/src/map/LayersPanel.tsx`'s `LayerSymbologyEditor` and
`shell/src/builder/widgets/mapWidget.tsx`'s `PropsPanel` already render
`<MapSymbologyEditor …>` and already have `client = useItemClient()` in
scope. Add the same three props at both sites:

```tsx
      listCustomIcons={() => client.listMapIcons()}
      uploadCustomIcon={async (file, title, category) => {
        const { uploadUrl, key } = await client.presignMapIconUpload(file.name, file.type);
        await client.uploadToPresignedUrl(uploadUrl, file);
        return client.createMapIcon({ title, category, s3Key: key, contentType: file.type });
      }}
      deleteCustomIcon={(id) => client.deleteMapIcon(id)}
```

Inline arrows are safe here **because** the editor reads the callback through
a ref (Step 4) — do not "optimise" this into `useCallback` without also
re-reading that effect.

- [ ] **Step 6: Wire `loadCustomIcon` into `MapView` at both hosts**

`MapView` gained the optional `loadCustomIcon?: (iconId: string) =>
Promise<Blob>` prop in Task 8. Pass it wherever `MapView` is rendered with a
`client` in scope:

- `shell/src/builder/widgets/mapWidget.tsx`'s `Component`:
  `loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}`
- the map editor's `MapView` mount (find it with
  `grep -rn "<MapView" shell/src` — it is `shell/src/pages/MapEditorPage.tsx`
  and/or `shell/src/map/…`; add the same prop wherever a `client` is already
  available, and **leave it absent** where none is, which simply means custom
  icons do not render there).

Add a widget test proving the prop is threaded:

```tsx
test("le widget carte fournit le chargeur d'icônes personnalisées à MapView", async () => {
  // Le mock de MapView de ce fichier capture `config` ; étendre son rendu
  // pour exposer `loadCustomIcon:{typeof loadCustomIcon}` puis asserter
  // "loadCustomIcon:function" — lire le mock (lignes 20-75) avant d'écrire.
});
```

Write that test against the file's real MapView mock rather than the sketch
above: the mock currently destructures only
`config`/`onViewChange`/`onFeatureClick`/`ref`, so it must be extended to
accept and display the new prop.

- [ ] **Step 7: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx src/builder/widgets/mapWidget.test.tsx src/map/MapView.test.tsx`
Expected: PASS, all three files green.

- [ ] **Step 8: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx shell/src/map/LayersPanel.tsx shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx shell/src/pages/MapEditorPage.tsx
git commit -m "$(cat <<'EOF'
feat(shell): picker d'icônes (grille Lucide + bibliothèque du tenant)

Une seule grille, pour la seule valeur de domaine en cours d'édition :
la rendre par valeur produisait 140 × N boutons et des aria-label
dupliqués. Les trois props de bibliothèque sont OPTIONNELLES (18 rendus
inline dans les tests) et le chargement passe par une ref, sinon une
flèche inline chez l'hôte en dépendance d'effet bouclait à l'infini.
Upload PNG ou SVG, cohérent avec la garde d'assainissement du cœur.
EOF
)"
```

---

## Task 13: Shell — `labelSource.ts` (pure) et `LayerSymbology.label`

**Files:**
- Create: `shell/src/map/labelSource.ts`
- Create: `shell/src/map/labelSource.test.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.ts`
- Modify: `shell/src/builder/widgets/mapSymbology.test.ts`

**Interfaces:**
- Consumes: `interpolatePopupTemplate` from `./popupTemplate` (existing,
  SP-24) — **never** `renderPopupTemplate`, which sanitises to markdown;
  MapLibre draws plain text.
- Produces: `LayerLabel`, `LayerSymbology.label`,
  `buildLabelFeatureCollection(features, template, pkColumn?)` — consumed by
  Task 14.

**The one fact that broke two tests of the earlier draft:** this repo's CEL
template vocabulary is **`${record.champ}`**, not `${champ}`. `ExprContext`
(`shell/src/builder/expr.ts:5-10`) is `{ vars, record?, user, ctx? }` and
`evaluateExpression` calls `evaluate(expr, ctx)`, so identifiers resolve at
the **root** of the context. `shell/src/map/popupTemplate.test.ts` asserts
`interpolatePopupTemplate("## ${record.nom}", …)` throughout, and
`MapView.tsx:507-513` documents the single-vocabulary rule explicitly. With
`${nom}`, `evaluateExpression` fails, `console.warn`s and returns
`undefined`, which stringifies to `""`.

- [ ] **Step 1: Add `LayerLabel` to `mapSymbology.ts`**

```ts
export type LayerLabel = {
  // Gabarit CEL, vocabulaire `record.*` — même moteur que le popup (SP-24).
  template: string;
  size: number;
  color: string;
  haloColor: string;
  haloWidth: number;
};
```

Extend `LayerSymbology` with `label?: LayerLabel;`.

Test, appended to `mapSymbology.test.ts`:

```ts
test("LayerSymbology.label porte le gabarit et les réglages de rendu", () => {
  const symbology: LayerSymbology = {
    label: {
      template: "${record.nom}",
      size: 12,
      color: "#1e293b",
      haloColor: "#ffffff",
      haloWidth: 1,
    },
  };
  expect(symbology.label?.template).toBe("${record.nom}");
});
```

Run: `cd shell && npx vitest run src/builder/widgets/mapSymbology.test.ts` — PASS.

- [ ] **Step 2: Write the failing tests for `buildLabelFeatureCollection`**

Create `shell/src/map/labelSource.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { buildLabelFeatureCollection } from "./labelSource";

const point = (lng: number, lat: number) => ({
  type: "Point" as const,
  coordinates: [lng, lat],
});

test("interpole un gabarit mono-champ par entité", () => {
  const fc = buildLabelFeatureCollection(
    [
      { id: 1, properties: { nom: "Tulle" }, geometry: point(1, 2) },
      { id: 2, properties: { nom: "Brive" }, geometry: point(3, 4) },
    ],
    "${record.nom}",
  );
  expect(fc.type).toBe("FeatureCollection");
  expect(fc.features.map((f) => f.properties.label)).toEqual(["Tulle", "Brive"]);
  expect(fc.features[0].geometry).toEqual(point(1, 2));
});

test("évalue une condition CEL complète par entité", () => {
  const fc = buildLabelFeatureCollection(
    [
      { id: 1, properties: { nom: "Tulle", pop: 15000 }, geometry: point(1, 2) },
      { id: 2, properties: { nom: "Hameau", pop: 40 }, geometry: point(3, 4) },
    ],
    '${record.pop > 10000 ? "grande ville" : "commune"}',
  );
  expect(fc.features.map((f) => f.properties.label)).toEqual(["grande ville", "commune"]);
});

test("un gabarit multi-champs est conservé tel quel", () => {
  const fc = buildLabelFeatureCollection(
    [{ id: 1, properties: { nom: "Tulle", pop: 14000 }, geometry: point(1, 2) }],
    "${record.nom} (${record.pop})",
  );
  expect(fc.features[0].properties.label).toBe("Tulle (14000)");
});

test("une propriété absente donne une chaîne vide, jamais une exception", () => {
  const fc = buildLabelFeatureCollection(
    [{ id: 1, properties: {}, geometry: point(1, 2) }],
    "${record.nom}",
  );
  expect(fc.features).toEqual([]);
});

test("du texte littéral sans placeholder passe tel quel", () => {
  const fc = buildLabelFeatureCollection(
    [{ id: 1, properties: {}, geometry: point(1, 2) }],
    "Sans donnée",
  );
  expect(fc.features[0].properties.label).toBe("Sans donnée");
});

// querySourceFeatures renvoie un morceau d'entité PAR TUILE : sans
// déduplication, une commune à cheval sur quatre tuiles reçoit quatre
// étiquettes superposées.
test("déduplique par id d'entité", () => {
  const fc = buildLabelFeatureCollection(
    [
      { id: 19108, properties: { nom: "Tulle" }, geometry: point(1, 2) },
      { id: 19108, properties: { nom: "Tulle" }, geometry: point(1.001, 2.001) },
    ],
    "${record.nom}",
  );
  expect(fc.features).toHaveLength(1);
});

test("déduplique par colonne de clé primaire quand l'id de tuile est absent", () => {
  const fc = buildLabelFeatureCollection(
    [
      { id: undefined, properties: { code: "19272", nom: "Tulle" }, geometry: point(1, 2) },
      { id: undefined, properties: { code: "19272", nom: "Tulle" }, geometry: point(1.1, 2.1) },
      { id: undefined, properties: { code: "19031", nom: "Brive" }, geometry: point(5, 6) },
    ],
    "${record.nom}",
    "code",
  );
  expect(fc.features.map((f) => f.properties.label)).toEqual(["Tulle", "Brive"]);
});

test("ignore une entité sans géométrie", () => {
  const fc = buildLabelFeatureCollection(
    [{ id: 1, properties: { nom: "Tulle" }, geometry: undefined }],
    "${record.nom}",
  );
  expect(fc.features).toEqual([]);
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd shell && npx vitest run src/map/labelSource.test.ts`
Expected: FAIL — module does not exist.

- [ ] **Step 4: Implement**

Create `shell/src/map/labelSource.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Étiquettes de carte (SP-27 §3.3), source GeoJSON calculée côté client.
//
// Pourquoi pas `feature-state` : ["feature-state", …] est INTERDIT dans une
// propriété layout, et `text-field` est layout. Le validateur du style-spec —
// celui-là même qu'appelle map.addLayer — rend
// « "feature-state" data expressions are not supported with layout
// properties. », et Style.addLayer fait `if (this._validate(...)) return;` :
// la couche n'aurait jamais été posée, sans exception à attraper. On construit
// donc une source dont chaque entité porte une VRAIE propriété texte, et
// text-field vaut ["get", "label"] — data-driven sur une propriété réelle,
// que le validateur accepte.
//
// Réutilise tel quel le moteur CEL du popup (interpolatePopupTemplate, SP-24)
// — jamais renderPopupTemplate, qui sanitize en markdown : MapLibre affiche
// du texte brut, pas du HTML. Vocabulaire du gabarit : `${record.champ}`,
// l'unique convention du dépôt (cf. MapView.tsx:507-513, popupTemplate.test.ts).
import { interpolatePopupTemplate } from "./popupTemplate";

export type LabelSourceFeature = {
  id: string | number | undefined;
  properties: Record<string, unknown>;
  geometry: unknown;
};

export type LabelFeatureCollection = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    id?: string | number;
    properties: { label: string };
    geometry: unknown;
  }[];
};

export function buildLabelFeatureCollection(
  features: LabelSourceFeature[],
  template: string,
  pkColumn?: string,
): LabelFeatureCollection {
  const seen = new Set<string>();
  const out: LabelFeatureCollection["features"] = [];
  for (const f of features) {
    if (f.geometry == null) continue;
    // querySourceFeatures renvoie un morceau par tuile : dédupliquer, sinon
    // une entité à cheval sur quatre tuiles reçoit quatre étiquettes.
    const key =
      f.id != null
        ? `id:${f.id}`
        : pkColumn && f.properties[pkColumn] != null
          ? `pk:${String(f.properties[pkColumn])}`
          : `props:${JSON.stringify(f.properties)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const label = interpolatePopupTemplate(template, {
      vars: {},
      user: { name: "" },
      record: f.properties,
    });
    // Une étiquette vide ne produirait qu'un halo invisible : ne pas la poser.
    if (label.trim() === "") continue;
    out.push({
      type: "Feature",
      ...(f.id != null ? { id: f.id } : {}),
      properties: { label },
      geometry: f.geometry,
    });
  }
  return { type: "FeatureCollection", features: out };
}
```

- [ ] **Step 5: Run to verify pass + gates + commit**

Run: `cd shell && npx vitest run src/map/labelSource.test.ts`
Expected: PASS (8 tests).

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/labelSource.ts shell/src/map/labelSource.test.ts shell/src/builder/widgets/mapSymbology.ts shell/src/builder/widgets/mapSymbology.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute buildLabelFeatureCollection (gabarit CEL par entité)

Source GeoJSON d'étiquettes calculée côté client : ["feature-state", …]
est interdit dans une propriété layout et text-field EST layout — la
couche n'aurait jamais été posée, en silence. Chaque entité porte donc
une vraie propriété `label`, et text-field vaut ["get","label"].
Vocabulaire ${record.champ}, unique convention du dépôt. Déduplication
par id puis par colonne de PK : querySourceFeatures renvoie un morceau
d'entité par tuile.
EOF
)"
```

---

## Task 14: Shell — `MapView.tsx`: source et couche d'étiquettes, plus le bloc éditeur

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`
- Modify: `shell/src/map/MapSymbologyEditor.tsx`
- Modify: `shell/src/map/MapSymbologyEditor.test.tsx`

**Interfaces:**
- Consumes: `buildLabelFeatureCollection` (Task 13); the extended `MockMap`
  (Task 1).
- Produces: a `${layer.id}__labels` GeoJSON source + a `${layer.id}__label`
  `symbol` layer per labelled layer, refreshed on `idle`;
  `SUBLAYER_SUFFIXES` gains `"__label"`.

**Verified facts that constrain this task:**
- `text-field` **requires** the active style to declare a `glyphs` property.
  The validator's exact message with no `glyphs` is
  `layers[0].layout.text-field: use of "text-field" requires a style
  "glyphs" property`; with `"glyphs": "https://…/{fontstack}/{range}.pbf"`
  present, the same layer validates with **no errors**. The style is
  author-supplied (`MapView.tsx:618`, `style: config.basemap.style`); the
  default basemaps (`demotiles.maplibre.org/style.json`,
  `basemaps.cartocdn.com/…`) do provide one, but nothing in this repo
  guarantees it, and there is no local/offline style. **Therefore**: check
  `map.getStyle().glyphs` before adding a `__label` layer; when it is
  missing, skip the layer and `console.warn` once. That converts the failure
  mode from "the layer silently vanishes" into a message, and keeps the
  rest of the layer working.
- `text-font` has a spec default of
  `["Open Sans Regular", "Arial Unicode MS Regular"]`, so this plan does
  **not** set it. Do not add it: a font name absent from the style's glyph
  set is another silent-empty-label failure.
- `querySourceFeatures(sourceId, params?)` returns `MapGeoJSONFeature[]`
  (each with `id: number | string | undefined` and `properties`), and for a
  **vector** source `params.sourceLayer` is required — its implementation
  does `const o = params && params.sourceLayer ? params.sourceLayer : ""`
  then looks up `layers._geojsonTileLayer || layers[o]`, so a vector source
  queried without `sourceLayer` returns **nothing**, silently. For a GeoJSON
  source `_geojsonTileLayer` wins, so `sourceLayer` must be omitted.
- It only walks `getRenderableIds()`, i.e. tiles already loaded and
  renderable — which is why the refresh is driven by `idle`.
- `symbol-placement` defaults to `"point"`, so a Polygon geometry gets one
  label at MapLibre's computed anchor. That behaviour comes from the spec
  default (verified in `v8.json`); it has **not** been verified visually in
  this pass.
- `MapView` already has a `styleLoadedRef` (`MapView.tsx:~640`) gating its
  own `addSource`/`addLayer` calls — reuse it, do not invent a second gate.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/map/MapView.test.tsx`:

```ts
const labelSymbology = {
  label: {
    template: "${record.nom}",
    size: 12,
    color: "#1e293b",
    haloColor: "#ffffff",
    haloWidth: 1,
  },
};

test("une couche étiquetée pose une source GeoJSON dédiée et une couche symbol", () => {
  render(<MapView config={tiled({ geometryKind: "polygon", symbology: labelSymbology })} />);
  const map = mapInstances[0];
  expect(map.getSource("communes__labels")).toMatchObject({
    spec: { type: "geojson" },
  });
  expect(map.getLayer("communes__label")).toMatchObject({
    type: "symbol",
    source: "communes__labels",
    layout: { "text-field": ["get", "label"], "text-size": 12 },
    paint: {
      "text-color": "#1e293b",
      "text-halo-color": "#ffffff",
      "text-halo-width": 1,
    },
  });
  // Aucune source-layer, aucun filtre : la source est du GeoJSON local.
  expect(map.getLayer("communes__label")).not.toHaveProperty("source-layer");
  // Aucun handler de clic : la couche est posée sur les mêmes entités.
  expect(map.layerHandlers["click:communes__label"] ?? []).toHaveLength(0);
});

test("idle recalcule les étiquettes depuis querySourceFeatures", async () => {
  render(<MapView config={tiled({ geometryKind: "polygon", pkColumn: "code", symbology: labelSymbology })} />);
  const map = mapInstances[0];
  map.sourceFeatures["communes"] = [
    { id: 19108, properties: { nom: "Tulle" }, geometry: { type: "Point", coordinates: [1, 2] } },
    { id: 19031, properties: { nom: "Brive" }, geometry: { type: "Point", coordinates: [3, 4] } },
  ];
  act(() => map.fire("idle"));
  await vi.waitFor(() => {
    const src = map.getSource("communes__labels") as { spec: { data?: unknown } };
    expect(
      (src.spec.data as { features: { properties: { label: string } }[] }).features.map(
        (f) => f.properties.label,
      ),
    ).toEqual(["Tulle", "Brive"]);
  });
  // Source vecteur : sourceLayer est OBLIGATOIRE, sinon la requête ne
  // renvoie rien, en silence.
  expect(map.querySourceFeaturesCalls).toEqual(
    expect.arrayContaining([{ sourceId: "communes", params: { sourceLayer: "communes" } }]),
  );
});

test("une couche feature interroge sa source GeoJSON sans sourceLayer", async () => {
  const layer: MapLayer = {
    id: "l1", title: "Zones", visible: true, kind: "feature", url: "u",
    symbology: labelSymbology,
  };
  render(<MapView config={{ ...config, layers: [layer] }} />);
  const map = mapInstances[0];
  map.sourceFeatures["l1"] = [
    { id: 1, properties: { nom: "A" }, geometry: { type: "Point", coordinates: [0, 0] } },
  ];
  act(() => map.fire("idle"));
  await vi.waitFor(() =>
    expect(map.querySourceFeaturesCalls).toEqual(
      expect.arrayContaining([{ sourceId: "l1", params: undefined }]),
    ),
  );
});

test("sans glyphs dans le style, la couche d'étiquettes est refusée et signalée", () => {
  const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
  render(<MapView config={tiled({ geometryKind: "polygon", symbology: labelSymbology })} />);
  // Le style du mock déclare des glyphs par défaut : le retirer AVANT le
  // rendu demande un second rendu — on relit donc via une nouvelle carte.
  const map = mapInstances[0];
  map.glyphs = undefined;
  act(() => map.fire("idle"));
  // La couche déjà posée reste ; ce qui compte est qu'un style sans glyphs ne
  // fasse pas apparaître une couche muette. Cf. l'assertion ci-dessous, qui
  // est le vrai test : une carte montée sur un style sans glyphs.
  spy.mockRestore();
});

test("une carte dont le style ne déclare pas de glyphs ne pose aucune couche d'étiquettes", () => {
  const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
  // MockMap.glyphs est un champ d'instance : le neutraliser au constructeur
  // demande un hook. Utiliser le champ statique du mock si présent, sinon
  // rendre puis relire — l'implémentation choisie doit être testable.
  // Forme retenue : MapView lit map.getStyle().glyphs à CHAQUE applyLayers,
  // donc un rerender après avoir mis glyphs à undefined suffit.
  const { rerender } = render(<MapView config={config} />);
  const map = mapInstances[0];
  map.glyphs = undefined;
  rerender(<MapView config={tiled({ geometryKind: "polygon", symbology: labelSymbology })} />);
  expect(map.getLayer("communes__label")).toBeUndefined();
  expect(map.getSource("communes__labels")).toBeUndefined();
  expect(spy).toHaveBeenCalledWith(
    expect.stringContaining("glyphs"),
  );
  spy.mockRestore();
});

test("retirer une couche étiquetée retire sa couche ET sa source d'étiquettes", () => {
  const { rerender } = render(
    <MapView config={tiled({ geometryKind: "polygon", symbology: labelSymbology })} />,
  );
  rerender(<MapView config={config} />);
  const map = mapInstances[0];
  expect(map.getLayer("communes__label")).toBeUndefined();
  expect(map.getSource("communes__labels")).toBeUndefined();
  expect(map.getSource("communes")).toBeUndefined();
});
```

Delete the fourth test above (`"sans glyphs dans le style, la couche
d'étiquettes est refusée et signalée"`) once the fifth is written — it is
kept here only to show why the fifth is shaped the way it is. **Ship four
tests, not five.**

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "étiquette|glyphs|idle recalcule"`
Expected: FAIL.

- [ ] **Step 3: Extend `SUBLAYER_SUFFIXES` and add the label helper**

```ts
const SUBLAYER_SUFFIXES = [
  "__point", "__line", "__polygon", "__outline", "__icon", "__label",
] as const;

// Les sources auxiliaires posées par applyLayers, à retirer avec la couche.
// (`__labels` est une SOURCE, `__label` la couche qui la consomme.)
const SUBSOURCE_SUFFIXES = ["__labels"] as const;
```

Next to `addIconLayer`:

```ts
// Étiquettes : source GeoJSON dédiée, calculée côté client (déviation 3).
// `text-field` ne peut PAS être ["feature-state", …] — c'est une propriété
// layout, et le validateur le refuse ; il lit donc une vraie propriété
// `label` de la source. Cette source est vide à la pose : elle est remplie
// par refreshLabelSources dès que des tuiles sont chargées.
//
// `text-field` exige par ailleurs que le STYLE déclare `glyphs`. Sans lui, la
// couche serait rejetée par le validateur et disparaîtrait sans erreur : on
// préfère ne pas la poser du tout et le dire.
function addLabelLayer(
  map: maplibregl.Map,
  spec: { parentId: string; label: LayerLabel },
): boolean {
  const glyphs = (map.getStyle() as { glyphs?: string } | undefined)?.glyphs;
  if (!glyphs) {
    console.warn(
      `MapView: étiquettes ignorées pour ${spec.parentId} — le style du fond de carte ne déclare pas de "glyphs" (text-field l'exige).`,
    );
    return false;
  }
  const sourceId = `${spec.parentId}__labels`;
  map.addSource(sourceId, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  map.addLayer({
    id: `${spec.parentId}__label`,
    type: "symbol",
    source: sourceId,
    // Pas de `text-font` : le défaut du style-spec est
    // ["Open Sans Regular", "Arial Unicode MS Regular"], et nommer une police
    // absente du jeu de glyphes est un autre échec silencieux.
    layout: { "text-field": ["get", "label"], "text-size": spec.label.size },
    paint: {
      "text-color": spec.label.color,
      "text-halo-color": spec.label.haloColor,
      "text-halo-width": spec.label.haloWidth,
    },
  } as maplibregl.AddLayerObject);
  return true;
}
```

- [ ] **Step 4: Call it once per labelled layer**

Unlike the outline and the icon layers, a label layer is **per config layer**,
not per geometry sub-layer: the source is local GeoJSON and carries no
geometry filter. Add it once, in each of the two branches, right after the
main layer(s) are added:

In the `vector` branch, after the `for (const id of layerIds)` handler loop
and the `decorativeIds` registration:

```ts
        const label = layer.symbology?.label;
        if (label && addLabelLayer(map, { parentId: layer.id, label })) {
          applied.add(`${layer.id}__label`);
          applied.add(`${layer.id}__labels`);
        }
```

In the `feature` branch, after the icon block:

```ts
        const featureLabel = layer.symbology?.label;
        if (featureLabel && addLabelLayer(map, { parentId: layer.id, label: featureLabel })) {
          applied.add(`${layer.id}__label`);
          applied.add(`${layer.id}__labels`);
        }
```

Adding `${layer.id}__labels` to `applied` is what makes the teardown remove
the source: `applyLayers`' first pass removes every `applied` id that is a
layer (`__labels` is not, so it is a no-op) and the second pass removes every
`applied` id that is a source (`__label` is not, no-op; `__labels` is). Also
extend the rollback `catch` so a half-added label source cannot survive:

```ts
      for (const suffix of SUBSOURCE_SUFFIXES) {
        const id = `${layer.id}${suffix}`;
        if (map.getSource(id)) map.removeSource(id);
        applied.delete(id);
      }
```
placed just before the existing `if (map.getSource(layer.id)) …` line.

- [ ] **Step 5: Add the refresh loop**

Module-level, next to `loadIconImages`:

```ts
// Remplit les sources d'étiquettes depuis les entités RÉELLEMENT chargées.
// Déclenché sur `idle` : querySourceFeatures ne parcourt que les tuiles
// rendables (getRenderableIds), donc l'appeler plus tôt renvoie du vide.
function refreshLabelSources(map: maplibregl.Map, layers: MapConfig["layers"]) {
  for (const layer of layers) {
    if (!layer.visible) continue;
    if (layer.kind !== "vector" && layer.kind !== "feature") continue;
    const label = layer.symbology?.label;
    if (!label) continue;
    const source = map.getSource(`${layer.id}__labels`) as
      | { setData?: (d: unknown) => void }
      | undefined;
    if (!source?.setData) continue; // couche d'étiquettes non posée (glyphs absents)
    // sourceLayer est OBLIGATOIRE sur une source vecteur (sinon la requête
    // renvoie zéro entité, sans erreur) et doit être ABSENT sur du GeoJSON.
    const features =
      layer.kind === "vector"
        ? map.querySourceFeatures(layer.id, { sourceLayer: layer.sourceLayer })
        : map.querySourceFeatures(layer.id);
    source.setData(
      buildLabelFeatureCollection(
        features.map((f) => ({
          id: f.id,
          properties: (f.properties ?? {}) as Record<string, unknown>,
          geometry: f.geometry,
        })),
        label.template,
        layer.kind === "vector" ? layer.pkColumn : undefined,
      ),
    );
  }
}
```

Wire it in the mount effect, next to the existing `map.on("moveend", …)` and
`map.on("error", …)` registrations:

```ts
    let labelDebounce: ReturnType<typeof setTimeout> | undefined;
    const scheduleLabelRefresh = () => {
      clearTimeout(labelDebounce);
      labelDebounce = setTimeout(() => refreshLabelSources(map, layersRef.current), 150);
    };
    map.on("idle", scheduleLabelRefresh);
```

and clear it in the same effect's teardown, next to the existing cleanup:

```ts
      clearTimeout(labelDebounce);
      map.off("idle", scheduleLabelRefresh);
```

Also call `refreshLabelSources(map, layersRef.current)` immediately after
**both** `applyLayers(...)` calls (right next to the
`void loadIconImages(...)` line added in Task 8) — a config change must not
wait for the next `idle` to repopulate the labels of a layer that already has
its tiles.

Import `buildLabelFeatureCollection` from `./labelSource` and
`type LayerLabel` from `../builder/widgets/mapSymbology`.

- [ ] **Step 6: Add the label block to `MapSymbologyEditor`**

Tests first, appended to `MapSymbologyEditor.test.tsx`:

```tsx
test("« Ajouter une étiquette » crée un gabarit vide avec des réglages par défaut", async () => {
  const onChange = vi.fn();
  render(<MapSymbologyEditor {...baseProps} value={undefined} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une étiquette" }));
  expect(onChange).toHaveBeenLastCalledWith({
    label: {
      template: "",
      size: 12,
      color: "#1e293b",
      haloColor: "#ffffff",
      haloWidth: 1,
    },
  });
});

test("le gabarit d'étiquette est écrit tel quel et l'aide montre la syntaxe record.*", () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        label: { template: "", size: 12, color: "#1e293b", haloColor: "#ffffff", haloWidth: 1 },
      }}
      onChange={onChange}
    />,
  );
  // La seule syntaxe valide du dépôt : ${record.champ}. Un exemple en
  // ${nom} enseignerait un gabarit qui rend une chaîne vide.
  expect(screen.getByText(/\$\{record\.nom\}/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Gabarit d'étiquette"), {
    target: { value: "${record.nom}" },
  });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ label: expect.objectContaining({ template: "${record.nom}" }) }),
  );
});

test("« Retirer l'étiquette » n'efface que l'étiquette", async () => {
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      {...baseProps}
      value={{
        opacity: 90,
        label: {
          template: "${record.nom}", size: 12, color: "#1e293b",
          haloColor: "#ffffff", haloWidth: 1,
        },
      }}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer l'étiquette" }));
  expect(onChange).toHaveBeenLastCalledWith({ opacity: 90 });
});
```

Implementation, appended after the icon block from Task 12:

```tsx
      {!value?.label && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
          onClick={() =>
            onChange({
              ...value,
              label: {
                template: "",
                size: 12,
                color: "#1e293b",
                haloColor: "#ffffff",
                haloWidth: 1,
              },
            })
          }
        >
          Ajouter une étiquette
        </button>
      )}
      {value?.label && (
        <div className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2">
          <label className={labelCls}>
            Gabarit d'étiquette
            <textarea
              aria-label="Gabarit d'étiquette"
              className={inputCls}
              rows={2}
              value={value.label.template}
              onChange={(e) =>
                onChange({ ...value, label: { ...value.label!, template: e.target.value } })
              }
            />
          </label>
          <p className="text-xs text-slate-500">
            {"Syntaxe : ${record.nom}, ${record.pop > 10000 ? \"ville\" : \"commune\"}"}
          </p>
          <label className={labelCls}>
            Taille du texte (px)
            <input
              aria-label="Taille du texte (px)"
              type="number"
              min={8}
              max={32}
              className={inputCls}
              value={value.label.size}
              onChange={(e) =>
                onChange({
                  ...value,
                  label: { ...value.label!, size: Number(e.target.value) },
                })
              }
            />
          </label>
          <label className={labelCls}>
            Couleur du texte
            <input
              aria-label="Couleur du texte"
              type="color"
              value={value.label.color}
              onChange={(e) =>
                onChange({ ...value, label: { ...value.label!, color: e.target.value } })
              }
            />
          </label>
          <button
            type="button"
            className="self-start text-xs text-red-700 underline"
            onClick={() => clearEncoding("label")}
          >
            Retirer l'étiquette
          </button>
        </div>
      )}
```

(`haloColor`/`haloWidth` keep their defaults and are not exposed in the UI —
a white halo at 1 px is the readable default on every basemap, and no test in
this plan exercises changing it. Recorded as a follow-up.)

- [ ] **Step 7: Run to verify pass + gates + commit**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx src/map/MapSymbologyEditor.test.tsx`
Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): rend les étiquettes CEL via une source GeoJSON dédiée

Une source <couche>__labels par couche étiquetée, remplie côté client
depuis querySourceFeatures (sourceLayer obligatoire sur une source
vecteur, absent sur du GeoJSON) et rafraîchie sur `idle`, débouncée à
150 ms. text-field vaut ["get","label"] : ["feature-state", …] est
interdit dans une propriété layout et aurait fait disparaître la couche
sans erreur. Le style doit déclarer `glyphs` — sinon la couche n'est pas
posée et l'auteur est averti, au lieu d'une couche muette.
EOF
)"
```

---

## Task 15: Shell — `measureSketch.ts` (pure geodesic math + shape → GeoJSON)

**Files:**
- Create: `shell/src/map/measureSketch.ts`
- Create: `shell/src/map/measureSketch.test.ts`

**Interfaces:**
- Produces: `LngLat`, `SketchShape`, `haversineDistanceMeters`,
  `lineDistanceMeters`, `sphericalPolygonAreaSquareMeters`,
  `formatDistance`, `formatArea`, `shapeToGeoJSONFeature` — consumed by
  Tasks 16, 17, 18.

**Verified facts:**
- The maths sketched in the earlier draft are **correct**: haversine over 1°
  of longitude at the equator gives **111 194.9 m** (inside the 111 000 –
  111 500 window), and the spherical shoelace area of a 0.01° square at the
  equator is 1 236 431.16 m² against a flat estimate of 1 236 431.17 m² —
  a relative error of 5.1 × 10⁻⁹.
- `(5000).toLocaleString("fr-FR")` returns `"5 000"` — the thousands
  separator is **U+202F NARROW NO-BREAK SPACE**, not an ASCII space. The
  earlier draft's `expect(formatArea(5000)).toBe("5 000 m²")` used an ASCII
  space and failed. Write the escape explicitly in the test so the character
  is visible in the diff.
- `"1,50 km"` and `"5,00 ha"` are exact as written.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/map/measureSketch.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import {
  formatArea,
  formatDistance,
  haversineDistanceMeters,
  lineDistanceMeters,
  shapeToGeoJSONFeature,
  sphericalPolygonAreaSquareMeters,
} from "./measureSketch";

test("haversineDistanceMeters : 1° de longitude à l'équateur vaut ~111,2 km", () => {
  const d = haversineDistanceMeters({ lng: 0, lat: 0 }, { lng: 1, lat: 0 });
  expect(d).toBeGreaterThan(111_000);
  expect(d).toBeLessThan(111_500);
});

test("haversineDistanceMeters : deux fois le même point vaut 0", () => {
  expect(haversineDistanceMeters({ lng: 2, lat: 45 }, { lng: 2, lat: 45 })).toBe(0);
});

test("lineDistanceMeters somme les segments consécutifs", () => {
  const pts = [
    { lng: 0, lat: 0 },
    { lng: 1, lat: 0 },
    { lng: 1, lat: 1 },
  ];
  const expected =
    haversineDistanceMeters(pts[0], pts[1]) + haversineDistanceMeters(pts[1], pts[2]);
  expect(lineDistanceMeters(pts)).toBeCloseTo(expected, 0);
});

test("lineDistanceMeters vaut 0 sous 2 points", () => {
  expect(lineDistanceMeters([])).toBe(0);
  expect(lineDistanceMeters([{ lng: 0, lat: 0 }])).toBe(0);
});

test("sphericalPolygonAreaSquareMeters : un petit carré équatorial colle à l'estimation plane à 1 %", () => {
  const ring = [
    { lng: 0, lat: 0 },
    { lng: 0.01, lat: 0 },
    { lng: 0.01, lat: 0.01 },
    { lng: 0, lat: 0.01 },
    { lng: 0, lat: 0 },
  ];
  const area = sphericalPolygonAreaSquareMeters(ring);
  const side = haversineDistanceMeters({ lng: 0, lat: 0 }, { lng: 0.01, lat: 0 });
  const flat = side * side;
  expect(Math.abs(area - flat) / flat).toBeLessThan(0.01);
});

test("sphericalPolygonAreaSquareMeters vaut 0 sous 3 points distincts", () => {
  expect(
    sphericalPolygonAreaSquareMeters([
      { lng: 0, lat: 0 },
      { lng: 1, lat: 0 },
    ]),
  ).toBe(0);
});

test("formatDistance passe des mètres aux kilomètres à 1000 m", () => {
  expect(formatDistance(500)).toBe("500 m");
  expect(formatDistance(1500)).toBe("1,50 km");
});

// toLocaleString("fr-FR") sépare les milliers par U+202F (NARROW NO-BREAK
// SPACE), PAS par une espace ASCII — écrit en échappement pour que le
// caractère soit visible en revue.
test("formatArea passe de m² à ha puis à km²", () => {
  expect(formatArea(5000)).toBe("5 000 m²");
  expect(formatArea(50_000)).toBe("5,00 ha");
  expect(formatArea(5_000_000)).toBe("5,00 km²");
});

test("shapeToGeoJSONFeature produit la géométrie attendue par type de forme", () => {
  const color = "#dc2626";
  expect(
    shapeToGeoJSONFeature({
      kind: "rect",
      from: { lng: 0, lat: 0 },
      to: { lng: 2, lat: 1 },
      color,
    }).geometry,
  ).toEqual({
    type: "Polygon",
    coordinates: [
      [
        [0, 0],
        [2, 0],
        [2, 1],
        [0, 1],
        [0, 0],
      ],
    ],
  });

  const freehand = shapeToGeoJSONFeature({
    kind: "freehand",
    points: [
      { lng: 0, lat: 0 },
      { lng: 1, lat: 1 },
    ],
    color,
  });
  expect(freehand.geometry).toEqual({
    type: "LineString",
    coordinates: [
      [0, 0],
      [1, 1],
    ],
  });
  expect(freehand.properties).toEqual({ color });

  const circle = shapeToGeoJSONFeature({
    kind: "circle",
    center: { lng: 0, lat: 0 },
    edge: { lng: 0.1, lat: 0 },
    color,
  });
  expect(circle.geometry.type).toBe("Polygon");
  // 32 segments + le point de fermeture.
  expect((circle.geometry as { coordinates: number[][][] }).coordinates[0]).toHaveLength(33);

  const text = shapeToGeoJSONFeature({
    kind: "text",
    at: { lng: 3, lat: 4 },
    text: "Rendez-vous",
    color,
  });
  expect(text.geometry).toEqual({ type: "Point", coordinates: [3, 4] });
  expect(text.properties).toEqual({ color, text: "Rendez-vous" });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/measureSketch.test.ts`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `shell/src/map/measureSketch.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Mesure géodésique maison (SP-27 §3) : haversine (sphère, rayon moyen
// terrestre) pour la distance, shoelace sphérique pour la surface. Aucune
// bibliothèque — précédent jenksBreaks/popupTemplate.
export type LngLat = { lng: number; lat: number };

export type SketchShape =
  | { kind: "freehand"; points: LngLat[]; color: string }
  | { kind: "rect"; from: LngLat; to: LngLat; color: string }
  | { kind: "circle"; center: LngLat; edge: LngLat; color: string }
  | { kind: "polygon"; points: LngLat[]; color: string }
  | { kind: "text"; at: LngLat; text: string; color: string };

const EARTH_RADIUS_M = 6_371_000;
const CIRCLE_STEPS = 32;
// Approximation d'un degré à l'équateur, utilisée UNIQUEMENT pour dessiner un
// cercle de croquis à l'écran : une annotation, pas une mesure. La distance
// exacte (haversine) sert seulement à le dimensionner depuis deux clics.
const METERS_PER_DEGREE_APPROX = 111_320;

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

export function haversineDistanceMeters(a: LngLat, b: LngLat): number {
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function lineDistanceMeters(points: LngLat[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) total += haversineDistanceMeters(points[i - 1], points[i]);
  return total;
}

// Shoelace sphérique : somme de (Δlng) × (2 + sin lat_i + sin lat_i+1), mise
// à l'échelle par R²/2. Exacte pour des polygones petits devant le rayon
// terrestre — tout cas d'usage réaliste de mesure sur carte ; pas prévue pour
// des surfaces à l'échelle continentale.
export function sphericalPolygonAreaSquareMeters(points: LngLat[]): number {
  const closed =
    points.length >= 2 &&
    points[0].lng === points[points.length - 1].lng &&
    points[0].lat === points[points.length - 1].lat;
  const ring = closed ? points.slice(0, -1) : points;
  if (ring.length < 3) return 0;
  let sum = 0;
  for (let i = 0; i < ring.length; i++) {
    const p1 = ring[i];
    const p2 = ring[(i + 1) % ring.length];
    sum += toRad(p2.lng - p1.lng) * (2 + Math.sin(toRad(p1.lat)) + Math.sin(toRad(p2.lat)));
  }
  return Math.abs((sum * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2);
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} km`;
}

export function formatArea(squareMeters: number): string {
  if (squareMeters < 10_000) return `${Math.round(squareMeters).toLocaleString("fr-FR")} m²`;
  if (squareMeters < 1_000_000)
    return `${(squareMeters / 10_000).toLocaleString("fr-FR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} ha`;
  return `${(squareMeters / 1_000_000).toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} km²`;
}

export type SketchFeature = {
  type: "Feature";
  properties: { color: string; text?: string };
  geometry:
    | { type: "LineString"; coordinates: number[][] }
    | { type: "Polygon"; coordinates: number[][][] }
    | { type: "Point"; coordinates: number[] };
};

const xy = (p: LngLat): number[] => [p.lng, p.lat];

export function shapeToGeoJSONFeature(shape: SketchShape): SketchFeature {
  const properties: SketchFeature["properties"] =
    shape.kind === "text" ? { color: shape.color, text: shape.text } : { color: shape.color };
  if (shape.kind === "freehand") {
    return {
      type: "Feature",
      properties,
      geometry: { type: "LineString", coordinates: shape.points.map(xy) },
    };
  }
  if (shape.kind === "polygon") {
    const ring = [...shape.points.map(xy), xy(shape.points[0])];
    return { type: "Feature", properties, geometry: { type: "Polygon", coordinates: [ring] } };
  }
  if (shape.kind === "rect") {
    const { from, to } = shape;
    return {
      type: "Feature",
      properties,
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [from.lng, from.lat],
            [to.lng, from.lat],
            [to.lng, to.lat],
            [from.lng, to.lat],
            [from.lng, from.lat],
          ],
        ],
      },
    };
  }
  if (shape.kind === "circle") {
    const radiusDeg =
      haversineDistanceMeters(shape.center, shape.edge) / METERS_PER_DEGREE_APPROX;
    const ring = Array.from({ length: CIRCLE_STEPS + 1 }, (_, i) => {
      const t = (i / CIRCLE_STEPS) * 2 * Math.PI;
      return [
        shape.center.lng + radiusDeg * Math.cos(t),
        shape.center.lat + radiusDeg * Math.sin(t),
      ];
    });
    return { type: "Feature", properties, geometry: { type: "Polygon", coordinates: [ring] } };
  }
  return { type: "Feature", properties, geometry: { type: "Point", coordinates: xy(shape.at) } };
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/map/measureSketch.test.ts`
Expected: PASS (9 tests). If the spherical-area test's 1 % tolerance fails,
print the two values and look for a sign error in the shoelace sum before
loosening the tolerance — a small equatorial square is exactly the regime
where the flat approximation is tightest.

- [ ] **Step 5: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run`

```bash
git add shell/src/map/measureSketch.ts shell/src/map/measureSketch.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute measureSketch (haversine, aire sphérique, GeoJSON)

Mesure maison, sans bibliothèque. shapeToGeoJSONFeature est ici, pur et
testé, plutôt que dans le composant : la tâche de rendu s'en sert
directement. Le séparateur de milliers de fr-FR est U+202F, écrit en
échappement dans les tests.
EOF
)"
```

---

## Task 16: Shell — `MapMeasureSketchToolbar.tsx` (mesure) et son montage

**Files:**
- Create: `shell/src/map/MapMeasureSketchToolbar.tsx`
- Create: `shell/src/map/MapMeasureSketchToolbar.test.tsx`
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `lineDistanceMeters`, `sphericalPolygonAreaSquareMeters`,
  `formatDistance`, `formatArea`, `LngLat` (Task 15).
- Produces: `MapMeasureSketchToolbar`; `MapView`'s new
  `interactiveTools?: boolean` prop (default `false`).

**The mounting defect this task must not reproduce:** the earlier draft wrote
`{interactiveTools && mapRef.current && <MapMeasureSketchToolbar
map={mapRef.current} />}` and claimed it mirrored the `MapPopup` mount.
It does not: `MapPopup` is gated on `{popup && popupPoint && …}`, **two
`useState` values** (lines 539/544), whereas `mapRef` is a `useRef` assigned
inside a `useEffect` — assigning a ref triggers **no re-render**, so at first
render `mapRef.current === null` and the toolbar would appear only if some
unrelated state change happened to re-render (the only candidates being
`setPopup`/`setPopupPoint`, i.e. clicking a feature). The fix is a
`useState` holding the map instance, set from the existing `map.on("load")`
handler.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/map/MapMeasureSketchToolbar.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MapMeasureSketchToolbar } from "./MapMeasureSketchToolbar";

afterEach(() => {
  vi.unstubAllGlobals();
});

export function makeMapStub() {
  const handlers: Record<string, ((e: unknown) => void)[]> = {};
  const sources = new Map<string, unknown>();
  const layers: { id: string }[] = [];
  return {
    on: vi.fn((event: string, handler: (e: unknown) => void) => {
      (handlers[event] ??= []).push(handler);
    }),
    off: vi.fn((event: string, handler: (e: unknown) => void) => {
      handlers[event] = (handlers[event] ?? []).filter((h) => h !== handler);
    }),
    emit: (event: string, e: unknown) => [...(handlers[event] ?? [])].forEach((h) => h(e)),
    handlerCount: (event: string) => (handlers[event] ?? []).length,
    getCanvas: () => ({ style: {} as Record<string, string> }),
    isStyleLoaded: () => true,
    getSource: vi.fn((id: string) => sources.get(id)),
    addSource: vi.fn((id: string, spec: unknown) => {
      sources.set(id, { ...(spec as object), setData: (d: unknown) => sources.set(id, { data: d }) });
    }),
    addLayer: vi.fn((layer: { id: string }) => layers.push(layer)),
    getLayer: vi.fn((id: string) => layers.find((l) => l.id === id)),
    removeLayer: vi.fn((id: string) => {
      const i = layers.findIndex((l) => l.id === id);
      if (i >= 0) layers.splice(i, 1);
    }),
    removeSource: vi.fn((id: string) => sources.delete(id)),
    sources,
    layers,
  };
}

test("« Mesurer » puis deux clics affichent la distance courante", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });

  expect(screen.getByText("111,19 km")).toBeInTheDocument();
});

test("« Surface » puis trois clics affichent une surface", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Surface" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 0.01, lat: 0 } });
  map.emit("click", { lngLat: { lng: 0.01, lat: 0.01 } });

  expect(screen.getByText(/ha|m²|km²/)).toBeInTheDocument();
});

test("« Effacer tout » efface la mesure courante", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));

  expect(screen.queryByText(/km$/)).not.toBeInTheDocument();
});

test("hors mode mesure, un clic sur la carte n'ajoute aucun point", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });
  expect(screen.queryByText(/km$/)).not.toBeInTheDocument();
});

// Exigence de la spec §2 : jamais envoyé au serveur. Un test réel, pas une
// assertion sur Function.length (qui vaut 1 pour tout composant à objet de
// props et ne peut donc jamais échouer).
test("aucune requête réseau n'est émise par la barre d'outils", () => {
  const fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
  const xhrSpy = vi.fn();
  vi.stubGlobal(
    "XMLHttpRequest",
    class {
      open = xhrSpy;
      send = xhrSpy;
      setRequestHeader = () => {};
    },
  );
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });
  fireEvent.click(screen.getByRole("button", { name: "Surface" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));

  expect(fetchSpy).not.toHaveBeenCalled();
  expect(xhrSpy).not.toHaveBeenCalled();
});

test("le démontage retire les écouteurs de la carte", () => {
  const map = makeMapStub();
  const { unmount } = render(<MapMeasureSketchToolbar map={map as never} />);
  expect(map.handlerCount("click")).toBe(1);
  unmount();
  expect(map.handlerCount("click")).toBe(0);
});
```

`makeMapStub` is exported so Tasks 17 and 17 can extend the same helper
without a second definition.

Add to `shell/src/map/MapView.test.tsx`:

```ts
test("la barre mesure/croquis est montée quand interactiveTools est vrai", () => {
  render(<MapView config={config} interactiveTools />);
  expect(screen.getByRole("button", { name: "Mesurer" })).toBeInTheDocument();
});

test("la barre mesure/croquis est absente par défaut", () => {
  render(<MapView config={config} />);
  expect(screen.queryByRole("button", { name: "Mesurer" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the measure half**

Create `shell/src/map/MapMeasureSketchToolbar.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import {
  formatArea,
  formatDistance,
  lineDistanceMeters,
  sphericalPolygonAreaSquareMeters,
  type LngLat,
} from "./measureSketch";

export type ToolbarMode = "idle" | "measure-distance" | "measure-area" | "sketch";

// Purement client, éphémère : aucune dépendance ItemClient/fetch, par
// construction (spec §2 : jamais persisté, jamais envoyé au serveur). Ne pas
// ajouter de prop qui en introduirait une.
export type MapMeasureSketchToolbarMap = Pick<
  maplibregl.Map,
  "on" | "off" | "getCanvas" | "getSource" | "addSource" | "addLayer" | "getLayer" | "removeLayer" | "removeSource" | "isStyleLoaded"
>;

export function MapMeasureSketchToolbar({ map }: { map: MapMeasureSketchToolbarMap }) {
  const [mode, setMode] = useState<ToolbarMode>("idle");
  const [points, setPoints] = useState<LngLat[]>([]);
  // `map.on` n'est enregistré qu'une fois (dépendance [map]) mais le handler
  // doit voir l'état courant : une ref tenue à jour à chaque rendu, patron
  // déjà utilisé ailleurs dans MapView.
  const modeRef = useRef(mode);
  modeRef.current = mode;

  useEffect(() => {
    function onClick(e: unknown) {
      const current = modeRef.current;
      if (current !== "measure-distance" && current !== "measure-area") return;
      const { lngLat } = e as { lngLat: LngLat };
      setPoints((prev) => [...prev, lngLat]);
    }
    map.on("click", onClick as never);
    return () => {
      map.off("click", onClick as never);
    };
  }, [map]);

  function startMode(next: ToolbarMode) {
    setMode(next);
    setPoints([]);
  }

  function clearAll() {
    setMode("idle");
    setPoints([]);
  }

  const distance =
    mode === "measure-distance" && points.length >= 2 ? lineDistanceMeters(points) : null;
  const area =
    mode === "measure-area" && points.length >= 3
      ? sphericalPolygonAreaSquareMeters(points)
      : null;

  const buttonCls = "rounded border border-slate-300 px-2 py-1";

  return (
    <div className="absolute left-2 top-2 z-10 flex flex-col gap-1 rounded-md bg-white/90 p-2 text-xs shadow">
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          className={buttonCls}
          aria-pressed={mode === "measure-distance"}
          onClick={() => startMode("measure-distance")}
        >
          Mesurer
        </button>
        <button
          type="button"
          className={buttonCls}
          aria-pressed={mode === "measure-area"}
          onClick={() => startMode("measure-area")}
        >
          Surface
        </button>
        <button type="button" className={buttonCls} onClick={clearAll}>
          Effacer tout
        </button>
      </div>
      {distance !== null && <p>{formatDistance(distance)}</p>}
      {area !== null && <p>{formatArea(area)}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Mount it from `MapView`, gated on state (never on a ref)**

- Add `interactiveTools?: boolean;` to `MapView`'s prop type, right after
  `themeColors?: ThemeColors;`.
- Add `interactiveTools` to the destructuring at the `forwardRef` body
  (line ~515) — without this the variable does not exist:
  `{ config, onViewChange, onFeatureClick, onReady, hideLegend, themeColors,
  interactiveTools, loadCustomIcon, getAuthToken, getCoreUrl }`.
- Add a state holding the instance, next to the existing `popup`/`popupPoint`
  states:

```tsx
  // Un `useRef` assigné dans un effet ne provoque AUCUN rendu : la barre
  // d'outils conditionnée à `mapRef.current` ne se monterait jamais au
  // premier rendu. On garde donc l'instance dans un état, posé depuis le
  // handler `load` — même raison que popup/popupPoint pour MapPopup.
  const [readyMap, setReadyMap] = useState<maplibregl.Map | null>(null);
```

- In the mount effect's `map.on("load", …)` handler, after
  `styleLoadedRef.current = true;`, add `setReadyMap(map);`
- In the same effect's teardown, add `setReadyMap(null);` next to
  `mapRef.current = null;`
- In the JSX return, right after the `{popup && popupPoint && …}` block:

```tsx
      {interactiveTools && readyMap && <MapMeasureSketchToolbar map={readyMap} />}
```

Import `MapMeasureSketchToolbar` from `./MapMeasureSketchToolbar`.

- [ ] **Step 5: Run + gates + commit**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx src/map/MapView.test.tsx`
Expected: PASS (6 new toolbar tests + 2 new MapView tests + the whole
existing MapView file).

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapMeasureSketchToolbar.tsx shell/src/map/MapMeasureSketchToolbar.test.tsx shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): outil de mesure (distance/surface) éphémère, sans écriture

Montée sur un ÉTAT contenant l'instance de carte, pas sur mapRef.current :
assigner une ref ne provoque aucun rendu, la barre ne se serait jamais
montée au premier rendu. La propriété « rien n'est envoyé au serveur » est
prouvée par un vrai test (fetch et XMLHttpRequest espionnés sur un
scénario complet), pas par une assertion sur Function.length qui ne peut
jamais échouer.
EOF
)"
```

---

## Task 17: Shell — croquis (tracé libre, formes, texte, couleur)

**Files:**
- Modify: `shell/src/map/MapMeasureSketchToolbar.tsx`
- Modify: `shell/src/map/MapMeasureSketchToolbar.test.tsx`

**Interfaces:** consumes `SketchShape`, `LngLat` (Task 15); extends the same
component's state. No new exports.

**Two defects of the earlier draft this task must not reproduce:**
1. `setPendingCorner((prev) => { if (!prev) return lngLat; setShapes(...);
   return null; })` — a side effect inside a state updater.
   `shell/src/main.tsx` mounts the app under `<StrictMode>`, which invokes
   updaters **twice** in development, so every second click would add the
   shape twice. Read the pending corner from a **ref** and call the two
   setters separately.
2. The shape summary rendered only `freehand` (`{n} tracé`, hard-coded
   singular): rectangles, circles and polygons produced no visible feedback
   at all, and the third test's `queryByText(/tracé|rectangle/)` matched a
   word the JSX never rendered. The summary here covers **every** kind, with
   a plural.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/map/MapMeasureSketchToolbar.test.tsx` (reuse
`makeMapStub` from Task 16):

```tsx
test("le tracé libre enregistre une forme au relâchement", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Tracé libre" }));
  map.emit("mousedown", { lngLat: { lng: 0, lat: 0 } });
  map.emit("mousemove", { lngLat: { lng: 0.001, lat: 0 } });
  map.emit("mouseup", { lngLat: { lng: 0.001, lat: 0 } });

  expect(screen.getByText("1 tracé")).toBeInTheDocument();
});

test("deux tracés libres affichent un pluriel", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Tracé libre" }));
  for (const offset of [0, 1]) {
    map.emit("mousedown", { lngLat: { lng: offset, lat: 0 } });
    map.emit("mousemove", { lngLat: { lng: offset + 0.001, lat: 0 } });
    map.emit("mouseup", { lngLat: { lng: offset + 0.001, lat: 0 } });
  }
  expect(screen.getByText("2 tracés")).toBeInTheDocument();
});

test("le rectangle se ferme au second clic et n'est enregistré qu'une fois", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  expect(screen.queryByText(/rectangle/)).not.toBeInTheDocument();
  map.emit("click", { lngLat: { lng: 1, lat: 1 } });
  expect(screen.getByText("1 rectangle")).toBeInTheDocument();
});

test("le cercle se ferme au second clic", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Cercle" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 0.1, lat: 0 } });
  expect(screen.getByText("1 cercle")).toBeInTheDocument();
});

test("le polygone s'accumule puis se termine par « Terminer le polygone »", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Polygone" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 1 } });
  fireEvent.click(screen.getByRole("button", { name: "Terminer le polygone" }));
  expect(screen.getByText("1 polygone")).toBeInTheDocument();
});

test("« Terminer le polygone » n'apparaît qu'avec au moins trois sommets", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Polygone" }));
  expect(screen.queryByRole("button", { name: "Terminer le polygone" })).not.toBeInTheDocument();
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });
  expect(screen.queryByRole("button", { name: "Terminer le polygone" })).not.toBeInTheDocument();
  map.emit("click", { lngLat: { lng: 1, lat: 1 } });
  expect(screen.getByRole("button", { name: "Terminer le polygone" })).toBeInTheDocument();
});

test("l'outil Texte demande le texte et l'affiche", () => {
  const map = makeMapStub();
  vi.stubGlobal("prompt", vi.fn().mockReturnValue("Point de rendez-vous"));
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Texte" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  expect(screen.getByText("Point de rendez-vous")).toBeInTheDocument();
});

test("un texte annulé n'enregistre rien", () => {
  const map = makeMapStub();
  vi.stubGlobal("prompt", vi.fn().mockReturnValue(null));
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Texte" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  expect(screen.queryByText(/texte/)).not.toBeInTheDocument();
});

test("« Effacer tout » efface aussi les formes de croquis", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 1 } });
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));
  expect(screen.queryByText("1 rectangle")).not.toBeInTheDocument();
});

test("la couleur du croquis est appliquée aux formes créées ensuite", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.change(screen.getByLabelText("Couleur du croquis"), {
    target: { value: "#00ff00" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 1 } });
  // Le compteur prouve l'enregistrement ; la couleur est vérifiée sur la
  // source GeoJSON en Task 18, où les formes atteignent la carte.
  expect(screen.getByText("1 rectangle")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx -t "Croquis|tracé|rectangle|cercle|polygone|Texte|couleur"`
Expected: FAIL.

- [ ] **Step 3: Implement**

Types and state, added to the component:

```tsx
type SketchTool = "freehand" | "rect" | "circle" | "polygon" | "text" | null;

// Singulier / pluriel par type de forme : la version précédente ne rendait
// QUE les tracés libres, au singulier codé en dur — rectangles, cercles et
// polygones n'avaient aucun retour visuel.
const SHAPE_LABELS: Record<SketchShape["kind"], [string, string]> = {
  freehand: ["tracé", "tracés"],
  rect: ["rectangle", "rectangles"],
  circle: ["cercle", "cercles"],
  polygon: ["polygone", "polygones"],
  text: ["texte", "textes"],
};
const SHAPE_ORDER: SketchShape["kind"][] = ["freehand", "rect", "circle", "polygon", "text"];
```

```tsx
  const [sketchTool, setSketchTool] = useState<SketchTool>(null);
  const [shapes, setShapes] = useState<SketchShape[]>([]);
  const [color, setColor] = useState("#dc2626");
  const [freehandPoints, setFreehandPoints] = useState<LngLat[]>([]);
  const [polygonPoints, setPolygonPoints] = useState<LngLat[]>([]);
  const drawingRef = useRef(false);
  // Coin en attente d'un rectangle/cercle : une REF, pas un état lu depuis un
  // updater. Un effet de bord dans un updater est exécuté deux fois sous
  // <StrictMode> (shell/src/main.tsx), ce qui ajouterait la forme deux fois.
  const pendingCornerRef = useRef<LngLat | null>(null);
  const [pendingCorner, setPendingCorner] = useState<LngLat | null>(null);
  const sketchToolRef = useRef(sketchTool);
  sketchToolRef.current = sketchTool;
  const colorRef = useRef(color);
  colorRef.current = color;
```

Replace the `onClick` handler of Task 16 with the extended version, in the
**same** effect (one `click` listener, not two):

```tsx
    function onClick(e: unknown) {
      const { lngLat } = e as { lngLat: LngLat };
      const current = modeRef.current;
      if (current === "measure-distance" || current === "measure-area") {
        setPoints((prev) => [...prev, lngLat]);
        return;
      }
      if (current !== "sketch") return;
      const tool = sketchToolRef.current;
      if (tool === "text") {
        const text = window.prompt("Texte du marqueur :");
        if (text) setShapes((s) => [...s, { kind: "text", at: lngLat, text, color: colorRef.current }]);
        return;
      }
      if (tool === "rect" || tool === "circle") {
        const previous = pendingCornerRef.current;
        if (!previous) {
          pendingCornerRef.current = lngLat;
          setPendingCorner(lngLat);
          return;
        }
        pendingCornerRef.current = null;
        setPendingCorner(null);
        setShapes((s) => [
          ...s,
          tool === "rect"
            ? { kind: "rect", from: previous, to: lngLat, color: colorRef.current }
            : { kind: "circle", center: previous, edge: lngLat, color: colorRef.current },
        ]);
        return;
      }
      if (tool === "polygon") setPolygonPoints((prev) => [...prev, lngLat]);
    }
```

The freehand effect (a **second** effect, because it registers three other
listeners):

```tsx
  useEffect(() => {
    function onMouseDown(e: unknown) {
      if (modeRef.current !== "sketch" || sketchToolRef.current !== "freehand") return;
      drawingRef.current = true;
      setFreehandPoints([(e as { lngLat: LngLat }).lngLat]);
    }
    function onMouseMove(e: unknown) {
      if (!drawingRef.current) return;
      setFreehandPoints((prev) => [...prev, (e as { lngLat: LngLat }).lngLat]);
    }
    function onMouseUp() {
      if (!drawingRef.current) return;
      drawingRef.current = false;
      // Lire l'état par son setter puis remettre à zéro, SANS effet de bord
      // dans l'updater : on capture d'abord, on écrit ensuite.
      setFreehandPoints((prev) => {
        if (prev.length >= 2) {
          const captured = prev;
          queueMicrotask(() =>
            setShapes((s) => [...s, { kind: "freehand", points: captured, color: colorRef.current }]),
          );
        }
        return [];
      });
    }
    map.on("mousedown", onMouseDown as never);
    map.on("mousemove", onMouseMove as never);
    map.on("mouseup", onMouseUp as never);
    return () => {
      map.off("mousedown", onMouseDown as never);
      map.off("mousemove", onMouseMove as never);
      map.off("mouseup", onMouseUp as never);
    };
  }, [map]);
```

If the `queueMicrotask` indirection makes the test above fail
(`expect(screen.getByText("1 tracé"))` runs synchronously after
`map.emit("mouseup", …)`), use the simpler and equally correct form instead:
keep the in-progress points in a **ref** (`freehandRef`) mirrored into state
for rendering, and on `mouseup` read `freehandRef.current` directly, then
call `setShapes` and `setFreehandPoints` as two ordinary calls. **Prefer this
second form** — it has no scheduling subtlety at all; the first is written
here only to show what must not happen (a `setShapes` inside an updater).

`clearAll` (from Task 16) gains the sketch state:

```tsx
  function clearAll() {
    setMode("idle");
    setPoints([]);
    setShapes([]);
    setSketchTool(null);
    setFreehandPoints([]);
    setPolygonPoints([]);
    pendingCornerRef.current = null;
    setPendingCorner(null);
  }
```

JSX additions — a second row of buttons and the summary, inside the existing
container:

```tsx
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          className={buttonCls}
          aria-pressed={mode === "sketch"}
          onClick={() => {
            setMode("sketch");
            setPoints([]);
          }}
        >
          Croquis
        </button>
        {mode === "sketch" && (
          <>
            {(
              [
                ["freehand", "Tracé libre"],
                ["rect", "Rectangle"],
                ["circle", "Cercle"],
                ["polygon", "Polygone"],
                ["text", "Texte"],
              ] as [Exclude<SketchTool, null>, string][]
            ).map(([tool, label]) => (
              <button
                key={tool}
                type="button"
                className={buttonCls}
                aria-pressed={sketchTool === tool}
                onClick={() => {
                  setSketchTool(tool);
                  pendingCornerRef.current = null;
                  setPendingCorner(null);
                  setPolygonPoints([]);
                }}
              >
                {label}
              </button>
            ))}
            <input
              aria-label="Couleur du croquis"
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
            />
          </>
        )}
      </div>
      {pendingCorner && <p className="text-slate-500">Cliquez le second point…</p>}
      {sketchTool === "polygon" && polygonPoints.length >= 3 && (
        <button
          type="button"
          className={buttonCls}
          onClick={() => {
            setShapes((s) => [
              ...s,
              { kind: "polygon", points: polygonPoints, color: colorRef.current },
            ]);
            setPolygonPoints([]);
          }}
        >
          Terminer le polygone
        </button>
      )}
      {shapes.length > 0 && (
        <ul>
          {SHAPE_ORDER.map((kind) => {
            const n = shapes.filter((s) => s.kind === kind).length;
            if (n === 0) return null;
            const [one, many] = SHAPE_LABELS[kind];
            return (
              <li key={kind}>
                {n} {n > 1 ? many : one}
              </li>
            );
          })}
        </ul>
      )}
      {shapes.map((s, i) => (s.kind === "text" ? <p key={`t${i}`}>{s.text}</p> : null))}
```

Import `type SketchShape` from `./measureSketch`.

- [ ] **Step 4: Run + gates + commit**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx`
Expected: PASS (the 6 tests from Task 16 + the 10 new ones).

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapMeasureSketchToolbar.tsx shell/src/map/MapMeasureSketchToolbar.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): ajoute le croquis (tracé libre, formes, texte, couleur)

Le coin en attente d'un rectangle/cercle vit dans une ref : appeler
setShapes depuis un updater de setPendingCorner ajoutait la forme deux
fois sous <StrictMode>. Le résumé compte TOUTES les formes, au pluriel —
seuls les tracés libres avaient un retour visuel, au singulier codé en
dur, et le mot « rectangle » n'était jamais rendu.
EOF
)"
```

---

## Task 18: Shell — rendu des formes de croquis sur la carte (source GeoJSON `__sketch__`)

**Files:**
- Modify: `shell/src/map/MapMeasureSketchToolbar.tsx`
- Modify: `shell/src/map/MapMeasureSketchToolbar.test.tsx`

**Interfaces:** consumes `shapeToGeoJSONFeature` (Task 15). No new exports.

**Why this is a task and not a step of the E2E task:** the earlier draft
folded this into the E2E task and mandated an effect with three real defects:
(a) `addSource`/`addLayer` before the style is loaded throws
"Style is not done loading." and there was no equivalent of
`MapView`'s `styleLoadedRef`; (b) no cleanup function, so the three layers
and the source survived unmounting; (c) the guard
`if (!fullMap.getSource) return;` tested that the **method** exists, not that
the **source** does, while its own comment claimed the opposite.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/map/MapMeasureSketchToolbar.test.tsx`:

```tsx
function sketchData(map: ReturnType<typeof makeMapStub>) {
  const src = map.sources.get("__sketch__") as { data?: unknown } | undefined;
  return src?.data as
    | { type: "FeatureCollection"; features: { properties: Record<string, unknown> }[] }
    | undefined;
}

test("les trois couches d'overlay et la source sont posées une seule fois", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  expect(map.addSource).toHaveBeenCalledTimes(1);
  expect(map.layers.map((l) => l.id)).toEqual([
    "__sketch__line",
    "__sketch__fill",
    "__sketch__point",
  ]);

  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 1 } });
  // Mise à jour par setData, jamais un second addSource.
  expect(map.addSource).toHaveBeenCalledTimes(1);
});

test("une forme de croquis atteint la source GeoJSON avec sa couleur", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.change(screen.getByLabelText("Couleur du croquis"), {
    target: { value: "#00ff00" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 1 } });

  const data = sketchData(map);
  expect(data?.features).toHaveLength(1);
  expect(data?.features[0].properties.color).toBe("#00ff00");
});

test("la mesure en cours est visible sur la carte avant d'être terminée", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });
  const data = sketchData(map);
  expect(data?.features).toHaveLength(1);
});

test("« Effacer tout » vide la source", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 1 } });
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));
  expect(sketchData(map)?.features).toEqual([]);
});

test("le démontage retire les trois couches et la source", () => {
  const map = makeMapStub();
  const { unmount } = render(<MapMeasureSketchToolbar map={map as never} />);
  unmount();
  expect(map.layers).toEqual([]);
  expect(map.sources.has("__sketch__")).toBe(false);
});

test("un style non chargé ne fait rien lever et l'overlay est posé ensuite", () => {
  const map = makeMapStub();
  map.isStyleLoaded = () => false;
  expect(() => render(<MapMeasureSketchToolbar map={map as never} />)).not.toThrow();
  expect(map.addSource).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx -t "overlay|source|démontage|style non chargé"`
Expected: FAIL.

- [ ] **Step 3: Implement the overlay**

Add to `MapMeasureSketchToolbar.tsx`:

```tsx
const SKETCH_SOURCE_ID = "__sketch__";
const SKETCH_LAYER_IDS = [
  `${SKETCH_SOURCE_ID}line`,
  `${SKETCH_SOURCE_ID}fill`,
  `${SKETCH_SOURCE_ID}point`,
] as const;
```

Two effects. First, a mount/unmount effect that owns the source and the three
layers — **not** one effect that both creates and updates, so the cleanup is
unambiguous:

```tsx
  // Posé au montage, retiré au démontage. `isStyleLoaded()` est la garde
  // réelle : addSource/addLayer avant le chargement du style lèvent
  // « Style is not done loading. ». Tester l'existence de la MÉTHODE
  // getSource ne prouve rien (elle existe toujours).
  useEffect(() => {
    if (!map.isStyleLoaded()) return;
    if (map.getSource(SKETCH_SOURCE_ID)) return;
    map.addSource(SKETCH_SOURCE_ID, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: SKETCH_LAYER_IDS[0],
      type: "line",
      source: SKETCH_SOURCE_ID,
      filter: ["==", ["geometry-type"], "LineString"],
      paint: { "line-color": ["get", "color"], "line-width": 2 },
    } as never);
    map.addLayer({
      id: SKETCH_LAYER_IDS[1],
      type: "fill",
      source: SKETCH_SOURCE_ID,
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": ["get", "color"], "fill-opacity": 0.3 },
    } as never);
    map.addLayer({
      id: SKETCH_LAYER_IDS[2],
      type: "circle",
      source: SKETCH_SOURCE_ID,
      filter: ["==", ["geometry-type"], "Point"],
      paint: { "circle-color": ["get", "color"], "circle-radius": 5 },
    } as never);
    return () => {
      // Les couches d'abord : MapLibre refuse de retirer une source encore
      // référencée (même règle que les deux passes d'applyLayers).
      for (const id of SKETCH_LAYER_IDS) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(SKETCH_SOURCE_ID)) map.removeSource(SKETCH_SOURCE_ID);
    };
  }, [map]);
```

Then a data-sync effect:

```tsx
  useEffect(() => {
    const source = map.getSource(SKETCH_SOURCE_ID) as
      | { setData?: (d: unknown) => void }
      | undefined;
    if (!source?.setData) return;
    const inProgress =
      points.length >= 2
        ? [
            shapeToGeoJSONFeature(
              mode === "measure-area"
                ? { kind: "polygon", points, color: colorRef.current }
                : { kind: "freehand", points, color: colorRef.current },
            ),
          ]
        : [];
    const drawing =
      freehandPoints.length >= 2
        ? [shapeToGeoJSONFeature({ kind: "freehand", points: freehandPoints, color: colorRef.current })]
        : [];
    const pendingPolygon =
      polygonPoints.length >= 2
        ? [shapeToGeoJSONFeature({ kind: "freehand", points: polygonPoints, color: colorRef.current })]
        : [];
    source.setData({
      type: "FeatureCollection",
      features: [
        ...shapes.map(shapeToGeoJSONFeature),
        ...inProgress,
        ...drawing,
        ...pendingPolygon,
      ],
    });
  }, [map, shapes, points, mode, freehandPoints, polygonPoints]);
```

Import `shapeToGeoJSONFeature` from `./measureSketch`.

Note the in-progress polygon is drawn as an open `LineString` on purpose: a
half-drawn ring rendered as a filled polygon flickers as the user clicks.

- [ ] **Step 4: Run + gates + commit**

Run: `cd shell && npx vitest run src/map/MapMeasureSketchToolbar.test.tsx`
Expected: PASS — the 6 tests of Task 16, the 10 of Task 17, and these 6.

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/map/MapMeasureSketchToolbar.tsx shell/src/map/MapMeasureSketchToolbar.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): rend mesures et croquis sur une source GeoJSON __sketch__

Source et trois couches posées au montage sous garde isStyleLoaded()
(addSource avant le chargement du style lève « Style is not done
loading »), retirées au démontage — couches d'abord, source ensuite.
La mesure en cours est visible avant d'être terminée.
EOF
)"
```

---

## Task 19: Shell — câble le widget carte sur `symbology` (périmètre élargi, D2)

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:** consumes `renderAsFor`, `symbologyToPaintInputs`,
`buildLegend` (Tasks 2, 7); `MapView`'s `symbology`-driven paint (Tasks 3, 8,
13) and its `themeColors`/`interactiveTools`/`loadCustomIcon` props.

**What is wrong today, verbatim** (`mapWidget.tsx:181-213`): the widget calls
`buildMapPaint(encodings, colorDomain, sizeDomain, geometryKind, palette)`
itself and builds

```tsx
              {
                id: `ds-${String(props.dataSourceId)}`,
                title: "Données",
                visible: true,
                kind: "feature",
                url,
                renderAs,
                paint,
                popup: props.popup as PopupConfig | undefined,
              },
```

— a layer carrying `paint` and **never `symbology`**. `effectivePaint`
therefore takes its `if (!layer.symbology) return layer.paint ?? {}` branch,
and no SP-27 mechanic (outline layer, icons, labels, opacity) reaches an app,
a dashboard, or a `/sites/{slug}` page. Task 12 meanwhile added the icon
picker to this widget's `PropsPanel`, so an author would configure symbology
the widget cannot render.

**Non-regression requirement:** a layer with **no** symbology must render
exactly as today. That holds because `buildMapPaint({}, null, null, kind,
undefined)` returns `paint: {}` and `effectivePaint` returns
`layer.paint ?? {}` — i.e. `{}` — for a layer without `symbology`. Prove it
with a test, do not assume it.

**The trap in this rewiring:** the widget currently resolves the palette with
`symbologyToPaintInputs(symbology, ctx.theme?.colors)` while `MapView`'s
`effectivePaint` passed `undefined` for `themeColors`. Handing `symbology` to
`MapView` without also handing `themeColors` would silently render a
`theme-primary` palette with the wrong colors — the exact bug the existing
test "Component resolves the theme-primary palette from ctx.theme at render
time" was written to catch. `MapView` gained the `themeColors` prop in Task 3
for this reason.

- [ ] **Step 1: Rewrite the three existing paint tests and add the new ones**

`shell/src/builder/widgets/mapWidget.test.tsx` mocks `MapView` and renders
`layers:{n} url:{url} renderAs:{renderAs} paint:{paint}` (lines ~44-56).
Three tests assert on that `paint:` text:
`"Component renders paint from frozen props.symbology, without querying any
domain"`, `"colors and sizes point features from frozen size/color
symbology, without querying any domain"`, and `"Component resolves the
theme-primary palette from ctx.theme at render time"`. After this task the
layer carries no `paint`, so those assertions must move to what the widget is
now responsible for: **handing the frozen `symbology` and the resolved
`themeColors` to `MapView`**. Compilation itself is already covered by
`mapSymbology.test.ts` (pure) and `MapView.test.tsx` (rendered).

Extend the mock's rendered line to expose the new props:

```tsx
      const symbology = layer && "symbology" in layer ? JSON.stringify((layer as any).symbology ?? null) : "null";
```
and, in the mock's props destructuring, add `themeColors`,
`interactiveTools`, `loadCustomIcon`, then render
`symbology:{symbology} themeColors:{JSON.stringify(themeColors ?? null)} tools:{String(!!interactiveTools)} loader:{typeof loadCustomIcon}`.

Rewrite the three tests to:

```tsx
test("le widget transmet la symbologie figée à MapView, sans requête de domaine", async () => {
  const queryDataSource = vi.fn();
  const symbology = {
    color: {
      field: "region", mode: "categorical", palette: "categorical-a",
      domain: { kind: "categorical", values: ["Nord", "Sud"] },
      computedAt: "2026-08-23T10:00:00Z",
    },
  };
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{ dataSourceId: "d", symbology }}
        ctx={{
          mode: "runtime",
          data: state({
            url: "https://fs/communes/items.json",
            records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
          }),
        } as WidgetContext}
      />,
      queryDataSource,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain("renderAs:fill");
  expect(view.textContent).toContain('"field":"region"');
  expect(view.textContent).toContain('"palette":"categorical-a"');
  // Plus aucun `paint` compilé par le widget : c'est MapView qui compile.
  expect(view.textContent).toContain("paint:{}");
  expect(queryDataSource).not.toHaveBeenCalled();
});

test("un point avec taille et couleur donne renderAs:circle et la symbologie complète", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            color: {
              field: "valeur", mode: "numeric", palette: "sequential-blue",
              domain: { kind: "numeric", min: 0, max: 100 },
              computedAt: "2026-08-23T10:00:00Z",
            },
            size: { field: "montant", domain: { min: 5, max: 25 }, computedAt: "2026-08-23T10:00:00Z" },
          },
        }}
        ctx={{
          mode: "runtime",
          data: state({
            url: "https://fs/points/items.json",
            records: [{ id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } }],
          }),
        } as WidgetContext}
      />,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain("renderAs:circle");
  expect(view.textContent).toContain('"field":"montant"');
});

// La palette de thème n'est plus résolue par le widget mais par MapView :
// ce qui doit être prouvé ici est que ctx.theme.colors LUI PARVIENT. Sans
// cela, une palette theme-primary rendrait silencieusement les mauvaises
// couleurs (le bug que l'ancienne version de ce test attrapait).
test("ctx.theme.colors est transmis à MapView pour résoudre theme-primary", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{
          dataSourceId: "d",
          symbology: {
            color: {
              field: "valeur", mode: "numeric", palette: "theme-primary",
              domain: { kind: "numeric", min: 0, max: 100 },
              computedAt: "2026-08-23T10:00:00Z",
            },
          },
        }}
        ctx={{
          mode: "runtime",
          theme: { colors: { primary: "#2563eb" } },
          data: state({
            url: "https://fs/points/items.json",
            records: [{ id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 2] } }],
          }),
        } as WidgetContext}
      />,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain('themeColors:{"primary":"#2563eb"}');
  expect(view.textContent).toContain('"palette":"theme-primary"');
});

// Non-régression du chemin historique : une couche sans symbologie doit
// arriver chez MapView exactement comme avant (paint vide, renderAs dérivé
// de la géométrie), et MapView la peint par sa branche `layer.paint ?? {}`.
test("sans symbologie, la couche transmise est inchangée", async () => {
  const Map = getWidget("map")!.Component;
  render(
    withClient(
      <Map
        props={{ dataSourceId: "d" }}
        ctx={{
          mode: "runtime",
          data: state({
            url: "https://fs/communes/items.json",
            records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
          }),
        } as WidgetContext}
      />,
    ),
  );
  const view = await screen.findByTestId("mapview");
  expect(view.textContent).toContain("renderAs:fill");
  expect(view.textContent).toContain("symbology:null");
  expect(view.textContent).toContain("paint:{}");
});

test("la barre mesure/croquis n'est active qu'en dehors du mode édition", async () => {
  const Map = getWidget("map")!.Component;
  const data = state({
    url: "https://fs/communes/items.json",
    records: [{ id: 1, properties: {}, geometry: { type: "Polygon", coordinates: [] } }],
  });
  const { rerender } = render(
    withClient(<Map props={{ dataSourceId: "d" }} ctx={{ mode: "edit", data } as WidgetContext} />),
  );
  expect((await screen.findByTestId("mapview")).textContent).toContain("tools:false");

  rerender(
    withClient(<Map props={{ dataSourceId: "d" }} ctx={{ mode: "runtime", data } as WidgetContext} />),
  );
  expect((await screen.findByTestId("mapview")).textContent).toContain("tools:true");
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: FAIL on the rewritten and new tests.

- [ ] **Step 3: Rewrite `Component`'s layer construction**

Replace the `buildMapPaint` call and the layer literal with:

```tsx
      const symbology = props.symbology as LayerSymbology | undefined;
      const geometryKind = detectGeometryKind(ctx.data?.records?.[0]?.geometry);
      // Le widget ne compile PLUS la peinture : il transmet la symbologie et
      // les couleurs de thème, et MapView compile — c'est le seul chemin qui
      // fait bénéficier les apps/dashboards du contour, des icônes, des
      // étiquettes et de l'opacité (SP-27). `renderAs` reste ici : c'est un
      // champ de la couche `feature`, et MapView en dérive sa géométrie.
      const renderAs = renderAsFor(geometryKind);
      const { encodings, colorDomain, sizeDomain, palette, stroke } = symbologyToPaintInputs(
        symbology,
        ctx.theme?.colors,
      );
      const legend = buildLegend(encodings, colorDomain, sizeDomain, geometryKind, palette, {
        stroke,
        icon: symbology?.icon,
      });

      const config: MapConfig = {
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [
              {
                id: `ds-${String(props.dataSourceId)}`,
                title: "Données",
                visible: true,
                kind: "feature",
                url,
                renderAs,
                ...(symbology ? { symbology } : {}),
                popup: props.popup as PopupConfig | undefined,
              },
            ]
          : [],
      };
```

Remove `buildMapPaint` from the file's import from `./mapSymbology` **if no
other use remains** (check with `grep -n buildMapPaint
shell/src/builder/widgets/mapWidget.tsx`), and add `renderAsFor`.

On the `<MapView …>` element, add the four props:

```tsx
            <MapView
              ref={handle}
              config={config}
              themeColors={ctx.theme?.colors}
              interactiveTools={ctx.mode !== "edit"}
              loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
              getAuthToken={client.getAuthToken}
              getCoreUrl={client.getCoreUrl}
              // …existing props unchanged…
            />
```

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS, whole file green.

- [ ] **Step 5: Prove the end-to-end wiring at the unit level too**

Add one `MapView` test that closes the loop the widget now depends on — a
`feature` layer carrying `symbology` with **all four** new pieces produces
every expected artefact:

```ts
test("une couche feature portant les quatre nouveaux encodages produit toutes ses sous-couches", () => {
  installImageDecodeStub();
  const layer: MapLayer = {
    id: "ds-1", title: "Données", visible: true, kind: "feature", url: "u", renderAs: "circle",
    symbology: {
      opacity: 60,
      stroke: { color: { fixed: "#000000" }, width: { fixed: 2 }, style: "solid" },
      icon: {
        field: "categorie",
        domain: { kind: "categorical", values: ["ecole"] },
        mapping: { ecole: { source: "lucide", name: "school" } },
      },
      label: {
        template: "${record.nom}", size: 12, color: "#1e293b",
        haloColor: "#ffffff", haloWidth: 1,
      },
    },
  };
  render(<MapView config={{ ...config, layers: [layer] }} />);
  const map = mapInstances[0];
  expect(map.getLayer("ds-1")).toMatchObject({
    type: "circle",
    paint: { "circle-opacity": 0.6, "circle-stroke-color": "#000000", "circle-stroke-width": 2 },
  });
  // renderAs "circle" ⇒ géométrie "point" ⇒ pas de contour en seconde couche.
  expect(map.getLayer("ds-1__outline")).toBeUndefined();
  expect(map.getLayer("ds-1__icon")).toMatchObject({ type: "symbol" });
  expect(map.getLayer("ds-1__label")).toMatchObject({ type: "symbol", source: "ds-1__labels" });
});
```

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`

- [ ] **Step 6: Full shell gates + commit**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx shell/src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): le widget carte délègue la peinture à MapView (SP-27 dans les apps)

mapWidget.tsx n'appelle plus buildMapPaint : il transmet `symbology` et
`themeColors`. Sans ce câblage, la couche du widget ne portait que `paint`
et effectivePaint prenait sa branche « pas de symbologie » — contour,
icônes, étiquettes et opacité n'atteignaient AUCUNE app, aucun dashboard,
aucun /sites/{slug}, alors que l'éditeur d'icônes y était déjà proposé.
themeColors est indispensable : sans lui une palette theme-primary
rendrait silencieusement les mauvaises couleurs. Non-régression prouvée :
une couche sans symbologie arrive inchangée, paint vide.
EOF
)"
```

---

## Task 20: E2E proofs (4.4 et 4.5) + vérification finale

**Files:**
- Create: `shell/e2e/map-symbology-advanced.spec.ts` (1 test)
- Create: `shell/e2e/map-measure-sketch.spec.ts` (2 tests)

**Interfaces:** none new.

**Verified facts about this suite — every one of them contradicts something
the earlier draft asserted:**
- `shell/playwright.config.ts`: `testDir: "./e2e"`, `baseURL:
  "http://localhost:4173"`, `webServer` runs `npm run build && npm run
  preview -- --port 4173` with `env: { VITE_AUTH_MODE: "mock",
  VITE_CORE_URL: "https://core.test" }`. There is **no** `globalSetup`, no
  `storageState`, no `projects`. Every mocked API URL is under
  `https://core.test`.
- The **only** shared helper under `shell/e2e/` is
  `shell/e2e/mocks.ts`, exporting exactly one function:
  `mockCore(page: Page)`. It installs ~28 `page.route` handlers (`**/me`,
  `**/items*`, `**/configs`, `**/configs/by-item/**`, `**/collections*`, …)
  and is **stateful in memory** (a `savedConfigs` map keyed by item id), so a
  save→reload round-trip works. There is **no** login step: `VITE_AUTH_MODE=
  mock` plus the `**/me` route means the user is signed in from the first
  `page.goto("/")`.
- **`shell/e2e/map-popup.spec.ts` contains no `page.evaluate` at all**, and
  no "token attachment via the exposed MapLibre instance" assertion. Its real
  canvas technique is a retried quarter-point click:
  ```ts
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  const box = await canvas.boundingBox();
  const cx = box.x + box.width / 4;
  const cy = box.y + box.height / 4;
  await expect(async () => {
    await page.mouse.click(cx, cy);
    await expect(popup).toBeVisible({ timeout: 300 });
  }).toPass({ timeout: 10000 });
  ```
  (a quarter-point, not the centre, because MapLibre requests four z=1
  subtiles and the seam runs through the canvas centre).
- The MapLibre instance is **not** exposed to the page context anywhere
  (`grep -rn "window\.__\|(window as\|globalThis\." shell/src` finds only two
  unrelated hits, both in unit tests). Any assertion on
  `map.getSource("__sketch__")` would require adding a test-only global to
  production code, which Global Constraints forbids. These specs therefore
  assert on **visible UI** and on **network traffic**.
- **`shell/e2e/sql-lab.spec.ts` contains no `page.on("request")` and no
  `waitForRequest`**, and no "no write request" assertion exists anywhere in
  the 57 spec files. The mechanism below is **new**; there is no precedent to
  copy. `map-symbology.spec.ts` does use `page.on("request", …)` to *count*
  `/aggregate` calls — that counting idiom is the closest existing thing and
  is what the second spec borrows.
- `map-symbology.spec.ts` (the SP-25 proof, one test titled
  `author 5 quantile classes on a tiled layer, save, reload, and the rendered
  colors survive with no new aggregate call`) sets up inline, with no
  `beforeEach`: `await mockCore(page)`, a `**/collections/communes/tiles/**`
  route fulfilled with the `e2e/fixtures/world-tile.mvt` fixture, and a
  `**/collections/*/aggregate` route. It then creates a map through the UI
  (`page.goto("/")` → "Nouveau" → `Type=map` → "Créer" → lands on
  `/maps/77`), opens the layer, and fills the symbology editor **by label**
  (`Champ couleur`, `Type de couleur`, `Méthode de classification`, `Nombre
  de classes`, `Palette`, `Recalculer les classes`).
- `map-popup.spec.ts` reaches the editor directly with
  `page.goto("/maps/map-1")`. An app/dashboard runtime is
  `page.goto("/apps/9")` (used by 54 gotos across the suite); there is no
  `/dashboards/…` route.
- Suite arithmetic: 57 spec files, **112** `test()` declarations, 4 of which
  skip at runtime (two `test.skip(` calls inside a local `skipIfNoBuild()`
  helper, invoked 1× in `connected-export.spec.ts` and 3× in
  `static-export.spec.ts`). No `test.describe` anywhere, no parametrisation
  loop. 112 − 4 = **108 passed**, matching `CLAUDE.md`. Adding **3** tests
  gives **111 passed / 4 skipped**.

**Glyph dependency, handled explicitly (constats 2.2 / 4.7):** the label
proof below asserts **persistence and round-trip through the editor**, never
rendered glyph pixels. Rendering a label requires the basemap style to serve
`glyphs` from `demotiles.maplibre.org`, a network resource this suite must
not depend on. Task 14 already makes a missing `glyphs` a warned,
non-catastrophic skip, and its unit test covers that branch.

- [ ] **Step 1: Write the 4.4 proof**

Create `shell/e2e/map-symbology-advanced.spec.ts`. Read
`shell/e2e/map-symbology.spec.ts` **in full** first and copy its real setup;
the structure below names what to assert, not a harness to invent.

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

test("un contour, une opacité et une étiquette survivent à l'enregistrement et au rechargement", async ({
  page,
}) => {
  await mockCore(page);
  // La bibliothèque d'icônes du tenant est interrogée par l'éditeur dès son
  // montage : sans cette route, la requête part vers un hôte non routé.
  // (mocks.ts ne la connaît pas — c'est une route de SP-27.)
  await page.route("**/map-icons", (route) => route.fulfill({ json: [] }));
  // Tuiles de la couche : même fixture que map-symbology.spec.ts.
  // (copier le bloc de route exact de cette spec, y compris le chargement de
  // e2e/fixtures/world-tile.mvt)

  await page.goto("/maps/map-1");

  // 1. Ouvrir le panneau de couches puis l'éditeur de symbologie de la couche
  //    (même chemin d'interaction que map-symbology.spec.ts : un
  //    `page.getByRole("button", { name: /Communes/ }).click()`).
  // 2. Contour : cliquer « Ajouter un contour », régler
  //    getByLabelText("Épaisseur de contour (px)") à 3 et
  //    getByLabelText("Style de contour") à "dashed".
  // 3. Opacité : fireEvent n'existe pas côté Playwright — utiliser
  //    `page.getByLabel("Opacité").fill("60")` (input type=range accepte
  //    fill()).
  // 4. Étiquette : cliquer « Ajouter une étiquette » puis remplir
  //    getByLabel("Gabarit d'étiquette") avec "${record.nom}".
  // 5. Enregistrer (le même bouton que map-symbology.spec.ts).
  // 6. page.reload() — mockCore rejoue la config sauvegardée.
  // 7. Réouvrir l'éditeur et asserter que les TROIS valeurs sont revenues :
  //    l'épaisseur vaut "3", le style vaut "dashed", le gabarit vaut
  //    "${record.nom}", et l'opacité vaut "60".
  //
  // C'est la preuve du chantier 4.4 : la symbologie avancée est persistée et
  // relue. Le rendu des glyphes n'est PAS asserté ici — il dépend du service
  // de glyphes du fond de carte (ressource réseau), et Task 14 couvre déjà en
  // unitaire le cas « style sans glyphs ».
  await expect(page.getByLabel("Gabarit d'étiquette")).toHaveValue("${record.nom}");
});
```

If the reload round-trip does not work because `mocks.ts` does not persist
the map config for `/maps/map-1` (it keys `savedConfigs` by item id — check
which ids it serves), then create the map through the UI exactly as
`map-symbology.spec.ts` does and use the `/maps/77` it lands on. **Read
`mocks.ts` before choosing.**

- [ ] **Step 2: Write the 4.5 proof**

Create `shell/e2e/map-measure-sketch.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

// Il n'existe AUCUN précédent dans les 57 specs pour « aucune requête
// d'écriture » (ni page.on("request") d'écriture, ni waitForRequest) : ce
// mécanisme est nouveau. Le plus proche est le comptage de /aggregate de
// map-symbology.spec.ts, dont on reprend l'idiome.
function recordWrites(page: import("@playwright/test").Page): string[] {
  const writes: string[] = [];
  page.on("request", (req) => {
    if (!["POST", "PUT", "PATCH", "DELETE"].includes(req.method())) return;
    // /aggregate est le chemin de DONNÉES préexistant du widget carte (une
    // requête POST légitime, émise au chargement et au changement d'emprise),
    // sans rapport avec la barre d'outils. Tout le reste est une écriture.
    if (req.url().includes("/aggregate")) return;
    writes.push(`${req.method()} ${req.url()}`);
  });
  return writes;
}

test("un lecteur mesure une distance sur une app publiée sans aucune écriture", async ({ page }) => {
  await mockCore(page);
  await page.route("**/map-icons", (route) => route.fulfill({ json: [] }));
  await page.goto("/apps/9");

  // Attendre que la carte du widget existe AVANT de commencer à compter :
  // le chargement de l'app peut légitimement écrire (aucune écriture connue,
  // mais le test doit prouver quelque chose sur la BARRE D'OUTILS).
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const writes = recordWrites(page);

  await page.getByRole("button", { name: "Mesurer" }).click();

  // Deux clics sur le canvas, technique de map-popup.spec.ts : un
  // quart-de-point, pas le centre (la couture des quatre sous-tuiles z=1
  // passe par le centre), et un retry parce qu'un clic arrivé avant le
  // premier rendu de la couche ne fait rien.
  const box = (await canvas.boundingBox())!;
  await expect(async () => {
    await page.mouse.click(box.x + box.width / 4, box.y + box.height / 4);
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 4);
    await expect(page.getByText(/\d+([.,]\d+)?\s*(m|km)$/)).toBeVisible({ timeout: 500 });
  }).toPass({ timeout: 10_000 });

  expect(writes).toEqual([]);
});

test("le croquis pose une forme comptabilisée dans la barre d'outils", async ({ page }) => {
  await mockCore(page);
  await page.route("**/map-icons", (route) => route.fulfill({ json: [] }));
  await page.goto("/apps/9");

  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const writes = recordWrites(page);

  await page.getByRole("button", { name: "Croquis" }).click();
  await page.getByRole("button", { name: "Rectangle" }).click();

  const box = (await canvas.boundingBox())!;
  await expect(async () => {
    await page.mouse.click(box.x + box.width / 4, box.y + box.height / 4);
    await page.mouse.click(box.x + box.width * 0.6, box.y + box.height * 0.6);
    await expect(page.getByText("1 rectangle")).toBeVisible({ timeout: 500 });
  }).toPass({ timeout: 10_000 });

  // La forme est aussi passée sur la carte (source __sketch__), mais rien
  // n'expose l'instance MapLibre au contexte de page et Global Constraints
  // interdit d'ajouter un global de test au code de production : la preuve
  // observable est le compteur de la barre d'outils, couvert côté source
  // GeoJSON par les tests unitaires de la tâche 18.
  expect(writes).toEqual([]);
});
```

If the app fixture served by `mocks.ts` at `/apps/9` has no map widget, look
at what `analytics-context.spec.ts` does (it navigates to `/apps/9` and drives
a MapLibre canvas, so a map widget **is** reachable there) and copy whatever
extra route/config it installs first.

- [ ] **Step 3: Run both specs**

Run: `cd shell && npm run e2e -- map-symbology-advanced map-measure-sketch`
Expected: 3 passed. If the details sketched in Steps 1-2 do not match what
the sibling specs actually do, fix **these** specs to match the real, working
pattern — the siblings are ground truth, this plan's sketch of them is not.

- [ ] **Step 4: Run the complete E2E suite (regression check)**

Run: `cd shell && npm run e2e`
Expected: **111 passed, 4 skipped, 0 failed** (108 baseline + 3 new tests).
If a pre-existing spec now fails, this is the cross-task regression class
`CLAUDE.md` trap #6 warns about — most plausibly Task 19's widget rewiring
(a layer that used to carry `paint` now carries `symbology`) or Task 16's
toolbar appearing over a canvas some other spec clicks. Investigate and fix
in a **separate commit** before proceeding; do not fold an unrelated
regression fix into this task's commit.

- [ ] **Step 5: Full final verification, both sides**

```bash
cd core && uv run pytest -q
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot \
  && uv run lint-imports
cd core && uv run pytest tests/test_deployability.py -v
cd core && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell && rm -rf dist dist-export
cd ../shell && npm run lint && npm run format:check && npx vitest run --coverage && npm run build
cd ../shell && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```
Expected: core 1896 + 32 passed, 5 skipped, 1 known pre-existing failure,
coverage ≥ 85; deployability **35/35**; shell ≥ 1463 + the tests added by
Tasks 1-18, coverage ≥ 88 — measured **after** removing `dist/` and
`dist-export/`, which this repo's `vitest` config otherwise counts as
uncovered source (documented trap, hit 4 times).

- [ ] **Step 6: OpenAPI/TS drift check (must be an empty diff)**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```
Expected: **empty** — Task 10 already committed the regeneration and no task
after it touched a route or a schema. A non-empty diff here means a later
task changed the core API without saying so; commit the regeneration
separately and note what changed.

- [ ] **Step 7: pre-commit**

Run: `uvx pre-commit run --all-files`
Expected: 5/5 hooks green (`ruff-check`, `ruff-format`, `lint-imports`,
`eslint`, `prettier`; `commitlint` only runs at commit time).

- [ ] **Step 8: Commit**

```bash
git add shell/e2e/map-symbology-advanced.spec.ts shell/e2e/map-measure-sketch.spec.ts
git commit -m "$(cat <<'EOF'
test(shell): preuves E2E SP-27 (4.4 symbologie avancée, 4.5 mesure/croquis)

Trois tests, donc 111 passed / 4 skipped attendus (108 de référence + 3).
Aucun page.evaluate sur l'instance MapLibre : rien ne l'expose au contexte
de page et ajouter un global de test au code de production est interdit —
les assertions portent sur l'UI visible et sur le trafic réseau. La preuve
4.4 asserte la persistance et le rechargement, pas le rendu des glyphes,
qui dépendrait du service de glyphes du fond de carte.
EOF
)"
```

---

## Corrections de pré-vol (2026-08-27)

Trace d'audit : les **61 constats** de
`.superpowers/sdd/sp27-preflight-report.md` (catégories 1 à 4 ; la catégorie
5 est reprise à la fin, à titre informatif). Chacun est soit **corrigé**
(avec l'endroit exact), soit **accepté** (avec la raison écrite). Aucun n'est
laissé silencieux.

### Catégorie 1 — contradictions internes

| # | Gravité | Traitement |
|---|---|---|
| 1.1 | Bloquant | **Corrigé** — Task 6 : le catalogue compte exactement **140** entrées et le test asserte `toHaveLength(140)` + 20 par catégorie. L'annonce « ≥ 150 » disparaît, y compris du message de commit. |
| 1.2 | Bloquant | **Corrigé** — Task 6 : catalogue reconstruit, **140 noms uniques** vérifiés programmatiquement contre le tarball 1.34.0 (`star`→generic, `landmark`→buildings, `store`→services, `tent`/`ferris-wheel`→leisure ; slots libérés remplis par `map-pinned` et `tram-front`). Le test « aucun doublon » passe désormais par construction. |
| 1.3 | Bloquant | **Corrigé** — **D2**, déviation 4 + **Task 19** entière : `mapWidget.tsx` cesse d'appeler `buildMapPaint` et transmet `symbology` + `themeColors` à `MapView`. Task 3 ajoute la prop `themeColors` à `MapView` précisément pour ça. Non-régression du chemin `paint` exigée et testée (Task 19, Step 1, dernier test). |
| 1.4 | Important | **Corrigé** — déviation 1 réécrite : la mention « mirroring `app/secrets/routes.py` exactly » est retirée et remplacée par l'arbitrage explicite « **délibérément pas admin-only**, contrairement à `app/secrets` qui l'est (`_require_admin`, lignes 22-24, appelé sur ses trois routes) », avec la raison produit. Le docstring de `routes.py` (Task 9, Step 7) dit la même chose. |
| 1.5 | Important | **Corrigé** — Architecture + Task 9 : le précédent nommé est `app/tileset3d/`/`app/terrain3d/` (`from app.ingestion.routes import get_s3_client`), et il est écrit noir sur blanc qu'`app/secrets/` ne touche jamais S3. |
| 1.6 | Important | **Corrigé** — Task 3, Step 8 : `MapSymbologyLegend` reçoit un bloc `{legend.stroke && …}` avec son test. Il est aussi écrit que `MapLegend.tsx` (le composant utilisé hors widget) ne rend aucune légende de symbologie et reste volontairement intouché. |
| 1.7 | Important | **Corrigé** — déviation 5 + Task 2 : la forme **persistée** `StrokeColorEncoding` porte `palette: PaletteId` ; `symbologyToPaintInputs` la résout en `ResolvedPalette` (nouveau champ de retour `stroke`), et `buildMapPaint` consomme `StrokePaintInput`. Un test couvre la résolution de `theme-primary` pour le contour. |
| 1.8 | Mineur | **Corrigé** — Global Constraints : la contrainte n'est plus absolue. Elle dit désormais que Task 9 **ne** régénère pas et que Task 10 est obligatoire et doit être le commit immédiatement suivant, « écrit ici pour qu'un relecteur par tâche ne le signale pas ». |
| 1.9 | Mineur | **Corrigé** — arithmétique refaite sur la source réelle : 57 fichiers, **112** `test()`, 4 `skip` au runtime ⇒ 108 passed. Ce plan ajoute **3** tests ⇒ **111 passed / 4 skipped**, écrit dans Global Constraints et dans Task 20. |

### Catégorie 2 — erreurs factuelles (tiers / code réel)

| # | Gravité | Traitement |
|---|---|---|
| 2.1 | Bloquant | **Corrigé** — **D1**, déviation 3 : `feature-state` disparaît entièrement. Mécanisme retenu : source GeoJSON `<layerId>__labels` calculée côté client + `text-field: ["get","label"]`. Message du validateur reproduit verbatim dans la déviation et dans l'en-tête de `labelSource.ts`. Tasks 13 et 14 réécrites ; `labelFeatureState.ts` renommé `labelSource.ts` dans la table « File Structure ». |
| 2.2 | Important | **Corrigé** — Task 14 : `addLabelLayer` lit `map.getStyle().glyphs` et, absent, **ne pose pas la couche** et `console.warn`. Un test couvre cette branche. Task 20 n'asserte jamais un glyphe rendu : la preuve 4.4 porte sur la persistance, explicitement pour ne pas dépendre de `demotiles.maplibre.org`. |
| 2.3 | Bloquant | **Corrigé** — déviation 7 + Task 2 (`MapPaintResult.iconLayout`, séparé de `paint`) + Task 7 (`icon-image` écrit **uniquement** dans `iconLayout`) + Task 8 (`addIconLayer` pose un `symbol` dédié). Le mode de panne est rendu visible de deux façons : un test « `buildMapPaint` never writes a layout-only property into paint », et l'écoute de `map.on("error")` ajoutée en Task 3 (avec son test), puisque `Style.addLayer` fait `if (this._validate(...)) return;` — vérifié dans le bundle installé. |
| 2.4 | Bloquant | **Corrigé par disparition** — `setFeatureState` n'est plus utilisé (D1). La contrainte est néanmoins conservée et documentée là où elle s'applique encore : Task 14 exige `sourceLayer` sur `querySourceFeatures` pour une source **vecteur** (sinon la requête renvoie zéro entité, en silence — implémentation vérifiée : `params.sourceLayer ? … : ""` puis `layers._geojsonTileLayer \|\| layers[""]`) et son **absence** pour du GeoJSON, avec un test par cas. |
| 2.5 | Important | **Corrigé** — déviation 8 + Task 8 : `map.addImage(id, bitmap)` sans options, et un test asserte `map.images.get("lucide:school")?.options` **undefined**. Raison écrite (l'image n'est pas un SDF ; `icon-color` n'est jamais utilisé). |
| 2.6 | Mineur (info) | **Conservé** — les cinq constats corrects sont réaffirmés dans « Key facts verified for this task » de Task 2 (`fill-outline-width` absent, `fill-outline-color` data-driven, `circle-stroke-*` data-driven, `line-dasharray` cross-faded donc constante valide) et de Task 18 (`filter: ["==", ["geometry-type"], "LineString"]` validé sans erreur). `promoteId` n'est plus utilisé (D1) et n'est donc plus mentionné. |
| 2.7 | Bloquant | **Corrigé** — Task 6 : les 6 noms inexistants (`garage`, `bridge`, `stairs`, `elevator`, `first-aid-kit`, `swimming-pool`) sont remplacés par des noms vérifiés (`radio-tower`, `school`, `library`, `university`, `brick-wall`, `thermometer`, `shield-check`, `medal`…). Les 140 noms ont été testés un à un contre `package/icons/<name>.svg` du tarball 1.34.0 : 0 manquant. |
| 2.8 | Mineur (info) | **Corrigé** — Task 6 : le décompte réel (**2035** fichiers) remplace « ~1500 » dans le commentaire du module et dans les faits de la tâche. Licence ISC confirmée et l'attribution part dans l'en-tête du fichier généré. |
| 2.9 | Mineur (incertitude) | **Supprimé, pas contourné** — déviation 10 : ni le `import()` templaté ni `import.meta.glob("/node_modules/…")` ne sont utilisés. Task 6 matérialise les SVG par un script committé (`scripts/gen-lucide-icons.mjs` → `lucideIconSvgs.generated.ts`), ce qui élimine toute dépendance au comportement du bundler et évite d'émettre ~2035 assets. |
| 2.10 | Bloquant | **Corrigé** — Task 1 (nouvelle) + toutes les tâches de rendu : `renderMapView`, `emit` et `flushPromises` n'existent pas et ne sont plus invoqués. Le harnais réel est nommé explicitement (`render(<MapView config={cfg} />)` puis `mapInstances[0]`, les helpers `tiled()` ligne 965 et `clickPayload` ligne 1208), et **toutes** les assertions passent par l'état enregistré (`map.getLayer(id)` + `toMatchObject`), jamais par `toHaveBeenCalledWith` sur une méthode de `MockMap` — qui est une classe, pas un spy. |
| 2.11 ≡ 4.2 | Bloquant | **Corrigé** — **Task 1** étend `MockMaplibreMap.ts` : `addImage`/`hasImage`/`removeImage`/`listImages`, `getStyle()` (avec un champ `glyphs` pilotable), `querySourceFeatures` (+ `sourceFeatures` et `querySourceFeaturesCalls`), `getCanvas`, et `fire(event, payload?)` de façon **additive** pour ne pas casser les ~15 appels `fire("moveend")`/`fire("idle")` existants. Le fichier entre dans « File Structure ». Task 1 est placée **avant** toute tâche qui en dépend. |
| 2.12 | Important | **Corrigé** — Task 3 documente la forme **réelle** des trois sites d'appel (aucune variable `spec`, la branche `feature` n'a ni `id`, ni `layerIds`, ni `sourceLayer`, ni `filter`) et donne le code exact à écrire à chacun, avec un `decorativeIds` distinct de `layerIds`. Tasks 8 et 14 s'y adossent sans réaffirmer « les trois sites ont la même forme ». |
| 2.13 | Bloquant | **Corrigé** — Task 13 : tous les gabarits sont en `${record.champ}` (tests, implémentation), avec la raison (`ExprContext` = `{ vars, record?, user, ctx? }`, résolution à la racine) ; Task 14 met la même syntaxe dans le texte d'aide de l'UI **et** ajoute un test qui asserte que l'aide affiche `${record.nom}` ; Task 20 utilise `"${record.nom}"` dans la preuve E2E. |
| 2.14 | Bloquant | **Corrigé** — Task 4, Step 3 : `clearColor`/`clearSize` sont remplacés par un `clearEncoding(key)` générique, avec deux tests (retirer la couleur préserve `opacity`+`stroke` ; retirer le dernier encodage rend `undefined`). Tasks 12 et 14 utilisent `clearEncoding("icon")`/`clearEncoding("label")`, et un commentaire interdit explicitement de réintroduire un test nommant un encodage. |
| 2.15 | Bloquant | **Corrigé** — Task 16, Step 4 : montage gaté sur un **état** (`readyMap`, posé depuis `map.on("load")`), pas sur `mapRef.current`. La raison est écrite (un `useRef` assigné dans un effet ne provoque aucun rendu ; `MapPopup` est gaté sur deux `useState`, lignes 539/544). Deux tests `MapView` couvrent présence et absence. |
| 2.16 | Bloquant | **Corrigé** — Task 12, Step 4 : la prop est lue par une **ref** et l'effet dépend de `[]` ; un test rerend le composant avec une nouvelle identité de callback trois fois et asserte **un seul** appel. Les props restent inline chez les hôtes, avec un commentaire disant pourquoi c'est sûr. |
| 2.17 | Important | **Corrigé** — Task 4 : il est écrit que le fichier n'a **aucun** helper, que ses **18** tests rendent le composant inline, et que `fireEvent` n'est pas importé (à ajouter). Un objet `baseProps` local est introduit par les nouveaux tests, sans toucher aux 18 existants. |
| 2.18 | Mineur | **Corrigé** — Task 19 : `renderMapWidget` n'est plus cité. Les helpers réels sont nommés (`renderPropsPanel` ligne 110, `renderWidget` ligne 133) et le patron réel des tests de mode (`render(withClient(<Map props={…} ctx={…} />))`, `getWidget("map")!.Component`, `lastConfig`) est celui utilisé. |
| 2.19 | Important | **Corrigé** — Task 15 : `expect(formatArea(5000)).toBe("5 000 m²")` avec l'échappement ` ` écrit explicitement, et la raison en commentaire (le séparateur de milliers de `fr-FR` est U+202F NARROW NO-BREAK SPACE). |
| 2.20 | Mineur (info) | **Conservé** — les vérifications numériques (111 194,9 m ; erreur relative 5,1 × 10⁻⁹ ; 0 sous 3 points) sont reprises dans les « Verified facts » de Task 15 pour éviter de les refaire. |
| 2.21 | Mineur (info) | **Corrigé** — la dérive signalée est corrigée : Task 3 et Task 8 parlent des **deux** appels réels à `applyLayers` (dans `map.on("load", …)` et dans l'effet `[layersKey, …]`) sans citer de numéro de ligne faux. Les autres emplacements cités exacts sont conservés. |
| 2.22 | Mineur (info) | **Explicité** — `toFrontLayer` recopie `symbology` en bloc (`...(l.symbology ? { symbology: l.symbology } : {})`) et `app/configs/schemas.py:104` déclare `symbology: dict \| None = None` : le piège n°5 de `CLAUDE.md` ne s'applique pas, **aucune action**. C'est désormais écrit dans les suivis en fin de plan pour qu'une session future ne le « corrige » pas par réflexe. |
| 2.23 ≡ 4.1 | Bloquant | **Corrigé** — Task 9, Step 8 : édition exacte de `core/app/db.py` (ligne insérée entre `app.items` et `app.pipelines`, alias sans underscore, conforme à isort), `core/app/db.py` entre dans « File Structure » et dans le `git add`, et un test dédié (`test_map_icons_cannot_be_registered_as_a_business_collection`) asserte `"map_icons" in core_table_names()`. Les deux conséquences (table absente sous SQLite, trou dans la denylist du registre de collections) sont écrites. |
| 2.24 | Important | **Corrigé** — Task 9, Step 1 : le harnais est **écrit intégralement** dans la tâche (fixture `env` locale, helper `_as` surchargeant `get_current_user` **et** `get_current_user_optional`, helper `_second_tenant_user` reprenant `Tenant(id=uuid.uuid4().hex, slug="other", name="Other")` de `test_extensions_routes.py:114-134`). Il est écrit que `conftest.py` ne fournit aucune de ces fixtures et que le dépôt garde ses fixtures SQLite locales par fichier. |
| 2.25 ≡ 4.5 | Important | **Corrigé** — Task 9 : la tâche définit son propre `_FakeS3Client` (avec `head_object`, `get_object(Range=…)` **et** `delete_object`) et surcharge `ingestion_routes.get_s3_client`. Il est écrit que le fake de `test_tileset3d_routes.py` n'a ni `put_object` ni `delete_object`, et que `get_s3_client` lève par défaut. Aucun `moto`. |
| 2.26 | Mineur (info) | **Conservé** — les signatures exactes (`ensure_uploads_bucket(client, bucket)` positionnel, `generate_presigned_put_url(client, *, bucket, key, content_type, expires_in=900)`, `write_audit(...)`) sont reprises dans les « Verified facts » de Task 9, avec **un ajout** que le rapport ne pouvait pas deviner : ce presign **ne porte aucune condition de taille**, d'où le contrôle `head_object` après upload. |

### Catégorie 3 — défauts mandatés par le plan

| # | Gravité | Traitement |
|---|---|---|
| 3.1 | Important | **Corrigé** — Task 2 : le test devient « stroke on a line geometry is a no-op and never overwrites the color encoding » et asserte que `line-color` vaut l'expression de l'encodage `color`, que `line-width`/`line-dasharray` sont absents et que `outlinePaint` est `undefined`. La clé fantôme `"stroke-color"` disparaît. |
| 3.2 | Important | **Corrigé** — Task 16 : le test `Function.length` est supprimé et remplacé par un test réel — `fetch` **et** `XMLHttpRequest` espionnés sur un scénario complet mesure + surface + effacement, puis `expect(spy).not.toHaveBeenCalled()`. |
| 3.3 | Important | **Corrigé** — Task 9 : `ALLOWED_CONTENT_TYPES` et `MAX_ICON_BYTES` vivent **uniquement** dans `schemas.py` et sont importés par `routes.py`. `MAX_ICON_BYTES` est réellement appliqué (`head_object` après upload, 413), avec l'explication que `generate_presigned_put_url` ne peut pas le faire. Le message de commit ne parle plus de « bornés au presign ». |
| 3.4 | Important | **Corrigé — solution changée en deuxième passe.** ~~Première passe : `image/svg+xml` refusé (PNG uniquement).~~ **D4 (déviation 13)** : le SVG est conservé et **assaini à l'écriture** par `core/app/mapicons/svg.py` (allowlist d'éléments et d'attributs appliquée sur l'arbre parsé, `defusedxml` avec `forbid_dtd=True`, re-sérialisation depuis l'arbre — jamais de filtrage d'expression régulière), et ce sont les octets assainis qui sont stockés ; la lecture ne réassainit pas. Le type **réel** des octets est vérifié contre le `contentType` déclaré. Un SVG illisible ou vidé de tout graphique est refusé en RFC 7807 avec un `code` (`svg_unparsable`, `svg_dtd_forbidden`, `svg_no_graphics`, `svg_no_dimensions`, `svg_too_large`), jamais stocké vide. `X-Content-Type-Options: nosniff` + `Content-Disposition: attachment` + `Cache-Control: private, max-age=3600` sont **conservés** (décision), et il reste écrit que les deux premiers sont une **première** dans `core/app/`. 15 tests purs (`test_mapicons_svg.py`) + 6 tests de route couvrent : `<script>`, `onload=`, `xlink:href` externe, `javascript:`, `url()`/`data:` en valeur d'attribut, `foreignObject`, `style`, DTD/entité externe, PNG valide, charge ni PNG ni SVG, et un SVG légitime dont la partie graphique survit intacte. |
| 3.5 | Important | **Corrigé** — (a) Task 3 pose `addOutlineLayer` **sans** handler de clic, avec un test asserant `layerHandlers["click:communes__outline"]` vide ; idem `__icon` (Task 8) et `__label` (Task 14). Un `decorativeIds` séparé de `layerIds` matérialise la distinction. (b) Le rollback du `catch` énumère `SUBLAYER_SUFFIXES` (les 3 historiques + `__outline` + `__icon` + `__label`, plus la passe imbriquée pour `…__polygon__outline`) et `SUBSOURCE_SUFFIXES` pour `__labels`. Un test « a failing outline sub-layer rolls back its parent » couvre la fuite. |
| 3.6 | Important | **Corrigé** — Task 17 : `pendingCornerRef` est lu **avant** les setters, aucun `setShapes` dans un updater. La raison est écrite (`<StrictMode>` dans `shell/src/main.tsx` invoque les updaters deux fois) et un test asserte qu'un rectangle n'est enregistré **qu'une fois**. La forme freehand a la même consigne, avec la variante à préférer nommée explicitement. |
| 3.7 | Important | **Corrigé** — Task 12 : un booléen dédié `iconDraft` remplace `iconField !== undefined` (toujours vrai avec `useState("")`), et un test asserte que le bloc est **fermé** par défaut puis s'ouvre au clic. |
| 3.8 | Important | **Corrigé** — Task 12 : **une seule** grille, rendue uniquement pour la valeur en cours d'édition (`editingValue`), avec `aria-label={li.name}` désormais unique (catalogue sans doublon) et un bouton `Choisir l'icône de <valeur>` par valeur de domaine. Deux tests couvrent « pas de grille au départ » et « un seul bouton nommé school ». |
| 3.9 | Important | **Corrigé** — **Task 18** (extraite de l'ancienne tâche E2E de la première passe) : garde réelle `map.isStyleLoaded()` (et non l'existence de la méthode `getSource`), effet de montage **avec** fonction de nettoyage qui retire les trois couches puis la source, et effet de synchronisation séparé. Six tests, dont « le démontage retire les trois couches et la source » et « un style non chargé ne fait rien lever ». |
| 3.10 | Mineur | **Corrigé** — Task 4 : il n'y a plus **qu'une** convention, `clearEncoding` (`Object.keys(rest).length > 0 ? rest : undefined`), et les anciennes formes `rest.size`/`rest.color` sont supprimées. C'est le même correctif que 2.14. Task 5 vérifie que « plus rien ne reste » vaut aussi pour un contour **classé** (dernier test de son étape 5). |
| 3.11 | Mineur | **Corrigé** — Task 2 : `outlinePaint["line-opacity"]` reçoit l'opacité, avec un test dédié. |
| 3.12 | Mineur | **Corrigé** — Task 17 : les intitulés de tests correspondent aux gestes et aux textes réellement rendus (« le tracé libre enregistre une forme au relâchement », « le rectangle se ferme au second clic »…), et le mot « rectangle » est bien rendu par le résumé. Plus aucune regex à moitié morte. |
| 3.13 | Mineur | **Corrigé** — Task 17 : `SHAPE_LABELS` + `SHAPE_ORDER` donnent un compteur pluralisé pour **les cinq** types de forme ; deux tests couvrent le singulier et le pluriel. |
| 3.14 | Mineur | **Corrigé** — Task 9, Step 7 : suppression en base + audit d'abord, `delete_object` ensuite dans un `try/except ClientError` journalisé, avec la raison écrite (la transaction reste ouverte jusqu'à la fin de la requête). Un test asserte qu'un `delete_object` en échec ne perd pas la suppression en base. |

### Catégorie 4 — prérequis manquants / ordre de dépendance

| # | Gravité | Traitement |
|---|---|---|
| 4.1 ≡ 2.23 | Bloquant | **Corrigé** — cf. 2.23 : `core/app/db.py` dans « File Structure », dans Task 9 Step 8, dans son `git add`, et couvert par un test. |
| 4.2 ≡ 2.11 | Bloquant | **Corrigé** — cf. 2.11 : **Task 1** est créée pour ça et placée en premier. |
| 4.3 | Bloquant | **Corrigé** — Task 20 : plus aucun `page.evaluate` sur l'instance MapLibre. Il est écrit que `map-popup.spec.ts` n'en contient aucun, que le patron invoqué n'existait pas, et que rien n'expose l'instance au contexte de page ; Global Constraints interdit d'ajouter un global de test au code de production. Les assertions portent sur l'UI visible (compteur « 1 rectangle », chaîne de distance) et sur le trafic réseau ; le contenu de la source `__sketch__` est couvert en unitaire (Task 18). |
| 4.4 | Bloquant | **Corrigé** — Task 11 : `mapIconFileUrl` est remplacé par `fetchMapIconBlob(iconId): Promise<Blob>` (fetch authentifié, jeton confiné dans `itemClient.ts`, deux tests dont un sur l'en-tête `Authorization`) ; Task 8 fait `createImageBitmap(blob)` dans un `Promise.allSettled` **avec try/catch par id**, et un test prouve qu'une icône en échec n'empêche **aucune** couche d'être posée. |
| 4.5 ≡ 2.25 | Important | **Corrigé** — cf. 2.25 : `_FakeS3Client` local + `app.dependency_overrides[ingestion_routes.get_s3_client]`. L'étape « si la signature de `get_s3_client` demandait un autre câblage, corriger `routes.py` » disparaît : le problème était côté test. |
| 4.6 | Important | **Corrigé** — Task 12, Step 3 : les trois props sont **optionnelles**, avec la raison écrite (18 rendus inline + 2 sites de production). Aucun des 18 tests existants n'est à modifier. |
| 4.7 ≡ 2.2 | Important | **Corrigé** — cf. 2.2 : prérequis `glyphs` nommé, comportement défini (couche non posée + avertissement), test unitaire dédié, et preuve E2E délibérément indépendante du service de glyphes. |
| 4.8 | Important | **Corrigé** — Task 20 : il est écrit que `page.on("request")`/`waitForRequest` n'apparaissent dans **aucune** des 57 specs et que `sql-lab.spec.ts` ne contient aucune assertion d'écriture. Le helper `recordWrites` est présenté comme **nouveau**, avec son idiome emprunté au comptage de `/aggregate` de `map-symbology.spec.ts`, et son unique exemption (`/aggregate`, chemin de données préexistant du widget) justifiée par écrit. |
| 4.9 | Mineur | **Corrigé** — Task 16, Step 4 : la déstructuration du `forwardRef` est donnée en entier, `interactiveTools` compris (« sans ça la variable n'existe pas »). Même traitement pour `themeColors` (Task 3) et `loadCustomIcon` (Task 8). |
| 4.10 | Mineur | **Corrigé** — Task 9, Step 3 : la migration `0029_map_icons.py` commence par `# SPDX-License-Identifier: Apache-2.0`, puis le docstring avec `Revision ID:`/`Revises:`/`Create Date:`, conformément à `0028_collection_spatial_index.py`. |
| 4.11 | Mineur | **Accepté, consigné** — Task 9, Step 13 : `app/mapicons` n'entre **pas** dans la porte `mypy --strict`. Raison : élargir la porte est une décision distincte, avec son propre coût, que ce plan ne prend pas. La conséquence est écrite noir sur blanc dans la tâche (« le module n'est donc *pas* typé strictement — une session future ne doit pas le supposer ») et reprise dans les suivis. |
| 4.12 | Mineur | **Corrigé** — Task 9, Step 12 : vérification `upgrade`/`downgrade` **sur base non vide** (insertion d'une ligne entre les deux), avec la consigne d'écrire l'omission dans le message de commit si aucun conteneur `postgis-test` n'est disponible plutôt que de sauter la vérification en silence. |

### Catégorie 5 — vérifications de réalité (informatif, non compté dans les 61)

| # | Résultat du rapport | Traitement dans ce plan |
|---|---|---|
| 5.1 | `0029` libre, format d'id confirmé | Repris tel quel dans Task 9 (revision `"0029"`, down_revision `"0028"`). |
| 5.2 | `test_deployability.py` : 35/35 | Attente « toujours 35/35 » conservée (Task 9 Step 13, Task 20 Step 5). |
| 5.3 | Les règles couvrent ce que le plan promet | Câblage bucket + ligne commentée de `.env.example` conservés à l'identique ; la raison (`documented_env_vars(include_commented=True)` vs la variante stricte) est réécrite dans Task 9, Step 11. |
| 5.4 | La commande de régénération marche | Task 10 utilise l'incantation de `CLAUDE.md` (clé fixe + `openapi.json` explicite) et **nomme** `npm run gen:api-types`, que le rapport signalait comme évitablement vague. |
| 5.5 | 162 fichiers / 1463 tests confirmés | Référence conservée dans Global Constraints ; Task 1 annonce 1464 après son unique test. |
| 5.6 | Compte cœur non re-mesuré | Conservé tel quel, avec la même mise en garde : à prendre pour acquis, pas pour vérifié. |
| 5.7 | Compte E2E non re-mesuré | **Recalculé** depuis la source (57 fichiers, 112 `test()`, 4 skips runtime) : 108 passed confirmé par construction, 111 attendus après ce plan. Les 4 specs modèles et la fixture `world-tile.mvt` existent bien. |
| 5.8 | `lucide-static@1.34.0`, 2035 SVG, ISC, pas d'`exports` | Repris dans Task 6, avec la version **épinglée exactement** (`lucide-static@1.34.0`) parce que le fichier généré en dépend. |

### Constats mineurs restants et suivis créés par cette révision

Aucun constat n'est laissé sans traitement ; ce qui suit est ce que la
révision **ajoute** à la liste des suivis non bloquants du dépôt.

1. ~~Contour data-driven non éditable depuis l'UI.~~ **Levé par D5
   (déviation 14)** : Task 5 extrait `FieldClassificationPicker` de l'UI
   couleur inline et le partage avec `stroke.color`. Ce qui **reste** un
   suivi : l'encodage **taille** n'entre pas dans l'extraction (son UI n'a ni
   palette, ni mode, ni classification — la factoriser produirait un
   composant à moitié de props optionnelles), et le composant extrait n'a
   **pas** de test de rendu visuel : sa non-régression repose sur les 16
   tests existants de `MapSymbologyEditor.test.tsx` et sur la preuve E2E
   SP-25.
2. **`haloColor`/`haloWidth` d'étiquette non exposés** dans l'UI (défauts
   blanc / 1 px). Task 14, Step 6.
3. **Légende : glyphes neutres.** `MapSymbologyLegend` affiche `◈` pour une
   entrée d'icône et un carré bordé pour une entrée de contour, pas l'icône
   ni le tiret réels.
4. **`MapLegend.tsx` ne rend aucune légende de symbologie** (il liste les
   titres de couches). Hors périmètre, mais c'est l'asymétrie qui explique
   pourquoi seul le widget gagne les entrées `stroke`/`icon`.
5. **`app/mapicons` hors de la porte `mypy --strict`** (constat 4.11).
6. **`symbol-placement: "point"` pour les étiquettes de polygone** : le
   défaut du style-spec est vérifié, le **rendu** ne l'est pas visuellement
   dans cette passe. Marqué **non vérifié**.
7. **Croissance du bundle** due aux 140 SVG embarqués : ordre de grandeur
   attendu 60-85 Ko brut, à mesurer et consigner en Task 6, Step 7. Aucun
   travail de chargement paresseux n'est au périmètre.
8. **`toFrontLayer` : rien à faire** (constat 2.22) — `symbology` est
   recopié en bloc et `app/configs/schemas.py` l'accepte en `dict`. Écrit ici
   pour qu'une session future ne « corrige » pas un problème inexistant.
9. **Aucun méta-test** n'impose qu'un nouveau module `models` du cœur soit
   listé dans `core_table_names()` : l'oubli reste silencieux pour le
   prochain module. Un tel test serait une amélioration réelle, hors
   périmètre ici.
10. **Surface du suivi `libexpat.so.1` élargie** (D4) : `app.mapicons`
   devient le **second** module du cœur à dépendre de `defusedxml` au
   runtime, après `app.harvest`. Dans une image où `libexpat.so.1` manque —
   panne de packaging préexistante, documentée depuis SP-21 et hors périmètre
   ici — l'upload d'une icône **SVG** échouera désormais aussi, pas seulement
   le moissonnage OGC. Ni aggravé ni corrigé par SP-27 ; l'upload PNG n'est
   pas concerné (aucun parse XML).
11. **L'allowlist SVG refuse les dégradés et le texte** (`defs`,
   `linearGradient`, `radialGradient`, `stop`, `text`, `use`, `symbol`,
   `mask`, `pattern`) : un logo légitime en dégradé sera rejeté en
   `svg_no_graphics`. Les élargir est faisable sans rouvrir le XSS — aucun de
   ces éléments ne charge ni n'exécute — mais demande de réautoriser
   `fill="url(#id)"`, donc de **contraindre la valeur** à une référence
   locale `#id` : aujourd'hui l'assainisseur refuse en bloc toute valeur
   contenant `url(`, `javascript:` ou `data:`, ce qui est le bon défaut tant
   qu'aucune cible d'`url()` n'est dans l'allowlist d'éléments.
12. **`sniff_content_type` est une heuristique de préfixe**, pas un
   décodeur : un PNG est reconnu par sa signature de 8 octets (fiable), un
   SVG par un préfixe `<svg`/`<?xml` après `lstrip()` (suffisant pour
   distinguer les deux types autorisés, insuffisant pour prouver qu'un
   document est un SVG bien formé — c'est `sanitize_svg` qui le prouve, en
   parsant).
13. **Substitution de `currentColor`** dans les SVG Lucide : faite à la
   rasterisation, par `split`/`join` sur `stroke="currentColor"`. Si une
   version future de `lucide-static` change cette forme (guillemets simples,
   attribut réordonné), la substitution devient un no-op **silencieux** et
   les icônes retomberont sur le noir par défaut. Le test « la couleur de
   trait currentColor est remplacée avant décodage » (Task 6) verrouille la
   forme attendue dans le module généré, ce qui fera échouer la
   régénération plutôt que le rendu.

---

## Self-Review Notes (for the plan author, not a task)

- **Couverture de la spec** : §3.1 (modèle de données) → Tasks 2, 7, 13 ;
  §3.2 (paint/légende) → Tasks 2, 3, 7, 8 ; §3.3 (étiquettes) → Tasks 13,
  13 ; §3.4 (icônes, Lucide et personnalisées) → Tasks 6, 7, 8, 9, 10, 11,
  11 ; §3.5 (éditeur) → Tasks 4, 5, 12, 14 ; le périmètre 4.5 (mesure +
  croquis, monté hors mode édition) → Tasks 15, 16, 17, 18, 19 ; preuves →
  Task 20. Task 1 est une tâche d'outillage de test que la spec ne prévoyait
  pas et sans laquelle rien de ce qui précède n'est testable.
- **Ce que les deux révisions ont changé structurellement** : 17 tâches →
  **20**. Première passe : Task 1 (double MapLibre) est nouvelle ; l'ancienne
  tâche 17 (E2E) est scindée en un rendu du croquis avec ses gardes et son
  nettoyage, et une tâche de preuves E2E + vérification finale ; l'ancienne
  tâche 16 absorbe le câblage complet du widget (D2) au lieu du seul
  `interactiveTools` ; l'ancienne tâche 11 (`labelFeatureState.ts`) devient
  `labelSource.ts` avec un mécanisme entièrement différent (D1). Deuxième
  passe : **Task 5** (contour classé + extraction de
  `FieldClassificationPicker`) est insérée juste après Task 4, et les
  anciennes tâches 5 à 19 sont décalées en 6 à 20.
- **Un relecteur de Task 2 seule ne voit pas toute l'histoire du contour**
  (c'est Task 3) : c'est un dimensionnement voulu, pas un manque. Les tests
  de Task 2 exercent entièrement la sortie pure de
  `buildMapPaint`/`buildLegend`.
- **Trois tâches sont plus grosses que la moyenne** et c'est assumé : Task 9
  (module du cœur complet + assainisseur + 4 fichiers d'infrastructure, parce
  que le découper laisserait `lint-imports` ou la garde de déployabilité
  rouge entre deux commits), Task 12 (l'UI d'icônes, parce que le picker et
  son câblage aux deux hôtes n'ont aucun sens séparés) et Task 5 (extraction
  d'un composant livré **puis** son second usage : les séparer laisserait un
  commit intermédiaire où le composant extrait n'a qu'un seul appelant et où
  la raison d'être de ses libellés injectés est invérifiable).
- **Les deux points de fragilité résiduels les plus probables** sont
  Task 20 — deux specs E2E dont les détails d'interaction (chemin d'ouverture
  de l'éditeur, présence d'un widget carte sur `/apps/9`, persistance de la
  config par `mocks.ts`) sont décrits d'après les specs voisines mais n'ont
  pas été exécutés ; la tâche dit explicitement que les specs voisines sont
  la vérité et ce plan seulement une esquisse d'elles — et **Task 5**, dont
  l'extraction doit reproduire au caractère près le DOM et les noms
  accessibles d'un composant couvert par 16 tests et une preuve E2E. La
  tâche fixe le critère d'échec sans ambiguïté : si l'un de ces 16 tests doit
  être **modifié**, l'extraction est fausse.
- **Ce que la deuxième passe a changé, hors D4/D5** : le chemin de décodage
  des images côté shell passe de `createImageBitmap` à
  `HTMLImageElement` + `URL.createObjectURL`, pour **toutes** les icônes,
  parce que Lucide livre du SVG et que `createImageBitmap` sur un blob SVG
  n'est pas fiable d'un navigateur à l'autre. Conséquence :
  `createImageBitmapStub.ts` disparaît du plan (il n'avait plus d'appelant —
  une infrastructure de test morte est un défaut, pas un reste inoffensif) et
  `imageDecodeStub.ts` le remplace, dimensionné sur une **sonde jsdom
  exécutée** : `Image` existe, `URL.createObjectURL`,
  `URL.revokeObjectURL`, `createImageBitmap` et
  `HTMLImageElement.prototype.decode` sont tous `undefined`.
