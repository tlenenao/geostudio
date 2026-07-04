# GeoStudio SP-0d — Builder no-code (parité ArcGIS Experience Builder)

> Design / spec macro. Arc SP-0d du shell GeoStudio (après SP-0c). Livre l'**éditeur no-code**
> qui compose des applications et dashboards par glisser-déposer de widgets sur un canevas,
> les lie à des sources de données, câble des actions widget→widget, et les **publie** via un
> lecteur runtime. Objectif de périmètre : **aussi complet qu'ArcGIS Experience Builder**.
>
> Date : 2026-07-03
> Statut : design validé — prêt pour `writing-plans` (plan de SP-0d.1 en premier).
> Prérequis : SP-0a (Builder Service), SP-0b (shell : item-client, catalogue, ItemActions,
> NewItemButton), SP-0c (MapView + éditeur de carte) livrés.

---

## 1. Contexte et périmètre

SP-0b/0c ont livré le shell, la gestion d'items et l'éditeur de carte. SP-0d livre le **corps
principal** de GeoStudio : le **builder** qui crée sites/apps/dashboards sans code, équivalent
d'ArcGIS Experience Builder (EB). Un utilisateur :

- part d'une app/dashboard vide ou d'un template ;
- **dépose des widgets** sur un canevas en grille responsive ;
- règle leurs propriétés dans un panneau ;
- **lie** les widgets à des **sources de données** (couches features, statistiques) ;
- **câble des actions** widget→widget (« quand la carte bouge → filtre la liste ») ;
- **prévisualise**, puis **publie** ; l'app publiée s'affiche via un lecteur runtime à `/apps/:pk`.

Le tout réutilise le `BuilderConfig` du Builder Service (SP-0a), déjà conçu par anticipation :
`layout{grid, breakpoints, items[{widget,x,y,w,h,props}]}`, `dataSources`, `messages`, `theme`.

**Hors périmètre (couvert par d'autres arcs) :** l'éditeur de carte lui-même (SP-0c, réutilisé
comme *widget* Carte) ; le CMS/sites de contenu (SP-1) ; l'administration/identité (GeoNode/
Keycloak) ; le déploiement infra (IMPLEMENTATION_PLAN). Édition collaborative temps réel : hors
périmètre.

## 2. Décisions de cadrage (validées)

| Sujet | Décision |
|---|---|
| Runtime | **Renderer config-driven dans le shell** : un seul moteur `AppRenderer(config, mode)` en modes `edit`/`preview`/`runtime` ; app publiée en lecture seule à `/apps/:pk`. Export statique : éventuellement plus tard, hors périmètre initial. |
| Layout | **Grille responsive** : étend le schéma existant (grid `x/y/w/h` + `breakpoints`) ; drag & resize sur grille, édition par breakpoint. |
| Actions inter-widgets | **Pilier central, phasé** : framework triggers→actions (`messages`) livré dans une sous-phase dédiée (SP-0d.3). |
| Stratégie | **Tranche verticale d'abord** : SP-0d.1 = moteur + canvas + 3 widgets statiques + runtime, pour prouver la boucle éditer→publier→afficher ; puis élargissement. |
| Tests | Libs lourdes (grille, charts, MapLibre/Deck) **mockées en unitaire** ; MSW ; **Playwright rendu réel** pour canvas/carte. |

## 3. Modèle de rendu — `AppRenderer`

Un unique moteur rend un `BuilderConfig` en trois modes :

- **`edit`** — canvas éditable : sélection, déplacement/redimensionnement sur grille, chrome
  d'édition (poignées, contour, palette, panneaux). Émet des mutations du *draft*.
- **`preview`** — app interactive (data + actions actives) **sans** chrome d'édition.
- **`runtime`** — app publiée en lecture seule (identique à `preview` mais chargée depuis le
  config persisté, sans état d'édition).

```ts
type RenderMode = "edit" | "preview" | "runtime";
function AppRenderer(props: {
  config: BuilderConfig;
  mode: RenderMode;
  onChange?: (config: BuilderConfig) => void; // requis en mode edit
  selectedId?: string;
  onSelect?: (id: string | null) => void;
}): JSX.Element;
```

`AppRenderer` monte le `GridCanvas` (layout) + un `ActionBus` (contexte runtime) + le contexte
de données. En `edit`, il route les mutations vers `onChange` (draft). Le même composant sert
l'éditeur, la preview et le runtime → zéro divergence de rendu.

## 4. Modèle de données (extensions `BuilderConfig`, additives)

Le schéma actuel (SP-0a) : `version, kind, theme{}, dataSources[], layout{type:"grid",
breakpoints{}, items[{widget,x,y,w,h,props}]}, messages[{from,event,to,action}], map`.

SP-0d ajoute (par sous-phase, toujours additif, jamais de rupture) :

- **`LayoutItem.id`** : identifiant stable du widget (nécessaire à la sélection et au routage des
  actions). *(SP-0d.1)*
- **`LayoutItem.layouts`** : positions par breakpoint `{ [bp: string]: {x,y,w,h} }` ; `x/y/w/h`
  restent la position par défaut/desktop. *(SP-0d.5)*
- **`DataSource`** déjà présent (`id,type,service,layer,query`) ; SP-0d le remplit et le
  consomme. *(SP-0d.2)*
- **`messages[]`** déjà présent (`from,event,to,action` + payload optionnel) ; SP-0d le remplit
  via l'`ActionsPanel`. *(SP-0d.3)*
- **`pages[]`** : liste de pages, chacune avec son `layout` ; `variables[]` : état partagé
  runtime. *(SP-0d.5)*

Chaque extension est introduite dans sa sous-phase avec migration/validation côté Builder Service
(Pydantic, valeurs par défaut → configs existants restent valides).

**Pas d'extension `BuilderConfig` pour SP-0d.6.** L'état de publication est porté par le champ
`is_published` déjà natif à la ressource GeoNode (déjà utilisé en lecture par `listItems`'s
`scope: "public"` filter) — pas par une nouvelle propriété de `BuilderConfig`, pour éviter deux
sources de vérité potentiellement divergentes (GeoNode vs Builder Service) sur un même item.

## 5. Registre de widgets & SDK

Chaque widget est décrit par une **définition** enregistrée dans un registre. Ceci reflète la forme
réellement implémentée depuis SP-0d.1–0d.5 (le bloc de type qui apparaissait ici avant SP-0d.7 avait
divergé de l'implémentation — `icon`/`actions`/`bus`/`navigate` notamment ; corrigé) :

```ts
type WidgetContext = {
  mode: RenderMode;
  data?: DataSourceState;            // résolu automatiquement si props.dataSourceId est défini
  bus?: ActionBus;
  navigate?: (pageId: string) => void;
  pages?: Page[];
  variables?: Record<string, string>; // valeurs courantes, lecture seule côté widget
  widgetId?: string;
};
type WidgetDefinition<P extends Record<string, unknown> = Record<string, unknown>> = {
  type: string;                      // ex. "text", "image", "map", "list", "chart", "filter"
  label: string;
  icon?: ReactNode;                  // déclaré, jamais consommé par WidgetPalette aujourd'hui
  defaultProps: P;
  defaultSize: { w: number; h: number };
  events?: readonly string[];        // noms d'événements déclarés (émis via ctx.bus?.emit)
  actions?: readonly string[];       // noms d'actions déclarées ; le widget les enregistre lui-même
                                      // via useBusAction(ctx.bus, ctx.widgetId, name, handler)
  PropsPanel: (p: { props: P; onChange: (props: P) => void; dataSources: DataSource[] }) => ReactNode;
  Component: (p: { props: P; ctx: WidgetContext }) => ReactNode;
};
function registerWidget(def: WidgetDefinition): void;
function getWidget(type: string): WidgetDefinition | undefined;
function listWidgets(): WidgetDefinition[];
```

Le registre est déjà, de fait, le point d'extension : `WidgetPalette`/`WidgetHost`/`PropsPanel`/
`ActionsPanel` ne font aucune distinction par `type` de widget — n'importe quelle définition
enregistrée avant leur montage s'intègre automatiquement partout, sans toucher au cœur. **SP-0d.7**
ne change donc pas ce mécanisme ; il le documente et le stabilise :

- **Contrat documenté et stable.** Un module d'export unique (ex. `shell/src/builder/sdk.ts`)
  réexporte tout ce qu'un widget a besoin d'importer aujourd'hui via des chemins relatifs profonds
  (`WidgetDefinition`, `WidgetContext`, `registerWidget`, `useBusAction`, `useSetFilter`,
  `useVariables`) — un seul point d'import stable plutôt que `../registry`/`../ActionBusContext`/
  `../DataContext`/`../VariablesContext` dispersés.
- **Enregistrement tiers = à la compilation, pas à l'exécution.** Un widget « brique additionnelle »
  est un module TS/React qui appelle `registerWidget(...)` avant le montage de l'app — que ce module
  vive dans ce dépôt ou dans un paquet npm importé statiquement. Pas de chargement dynamique d'un
  bundle hébergé séparément (le dépôt n'a ni monorepo ni infrastructure de type module federation) ;
  reporté à une évolution ultérieure si un jour nécessaire.
- **Garde-fou léger contre les collisions.** `registerWidget` avertit (`console.warn`, jamais
  d'exception) si un `type` déjà enregistré est réécrit — la doc recommande de préfixer les types
  non natifs (`"acme.monWidget"`) pour éviter une collision avec un futur widget natif ou un autre
  tiers. Comportement inchangé pour tous les widgets natifs existants.
- **`PropsPanel` reste libre.** Le contrat ne fixe que la signature de fonction ; aucun composant de
  champ partagé n'est imposé (aucun widget natif n'utilise `shell/src/ui/` aujourd'hui — cohérent
  avec l'existant plutôt qu'une nouvelle convention à faire adopter rétroactivement).
- **Widget d'exemple.** Un widget de démonstration, enregistré depuis un module clairement séparé
  des widgets natifs (pas dans `shell/src/builder/widgets/`), n'important *que* le barrel `sdk.ts` —
  preuve que la surface exportée est suffisante et qu'aucun import relatif profond n'est requis.

## 6. Composants (shell)

- **`AppRenderer`** (§3) — moteur 3-modes.
- **`GridCanvas`** — surface de grille responsive 12 colonnes. En `edit` : drag depuis la palette,
  déplacement/redimensionnement, snap, sélection ; sinon rendu statique. Interface :
  `GridCanvas({ items, breakpoint, editable, selectedId, onLayoutChange, onSelect, renderItem })`.
- **`WidgetHost`** — rend un `LayoutItem` via `getWidget(item.widget)`, fournit le `WidgetContext`
  (données résolues + `bus` + `navigate`), isole les erreurs d'un widget (un widget en échec
  n'abat pas l'app).
- **`WidgetPalette`** — liste `listWidgets()`, éléments déposables sur le canvas.
- **`PropsPanel`** — rend le `PropsPanel` de la définition du widget sélectionné ; écrit `props`.
- **`DataSourcePanel`** *(0d.2)* — CRUD des sources de données de l'app (choix service/couche/req).
- **`ActionsPanel`** *(0d.3)* — édite `messages` : choisir un événement d'un widget source → une
  action d'un widget cible.
- **`ThemePanel`** *(0d.5)* — édite `theme` (couleurs, typo, espacements) appliqué par le renderer.
- **`PageManager`** *(0d.5)* — gère `pages[]` (ajouter/renommer/supprimer/ordonner) + navigation.
- **`BuilderToolbar`** — bascule de mode (edit/preview), bascule de breakpoint, **Enregistrer**,
  **Publier**, retour catalogue.
- **`AppBuilderPage({ pk })`** — assemble palette + `AppRenderer(edit)` + panneaux + toolbar ;
  charge le config (`getAppConfig`), tient un *draft* local, sauvegarde (`saveAppConfig`).
- **Route runtime** — `/apps/:pk` → charge le config publié → `AppRenderer(runtime)`.

## 7. Sources de données

`DataSource{ id, type, service, layer, query }` résolue par l'`item-client` (façade) :

- **features** — pg_featureserv `/collections/{layer}/items` (GeoJSON) filtré par `query`.
- **statistics** — agrégations (count/sum/avg/group-by) via un endpoint de stats (best-effort,
  confiné à la façade, défini par les mocks ; ajusté contre le service réel).
- **static** — données inline (listes/tables de démonstration).

Le contexte de données de l'`AppRenderer` résout chaque `DataSource` (via TanStack Query),
expose l'état `{ loading, error, records }` aux widgets liés. Un widget se lie par
`props.dataSourceId` + mappages de champs. Un filtre (SP-0d.3) modifie le `query` d'une source →
invalidation → refetch → widgets liés se rafraîchissent.

## 8. Framework d'actions (`ActionBus`) — pilier

- **Runtime** : `ActionBus` = petit bus d'événements par instance d'app. Les widgets **émettent**
  des événements (`bus.emit(widgetId, event, payload)`) et **exposent** des actions
  (`bus.register(widgetId, action, handler)`). À l'init, l'`AppRenderer` lit `config.messages` et
  câble chaque `{from,event → to,action}` : à l'émission d'un event, il invoque l'action cible.
- **Triggers** (exemples) : `map.extentChanged`, `list.itemSelected`, `filter.changed`,
  `button.clicked`.
- **Actions** (exemples) : `dataSource.setFilter`, `map.flyTo`, `map.highlight`,
  `page.navigate`, `variable.set`.
- **Éditeur** : `ActionsPanel` liste les widgets, leurs events/actions déclarés, et compose les
  `messages` visuellement (« Quand *Carte*.extentChanged → *Liste*.setFilter »).
- **Variables** *(0d.5)* : état partagé (`variables[]`) lisible/écrivable par les actions, pour
  des interactions plus riches.

## 9. Système de layout (grille responsive)

- Grille **12 colonnes**, hauteur en lignes ; chaque `LayoutItem` a `x/y/w/h` (défaut) et, à
  partir de 0d.5, `layouts[bp]` par breakpoint (`sm/md/lg`).
- Éditeur : glisser depuis la palette crée un item à `defaultSize` ; déplacement/redimensionnement
  met à jour `x/y/w/h` (ou `layouts[bp]` selon le breakpoint courant) ; snap à la grille.
- Rendu responsive : le renderer choisit `layouts[bp]` selon la largeur, retombe sur `x/y/w/h`.
- Décision d'implémentation : brique de grille légère maison (interface `GridCanvas`) pour éviter
  une dépendance lourde ; `react-grid-layout` reste une option de repli documentée si la brique
  maison s'avère insuffisante. Le choix est tranché dans le plan de SP-0d.1.

## 10. Runtime & routage

- **Édition** : `/apps/:pk/edit` → `AppBuilderPage`. Ouvrir une app depuis le catalogue/détail
  route les items `app`/`dashboard` vers l'éditeur (comme SP-0c route les `map` vers `/maps/:pk`).
- **Runtime** : `/apps/:pk` → `AppRenderer(runtime)` sur le config chargé (`getAppConfig`), rendu
  **sans** le chrome `AppLayout` (pas d'en-tête GeoStudio, pas de nav) — c'est déjà « ce que voit
  l'utilisateur final », donc c'est aussi, sans URL ni route séparée, la vue embed/iframe (§ci-
  dessous). Dashboards : même moteur, layout dense.
- `NewItemButton` crée déjà `app`/`dashboard` (SP-0b) ; après création on navigue vers
  `/apps/:pk/edit`.
- **Accès public (SP-0d.6).** Aujourd'hui, `RequireAuth` englobe toute l'app (`App.tsx`) : aucune
  route ne rend pour un visiteur anonyme, et le Builder Service ne vérifie *aucune* permission sur
  `GET /configs/by-item/:id` — n'importe quel appelant, token ou pas, reçoit la config s'il connaît
  l'`item_id`. Retirer `RequireAuth` de la route runtime ne suffirait donc pas : la config resterait
  accessible à quiconque connaît l'id, indépendamment du partage GeoNode réel.
  Le garde-fou choisi : la route runtime (authentifiée ou non) appelle **d'abord** `getItem(pk)`
  (`GET {geonodeUrl}/api/v2/resources/:pk`) — c'est cet appel qui applique déjà les vraies
  permissions GeoNode (privé/partagé/`anonymous`). Ce n'est qu'après un `getItem` réussi que la
  route va chercher la config au Builder Service. Un `getItem` en 401/403/404 affiche le message
  d'accès du shell (§11) et **n'appelle jamais** `getAppConfig`. Cette vérification passe par
  GeoNode uniquement — aucun changement d'auth n'est apporté au Builder Service dans ce lot ; sa
  lacune (config lisible sans vérification propre) reste documentée comme dette pour une évolution
  ultérieure si le Builder Service doit un jour être exposé sans ce garde-fou en amont.
- **Embed/iframe.** Découle directement du point précédent, sans route ni URL supplémentaire : la
  route runtime étant déjà chrome-less et accessible sans authentification (sous réserve du partage
  GeoNode), elle est déjà intégrable telle quelle dans un `<iframe>` externe. Aucune modification
  des en-têtes de sécurité (`X-Frame-Options`/CSP `frame-ancestors`) : aucune n'existe aujourd'hui
  dans `shell/nginx.conf`, donc l'intégrabilité cross-origin reste, comme actuellement, un défaut
  non explicite plutôt qu'une décision explicite — hors scope de ce lot.
- **Miniature.** `uploadThumbnail` (upload manuel d'un fichier) existe déjà mais `ItemCard` n'affiche
  jamais `thumbnailUrl` — corrigé dans ce lot. Un bouton « Capturer » dans l'éditeur photographie le
  rendu DOM actuel de l'`AppRenderer` (nouvelle dépendance légère, ex. `html-to-image`) et réutilise
  `uploadThumbnail` tel quel — pas de nouvel endpoint, pas de capture automatique au save.

## 11. Gestion d'erreurs

- Un widget dont le rendu ou la source échoue est **isolé** (`WidgetHost` : bornage + message
  local) ; le reste de l'app rend.
- `getAppConfig`/source en erreur → état d'erreur localisé + retry.
- Save/Publish échoué → `role="alert"` ; le draft reste préservé, l'éditeur reste ouvert.
- 401/403 → géré par le shell ; `getItem` en échec sur la route runtime publique → message
  d'accès, `getAppConfig` n'est jamais appelé (§10).

## 12. Stratégie de tests

- **Unitaire (Vitest + Testing Library)** : registre/`WidgetHost` (rend le bon widget, isole les
  erreurs) ; `GridCanvas` (drag/resize/select → mutations de layout, grille mockée) ; `PropsPanel`
  (schema-driven) ; `AppRenderer` par mode ; `ActionBus` (câblage `messages` → invocation
  d'actions) ; `DataSourcePanel`/résolution de sources (MSW) ; `item-client` `getAppConfig`/
  `saveAppConfig` (MSW). Libs lourdes mockées.
- **E2E (Playwright, WebGL réel)** : créer une app → déposer des widgets → éditer props → **preview
  → enregistrer → ouvrir le runtime** et vérifier le rendu ; puis, par sous-phase, lier une source,
  câbler une action, publier.
- **Backend (pytest)** : Builder Service valide les extensions de schéma (item id, layouts par
  breakpoint, pages, variables) — round-trips, configs existants restent valides.

## 13. Phasage du plan d'implémentation

Chaque sous-phase est testable seule et livrée en branche → PR (workflow habituel).

- **SP-0d.1 — Moteur & canvas (tranche verticale)** : registre de widgets ; `AppRenderer`
  (edit/preview/runtime) ; `GridCanvas` (grille, drag/resize/select) ; `WidgetHost` (isolation) ;
  `WidgetPalette` ; `PropsPanel` ; 3 widgets statiques **Texte / Image / Bouton** ;
  `BuilderToolbar` (mode + save) ; `AppBuilderPage` à `/apps/:pk/edit` ; route runtime `/apps/:pk` ;
  `LayoutItem.id` ; item-client `getAppConfig`/`saveAppConfig` (endpoints by-item réutilisés) ;
  ouverture depuis catalogue/détail des items app/dashboard vers l'éditeur ; **E2E** éditer→
  enregistrer→runtime. **Prouve la boucle complète.**
- **SP-0d.2 — Sources de données & widgets liés** : `DataSource` (features + statistics) +
  `DataSourcePanel` + résolution via item-client ; widgets **Liste/Cartes**, **Table**, **Carte**
  (réutilise `MapView`), **Indicateur**.
- **SP-0d.3 — Framework d'actions (pilier)** : `ActionBus` runtime + `ActionsPanel` éditeur ;
  triggers (extent carte, sélection, filtre) & actions (setFilter, flyTo, highlight, navigate) ;
  widget **Filtre/Requête**.
- **SP-0d.4 — Graphiques & analytique** : widgets **Chart** (barres/lignes/camembert) liés aux
  statistiques ; **Table** avancée (tri/pagination) ; **Texte** à liaisons dynamiques.
- **SP-0d.5 — Pages, navigation, thème, templates, responsive** : `pages[]` + widget
  **Navigation/Menu** + routage de pages ; `variables[]` ; `ThemePanel` ; galerie de **templates** ;
  édition **par breakpoint** (`LayoutItem.layouts`).
- **SP-0d.6 — Publication & partage** : bascule `is_published` (GeoNode, réutilisé — pas de nouveau
  champ `BuilderConfig`) exposée dans l'éditeur/catalogue ; runtime rendu sans le chrome
  `AppLayout` et accessible sans authentification, gardé par un `getItem` GeoNode préalable (§10)
  plutôt que par le Builder Service — ce qui fournit embed/iframe sans route ni en-tête
  supplémentaire ; correction de l'affichage de `thumbnailUrl` dans `ItemCard` (jamais rendu
  aujourd'hui) + capture DOM manuelle côté éditeur réutilisant `uploadThumbnail`.
- **SP-0d.7 — SDK widgets (briques)** : barrel d'export stable (`sdk.ts`, §5) réexportant le
  contrat déjà implémenté (`WidgetDefinition`/`WidgetContext`/`registerWidget` + hooks
  `useBusAction`/`useSetFilter`/`useVariables`) ; garde-fou `console.warn` sur collision de `type` ;
  un widget d'exemple enregistré hors de `builder/widgets/`, n'important que le barrel. Aucun
  chargement de plugin à l'exécution (extension à la compilation uniquement) ; `PropsPanel` reste
  libre (pas de composants de champ partagés imposés).

`writing-plans` produira d'abord le plan de **SP-0d.1**.

## 14. Dépendances

- Front : une brique de grille (maison ; `react-grid-layout` en repli documenté) ; plus tard une
  lib de charts (ex. `recharts` ou `@visx`) en SP-0d.4 ; une lib légère de capture DOM→image (ex.
  `html-to-image`) en SP-0d.6, pour la miniature uniquement. Réutilise `MapView`/Deck.gl (SP-0c)
  pour le widget Carte. Aucune nouvelle dépendance backend, à aucune sous-phase.
- Backend : extensions Pydantic additives au `BuilderConfig` (item id, layouts, pages, variables),
  introduites par sous-phase. SP-0d.6 n'en introduit aucune (§4) — l'état de publication reste
  porté par GeoNode, pas par `BuilderConfig`.

## 15. Contraintes globales

- Un seul moteur de rendu pour édition/preview/runtime — zéro divergence.
- Persistance via Builder Service `kind="app"|"dashboard"` ; extensions de schéma **additives**,
  configs existants restent valides.
- Front : tout accès réseau via `item-client` ; aucune URL de service en dur (config env) ;
  `Item`/`ItemClient`/`BuilderConfig` étendus sans rupture.
- Un widget en erreur ne doit jamais faire échouer le rendu de toute l'app (isolation).
- Libs lourdes mockées en unitaire ; rendu réel validé en E2E.
- Pas de token en localStorage (inchangé).
- Les endpoints de sources (features/statistics) sont best-effort, confinés à la façade et définis
  par les mocks ; à ajuster contre les services réels.
