# Spec — Vague C : polish, a11y AA, perf perçue, onboarding (6 SP)

> Périmètre : les 6 SP proposés par `docs/revue/2026-09-24-diagnostic-ui-ux.md`
> §3 "Vague C" (SP-C1→SP-C6, défauts D32/D41/D48/D34/D43/D42/D46/D47/D10/D07/
> D49/D08/D51/D54/D50/D52/D35/D36/D38/D39/D11/D12/D15/D16/D55/D56/D04).
> Recherche de code menée par 6 agents general-purpose le 2026-09-27 (résumés
> ci-dessous par tâche). Suite directe de la Vague B (12 SP, clôturée, cf.
> `CLAUDE.md` § Livré). Hors périmètre, explicitement (déjà trackés, aucune
> nouvelle action) : **D45** (REV-088, partiellement fermé), **D23**
> (GAP-82/REV-185, ouvert mais suivi séparément), **D53** (GAP-19, disclosed),
> **D27** (constat neutre, pas un défaut).

## Décisions de scope

- **SP-B12/D44/D14 (Vague B) n'a été exécuté qu'à moitié** — trouvé en
  recherche SP-C3, pas dans le diagnostic d'origine. `AppRuntimePage.tsx`
  n'a eu que ses couleurs Tailwind brutes tokenisées (commit `858b5bfe`) ;
  il importe toujours `../ui/button`/`../ui/input` legacy au lieu du kit, et
  `printLayout.showLegend` (D14) n'a jamais été câblé dans son overlay
  d'export malgré `CLAUDE.md` § Livré qui marque SP-B12 clos. Retenu :
  **finir ce chantier dans SP-C3** (même page, même fil d'investigation)
  plutôt que d'ouvrir un ticket séparé — migration `ui/button`→
  `ui/kit/Button`, `ui/input`→`ui/kit/Input`, câblage de `showLegend` dans
  l'overlay d'export (aux côtés de `title`/`cartouche` déjà mirrorés,
  ~ligne 188-202). La correction du récit `CLAUDE.md`/historique est un
  suivi documentaire à la clôture de cette vague, pas un chantier à part.
- **D34** — le diagnostic affirme à tort que `PipelinePalette.tsx`
  (REV-060) est "le même patron déjà fermé" à copier pour
  `FieldOverrides`. Vérifié faux : REV-060 corrigeait l'**ajout** d'une
  opération (palette source → canevas, remplacé par un vrai `<button>`),
  pas un **réordonnancement** de liste. Aucun précédent clavier-accessible
  de réordonnancement n'existe dans le dépôt (`grep draggable` : seulement
  ces deux fichiers). SP-C1 conçoit un nouveau motif minimal (boutons
  Monter/Descendre), pas une copie.
- **D48** — le diagnostic affirme (test clavier manuel) que le focus ne
  revient pas au déclencheur après fermeture Échap d'un `Drawer`. Lecture
  statique de `Drawer.tsx` ne trouve aucune surcharge du comportement par
  défaut de Radix (`FocusScope` restaure normalement le focus). Retenu :
  **falsifier avant de coder** — écrire le test Vitest/Testing Library
  décrit en SP-C1 en premier ; s'il passe déjà, D48 est classé
  déjà-correct (le test reste comme filet), aucun correctif de code.
- **D08** — plus profond que "livré côté cœur sans UI". `GET
  /admin/usage` existe et répond `UsageSnapshotResponse{itemCount,
  collectionCount, userCount, storageBytes}` mais **ne porte aucune
  limite configurée** — les plafonds (`max_storage_bytes_per_tenant()`
  etc.) ne sont lus que côté serveur par `check_quota_or_raise`, jamais
  exposés. Affiche "X/Y Go" nécessite d'abord un changement cœur (ajouter
  `maxItems`/`maxCollections`/`maxStorageBytes: int | null` à
  `UsageSnapshotResponse`), **puis** régénérer OpenAPI/TS (piège n°1,
  `CLAUDE.md`), **puis** le travail shell. SP-C4 couvre les trois étapes.
- **D46** — l'échelle typographique Tailwind v4 par défaut (aucune
  redéfinition dans `tokens.css`) n'a aucun palier entre `text-xs` (12px)
  et rien — remonter les 24 occurrences `text-[9px]`/`text-[10px]` vers
  `text-xs` est un bond de 20-33%. Retenu : remap mécanique vers
  `text-xs` pour les usages "texte libre" (19 occurrences, 11 fichiers) ;
  pour les badges circulaires `PipelineCanvas.tsx`/`MapSymbologyEditor.tsx`
  (8 occurrences, contrainte de taille `h-4 w-4`), **introduire un nouveau
  token** `--text-2xs` (0.6875rem/11px) dans `@theme inline` — un besoin
  répété (8 sites), pas un one-off, absorbe le palier manquant une fois.
- **D07** — pas de dépendance `cmdk` (≈82 Ko non gzippé, pèserait sur
  `.bundle-size-threshold` si elle atterrissait dans le chunk d'entrée).
  Retenu : composant maison `ui/kit/CommandPalette.tsx` réutilisant les
  primitives déjà en prod (`Dialog` + le patron de liste filtrable de
  `Combobox.tsx`), chargé en `React.lazy()` (patron déjà posé par SP-60)
  pour rester hors du chunk initial.
- **D54** — CodeMirror confirmé nécessaire (aucune lib d'éditeur de code
  existante), mais `SqlLabPage` est déjà chargée en `lazy()` (SP-60) et
  `check-bundle-size.mjs` ne mesure que le graphe d'imports **statiques**
  atteignable depuis l'entrée — CodeMirror devrait donc tomber dans le
  chunk asynchrone de la route et ne pas toucher le seuil actuel. À
  confirmer empiriquement après `npm run build` réel une fois le paquet
  installé ; ajuster `.bundle-size-threshold` seulement si la mesure le
  montre, pas préventivement.
- **D38** — le diagnostic documentait "~15" `<label>` non associés ; grep
  brut donne 248, mais l'analyse programmatique (label wrappant déjà son
  contrôle = valide en HTML/a11y sans `htmlFor`) réduit le vrai défaut à
  **1 seul site** : `builder/widgets/form.tsx:652`, où un `<label>` unique
  wrappe `<AttachmentFieldInput>` qui rend plusieurs contrôles interactifs
  (liste de pièces jointes, boutons supprimer/télécharger, `<input
  type="file">`) — association ambiguë. Scope réduit en conséquence.
- **D15** — effort réel **M**, pas **S** comme classé par le diagnostic.
  `MapEditorPage.tsx` affiche déjà une légende de **titres** de couches via
  `MapView`/`MapLegend` (le diagnostic se trompait sur un "zéro grep hit" —
  le composant est monté indirectement). Le vrai manque : la légende de
  **symbologie** (swatches couleur/catégorie/classe) n'existe que dans
  `mapWidget.tsx` (`MapSymbologyLegend`, non extrait en composant
  partagé). SP-C6 extrait ce composant et le branche dans l'éditeur
  standalone.
- **D56** — l'aperçu-avant-application des opérations copilote (doctrine
  GAP-17) n'a pas de chemin mécanique simple (nécessite un état "opérations
  en attente" avant `setDraft`, changement de flux non trivial) alors que
  le risque est déjà mitigé par Undo/Redo (SP-19) et que GAP-17 lui-même ne
  couvre que SQL Lab/requête visuelle (pas les copilotes App/Pipeline).
  Retenu : **SP-C6 ne livre que la persistance d'historique** (réutilisant
  le patron `sqlLabHistory.ts`) ; l'aperçu-avant-application reste un suivi
  non bloquant, à ouvrir séparément si un besoin produit réel apparaît.
- **D04** — le tool MCP `run_alert_rule` ne vérifie que `can(...,"read")`
  (commentaire du code : "No REST route equivalent exists"). La nouvelle
  route REST `POST /alerts/{item_id}/evaluate` durcit à `"write"` (un vrai
  déclenchement manuel mérite plus qu'une permission de lecture) ; le tool
  MCP existant n'est **pas** modifié (hors périmètre, éviter un changement
  de comportement non demandé ailleurs).

## SP-C1 (D32+D41+D48+D34) — a11y clavier/focus

**D32** — `shell/src/builder/widgets/form.tsx`, `FieldInput`. SP-B8 déjà
livré dans ce fichier (`errorId`/`errorProps`, lignes 385-386) — ajouter un
second objet `requiredProps` à côté, pas de conflit de signature :
```
const requiredProps = field.required ? { "aria-required": "true" as const } : {};
```
posé sur les 6 branches (boolean 400-408, integer/number 413-422, date
427-436, datetime 441-450, enum 455-463, texte 474-483 ; attachment 388-397
exclu, comme `validateField` l'exclut déjà). **Piège trouvé, absent du
diagnostic** : ne PAS poser l'attribut natif `required` sans ajouter
`noValidate` au `<form>` (ligne 647) dans le même correctif — sinon la
validation navigateur native court-circuite `handleSubmit`/le flux
`touched` existant, et pour la branche boolean force `checked=true` alors
que `validateField` (ligne 221) traite `false` explicite comme valide.
`aria-required` seul suffit à l'objectif réel (annonce lecteur d'écran).

**D41** — `shell/src/map/MapPopup.tsx` (`role="dialog"` ligne 42, composant
présentationnel sans Radix, positionné en `x`/`y` absolus sur une feature
carte, coexistant avec l'interaction carte derrière). Pas un bon candidat
pour `ui/kit/Dialog`/`Drawer` (modal, overlay plein écran, `FocusScope`
piégeant — contraire à l'usage actuel). Fix : `useEffect` maison au montage
— listener `keydown`/`Escape` → `onClose()` (cleanup au démontage) + focus
du premier élément focusable via une `ref` sur le conteneur (ligne 41),
`container.querySelector<HTMLElement>('button, a, [tabindex]')?.focus()`.
Pas de restauration de focus à la fermeture (déclencheur = clic sur feature
carte, cible de restauration ambiguë, hors périmètre naturel).

**D48** — `shell/src/ui/kit/Drawer.tsx` : aucune surcharge trouvée
(`onCloseAutoFocus`/`modal={false}`/`onEscapeKeyDown` : zéro occurrence
dans tout le dépôt) — Radix devrait restaurer le focus par défaut.
**Falsifier avant de coder** (`NewItemButton.test.tsx` ou nouveau
`Drawer.test.tsx`) :
```
await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
expect(screen.getByRole("dialog")).toBeInTheDocument();
await userEvent.keyboard("{Escape}");
await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
expect(document.activeElement).toBe(screen.getByRole("button", { name: "Nouveau" }));
```
Si le test passe tel quel : D48 déjà correct, le test devient le filet, pas
de correctif. S'il échoue : creuser côté jsdom (piège n°10, `hasPointerCapture`/
`PointerEvent`) avant d'imputer un vrai bug Drawer.

**D34** — `shell/src/builder/widgets/form.tsx`, `FieldOverrides` (lignes
71-84) : `draggable`/`onDragStart`/`onDrop` sans `onKeyDown`. `reorder(fromIndex,
toIndex)` (58-64) déjà générique, réutilisable telle quelle. Fix : 2 boutons
Monter/Descendre par `<li>` à côté de la poignée (87-89) :
```
<button type="button" aria-label={t("widgetForm.moveFieldUpAria", {name: f.name})}
  disabled={i === 0} onClick={() => reorder(i, i - 1)}>↑</button>
<button type="button" aria-label={t("widgetForm.moveFieldDownAria", {name: f.name})}
  disabled={i === sorted.length - 1} onClick={() => reorder(i, i + 1)}>↓</button>
```
Nouvelles clés `widgetForm.moveFieldUpAria`/`moveFieldDownAria`
(interpolant `{name}`). Aucun changement de `reorder()`/`onChange`.

**Filet** : contrat test sur `FieldInput` — un champ `required` du schéma
pose `aria-required`, pas seulement un suffixe visuel.

## SP-C2 (D43+D42) — audit a11y & mouvement

**D43** — `shell/e2e/a11y-audit.spec.ts` : 17 `page.goto(` confirmés,
`routes.tsx` déclare 29 routes, 12 non couvertes (statiques :
`/bookmarks`, `/reports`, `/pipelines/new`, `/reports/new`,
`/admin/compliance`, `/internal/kit-gallery` [dev-only], `/settings` ;
dynamiques : `/apps/:pk/:pageId?` [AppRuntimePage — la vraie priorité],
`/embed/:token`, `/public/items/:pk`, `/public/datasets/:collectionId`,
`/datasets/visual-query/:pipelinePk/edit` [seule sans fixture existante]).
Précédent directement réutilisable : `shell/src/shell/routeReachability.test.ts`
(filet D01/GAP-80) fait déjà `readFileSync(routes.tsx)` +
`matchAll(/<Route\s+path="([^"]+)"/g)`. Fix : nouveau
`a11yAuditCoverage.test.ts` sur le même patron — extraire les routes,
extraire les `page.goto(...)`, convertir `:segment`→regex, échouer sur
toute route non couverte et non listée dans une allowlist explicite
(`/internal/kit-gallery` seule exemption anticipée). Fixtures : zéro mock
nouveau pour AppRuntimePage (`mocks.ts:560-565` anticipe déjà le split
`?mode=runtime`, `e2e/publication.spec.ts:26` fait déjà `goto("/apps/9")`
sans setup dédié) ; les 10 autres routes ont déjà une fixture E2E à copier
(`settings-page.spec.ts:13`, `compliance-admin.spec.ts:29`,
`embed.spec.ts:69`, `bookmarks.spec.ts:268`) ; seule
`/datasets/visual-query/:pipelinePk/edit` demande un fixture neuf.

**D42** — Zéro `prefers-reduced-motion`. Surface CSS confirmée : 7 fichiers
(`PipelineCanvas.tsx:95`, `LoadingState.tsx:8`, `Skeleton.tsx:5`,
`Spinner.tsx:7` en `animate-*` ; `Switch.tsx:31`, `Tree.tsx:48`,
`Progress.tsx:22` en `transition-transform`). Aucun Dialog/Drawer/Toast/
Popover/Menu/Select/Combobox/Tooltip n'a de transition d'ouverture — pas
d'exemption à prévoir. Fix CSS : une règle globale
`@media (prefers-reduced-motion: reduce) { *, *::before, *::after {
animation-duration: 0.01ms !important; transition-duration: 0.01ms
!important; } }` dans `shell/src/styles/tokens.css`. **Insuffisant pour la
carte** : `map.flyTo()`/`fitBounds()` (maplibre-gl) sont pilotés en JS,
invisibles à une media query CSS. `MapView.tsx:1290-1306` bascule déjà
conditionnellement `flyTo`→`jumpTo` (contournement d'une régression de
pitch/terrain) — réutiliser cette même primitive "instantanée", déclenchée
sur `window.matchMedia("(prefers-reduced-motion: reduce)").matches`.

**Filet** : la liste de routes dérivée de `routes.tsx` dans
`a11yAuditCoverage.test.ts` est elle-même le filet (coverage ne peut plus
dériver silencieusement).

## SP-C3 (D46+D47+D10, + finition SP-B12/D14) — cohérence design

**D46** — Grep à jour : 79 `text-\[...\]` au total, dont 58 sont des
couleurs (`text-[var(--gs-color-*)]`, hors périmètre ici). Vraies tailles
arbitraires : **24 occurrences** (23× `text-[10px]` + 1× `text-[9px]`) sur
14 fichiers. Remap mécanique vers `text-xs` (12px) pour 19 occurrences
"texte libre" (`form.tsx`, `StatusBar.tsx`, `navigation.tsx`,
`ExplorerDrawer.tsx`, `DatasetDownloadButtons.tsx`, `data.tsx`,
`gallery.tsx`, `index.tsx`, `PipelinePreviewMap.tsx`, `NavigationPanel.tsx`,
`PipelineNodeInspector.tsx`). Nouveau token `--text-2xs` (0.6875rem/11px,
`@theme inline` de `tokens.css`) pour les 8 occurrences en contrainte
`h-4 w-4` (`PipelineCanvas.tsx` ×5, `MapSymbologyEditor.tsx` ×3) —
vérifier à l'œil (screenshot) qu'aucun débordement visuel n'apparaît.
Garde-fou : répliquer le patron réel de ce dépôt — **pas** un fichier
`.threshold` numérique (celui de la spec Vague B, `.raw-color-threshold`,
n'existe pas) mais `shell/scripts/check-raw-colors.mjs` (script autonome,
tolérance zéro, pragma `// gs-raw-color-ok: <raison>`), câblé dans
`npm run lint`. Nouveau `check-arbitrary-text-size.mjs` sur le même
patron.

**D47** — `shell/src/pages/AppBuilderPage.tsx` : toggle Édition/Aperçu
(ligne 397, `variant={mode === "edit" ? "default" : "outline"}`) et bouton
Enregistrer (567-576, aucun `variant` → `default` CVA par défaut) tous
deux `default` (bg-accent plein) simultanément visibles — pas dans la même
barre mais dans le même écran. 3e occurrence du même idiome sur les
boutons de largeur d'écran (419-427). Fix : démoter le toggle mode et les
boutons de largeur vers un style segmented-control (`outline` +
surbrillance `bg-sunken` sur l'état actif, jamais `bg-accent` plein) ;
Enregistrer reste le seul `default` légitime (action ponctuelle
intentionnelle).

**D10** — Les 4 pages sont toutes mélangées `ui/*`/`ui/kit/*` :
`CatalogPage.tsx` (`ui/ItemCard` legacy + `ui/kit/{Input,Button,Panel,
EmptyState}`), `ItemDetailPage.tsx` (`ui/kit/{Button,Panel}` +
`ui/MetadataForm`/`ui/ThumbnailUpload` legacy), `DatasetEditPage.tsx`
(`ui/kit/{Button,Panel,LoadingState}` + `ui/MetadataForm` legacy),
`AppRuntimePage.tsx` (cf. décision de scope ci-dessus — `ui/button`/
`ui/input` legacy + `ui/kit/Dialog`). Fix : migrer les imports legacy
restants vers le kit sur les 4 pages ; legacy commun à porter :
`ui/ItemCard`, `ui/MetadataForm`, `ui/ThumbnailUpload`, `ui/button`,
`ui/input`. Clés i18n orphelines : **aucun script de ce dépôt ne les
détecte** (`check-i18n-coverage.mjs` détecte des chaînes françaises en
dur, pas des clés inutilisées) — le "4 clés" du diagnostic est invérifiable
avec l'outillage actuel ; traiter comme non prouvé, ne pas chasser ce
chiffre sans nouvel outillage (hors périmètre de cette tâche).

**Finition SP-B12/D14** : dans le même passage sur `AppRuntimePage.tsx`,
câbler `printLayout.showLegend` dans l'overlay d'export (à côté de
`title`/`cartouche` déjà mirrorés, ~lignes 188-202) — referme réellement
D14/SP-B12 après sa découverte à moitié faite.

## SP-C4 (D07+D49+D08) — onboarding

**D07** — `ui/kit/Kbd.tsx` sans consommateur de production (confirmé,
seul hit hors test = galerie interne). Composant maison
`ui/kit/CommandPalette.tsx` (cf. décision de scope) réutilisant `Dialog`+
patron `Combobox.tsx` (navigation clavier ArrowUp/Down/Enter/Escape déjà
éprouvée, lignes 61-146). Commentaire ⌘K trouvé à
`shell/src/auth/capabilities.ts:11` (chemin réel, pas
`shell/src/capabilities.ts`). Actions v1 : les 8 domaines de
`navigableDomains(profile)` (`auth/capabilities.ts:33-120`) + "Nouvel
élément" réutilisant la garde privilège×capacité déjà dans
`NewItemButton.tsx` + les 7 destinations `SettingsNav.tsx:12-37` filtrées
par privilège. Raccordement : `shell/src/shell/AppLayout.tsx` (calcule déjà
`profile` une fois pour toute route protégée, lignes 34-46) — `useEffect`
sur `window keydown`, `(e.metaKey || e.ctrlKey) && e.key === "k"`, montage
de `<CommandPalette>` juste avant/après `<TopBar/>` (ligne 55). Bouton
visible dans `TopBar.tsx` (8-20, à côté de `NewItemButton`) avec
`<Kbd>⌘K</Kbd>` comme indice — donne enfin un vrai consommateur à `Kbd`.

**D08** — Cf. décision de scope (changement cœur requis en premier).
1. Cœur : `core/app/quotas/routes.py` (`GET /admin/usage`) — étendre
   `UsageSnapshotResponse` avec `maxItems`/`maxCollections`/
   `maxStorageBytes: int | null`, peuplés depuis `max_items_per_tenant()`/
   `max_collections_per_tenant()`/`max_storage_bytes_per_tenant()`
   (`core/app/quotas/service.py:141-153`) dans `get_usage()`.
2. Régénérer OpenAPI + types TS (piège n°1 CLAUDE.md, incantation
   `PYTHONPATH=.` + `CORE_SECRETS_MASTER_KEY`).
3. Shell : nouveau hook `useQuotaUsage()` (`shell/src/api/domains/`, sur le
   modèle de `usage.hooks.ts`), site = `shell/src/pages/
   AdminInfrastructurePage.tsx` (route `/admin/infrastructure`, **pas**
   `UsagePage.tsx` — même privilège `settings.instance.manage` que `GET
   /admin/usage`, déjà dans `SettingsNav`, déjà une liste d'infos
   d'instance ; `UsagePage.tsx` porte un tout autre privilège `tasks.view`
   et un tout autre concept). Insertion après le bloc MinIO (~ligne 79) :
   3 lignes/barres (items, collections, stockage), repli "pas de limite
   configurée" si `max*` est `null`.

**D49** — Composant à réutiliser : `ui/kit/Popover.tsx` (contenu riche),
**pas** `Tooltip.tsx` (déclenché au survol seul, inutilisable au tactile —
contredirait D16). Déclencheur : `IconButton` + icône `HelpCircle`
(`lucide-react`, déjà dépendance directe, déjà consommée ailleurs). 4
points d'insertion : CEL (`PropsPanel.tsx:35-36`, label `visibleWhenLabel`
avant le `<textarea>`) ; AppConfig (`AppBuilderPage.tsx:465-467`, en-tête
`propertiesLabel` avant `<PropsPanel>`) ; pipeline (`PipelineBuilderPage.tsx:
351-352`, `<h2>` du titre, même conteneur flex que Undo/Redo) ; SQL Lab
(`SqlLabPage.tsx:92`, `<h1>SQL Lab</h1>`). **Trouvaille annexe, à corriger
dans le même geste** : ce titre `<h1>SQL Lab</h1>` est un littéral jamais
passé par `t(...)` — un oubli de `lint:i18n` distinct de D49/D50, à
corriger puisqu'on touche déjà cette ligne.

**Filet** : plancher de consommateurs de production sur `Kbd`/`Popover`
utilisé pour l'aide (au moins 4 sites après cette SP).

## SP-C5 (D51+D54) — SQL Lab

**D51** — `SqlLabPage.tsx:110-114` affiche `(run.error as Error).message`
brut ; `runAnalyticsSql` (`api/domains/exportsIngestion.ts:13-35`) ne passe
**pas** par `request()`/`ApiError` (SP-B5) — chemin d'erreur non centralisé
confirmé, pas juste "pas de ligne/colonne". Cœur (`core/app/features/
routes.py:463-519`) répond en 400 `{"errors":[{"field":"sql","code":
"sql_error","message": str(exc)}]}`, `str(exc)` = message DuckDB brut.
Format DuckDB vérifié empiriquement : `<Catégorie> Error: <message>` puis
`\n\nLINE <n>: <sql tronqué>\n<espaces>^` (position du `^` = colonne).
Fix : nouveau `parseDuckDbError(message: string)` (regex sur `/^LINE
(\d+): (.*)$/m` + position du `^`) extrayant `{category, message, line,
column, sqlSnippet}`, fallback = message tel quel si la regex ne matche
pas ; affichage dans un cadre stylé (composant `ui/kit` à identifier/créer,
aucun "erreur encadrée" existant à réutiliser tel quel). **Corriger en même
temps** : brancher `runAnalyticsSql` sur `ApiError`/`problem+json` pour les
statuts non-400 (actuellement `"Request failed: 500 POST /analytics/sql"`
générique), cohérent avec SP-B5/D22.

**D54** — `<textarea>` brut confirmé (`SqlLabPage.tsx:95-100`). Aucune
dépendance CodeMirror (`@uiw/react-codemirror` + `@codemirror/lang-sql`,
choix le plus courant). Autocomplétion sans nouvelle route : tables via
`useCollectionsAdmin` (déjà appelé ligne 36, activé seulement si
`copilotEnabled` — **à activer inconditionnellement** pour
l'autocomplétion), noms réels = `col.id` (slug, pas le titre affiché) ;
colonnes via `useCollectionSchema(collectionId)` (déjà consommé ailleurs)
→ `fields[].name`. Pas de hook batch existant — décision à prendre dans le
plan : appel lazy par table au moment de la frappe, ou préchargement des
schémas des collections visibles (nombre modeste par tenant). Bundle :
cf. décision de scope (probablement hors seuil grâce au lazy-loading
existant, à confirmer empiriquement après build réel).

## SP-C6 (D50+D52+D35+D36+D38+D39+D11+D12+D15+D16+D55+D56+D04) — cohérence texte & finitions carte

**D50** — Pas de react-i18next, `t()` (`i18n/index.ts:14-21`) = simple
`.replace`. ≥5 clés grammaticalement fausses confirmées
(`catalog.count`, `datasetPage.featureCount`,
`widgetDatasetCard.featureCount`, `layerPicker.featureCountTemplate`,
`importFile.layerOptionTemplate`, toutes `catalog.fr.ts`). 2 conventions
concurrentes (plurale nue vs suffixe `(s)`) — trancher une convention
unique dans le plan. `useDocumentMeta` : présent `SitePublicPage.tsx:6,
32-38`, absent `PublicItemPage.tsx` (confirmé) — ajouter sur le même
patron.

**D52** — Zéro `clipboard.writeText` confirmé. 2 sites exacts dans
`ShareForm.tsx` : lien de partage (116-121, `<span>` brut) et snippet
embed (122-131, `<textarea readOnly>`) — bouton icône copier à droite de
chacun, `navigator.clipboard.writeText` + repli `document.execCommand`.

**D35** — Pas de composant `CelEditor` dédié ; erreur brute via
`builder/expr.ts:21-25` (`validateExpression().errors.join("; ")`,
messages `cel-js` techniques/anglais) à 4 sites (`PropsPanel.tsx:44-48`,
`NavigationPanel.tsx:100`, `ActionsPanel.tsx:77`, `PopupEditor.tsx:30`).
Affichage `fr-FR` : 2 points d'insertion `Intl.NumberFormat`/
`Intl.DateTimeFormat` — `cellValue()` (`widgets/data.tsx:39`, `String(value)`
brut) et `popupTemplate.ts:37-38` (stringify brut), selon le type de champ
du schéma. Saisie native (`<input type="number"/date"/datetime-local">`,
`form.tsx`) reste hors périmètre formatage.

**D36** — `AttachmentFieldInput` (`form.tsx:245-293`) : un seul booléen
`uploading` (262). Fix : `Record<string, "pending"|"uploading"|"done"|
"error">` par nom de fichier, mis à jour à chaque étape de la boucle
presign→PUT→confirm (269-286). Pas de vrai pourcentage octet-par-octet
sans passer à `XMLHttpRequest` pour l'event `progress` — hors périmètre,
statut discret par fichier suffit.

**D38** — Vrai défaut = **1 site** (cf. décision de scope) :
`form.tsx:652`, `<label>` unique wrappant `<AttachmentFieldInput>`
(plusieurs contrôles interactifs descendants). Fix : séparer visuellement
le texte de label (élément indépendant, `id` stable) de
`<AttachmentFieldInput>`, relier par `aria-labelledby` sur le conteneur de
la liste plutôt qu'un wrapping `<label>`.

**D39** — `builder/pipeline/SecretParamSelect.tsx` : 23 champs sans
`placeholder` (name 220, type 230, location 248, key 260, value 269,
token 282, username 295/451, password 304/460, tokenUrl 318, clientId 327,
clientSecret 336, dsn 353, awsAccessKeyId 366, awsSecretAccessKey 375,
endpointUrl 385, accountName 398, accountKey 407, serviceAccountInfo 420,
host 432, port 441, fromAddress 470). Fix : `placeholder={t("secretParamSelect.
xxxPlaceholder")}` sur chacun (ex. dsn → `postgresql://user:pass@host:5432/db`).

**D11+D12** — `builder/widgets/mapWidget.tsx` : `availableFields={[]}`
codé en dur (225 symbologie, 279 popup) alors que `schemaQuery` (194-198)
est déjà chargé juste au-dessus pour `attachmentFields`. Fix : répliquer
`LayersPanel.tsx:58-64,105-111` (`schema.data?.fields.filter(f => f.type
!== "attachment").map(f => f.name) ?? []`). Centre/zoom : `MapConfig.view`
codé en dur (371-372, `center:[2.4,46.6], zoom:5`) — ajouter 2 champs
numériques (ou bouton "Utiliser la vue actuelle") près de `CameraControls`
(216-222) dans le `PropsPanel`, stockés dans `props.center`/`props.zoom`,
lus au lieu du littéral (l'auto-cadrage D18 écrase déjà ça au chargement
via `fitBounds`, ceci ne fixe qu'une vue par défaut alternative).

**D15** — Cf. décision de scope (effort réel M). `MapLegend` (titres)
déjà rendu dans `MapEditorPage.tsx` via `MapView`. Manque réel :
`MapSymbologyLegend` (swatches, `mapWidget.tsx:46...436`) n'existe que
là. Fix : extraire en composant partagé (+ `buildLegend`), appeler par
couche visible dans `MapEditorPage.tsx` (onglet "map", 203-216) — domaine
couleur/taille déjà calculable via `LayerSymbologyEditor`
(`LayersPanel.tsx`).

**D16** — Aucune vérification dynamique existante, aucun projet mobile
dans `playwright.config.ts`. Fix : nouveau
`shell/e2e/map-touch.spec.ts` + projet `devices["iPhone 13"]`/
`hasTouch:true` ; scénarios pinch-zoom simulé, tap→popup, taille de cible
barre de mesure (`getBoundingClientRect ≥ 24×24px`). Fix de code seulement
si un vrai défaut est trouvé en exécutant ce test.

**D55** — `PipelineBuilderPage.tsx:79` calcule `readOnly` mais ne le passe
jamais à `<PipelineCanvas>` (378) ; `PipelineCanvasInner` (`PipelineCanvas.tsx:
267-297`) n'a aucune prop `readOnly`. Fix : ajouter `readOnly?: boolean` à
`PipelineCanvasInner`, gater `onConnect`/`handleNodesChange`
(suppression/ajout de zone) + boutons Undo/Redo (355-359) + raccourci
clavier Ctrl+Z (140-154) derrière `!readOnly`.

**D56** — `CopilotPanel.tsx` : zéro persistance, `handleClientOps` (49-57)
applique directement via `setDraft`. Cf. décision de scope (aperçu
hors périmètre). Fix : historique seul, réutilisant le patron
`shell/src/lib/sqlLabHistory.ts` (`readSqlHistory`/`appendSqlHistory`, 20
entrées max, try/catch silencieux) avec une nouvelle clé
`geostudio.copilot.history`.

**D04** — `AlertRuleEditor.tsx` : aucun bouton (seuls delete 34-42, create
216-225). Mécanisme existant : tool MCP `run_alert_rule`
(`core/app/mcp/tools/alerts.py:99-124`) — `create_evaluation`→`commit`→
`evaluate_alert_task.defer(...)`, commentaire explicite "No REST route
equivalent exists". Fix : nouvelle route `POST /alerts/{item_id}/evaluate`
(`core/app/alerts/routes.py`) répliquant cette séquence, durcie à `can(...,
"write")` (cf. décision de scope — le tool MCP reste inchangé à `"read"`) ;
bouton "Exécuter maintenant" dans `AlertRuleEditor.tsx` appelant la
nouvelle route via `ItemClient`.

## Filets anti-régression transverses

| Net | Où | Comment |
|---|---|---|
| Champ généré sans `aria-required` | Test de contrat sur `FieldInput` (SP-C1) | Contrat `required` schéma → `aria-required` posé |
| Focus non restauré après Échap d'un dialogue | `Drawer.test.tsx` (SP-C1) | Test de falsification — reste comme régression même si D48 s'avère déjà correct |
| Route de `routes.tsx` non auditée par axe-core | `a11yAuditCoverage.test.ts` (SP-C2) | Liste dérivée mécaniquement de `routes.tsx`, même patron que `routeReachability.test.ts` |
| `text-[Npx]` arbitraire réintroduit hors token typographique | `check-arbitrary-text-size.mjs` (SP-C3) | Même patron que `check-raw-colors.mjs` : tolérance zéro + pragma d'exemption |
| Palette de commandes/aide contextuelle posée puis jamais adoptée | Plancher de consommateurs sur `Kbd`/`Popover` (SP-C4) | Même famille que les planchers de consommateurs de la Vague B |
| `window.confirm`/couleur brute/toast manquant réintroduits | Déjà couverts par les filets Vague B (`check-raw-colors.mjs`, lint `window.confirm`) | Pas de nouveau filet — vérifier simplement la non-régression |

## Ordre d'exécution suggéré

C1 et C2 d'abord (a11y mesurable, filets les plus proches d'une porte CI,
peu de dépendances croisées). C3 ensuite (finit au passage SP-B12/D14,
doit se faire avant que d'autres tâches ne re-touchent `AppRuntimePage`).
C4 (dépend d'un aller-retour cœur pour D08 — régénération OpenAPI/TS à ne
pas oublier) et C5 (CodeMirror, chantier isolé sur `SqlLabPage`) peuvent se
faire en parallèle. C6 en dernier — le plus large (13 défauts) mais le
plus mécanique/indépendant, bénéficie d'un arbre stabilisé par les
correctifs précédents (notamment D51/SP-C5 sur le même fichier
`SqlLabPage.tsx` que l'aide contextuelle D49/SP-C4 — séquencer pour éviter
un conflit sur le même `<h1>`).
