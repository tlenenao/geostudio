# Spec — Vague B : états système et cohérence (12 SP)

> Périmètre : les 12 SP proposés par `docs/revue/2026-09-24-diagnostic-ui-ux.md`
> §3 "Vague B" (SP-B1→SP-B12, défauts D19/D20/D26/D28/D21/D22/D29/D31/D33/D06/
> D24/D25/D57/D17/D40/D44, + points mineurs D30/D14). Recherche de code menée
> par 12 agents general-purpose le 2026-09-26 (résumés ci-dessous par tâche).
> Suite directe de la Vague A (7 SP, clôturée, cf. `CLAUDE.md` § Livré).

## Décisions de scope

- **SP-B6 (D29)** — la recherche infirme le cadrage du diagnostic
  ("contrainte structurelle", "chantier prioritaire"). Le routeur est déjà
  plat, 100% component-driven (aucun loader/action), `react-router-dom`
  `6.30.4` est déjà installé (supporte `createBrowserRouter`/`useBlocker`
  nativement). Migrer `BrowserRouter` → `createBrowserRouter`+`RouterProvider`
  ne touche que 2 fichiers de code (`App.tsx`, `shell/routes.tsx`, ce dernier
  gardant sa même arborescence de `<Route>` via `createRoutesFromElements`)
  + 2 fichiers de test (`App.test.tsx`, `routes.test.tsx`) ; les ~30 sites
  `useNavigate`/`useParams`/`<Link>` répartis sur 10 fichiers sont
  **inchangés**. Retenu : migrer (option A), pas de garde manuelle
  `beforeunload`+interception de clic (option B, qui aurait créé une 2e API
  de navigation parallèle à maintenir indéfiniment). Aucun `isDirty` n'existe
  nulle part aujourd'hui (même `canUndo` de `useUndoableDraft` ne convient
  pas : il reste `true` après sauvegarde, faute de `resetDraft` au save) —
  un nouveau signal de brouillon sale est nécessaire dans les 5 éditeurs
  **indépendamment** du choix de routeur ; ce n'est donc pas un argument en
  faveur de l'option B.
- **SP-B12 (D44)** découpé en 4 sous-tâches à la demande de la recherche
  (effort L confirmé, 193 occurrences sur 54 fichiers au 2026-09-26 — le
  chiffre du diagnostic, 187/40, a dérivé en 2 jours et est à considérer
  périmé) : (1) `AppRuntimePage` seule — page la plus visitée, plus petit
  diff, gain maximal ; (2) 3 pages publiques + `DatasetDownloadButtons` ;
  (3) balayage du reste (~50 fichiers), en commençant par le cluster
  `builder/widgets/*` + `builder/*Panel.tsx` qui concentre ~90 des 193
  occurrences ; (4) garde-fou non régressif (`.raw-color-threshold`, même
  patron que `.bundle-size-threshold`). Le "2 littéraux français non
  traduits" du diagnostic sur les 3 pages publiques n'a pas été retrouvé par
  la recherche (tout passe déjà par `t(...)`) — traité comme déjà résolu
  entre-temps, pas relancé.
- **D14 (printLayout.showLegend pour les Apps)**, rattaché à SP-B12 : ce
  n'est **pas** un simple passe-plat (contrairement à D30/timeout de SP-B7 ou
  d'autres correctifs mécaniques de cette vague) — une App n'a pas de liste
  de couches unique comme `MapConfig.layers`, elle a zéro-à-N widgets `map`
  répartis sur ses pages. Décision de scope : la légende exportée reprend
  les couches du **premier widget `map` trouvé sur la page active** au
  moment de l'export (même page que celle qui définit déjà `title`/
  `cartouche` dans l'overlay d'export) ; zéro widget carte sur la page ⇒
  comportement inchangé (pas de légende, comme aujourd'hui). Sélection
  multi-widgets plus fine explicitement hors périmètre, à revisiter si un
  besoin réel apparaît.
- **SP-B10** regroupe 4 défauts d'ampleur très inégale. Retenu : livrer
  intégralement D25 (harmonisation du vocabulaire de statut, corrige au
  passage un vrai bug i18n — `PipelineRunPanel` affiche les littéraux anglais
  non traduits `"succeeded"`/`"failed"`), D57 (texte "Export en cours…") et
  D17 (indicateur de troncature MVT, nécessite un petit ajout cœur : en-tête
  `X-Tile-Truncated` quand la sous-requête `ST_AsMVT` retourne exactement
  `MAX_TILE_FEATURES` lignes). D24 (pourcentage générique + annulation) est
  **partiellement** hors périmètre : aucune primitive d'annulation de job
  n'existe côté cœur (procrastinate le supporte en théorie, jamais câblé ici)
  — l'implémenter serait un chantier cœur à part entière. Cette vague ne
  livre qu'un indicateur de progression grossier pour les pipelines (dérivé
  de `PipelineRun.node_stats`, déjà présent, N nœuds terminés / M nœuds du
  DAG) ; ingestion/export/tileset3D/terrain3D n'ont aucune primitive
  équivalente et restent sans pourcentage — à ouvrir en suivi non bloquant,
  pas dans SP-B10.
- **SP-B9** : périmètre différencié par builder. App builder et Pipeline
  builder gagnent un miroir URL (`?page=`/`?widget=`, `?node=`) via un hook
  partagé `useUrlSyncedState` répliquant le patron déjà en prod
  d'`ItemDetailPage` (`useSearchParams`, validation avec repli, `replace:
  true`). SQL Lab **n'expose pas** sa requête SQL brute dans l'URL (taille/
  sensibilité) : seul un `?historyId=<id>` pointant vers l'historique local
  existant (`sqlLabHistory.ts`) est mirroté, la requête est réhydratée
  depuis cet id. L'éditeur de carte n'a **aucun état de navigation interne
  au niveau page** aujourd'hui (le seul état candidat, l'accordéon
  ouvert/fermé de `LayersPanel`, est interne au composant) — décision :
  hors périmètre pour cette vague plutôt qu'un refactor de lift-state non
  demandé ailleurs par le diagnostic.
- **SP-B11** : `DataTable` du kit a lui-même un vrai défaut d'accessibilité
  (tri au clic sans `tabIndex`/`onKeyDown`, alors qu'il expose déjà
  `aria-sort`) — à corriger **avant** toute migration, sinon le problème que
  D40 dénonce se relocalise dans le composant "de référence". Ordre de
  migration retenu (du plus simple au plus risqué) : Rôles → Harvest →
  Utilisateurs → Collections → Usage → aperçu pipeline → widget table de
  l'App Builder (dernier : seul des 7 à avoir des colonnes pilotées par
  schéma/CEL à l'exécution, traité comme une sous-tâche à part avec un
  adaptateur colonnes-depuis-config).

## SP-B1 (D19+D20) — état vide avec CTA

Catalogue (`shell/src/pages/CatalogPage.tsx:268-270`) : texte brut
`{t("catalog.empty")}`. 4 listes admin (`HarvestSourcesAdminPage.tsx`,
`RolesAdminPage.tsx`, `UsersAdminPage.tsx`, `CollectionsAdminPage.tsx`) ne
testent jamais `data.length === 0` — le `<table>` vide s'affiche quand même
(juste l'en-tête, indistinguable d'un chargement). Le kit `EmptyState`
(`shell/src/ui/kit/EmptyState.tsx`, props `title`/`description`/`action`)
a déjà 2 vrais consommateurs (`UsagePage.tsx:79`, `SqlLabPage.tsx:135`),
aucun n'utilise encore `action` — `UsagePage.tsx` est le patron de référence
à copier tel quel (branche `isLoading`/`isError`/`data.length === 0` déjà
correcte).

Fix : ajouter la branche manquante dans les 4 pages admin (identique à
`UsagePage.tsx:78-81`, `action` = bouton "Ajouter" réutilisant le handler
d'ajout déjà câblé sur chaque page) ; sur le catalogue, remplacer le `<p>`
par `EmptyState` avec un titre conditionnel — `catalog.emptyFiltered` +
CTA "Effacer les filtres" si un filtre est actif (`q`/`type`/`ownerFilter`/
`selectedKeywords.length`/`spatialBbox`, tous déjà en scope dans
`CatalogPage.tsx`), sinon `catalog.empty` reformulé + CTA de création
(réutilise le flux `NewItemButton`). Aucun changement de signature
`EmptyState`. Nouvelles clés FR : `catalog.emptyFiltered`,
`catalog.emptyClearFilters`, `harvest.empty`, `roles.empty`, clé namespace
users à vérifier avant écriture, `collectionsAdmin.empty`.

## SP-B2 (D26) — confirmation systématique des suppressions

3 sites `window.confirm` réels confirmés au 2026-09-26 (4e hit trouvé par
grep est une assertion de test, pas du code de prod) :
`MapSymbologyEditor.tsx:697` (suppression d'icône, message a déjà le nom),
`builder/widgets/form.tsx:512` (suppression d'un enregistrement, message
générique — pas de nom disponible pour une feature brute, acceptable),
`builder/ConfigHistoryPanel.tsx:66` (restauration de version, message a déjà
`{version}`). Plus l'oubli total de confirmation sur la suppression de
pièce jointe (`form.tsx`, `AttachmentFieldInput.handleDelete`, lignes
292-296 — clic direct, `a.filename` disponible en scope).

Fix, patron identique aux ~7 sites `ConfirmDialog` déjà en prod
(`ItemActions.tsx:129`, `CollectionsAdminPage.tsx:269`,
`RolesAdminPage.tsx:143` — état local `useState` du sujet à confirmer +
`<ConfirmDialog open title message confirmLabel pending={mutation.isPending}
onConfirm onCancel>`) : remplacer les 3 `window.confirm` et ajouter la
confirmation manquante sur la pièce jointe. Chaque site a besoin d'une
nouvelle clé `title` (le `confirm()` natif n'a pas de titre séparé) — 4
nouvelles clés titre + 1 nouvelle clé message (`widgetForm.
deleteAttachmentConfirm`, interpolant `{filename}`), le reste réutilise les
clés message existantes. `ConfigHistoryPanel.test.tsx:71` (mock de
`window.confirm`) à mettre à jour dans le même correctif.

## SP-B3 (D28) — câbler le Toast

`Toast` (`shell/src/ui/kit/Toast.tsx`) est entièrement contrôlé, sans hook
ni file d'attente — chaque appelant possède son propre état `open`. Monté
une fois à la racine (`App.tsx:46-59`, `ToastPrimitive.Provider`+
`Viewport`), seul consommateur réel : la galerie interne. Aucun des 5
éditeurs (Carte/Dataset/App/Pipeline/Rapport) ne lit `isSuccess` de sa
mutation de sauvegarde.

Fix : nouveau `shell/src/ui/kit/ToastProvider.tsx` — contexte +
`useToast().showToast(title, description?)`, un seul `<Toast>` rendu en
interne, monté dans `App.tsx` à l'intérieur du `ToastPrimitive.Provider`
existant (ne pas en imbriquer un 2e). Câblage dans `onSuccess` :
`useSaveMap`/`useSaveDataset`/`useSaveApp` (3 lignes chacun, patron
uniforme). Carte particulière pour Pipeline et Rapport : leur sauvegarde
passe par un `onSave()` local avec `try/mutateAsync/catch` plutôt que par
l'`onSuccess` du hook — câbler le toast dans `onSuccess` de
`useSavePipeline`/`useCreatePipeline`/`useSaveReportSchedule`/
`useCreateReportSchedule` directement (couvre aussi les deux, création ET
mise à jour, et le chemin `ConfigHistoryPanel` qui réutilise ces mêmes
hooks) plutôt que dans la page. Nouvelle clé unique `toast.saveSuccess`
("Enregistré"), pas de clé par éditeur sauf besoin produit ultérieur.

## SP-B4 (D21) — adoption de Spinner/Skeleton

`Spinner`/`Skeleton` (`shell/src/ui/kit/`) ont un seul vrai usage : la
galerie interne. 38 sites réels en `<p role="status">{t("common.loading")}
</p>` confirmés par grep, répartis en 4 catégories sans wrapper partagé
existant (`grep LoadingState/LoadingSpinner/LoadingIndicator` : zéro hit,
c'est du copié-collé, pas une seule surface à corriger) :

1. **Chargement de page pleine** (page entière ne rend que le `<p>`) :
   `PipelineBuilderPage.tsx` (4 sites), `AppBuilderPage.tsx`,
   `AppRuntimePage.tsx`, `DatasetPage.tsx`, `DatasetEditPage.tsx`,
   `MapEditorPage.tsx`, `ItemDetailPage.tsx`, `ReportEditPage.tsx`,
   `EmbedPage.tsx` (×2), `KitGalleryPage.tsx`. → `Skeleton` shape page.
2. **Listes/pages admin** (page-shell déjà rendue, corps en texte brut) :
   `CollectionsAdminPage.tsx`, `UsersAdminPage.tsx`, `RolesAdminPage.tsx`,
   `CatalogPage.tsx`, `HarvestSourcesAdminPage.tsx`, `UsagePage.tsx`. →
   `Skeleton` shape lignes de tableau/liste.
3. **Widgets du builder** (petite tuile de taille fixe) : `gallery.tsx`,
   `sliderFilter.tsx`, `pivot.tsx`, `datasetCard.tsx`, `selectFilter.tsx`,
   `chart.tsx` (×2), `indicator.tsx`, `data.tsx` (×2),
   `ExplorerDrawer.tsx`. → mixte `Spinner` (contrôles minuscules) /
   `Skeleton` (contenu à forme connue : graphique, carte, liste).
4. **Panneaux/dialogues transitoires** : `SettingsPage.tsx` (×2),
   `CollectionSharePanel.tsx`, `RegisterCollectionPanel.tsx`,
   `ShareForm.tsx` (×2), `EditCollectionPanel.tsx`. → `Spinner` en
   général, `Skeleton` pour les 2 sites qui chargent une liste de
   candidats/liens.

Fix : un nouveau composite `shell/src/ui/kit/LoadingState.tsx` (`variant:
"page" | "inline" | "rows"`, `rows?: number`) qui choisit `Skeleton`
(page/rows) ou `Spinner` (inline) en interne, garde `role="status"` +
label `t("common.loading")` (accessible même si le skeleton visuel ne
l'est pas), puis balayage mécanique des 38 sites triés par catégorie
(1 et 2 en priorité — plus gros gain UX, page pleine → écran blanc évité).

## SP-B5 (D22) — problem+json et différenciation du 429

Client générique (`shell/src/api/base.ts`) : 6 sites `fetch()`
(`request()` ligne 197 = wrapper générique principal, + 5 fonctions
sœurs), aucun ne lit le corps sur `!res.ok` — juste `throw new
Error(\`Request failed: ${status}...\`)`. Un site (`api/domains/
layers.ts:161-193`, `uploadMapIcon`) ré-implémente déjà à la main le
parsing `problem+json` — preuve que le besoin est connu mais jamais
centralisé. Le cœur renvoie bien du `application/problem+json`
(`core/app/main.py:144-169`) et un 429 a un `Retry-After` fixe (`:215-235`,
valeur codée en dur `"60"`) — rien ne distingue structurellement un 429
d'un 4xx générique côté client aujourd'hui, seul `res.status` le permettrait
si le client le lisait.

Fix : nouveau type `ApiError extends Error { status; title?; detail?;
retryAfter? }` dans `base.ts`, peuplé par `await res.json().catch(() =>
undefined)` + `res.headers.get("Retry-After")` sur les 6 sites `fetch`
(remplacer aussi le parsing ad hoc de `layers.ts` par le helper partagé).
Garder `message` rétrocompatible (`detail ?? message actuel`) pour ne pas
casser les tests qui matchent déjà sur `.message` au niveau des fonctions
de domaine (`AlertRuleEditor.test.tsx`, `DatasetEditPage.test.tsx` — non
affectés, ils mockent au niveau domaine, pas `fetch`). Une dizaine de
sites d'affichage (`NewItemButton`, `AlertRuleEditor`, `DatasetEditPage`,
`PipelineRunPanel`, `MapSymbologyEditor`, `SqlLabPage`...) passent de
`e.message`/clé i18n fixe à `e instanceof ApiError ? e.detail ?? e.message
: fallback`, avec une branche dédiée `status === 429` (afficher
`retryAfter`). **Changement de comportement assumé et à documenter** :
`shell/e2e/quota-guard.spec.ts` teste aujourd'hui explicitement le message
générique actuel ("Échec de la création.", indépendant de la cause) — ce
test doit être mis à jour pour attendre le `detail` réel, pas laissé tel
quel par accident.

## SP-B6 (D29) — garde de navigation sur brouillon non sauvegardé

Cf. décision de scope ci-dessus (migration retenue). Étapes :

1. **Migration routeur** : `App.tsx` — `useMemo(() =>
   createBrowserRouter(createRoutesFromElements(<AppRoutes/>...)), [])` +
   `<RouterProvider router={router} />` au lieu de `<BrowserRouter>` ;
   `shell/routes.tsx` garde son arbre `<Route element={...}>` existant
   (aucune restructuration en objets loader/action). `App.test.tsx` et
   `routes.test.tsx` (seuls fichiers de test montant le routeur réel, les
   33 autres utilisateurs de `MemoryRouter` testent une page isolée et ne
   changent pas) migrent vers `createMemoryRouter`+`RouterProvider`.
2. **Signal de brouillon sale**, nouveau par éditeur (aucun n'existe
   aujourd'hui, pas même une réutilisation fiable de `canUndo` —
   documenté : reste `true` après save faute de `resetDraft` au
   succès) : un booléen `isDirty` simple, mis à `true` à toute mutation
   locale du brouillon, remis à `false` au `onSuccess` de la sauvegarde et
   au chargement initial. Les 5 éditeurs (Carte/Dataset/App/Pipeline/
   Rapport) le portent indépendamment de l'undo stack — ne PAS réutiliser
   `canUndo` (couplerait deux concepts orthogonaux et réintroduirait la
   classe de bug déjà documentée en SP-19 sur les id de sélection périmés).
3. **Garde** : `useBlocker(isDirty)` (react-router v6, maintenant
   disponible) pour la navigation interne → `ConfirmDialog` "quitter sans
   enregistrer ?" ; `window.beforeunload` pour fermeture d'onglet/rechargement
   (couverture complémentaire, pas remplaçable par `useBlocker`).

## SP-B7 (D31+D30) — timeout réseau explicite et message unifié

`new QueryClient()` (`App.tsx:23`) sans `defaultOptions` — retry par défaut
de React Query (3× backoff exponentiel), aucun timeout. `base.ts` : aucun
des 6 sites `fetch()` (mêmes que SP-B5) ne passe de `signal`. Zéro concept
de connectivité/hors-ligne dans le dépôt (`navigator.onLine`,
`online`/`offline` : aucun hit).

Fix : dans `base.ts`, passer `signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS)`
(natif, ~20-30s) sur les 6 sites `fetch` ; capturer `TimeoutError`/
`AbortError` et relancer un type dédié `CoreUnreachableError extends Error`
(distinct d'`ApiError` de SP-B5 — une erreur réseau/timeout n'est PAS une
réponse HTTP). Nouveau petit module (`shell/src/api/connectivity.ts`) +
bannière réutilisant la plomberie Toast déjà posée par SP-B3 : déclenchée
**uniquement** sur `CoreUnreachableError` (jamais sur une réponse HTTP
4xx/5xx normale, pour ne pas noyer les erreurs de validation habituelles
dans une bannière globale). Complément : ajuster `defaultOptions.queries`
du `QueryClient` (retry borné, ex. 1, au lieu du défaut 3× qui multiplierait
le nouveau timeout par 3+ avant que la query ne se stabilise en erreur).

## SP-B8 (D33) — aria-describedby/aria-invalid + résumé d'erreurs

Le kit `Field.tsx` (`shell/src/ui/kit/`) n'a **aucun consommateur de
production** (seule la galerie interne) — corriger uniquement `Field.tsx`
ne changerait rien en prod. Le vrai chemin utilisé partout est le
formulaire généré (`builder/widgets/form.tsx`, `FieldInput` ligne 348 +
markup inline `FormComponent` lignes 616-635) : aucun `aria-describedby`/
`aria-invalid`, l'erreur (`errorFor(f)`, `role="alert"`) n'a pas d'id et
n'est jamais reliée au contrôle.

Fix : `errorId = \`${f.name}-error\`` (clé déjà stable, pas besoin de
`useId()`), thread `aria-invalid={err ? true : undefined}` +
`aria-describedby={err ? errorId : undefined}` sur les 6 branches de
`FieldInput` (boolean/integer/date/datetime/enum/texte — pièce jointe
exclue, pas de validation), poser `id={errorId}` sur le `<span>` d'erreur.
Ajouter un résumé d'erreurs en tête du `<form>` de `FormComponent` (région
`role="alert"`, liens/`focus()` vers le premier champ invalide, construit
depuis l'ensemble touché-et-invalide déjà calculé dans `handleSubmit`).
**Coordination requise avec D32/SP-C1** (aria-required, hors périmètre de
cette vague mais même fichier/mêmes lignes de `FieldInput`) : séquencer les
deux correctifs sur la même tâche ou l'une immédiatement après l'autre pour
éviter que deux agents ré-touchent la signature de `FieldInput`
indépendamment et entrent en conflit.

## SP-B9 (D06) — restauration de l'état de navigation des builders

`ItemDetailPage.tsx:29-42` est le patron de référence : `useSearchParams`,
une seule clé `?panel=`, validation contre une union `PanelKind` avec
repli, écriture via `setSearchParams(params, {replace:true})`.

Fix, cf. décision de scope : nouveau hook partagé
`useUrlSyncedState(key, decode, encode)` répliquant ce patron, réutilisé
4× (proportionné — c'est le même motif de 6 lignes copié-collé, pas une
sur-abstraction au sens du piège n°13) :
- **App builder** (`AppBuilderPage.tsx`) : `activePageId` → `?page=`,
  `selectedId` → `?widget=`. Garder inchangée la logique de validation
  contre le brouillon courant (lignes 134-146) qui protège déjà contre les
  id périmés après un undo (SP-19) — elle doit désormais s'exécuter sur la
  valeur lue depuis l'URL, pas seulement depuis un `useState`, y compris
  pour un id périmé arrivé par navigation arrière/avant ou lien partagé.
- **Pipeline builder** (`PipelineBuilderPage.tsx`) : `selectedNodeId` →
  `?node=`, même patron.
- **SQL Lab** (`SqlLabPage.tsx`) : PAS la requête SQL brute en clair dans
  l'URL — `?historyId=<id>` pointant vers `sqlLabHistory.ts`, `sql`
  réhydraté depuis cet id au chargement.
- **Éditeur de carte** : rien à mirroter au niveau page aujourd'hui — hors
  périmètre (cf. décision de scope), pas de lift-state de
  `LayersPanel` non demandé par le diagnostic.

Orthogonalité avec l'undo/redo : le contenu du brouillon (pile undo) et
"quel morceau d'UI on regarde" (état d'URL) restent deux concepts
distincts, comme documenté dans le code actuel — ce refactor ne fait que
déplacer le stockage du second, sans toucher au premier.

## SP-B10 (D24+D25+D57+D17) — progression et vocabulaire des jobs

Cf. décision de scope pour le découpage exact. 4 vocabulaires de statut
indépendants trouvés (`ReportRunPanel.tsx:9-15`, `PipelineRunPanel.tsx:9-14`
— avec un vrai bug i18n, littéraux anglais `"succeeded"`/`"failed"` non
traduits —, `ImportFileButton.tsx` avec un enum `Phase` local sans rapport
avec `job.status`, export Bookmark/App qui n'affiche aucun libellé du
tout). `PipelineRun.node_stats` (JSON déjà présent, compte de lignes par
nœud) est la seule primitive de progression exploitable sans changement
cœur ; ingestion/export/tileset3D/terrain3D n'ont qu'un statut enum, pas de
pourcentage. Le plafond MVT (`core/app/features/tiles.py`,
`MAX_TILE_FEATURES = 5000`, `ST_AsMVT` + `LIMIT`) n'est signalé nulle part
au frontend aujourd'hui.

Fix : (1) module i18n canonique unique `shell/src/lib/jobStatusLabel.ts`,
remplace les 4 vocabulaires, corrige au passage le bug i18n de
`PipelineRunPanel` ; (2) texte "Export en cours…" pendant le sondage dans
`ExportPanel.tsx`/`AppExportPanel.tsx`, réutilisant ce vocabulaire ; (3)
côté cœur, en-tête `X-Tile-Truncated: true` sur `tiles.py` quand la
sous-requête retourne exactement `MAX_TILE_FEATURES` lignes (comptage déjà
fait par PostGIS via le `LIMIT`, coût marginal), consommé côté carte par un
badge/tooltip sur la couche concernée ; (4) indicateur de progression
grossier (N/M nœuds) pour les pipelines uniquement, dérivé de
`node_stats` — pas de pourcentage générique ni d'annulation pour les
autres types de job (suivi non bloquant à ouvrir séparément).

## SP-B11 (D40) — adoption de DataTable

`DataTable` (`shell/src/ui/kit/DataTable.tsx`) a un vrai défaut
d'accessibilité propre (tri au clic sans `tabIndex`/`onKeyDown` malgré
`aria-sort` déjà posé) et aucune intégration `EmptyState`/pagination — à
corriger avant migration (cf. décision de scope). 7 implémentations
divergentes trouvées : Utilisateurs, Rôles, Collections, Harvest, Usage
(5 pages admin), aperçu de run pipeline (`PipelinePreviewPanel.tsx` — déjà
accessible au clavier, bon exemple à suivre pour le fix du kit), widget
table de l'App Builder (`builder/widgets/data.tsx` — seul à avoir des
colonnes pilotées par schéma/CEL à l'exécution, `aria-sort` totalement
absent malgré un tri déjà au clavier via un vrai `<button>`).

Fix : (1) corriger `DataTable` lui-même (clavier sur l'en-tête de tri,
nouvelle prop `onRowClick` nécessaire pour l'aperçu pipeline et le widget
table qui font une sélection au clic de ligne, pas de case à cocher) ; (2)
migrer dans l'ordre Rôles → Harvest → Utilisateurs (aucun tri/pagination,
valide le patron colonne actions + cellule interactive) → Collections →
Usage (valide la composition avec pagination externe "charger plus"/
Précédent-Suivant) → aperçu pipeline (valide tri+pagination+clic de ligne
ensemble) → widget table de l'App Builder en dernier, avec son propre
adaptateur colonnes-depuis-config (`TableColumn[]` incluant les colonnes
calculées CEL → forme `columns` de `DataTable`), traité comme sous-tâche
séparée vu le risque/la surface la plus élevée (surface utilisateur final,
pas admin).

## SP-B12 (D44+D14) — migration `AppRuntimePage` + pages publiques

Cf. décision de scope pour le découpage en 4 sous-tâches et la règle D14.
Patron de tokenisation déjà posé par SP-34 sur `shell/src/map/*` : classes
Tailwind sémantiques littérales (`text-ink`, `text-ink-2`, `text-ink-3`,
`bg-surface`, `bg-sunken`, `border-rule`, `border-rule-2`, `text-accent`,
`text-danger`, `text-warn`, `text-ok`, + variantes `-soft`), exposées via
le bloc `@theme inline` de `shell/src/styles/tokens.css` — pas de syntaxe
`text-[color:var(--...)]`. 193 occurrences de couleurs Tailwind brutes sur
54 fichiers hors `shell/src/map/*` au 2026-09-26 (chiffre à jour, celui du
diagnostic est périmé).

1. **`AppRuntimePage.tsx`** (244 lignes) : remplacer les imports legacy
   `ui/button`/`ui/input` par `ui/kit/Button`/`ui/kit/Input` (`ui/kit/Dialog`
   déjà utilisé), tokeniser ses 5 classes de couleur brute (`text-red-600`
   ×3, `border-slate-200`, `bg-white/90` ×2 pour les overlays d'export).
   Dans le même passage, câbler `printLayout.showLegend` (D14, règle de
   scope ci-dessus) dans l'overlay d'export (lignes ~188-202, à côté de
   `title`/`cartouche` déjà mirrorés).
2. **3 pages publiques + `DatasetDownloadButtons`** :
   `SitePublicPage.tsx`/`PublicItemPage.tsx` (1 couleur brute chacune),
   `DatasetPage.tsx` (4) + `DatasetDownloadButtons.tsx` (7, plus un
   `<button>` natif à remplacer par `ui/kit/Button`). Le "2 littéraux
   français non traduits" du diagnostic n'a pas été retrouvé (tout passe
   par `t(...)`) — ne pas relancer cette recherche, traiter comme
   already-resolved.
3. **Balayage du reste** (~50 fichiers restants) — prioriser le cluster
   `builder/widgets/*` + `builder/*Panel.tsx` (concentre ~90 des 193
   occurrences : `DataSourcePanel.tsx` 19, `form.tsx` 10, `data.tsx` 10,
   `indicator.tsx` 9, `VariablesPanel.tsx` 9, `NavigationPanel.tsx` 9,
   `chart.tsx` 7, `PipelineCanvas.tsx` 7, `DatasetDownloadButtons.tsx` 7
   déjà couvert en (2), `ActionsPanel.tsx` 7).
4. **Garde-fou non régressif** : script mirrorant `check-bundle-size.mjs`
   — grep du même motif de couleur brute sur `shell/src` (hors
   `shell/src/map/*` et tout répertoire déjà couvert par 1-3), seuil
   `.raw-color-threshold` non régressif, câblé comme `.coverage-threshold`.

## Filets anti-régression transverses

| Net | Où | Comment |
|---|---|---|
| Composant du kit posé mais jamais adopté | Test de plancher de consommateurs (hors galerie) sur `EmptyState` (SP-B1), `Toast`/`ToastProvider` (SP-B3), `Spinner`/`Skeleton`/`LoadingState` (SP-B4), `DataTable` (SP-B11) — non régressif comme `.coverage-threshold` |
| `window.confirm` réintroduit | Lint interdisant `window.confirm` hors fichiers explicitement exemptés (SP-B2) |
| Couleur Tailwind brute réintroduite hors `shell/src/map/*` | `.raw-color-threshold` (SP-B12, point 4 ci-dessus) |
| Mutation de sauvegarde sans toast de succès | Motif de test partagé : tout hook `useSave*`/`useCreate*` d'un éditeur principal doit appeler `showToast` dans son `onSuccess` (SP-B3) |
| Champ généré sans `aria-invalid`/`aria-describedby` | Test de contrat sur `FieldInput` (SP-B8), séquencé avec le test `aria-required` de SP-C1 pour éviter un double correctif sur la même signature |
| Route/onglet de builder non restaurable depuis l'URL | Pas de filet dédié proposé ici — périmètre volontairement limité aux 2 builders concernés (App/Pipeline), cf. décision de scope SP-B9 |

## Ordre d'exécution suggéré

Gains rapides d'abord (B1, B2, B3, B7 — diffs mécaniques ou centralisés en
un seul fichier), puis B5 (partage `base.ts` avec B7, à faire dans la même
fenêtre pour éviter deux passes sur le même fichier), B8, B4, B10, B9, B11,
B6 et B12 en dernier (les deux chantiers les plus larges, B6 parce qu'il
touche le routeur global et bénéficie d'un arbre stabilisé par les fixes
précédents, B12 parce que son découpage en 4 sous-tâches tolère bien d'être
étalé).
