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
- **`published`** : booléen/état de publication. *(SP-0d.6)*

Chaque extension est introduite dans sa sous-phase avec migration/validation côté Builder Service
(Pydantic, valeurs par défaut → configs existants restent valides).

## 5. Registre de widgets & SDK

Chaque widget est décrit par une **définition** enregistrée dans un registre :

```ts
type WidgetContext = {
  mode: RenderMode;
  data?: DataSourceState;          // données résolues si le widget est lié
  bus: ActionBus;                  // émettre/écouter des événements
  navigate: (pageId: string) => void;
};
type WidgetDefinition<P = Record<string, unknown>> = {
  type: string;                    // ex. "text", "image", "map", "list", "chart", "filter"
  label: string;
  icon: ReactNode;
  defaultProps: P;
  defaultSize: { w: number; h: number };
  PropsPanel: (p: { props: P; onChange: (p: P) => void; dataSources: DataSource[] }) => JSX.Element;
  Component: (p: { props: P; ctx: WidgetContext }) => JSX.Element;
  events?: string[];               // triggers exposés (ex. "itemSelected")
  actions?: Record<string, (args: unknown) => void>; // actions exposées (déclarées côté instance)
};
function registerWidget(def: WidgetDefinition): void;
function getWidget(type: string): WidgetDefinition | undefined;
function listWidgets(): WidgetDefinition[];
```

Le registre est le point d'extension : ajouter un widget = enregistrer une définition. C'est la
base du **SDK « briques »** (SP-0d.7) : les briques additionnelles enregistrent leurs widgets sans
toucher au cœur.

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
- **Runtime** : `/apps/:pk` → `AppRenderer(runtime)` sur le config chargé (`getAppConfig`).
  L'accès public respecte le partage GeoNode (SP-0d.6). Dashboards : même moteur, layout dense.
- `NewItemButton` crée déjà `app`/`dashboard` (SP-0b) ; après création on navigue vers
  `/apps/:pk/edit`.

## 11. Gestion d'erreurs

- Un widget dont le rendu ou la source échoue est **isolé** (`WidgetHost` : bornage + message
  local) ; le reste de l'app rend.
- `getAppConfig`/source en erreur → état d'erreur localisé + retry.
- Save/Publish échoué → `role="alert"` ; le draft reste préservé, l'éditeur reste ouvert.
- 401/403 → géré par le shell ; runtime public non autorisé → message d'accès.

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
  breakpoint, pages, published) — round-trips, configs existants restent valides.

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
- **SP-0d.6 — Publication & partage** : état `published` ; runtime public respectant le partage
  GeoNode ; **embed/iframe** ; capture de miniature.
- **SP-0d.7 — SDK widgets (briques)** : contrat de widget documenté + enregistrement tiers +
  widgets d'exemple → base des **briques additionnelles** intégrables.

`writing-plans` produira d'abord le plan de **SP-0d.1**.

## 14. Dépendances

- Front : une brique de grille (maison ; `react-grid-layout` en repli documenté) ; plus tard une
  lib de charts (ex. `recharts` ou `@visx`) en SP-0d.4. Réutilise `MapView`/Deck.gl (SP-0c) pour le
  widget Carte. Aucune nouvelle dépendance backend obligatoire.
- Backend : extensions Pydantic additives au `BuilderConfig` (item id, layouts, pages, published),
  introduites par sous-phase.

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
