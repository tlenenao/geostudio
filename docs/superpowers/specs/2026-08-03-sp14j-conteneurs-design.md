# SP-14j — Conteneurs : onglets, modale, tiroir (design)

> **Date : 2026-08-03 · Statut : validé (brainstorm)**
> Dixième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur**,
> **SP-14d — Menu explorer & voir les entités**, **SP-14e — KPI riche &
> séries temporelles comparées**, **SP-14f — Nouveaux types de graphiques**,
> **SP-14g — Tableau croisé / pivot**, **SP-14h — Carte analytique** et
> **SP-14i — SQL Lab**. Traite un des éléments encore listés « hors
> périmètre » par 14i (« Conteneurs [...], requête visuelle, source
> `arcgis`, MCP analytique — sous-parties SP-14 ultérieures (14j…) ») : les
> **conteneurs** (« onglets/modale/tiroir » — feuille de route §SP-14, bullet
> Widgets analytiques). Requête visuelle, source `arcgis`, MCP analytique
> restent hors périmètre — sous-parties SP-14 ultérieures (14k…).

## 1. Objectif & non-buts

**Objectif.** Aujourd'hui chaque page d'app est une grille **plate** de
`WidgetItem` (`shell/src/api/types.ts:170-194`) : aucun widget n'en contient
d'autres, et le rendu (`AppRenderer` → `GridCanvas` → `WidgetHost`) ne
recourt jamais. SP-14j introduit le premier niveau d'imbrication : trois
nouveaux widgets — `tabs`, `modal`, `drawer` — dont les enfants sont
eux-mêmes des `WidgetItem[]` complets, pour organiser un dashboard dense
(ex. « détail d'un incident dans une modale ouverte depuis le clic sur une
ligne de table », « bascule entre 3 vues d'un même jeu de données en
onglets », « filtres avancés dans un tiroir pour ne pas encombrer l'écran »).

**Constat clé qui cadre l'approche.** `WidgetPalette`, `GridCanvas` et
`PropsPanel` sont déjà **totalement génériques** — aucun des trois ne
connaît `AppConfig` ni `AppBuilderPage` ; ils opèrent sur des `WidgetItem[]`
et des callbacks (`onAdd`, `onChange`, `onSelect`, `onMoveItem`) fournis par
l'appelant (`shell/src/pages/AppBuilderPage.tsx:81-124` pour le niveau page).
Un widget conteneur peut donc réutiliser exactement ces trois briques pour
éditer ses propres enfants, sans dupliquer ni refactorer le builder
existant — composition pure, zéro changement à `AppBuilderPage.tsx`.
Symétriquement, `GridCanvas` gère déjà les deux modes (`editable={true|false}`)
et `WidgetHost` ne dépend que de contexte React (`useDataStates`,
`useVariables`, `useActionBus`, `useAnalyticsContext`) jamais de props
transmises depuis un parent précis — le rendu runtime des enfants d'un
conteneur est donc la même primitive que le rendu runtime d'une page,
appelée une fois de plus.

**Non-buts explicites** (reportés) :

- **Conteneur dans un conteneur.** Un seul niveau d'imbrication. Appliqué en
  excluant `tabs`/`modal`/`drawer` de la palette utilisée à l'intérieur d'un
  conteneur (`WidgetPalette` gagne un `exclude?: string[]`) — pas une
  contrainte de schéma, cohérent avec le reste du builder qui ne valide pas
  fortement les configs.
- **Action `selectTab` pilotable depuis l'extérieur** (parité avec
  `open`/`close` de modal/drawer, sur le modèle de `map.flyTo`). Non demandé
  par la feuille de route pour les conteneurs ; YAGNI pour un v1 — l'onglet
  actif reste un état purement local au widget `tabs`. Pourra s'ajouter sans
  rupture (nouvelle entrée `actions`) si le besoin émerge.
- **Enregistrer un conteneur comme template réutilisable.** Hors sujet — la
  copie d'un widget conteneur suit le même (non-)mécanisme que tout autre
  widget aujourd'hui (aucun).
- **Conteneur au niveau page.** Déjà couvert par les pages multiples et
  `navigationMode: "story"` (chapitres) — les conteneurs SP-14j sont un
  niveau *widget*, pas une alternative aux pages.
- Requête visuelle, source `arcgis`, MCP analytique — reste de la liste
  SP-14, sous-parties ultérieures.

## 2. Modèle de données

Trois nouveaux `widget` (kinds), cohérents avec le patron existant de kinds
séparés par variante plutôt qu'un kind générique + `variant` (ex.
`dateRangeFilter`/`selectFilter`/`sliderFilter` sont déjà 3 kinds distincts) :

```ts
// tabs
type TabsProps = { tabs: Array<{ id: string; label: string; items: WidgetItem[] }> };
// defaultProps: { tabs: [{ id: crypto.randomUUID(), label: "Onglet 1", items: [] }] }

// modal
type ModalProps = { title: string; items: WidgetItem[]; wide?: boolean };
// defaultProps: { title: "Modale", items: [] }
// actions: ["open", "close"]

// drawer
type DrawerProps = { title: string; items: WidgetItem[]; side: "left" | "right" };
// defaultProps: { title: "Tiroir", items: [], side: "right" }
// actions: ["open", "close"]
```

Chaque `items` est un `WidgetItem[]` complet — une mini grille avec ses
propres coordonnées `x/y/w/h` par breakpoint (`WidgetItem.layouts`,
`types.ts:170-180`), positionnée par le même `GridCanvas` que le niveau page.

**Déclenchement de la modale/du tiroir : exclusivement via l'`ActionBus`
existant** (SP-5c, `builder/ActionBus.ts`). `modal`/`drawer` enregistrent les
actions `open`/`close` via `useBusAction(bus, widgetId, "open"/"close", …)` —
n'importe quel widget émetteur (bouton, ligne de table sélectionnée, …) s'y
câble depuis le panneau **Actions** déjà livré
(`shell/src/builder/ActionsPanel.tsx`), en choisissant le conteneur comme
cible et `open`/`close` comme action. **Zéro nouveau mécanisme de
déclenchement.** `tabs` n'a pas besoin d'action bus : le switch d'onglet est
un clic direct sur la barre d'onglets du widget lui-même.

## 3. Édition — nouveau composant `LayoutEditor`

Nouveau fichier `builder/LayoutEditor.tsx`, composition pure des trois
briques déjà génériques, avec un état local propre à l'instance éditée :

```tsx
function LayoutEditor({ items, onChange, dataSources, breakpoint }: {
  items: WidgetItem[];
  onChange: (items: WidgetItem[]) => void;
  dataSources: DataSource[];
  breakpoint: Breakpoint;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = items.find((i) => i.id === selectedId) ?? null;

  function addWidget(type: string) {
    const def = getWidget(type);
    if (!def) return;
    const { x, y } = nextFreePosition(items);
    const item: WidgetItem = { id: crypto.randomUUID(), widget: type, x, y, w: def.defaultSize.w, h: def.defaultSize.h, props: { ...def.defaultProps } };
    onChange([...items, item]);
    setSelectedId(item.id);
  }
  function updateSelectedProps(props: Record<string, unknown>) {
    onChange(items.map((i) => (i.id === selectedId ? { ...i, props } : i)));
  }
  function handleMove(id: string, dx: number, dy: number) {
    onChange(items.map((i) => (i.id === id ? moveItemAt(i, breakpoint, dx, dy) : i)));
  }

  return (
    <div className="flex flex-col gap-2">
      <WidgetPalette onAdd={addWidget} exclude={["tabs", "modal", "drawer"]} />
      <div className="h-48 border">
        <GridCanvas
          items={items}
          breakpoint={breakpoint}
          editable
          selectedId={selectedId}
          onSelect={setSelectedId}
          onMoveItem={handleMove}
          renderItem={(item) => <WidgetHost item={item} mode="edit" />}
        />
      </div>
      <PropsPanel
        item={selected}
        dataSources={dataSources}
        onChange={updateSelectedProps}
        onVisibleWhenChange={(expr) => selected && onChange(items.map((i) => (i.id === selectedId ? { ...i, visibleWhen: expr || undefined } : i)))}
      />
    </div>
  );
}
```

Chaque `PropsPanel` de conteneur l'utilise :

- `tabs.PropsPanel` : liste d'onglets (ajouter/renommer/supprimer/réordonner
  — boutons simples, pas de drag-and-drop) + un sélecteur d'onglet actif +
  un `LayoutEditor` monté sur l'onglet sélectionné (`tabs[i].items`).
- `modal.PropsPanel` / `drawer.PropsPanel` : champ `title` (+ `side` pour
  drawer, + case à cocher `wide` pour modal) + un seul `LayoutEditor` monté
  sur `items`.

Changement additif mineur : `WidgetPalette` gagne un prop optionnel
`exclude?: string[]` (filtre `listWidgets()` par `def.type`), rétrocompatible
(défaut `[]`, comportement actuel inchangé pour la palette du niveau page).

## 4. Rendu runtime

- `GridCanvas` gère déjà `editable={false}` (pas d'overlay de sélection, pas
  de `pointer-events-none`) → réutilisé tel quel pour le rendu runtime des
  enfants.
- **Nouveau besoin : le `breakpoint` actif.** Aujourd'hui `AppRenderer`
  calcule `bp` (`AppRenderer.tsx:118`) et le donne uniquement à son propre
  `GridCanvas` (`AppRenderer.tsx:191-199`) — jamais à un widget `Component`,
  puisqu'aucun n'en avait besoin jusqu'ici. Un conteneur doit connaître `bp`
  pour positionner sa propre grille interne (`posFor(item, breakpoint)`).
  Ajout d'un champ optionnel `breakpoint?: Breakpoint` à `WidgetContext`
  (`builder/registry.ts:6-15`), threadé `AppRenderer` → `WidgetHost` (nouveau
  prop `breakpoint`, passé dans `ctx`) → conteneur. Rétrocompatible :
  `undefined` par défaut, ignoré par les 19 widgets existants.
- `tabs.Component` (runtime, `ctx.mode !== "edit"`) : barre d'onglets
  (boutons, état `activeTab` en `useState` local, initialisé au premier
  onglet) + `<GridCanvas items={activeTab.items} breakpoint={ctx.breakpoint ?? "lg"} editable={false} selectedId={null} onSelect={() => {}} onMoveItem={() => {}} renderItem={(item) => <WidgetHost item={item} mode={ctx.mode} pages={ctx.pages} navigate={ctx.navigate} />} />`.
- `modal.Component` : état local `open` (`useState(false)`), enregistré sur
  le bus (`useBusAction(ctx.bus, ctx.widgetId, "open", () => setOpen(true))`,
  idem `"close"`). Rendu via le composant `Dialog` existant
  (`shell/src/ui/dialog.tsx`) — extension additive mineure : `Dialog` gagne
  un prop optionnel `wide?: boolean` (`max-w-2xl` au lieu de `max-w-md`) pour
  ne pas être étranglé quand le contenu est une grille de widgets.
- `drawer.Component` : même mécanique `open`/`close` via le bus. Pas de
  générique réutilisable (`ExplorerDrawer.tsx` est spécifique au contexte
  analytique, pas un composant présentationnel générique) — nouveau
  composant autonome à l'intérieur de `drawer.tsx`, même patron visuel que
  `ExplorerDrawer`/`Dialog` (position fixe, glissant depuis `side`, Escape
  pour fermer, backdrop cliquable), sans extraction partagée.
- En mode edit, `tabs`/`modal`/`drawer` occupent une cellule de grille comme
  tout widget. `tabs` affiche statiquement son premier onglet (la barre
  d'onglets n'a aucun intérêt interactif en édition, cohérent avec le
  `pointer-events-none` déjà posé par le `GridCanvas` parent —
  `GridCanvas.tsx:52`) ; `modal`/`drawer` affichent un badge statique
  (« Modale : {title} », « Tiroir : {title} ») — **jamais ouverts pendant
  l'édition**, l'édition de leur contenu se fait exclusivement via leur
  `PropsPanel` (§3).

## 5. Compatibilité & tests

- **Additif pur** : 3 nouveaux kinds enregistrés dans
  `builder/widgets/index.ts` (`registerBuiltinWidgets`), 1 nouveau fichier
  `LayoutEditor.tsx`, 1 champ optionnel `breakpoint` sur `WidgetContext` +
  `WidgetHost`, 1 prop optionnel `exclude` sur `WidgetPalette`, 1 prop
  optionnel `wide` sur `Dialog`. Aucun changement à `AppBuilderPage.tsx`,
  `GridCanvas.tsx` (logique inchangée, juste réappelé), `core/`, ni au
  modèle `AppConfig`/`Page`. Les 76+ E2E existants restent verts sans
  modification.
- **Unitaires** :
  - `LayoutEditor.test.tsx` : ajouter/déplacer/supprimer un enfant, la
    palette interne exclut bien les 3 kinds conteneurs, sélectionner un
    enfant affiche son `PropsPanel`, éditer ses props/`visibleWhen` propage
    par `onChange`.
  - `tabs.test.tsx` : rendu runtime affiche le premier onglet par défaut,
    clic sur un autre onglet bascule son contenu, mode edit statique sur le
    premier onglet, `PropsPanel` ajoute/renomme/supprime un onglet.
  - `modal.test.tsx` / `drawer.test.tsx` : fermé par défaut au montage ;
    `bus.emit` d'un événement câblé sur `open`/`close` (via `ActionBus`
    directement, comme `button.test.tsx`/`filter.test.tsx`) ouvre/ferme ;
    Escape et clic backdrop ferment ; mode edit affiche le badge statique
    sans jamais ouvrir ; `PropsPanel` édite `title`/`side`/`wide`.
- **E2E** (`e2e/containers.spec.ts`, patron des specs widgets existantes) :
  construire un widget `tabs` avec un widget `indicator` par onglet et
  vérifier le switch ; câbler un `button` (panneau Actions) sur l'action
  `open` d'un `modal` contenant un widget `table`, vérifier l'ouverture puis
  la fermeture (Escape) ; même scénario pour `drawer`. Non-régression :
  aucune spec E2E existante ne change de comportement.

## 6. Risques

- **`PropsPanel` imbriqué dans `LayoutEditor` imbriqué dans `PropsPanel`** —
  composition, pas de récursion runtime dangereuse : un seul niveau
  d'imbrication est atteignable (palette filtrée), donc la profondeur
  d'appel reste bornée (`PropsPanel` du niveau page → `LayoutEditor` du
  conteneur → `PropsPanel` de l'enfant, jamais plus loin).
- **Superposition visuelle** — `modal` (`fixed inset-0 z-50`, comme
  `Dialog`), `drawer` (nouveau, `fixed` côté `side`) et `ExplorerDrawer`
  (déjà `fixed`) doivent avoir des `z-index` cohérents pour ne pas se
  chevaucher si plusieurs sont ouverts simultanément — à vérifier par un
  test E2E dédié (drawer + explorer ouverts en même temps) plutôt que par
  inspection visuelle seule.
- **`localStorage`/état non persisté** — l'onglet actif et l'état
  ouvert/fermé de modal/drawer sont des `useState` locaux au widget, jamais
  sérialisés dans l'URL/le `config` — cohérent avec le fait que ce ne sont
  pas des « situations » partageables (bookmarks, hors périmètre SP-14
  jusqu'ici) ; à documenter explicitement pour ne pas surprendre en revue.
