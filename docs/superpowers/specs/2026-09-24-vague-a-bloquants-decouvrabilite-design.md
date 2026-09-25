# Spec — Vague A : bloquants et découvrabilité (7 SP)

> Périmètre : les 7 SP proposés par
> `docs/revue/2026-09-24-diagnostic-ui-ux.md` §3 "Vague A" (SP-A1→SP-A7,
> défauts D01/D02/D03/D09/D18/D13/D05/D58). Recherche de code menée par 7
> agents Explore le 2026-09-24 (résumés ci-dessous par tâche). Décisions de
> scope tranchées par Tanguy (SP-A5 : implémenter maintenant, pas différer).

## Décisions de scope

- **SP-A5 (D13)** est un chantier L très supérieur aux 6 autres (S/M). Le
  moteur de rendu partagé (`MapView.tsx`) est déjà générique sur les 5
  types de couche — la restriction est uniquement dans le widget carte
  (props + `PropsPanel`). Scope retenu pour cette passe : le widget gagne
  un tableau `layers: MapLayer[]` **additionnel** à la couche `feature`
  déjà dérivée de sa `DataSource` liée — pas de refonte du binding
  multi-DataSource (signalé par la recherche comme la partie coûteuse et
  incertaine). L'auteur peut ajouter des couches raster/vector-direct/
  deck/tiles3d indépendantes de la DataSource, via les mêmes composants
  `LayerPicker`/`LayersPanel` déjà utilisés par l'éditeur autonome.
- **Filets anti-régression** : seuls 2 des 10 filets proposés par le
  diagnostic (§4) concernent la vague A : l'inventaire de routes sans lien
  entrant (D01/A1) et la matrice rôle×flag (D03/A3). Les 8 autres visent
  des défauts de vague B/C, hors périmètre ici.
- **D05 (secrets)** : reste un *hard delete* sans vérification de
  référence — aucun mécanisme de ce type n'existe ailleurs dans le dépôt
  (confirmé par la recherche) ; l'ajouter serait un chantier disproportionné
  par rapport à l'effort M annoncé. Le seul filet ajouté est une
  confirmation utilisateur (`ConfirmDialog`) avant suppression.

## SP-A1 (D01) — liens de navigation vers `/bookmarks` et `/analytics/sql`

Les deux routes existent, fonctionnent, ne sont gardées par aucun lien
entrant (confirmé par grep exhaustif). Précédent direct déjà en prod :
`CatalogPage.tsx:147-151` affiche un lien conditionnel `/reports` sur
l'atterrissage du domaine Automatisation (`type === "pipeline" && !fixedType`).

Décision : même patron, deux nouveaux blocs juste après celui de
`/reports` :
- `type === "bookmark" && !fixedType` → lien vers `/bookmarks`, aucune
  garde de privilège (route ouverte à tout utilisateur authentifié, comme
  `/`).
- Garde par privilège `analytics.sql_lab.access` (via `useMe()`, même
  idiome que `SettingsNav.tsx:42-45`) → lien vers `/analytics/sql`, affiché
  uniquement sur l'atterrissage où il a un sens : `type === "bookmark"`
  également, puisque `DOMAIN_PATHS.analytics === "/?type=bookmark"`
  (`domainRoutes.ts:21`) — c'est le seul atterrissage du domaine
  Analytique aujourd'hui.

Nouvelles clés i18n (`shell/src/i18n/catalog.fr.ts`, patron
`catalog.scheduledReportsLink`) : `catalog.bookmarksLink` ("Signets →"),
`catalog.sqlLabLink` ("SQL Lab →").

**Filet anti-régression (D01)** : test d'inventaire statique — pour
chaque chemin de route déclaré dans `routes.tsx`, vérifier qu'il existe au
moins une occurrence de ce chemin en dehors de `routes.tsx`/son fichier de
test (un `<Link to="...">`, une navigation programmatique, ou une entrée
dans un registre `DEEP_LINK_ONLY_ROUTES` explicite pour les routes
volontairement non liées — ex. `/pipelines/new`, `/apps/:pk/edit`
paramétrées, `/sites/:slug` qui n'a de sens qu'en deep-link de contenu
publié). Implémenté comme test Vitest lisant `routes.tsx` par regex plutôt
que par exécution du routeur (pas d'framework générique lourd — c'est le
choix de scope proportionné).

## SP-A2 (D02) — item Site : branche d'édition manquante

Un-liner confirmé par la recherche : `ItemDetailPage.tsx:116` liste
`["map", "app", "dashboard", "dataset", "pipeline"]` sans `"site"`. Les
deux dispatchers (`onOpenEditor` dans `routes.tsx:116-125` et
`useOpenItem.ts`) routent déjà `"site"` vers `/apps/${pk}/edit`
(`AppBuilderPage` est agnostique au kind). Fix : ajouter `"site"` au
tableau. Aucun autre changement.

## SP-A3 + D09 (D03) — garde rôle×flag sur `NewItemButton` + spinner infini

Deux défauts liés, un seul lot :

1. **D03** : `NewItemButton.tsx` gate pipeline/visual-query uniquement sur
   `etlEnabled` (capacité d'instance), jamais sur le privilège
   `automation.manage` (`core/app/roles/privileges.py:11`,
   `AUTOMATION_MANAGE`). Le doublet privilège+capacité existe déjà pour la
   barre de domaines (`capabilities.ts:61-66`, doctrine "un privilège
   manquant MASQUE, une capacité coupée VERROUILLE") — `NewItemButton`
   doit reprendre exactement ce doublet. `hasAnyCreatableKind` (ligne 68)
   OR-e directement `etlEnabled` sans privilège : à corriger aussi, sinon
   un rôle à 0 privilège verrait encore le bouton apparaître uniquement à
   cause du flag d'instance.
2. **D09** : `PipelineBuilderPage.tsx:141` — `if (opsQuery.isLoading ||
   !opsQuery.data) return <p role="status">{t("common.loading")}</p>;`
   n'a pas de branche d'erreur, contrairement aux blocs `configQuery`/
   `itemQuery` juste au-dessus. Quand `CORE_ETL_ENABLED=false`, les routes
   pipeline ne sont pas montées côté cœur (404), `opsQuery.isError` devient
   vrai mais n'est jamais lu → spinner infini. Fix : lire
   `useInstanceInfo().data?.etlEnabled` (déjà utilisé ailleurs dans ce
   fichier/`NewItemButton`) et afficher, si `false`, le même patron que
   `AdminInfrastructurePage.tsx:38-40`
   (`<p className="text-sm text-ink-2">{t("pipelineBuilder.etlDisabled")}</p>`)
   à la place du spinner — avant même d'attendre `opsQuery`.

**Filet anti-régression (D03)** : test de matrice ciblé sur
`NewItemButton` — pour les 4 rôles prédéfinis (Administrateur/
Créateur/Analyste/Lecteur, privilèges exacts de
`core/app/roles/privileges.py`) croisés avec `etlEnabled` on/off, vérifier
que l'option Pipeline/Visual-query du sélecteur "Type" n'est **jamais**
visible sans le privilège `automation.manage`, et toujours visible quand
privilège + flag sont réunis. Champ d'application volontairement limité à
ce couple privilège/flag précis (pas un framework générique 4 rôles ×
tous les `CORE_*_ENABLED` — hors périmètre de cette vague, cf. diagnostic
§4 qui propose ce filet plus large pour une vague ultérieure).

## SP-A4 (D18) — auto-cadrage sur l'emprise des données

Plus fort impact du diagnostic (9/9), structurel sur les deux hôtes.
Bonne nouvelle confirmée par la recherche : `Item.bbox` est **déjà**
calculé et persisté côté cœur à chaque sauvegarde de carte
(`core/app/configs/bbox.py:44-79`, `core/app/items/schemas.py:42`) mais
jamais lu côté shell (absent du type `Item` shell). MapLibre GL expose déjà
`fitBounds`, déjà utilisé dans `PipelinePreviewMap.tsx:148-149` avec un
calcul de bbox client (`computeBounds`/`collectCoordinates`,
lignes 12-51) qu'on va factoriser plutôt que dupliquer.

Décisions :
- **Éditeur autonome** (a une vue persistée, `MapConfig.view`, qui peut
  avoir été ajustée et enregistrée par l'utilisateur) : n'auto-cadrer
  **que** si la vue actuelle est encore la valeur par défaut littérale
  (`center: [2.4, 46.6], zoom: 5`, cf. `layers.ts:43`) — jamais écraser un
  cadrage que l'utilisateur a explicitement choisi et sauvegardé. Ajout
  d'un bouton manuel "Ajuster à l'emprise des données" à côté du bouton
  reset existant de `CameraControls` (`MapEditorPage.tsx:173-177`), pour
  re-déclencher l'ajustement à tout moment (y compris si la vue n'est pas
  la valeur par défaut).
- **Widget carte** : aucune vue n'est jamais persistée (confirmé — le
  widget reconstruit `view` avec la valeur par défaut à chaque rendu, sans
  jamais l'exposer en prop). Auto-cadrage **systématique** dès que les
  données (`ctx.data.records`) sont chargées, calculé côté client avec la
  fonction factorisée. Même bouton manuel ajouté à côté du reset de
  `CameraControls` dans le `PropsPanel` du widget
  (`mapWidget.tsx:213-219`).
- Factoriser `computeBounds`/`collectCoordinates` de
  `PipelinePreviewMap.tsx` vers `shell/src/lib/geometryBbox.ts` (qui a
  déjà `bboxFromGeometry` pour une géométrie unique) sous un nom
  `bboxFromFeatureCollection`, et faire pointer `PipelinePreviewMap.tsx`
  dessus (DRY, un seul calcul de bbox client dans tout le dépôt).
- Nouvelle méthode `fitBounds(bbox: [number, number, number, number],
  opts?: { padding?: number; maxZoom?: number })` sur `MapViewHandle`
  (`map/MapView.tsx:91-99`), appelant `map.fitBounds` en interne — même
  patron que `flyTo`/`highlight` déjà exposés.
- Ajouter `bbox: [number, number, number, number] | null` au type `Item`
  shell (`api/types.ts`), déjà présent sur le fil depuis
  `GET /items/{pk}` (`ItemRead.bbox`, `core/app/items/schemas.py:42`) —
  aucun changement backend nécessaire.

## SP-A5 (D13) — parité de couches du widget carte (raster/deck/tiles3d)

Cf. « Décisions de scope » ci-dessus. Le widget garde sa couche `feature`
unique dérivée de `dataSourceId` (inchangée), et gagne une nouvelle prop
`layers: MapLayer[]` pour des couches additionnelles indépendantes de
toute `DataSource` (raster/vector-direct par URL/deck/tiles3d/feature par
URL ou catalogue) :

- `mapWidget.tsx` : `defaultProps.layers = []`. Le `configSchema` du
  widget (scalaires uniquement, `widgetPropSchema.ts:8-13`) n'expose pas
  `layers` — même traitement que `symbology`/`popup`, déjà hors
  `configSchema` aujourd'hui (précédent direct).
- Runtime (`Component`, lignes 316-341) : construire
  `layers: [...(dataSourceLayer ? [dataSourceLayer] : []), ...(props.layers
  ?? [])]` au lieu du tableau à une seule entrée actuel — `MapView` n'a
  besoin d'aucun changement (déjà générique sur les 5 `kind`).
- `PropsPanel` (`mapWidget.tsx:177-282`) : ajouter `<LayerPicker
  onAdd={...} />` + `<LayersPanel layers={props.layers ?? []}
  onChange={...} />` (composants déjà découplés de `MapConfig`, déjà
  utilisés tels quels par `MapEditorPage.tsx`), positionnés après les
  réglages de symbologie/popup de la couche `feature` de base.

## SP-A6 (D05) — suppression de secret (UI + MCP)

Recherche : le backend (`DELETE /secrets/{id}`, garde
`require_any_privilege([ADMIN_SECRETS_MANAGE, AUTOMATION_SECRETS_MANAGE])`,
audit `secret.delete`) et le client API (`deleteSecret`/`useDeleteSecret`,
testés) existent déjà et n'ont **aucun appelant**. Seuls manquent :

- **UI** : bouton de suppression par ligne dans `SecretParamSelect.tsx`
  (liste `<select>`, lignes 29-41 — remplacer par une liste avec un bouton
  poubelle par option, ou ajouter le bouton à côté du select pour le
  secret actuellement sélectionné), avec confirmation `ConfirmDialog` du
  kit (jamais `window.confirm`, cf. décision D26/conventions déjà
  tranchées) avant d'appeler `useDeleteSecret().mutateAsync(id)`.
- **Outil MCP** : nouveau module `core/app/mcp/tools/secrets.py`,
  `delete_secret(secret_id: str)`, modelé sur `create_group`
  (`sharing.py:41-71`) : `@server.tool()` + `@write_tool`,
  `resolve_actor`, garde
  `require_any_privilege(session, user, [Privilege.ADMIN_SECRETS_MANAGE.value,
  Privilege.AUTOMATION_SECRETS_MANAGE.value])` traduite en `ValueError`
  via `http_exception_to_value_error`, `write_audit(action="secret.delete",
  payload={"name":..., "kind":...})` — garde strictement identique à la
  route REST (REV-009 : ne jamais rouvrir côté MCP un trou fermé côté
  REST). Enregistré dans `core/app/mcp/tools/__init__.py`.
- Pas de vérification de référence avant suppression (cf. décision de
  scope ci-dessus) : suppression immédiate après confirmation, comme la
  route REST existante.

## SP-A7 (D58) — réouverture d'un pipeline créé par le wizard visuel

Deux points d'entrée dupliqués routent aujourd'hui `kind: "pipeline"` vers
le DAG complet sans condition : `useOpenItem.ts:42-45` et le dispatcher
inline `onOpenEditor` de `ItemDetailRoute`
(`routes.tsx:109-129`, ligne 122-123). Aucun marqueur de création
(`createdVia`) n'existe sur l'item/la config — confirmé par recherche
exhaustive. Le seul moyen fiable de décider est de rejouer la même
reconnaissance de forme que le wizard lui-même :

- Nouvelle fonction partagée `resolvePipelineEditorPath(client: ItemClient,
  pk: string): Promise<string>` dans un nouveau fichier
  `shell/src/shell/resolvePipelineEditorPath.ts` : appelle
  `client.getPipelineConfig(pk)`, passe le résultat à
  `decompilePipelineToWizardState` (déjà exporté par
  `builder/visualQuery/compilePipeline.ts`) ; retourne
  `` `/datasets/visual-query/${pk}/edit` `` si le résultat est non-null,
  sinon `` `/pipelines/${pk}/edit` ``. En cas d'échec du fetch, retombe sur
  `` `/pipelines/${pk}/edit` `` (choix sûr par défaut, cohérent avec le
  comportement actuel).
- `useOpenItem.ts` et `ItemDetailRoute` (`routes.tsx`) appellent tous les
  deux cette fonction unique pour `type === "pipeline"` au lieu de
  chacun hardcoder `/pipelines/${pk}/edit` — élimine la duplication
  identifiée par la recherche (piège n°4 : un correctif posé sur une
  surface et jamais reporté sur sa jumelle).
- `useOpenItem`'s pipeline branch devient asynchrone comme les branches
  `bookmark`/`alert` déjà existantes dans ce fichier (même patron
  `try/catch` → `openError` en cas d'échec).

## Filets anti-régression — résumé des 2 nets de vague A

| Net | Où | Comment |
|---|---|---|
| Route sans lien entrant | Test statique lisant `routes.tsx`, nouveau fichier `shell/src/shell/routeReachability.test.ts` | Chaque chemin déclaré doit apparaître ailleurs dans `shell/src` (hors `routes.tsx`/son test) ou figurer dans un registre `DEEP_LINK_ONLY_ROUTES` explicite et commenté |
| Asymétrie rôle×flag | `NewItemButton.test.tsx`, nouveau describe "matrice rôle×flag pipeline/visual-query" | 4 rôles prédéfinis × `etlEnabled` on/off → option visible ⟺ (privilège `automation.manage` ET `etlEnabled`) |
