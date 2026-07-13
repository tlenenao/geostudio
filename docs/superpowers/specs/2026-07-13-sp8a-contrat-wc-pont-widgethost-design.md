# SP-8a — Contrat Web Component + pont WidgetHost : design

**Date** : 2026-07-13
**Statut** : validé (brainstorm), prêt pour plan d'implémentation

## Contexte

SP-8 (feuille de route, `docs/vision/2026-07-04-feuille-de-route-geostudio.md`
§SP-8) est le plus gros SP de la route (60–110 h estimées) et dépend de SP-5
(clos). Comme SP-4/SP-6/SP-7, il est découpé en sous-phases avec leur propre
spec/plan/revue :

- **SP-8a (cette spec)** : le contrat de widget Web Component et le pont
  `WidgetHost` React ↔ custom element — prototypé sur le `Compteur`, statique
  (bundlé dans le repo, pas encore chargé dynamiquement par URL).
- **SP-8b** : chargement dynamique de modules ES par URL, registre
  d'« extensions » côté cœur (item de type `extension`, activable par
  l'admin), permissions déclaratives, robustesse face à un widget tiers
  potentiellement cassé.
- **SP-8c** : guide « écrire un widget », durcissement, E2E de bout en bout
  (un widget WC développé hors repo, servi comme module ES, se charge dans le
  builder).

Ce découpage suit exactement le risque documenté dans la feuille de route :
« Frontière React↔WC (synchronisation props/events, SSR sans objet ici) ;
prototyper le pont sur le Compteur avant de figer le manifeste » — SP-8a
livre et valide ce pont isolément, avant que SP-8b n'y ajoute la confiance
zéro (code tiers non lu) et la complexité du chargement réseau.

État vérifié du code actuel (2026-07-13) :

- `shell/src/builder/registry.ts` : `WidgetDefinition<P>` = `{ type, label,
  defaultProps, defaultSize, events?, actions?, PropsPanel, Component }`,
  stockée dans une `Map` globale via `registerWidget`/`getWidget`/
  `listWidgets`. C'est l'unique point d'entrée que `WidgetPalette`,
  `AppBuilderPage.addWidget`, `PropsPanel.tsx` et `WidgetHost.tsx`
  connaissent — aucun de ces consommateurs ne sait qu'un widget est React ou
  autre chose.
- `shell/src/builder/WidgetHost.tsx` : résout `visibleWhen` et les bindings
  `$expr` (SP-5a/SP-5c, `resolveExprBindings`) **avant** d'invoquer
  `def.Component({ props, ctx })` — ce traitement est générique, il
  s'applique déjà à n'importe quel `WidgetDefinition` sans changement.
  `ctx: WidgetContext` porte `{ mode, navigate, pages, variables, data, bus,
  widgetId, user }`.
- `shell/src/builder/theme.ts` (`themeToCssVars`) pose déjà les couleurs/
  police/rayon/espacement comme custom properties CSS (`--gs-*`) sur le
  conteneur racine du renderer (SP-0d) — ces propriétés sont héritées
  nativement à travers tout le DOM, shadow DOM inclus (comportement standard
  des CSS custom properties, pas une fonctionnalité à construire).
- `shell/src/builder/ActionBus.ts` : `emit(widgetId, event, payload)` route
  vers les actions câblées par `AppRenderer` (`ActionMessage[]`) ;
  `register(widgetId, action, handler)` renvoie une fonction de
  désinscription. Les widgets React s'y abonnent via le hook
  `useBusAction(bus, widgetId, action, handler)` (`ActionBusContext.tsx`).
- `shell/src/builder/examples/counterWidget.tsx` : le widget `Compteur`
  actuel (React), `type: "example.counter"`, prop `initial: number`,
  `events: ["changed"]`, `actions: ["reset"]`, `defaultSize: { w: 2, h: 2 }`
  — c'est le widget de référence à porter en WC, sa forme (props/events/
  actions) devient le cas de test du manifeste.
- `shell/src/builder/PropsPanel.tsx` : rend `def.PropsPanel({ props,
  dataSources, onChange })` tel quel — n'importe quelle fonction respectant
  cette signature fonctionne, y compris une fonction générée plutôt
  qu'écrite à la main.

## Objectif

Un widget peut être écrit comme un Web Component standard (custom element +
manifeste JSON typé) plutôt qu'en React, et se comporte comme un widget
interne dans le builder : palette, panneau de props, thème, data source,
events, actions composées — sans toucher au renderer, à la palette ou au
panneau de props existants. Le pont est validé en profondeur sur le
`Compteur` avant que SP-8b ne l'expose au chargement dynamique de code non
lu.

## Hors périmètre (reporté à SP-8b/SP-8c)

- Chargement dynamique d'un module ES par URL (`import()` réseau).
- Registre d'extensions côté cœur, activation/désactivation par l'admin,
  item de type `extension`.
- Permissions déclaratives et tout ce qui relève de la confiance envers du
  code tiers non lu (SP-8b : « extensions *trusted* + permissions
  déclaratives », compromis assumé par la feuille de route).
- Isolation d'un widget WC qui plante après montage (voir « Limite
  documentée » ci-dessous — creusé en détail en SP-8b, où le risque devient
  réel puisque le code n'est plus écrit par nous).
- Slots (composition de contenu enfant) — aucun besoin identifié pour le
  `Compteur` ni dans le contenu SP-8 de la feuille de route ; à réintroduire
  si un futur widget WC en a besoin.
- Retrait ou dépréciation du `Compteur` React existant — les deux coexistent
  pendant SP-8a/8b pour comparer le pont à l'original.

## Architecture

### Manifeste (`WcWidgetManifest`)

Nouveau type dans `shell/src/builder/wc/manifest.ts` :

```ts
export type WcWidgetManifest = {
  type: string;       // identifiant du widget, ex: "example.counter-wc"
  tag: string;         // nom de l'élément custom, ex: "gs-counter"
  label: string;       // libellé palette, ex: "Compteur (WC)"
  props: Array<{
    name: string;
    type: "string" | "number" | "boolean"; // ensemble minimal v1 (YAGNI) — suffisant pour le Compteur
    label: string;
    default: unknown;
  }>;
  events?: readonly string[];   // widget → host, CustomEvent natif
  actions?: readonly string[]; // host → widget, méthode publique du même nom
  defaultSize: { w: number; h: number };
};
```

`props[].type` pilote uniquement le champ généré dans le panneau (texte/
nombre/case à cocher) — pas de validation stricte au runtime au-delà de ça
en v1 (même niveau de rigueur que les `defaultProps` des widgets React
actuels, qui ne sont pas non plus validés par un schéma).

### Adaptateur `registerWcWidget`

`shell/src/builder/wc/registerWcWidget.ts` — une fonction qui construit un
`WidgetDefinition` standard à partir d'un manifeste et l'enregistre via
`registerWidget` (`registry.ts`, inchangé) :

```ts
export function registerWcWidget(manifest: WcWidgetManifest): void {
  registerWidget({
    type: manifest.type,
    label: manifest.label,
    defaultProps: Object.fromEntries(manifest.props.map((p) => [p.name, p.default])),
    defaultSize: manifest.defaultSize,
    events: manifest.events,
    actions: manifest.actions,
    PropsPanel: makeGeneratedPropsPanel(manifest),
    Component: makeWcHost(manifest),
  });
}
```

Conséquence directe : `WidgetPalette`, `AppBuilderPage.addWidget`,
`PropsPanel.tsx`, `WidgetHost.tsx` ne changent pas — ils consomment déjà
`WidgetDefinition` de façon générique. Le pont est entièrement contenu dans
`shell/src/builder/wc/`.

### Panneau de props généré

`makeGeneratedPropsPanel(manifest)` retourne une fonction respectant la
signature `PropsPanel` existante. Un champ par entrée de `manifest.props`,
rendu selon son `type` :

- `string` → `<input type="text">`
- `number` → `<input type="number">`
- `boolean` → `<input type="checkbox">`

Même patron de composition que le panneau à la main du `Compteur` React
actuel, mais dérivé de données plutôt qu'écrit par widget. Chaque prop reste
bindable par `{ $expr: "…" }` (SP-5c) — ce mécanisme vit dans `WidgetHost`,
en amont de `Component`, donc aucune adaptation n'est nécessaire ici.

### `WcHost` — le pont Component

`makeWcHost(manifest)` retourne un composant React `({ props, ctx }) =>
ReactNode` :

```tsx
function WcHostFor(manifest: WcWidgetManifest) {
  return function WcHost({ props, ctx }: { props: Record<string, unknown>; ctx: WidgetContext }) {
    const containerRef = useRef<HTMLDivElement>(null);
    const elRef = useRef<HTMLElement | null>(null);

    useEffect(() => {
      const el = document.createElement(manifest.tag);
      elRef.current = el;
      containerRef.current?.appendChild(el);
      return () => { el.remove(); elRef.current = null; };
    }, []); // un seul montage par instance de widget, tag fixe

    useEffect(() => {
      const el = elRef.current;
      if (!el) return;
      (el as any).props = props;
      (el as any).data = ctx.data;
      (el as any).user = ctx.user;
      (el as any).navigate = ctx.navigate;
    }); // à chaque rendu — propriétés DOM, jamais d'attributs sérialisés

    useEffect(() => {
      const el = elRef.current;
      if (!el || !ctx.bus || !ctx.widgetId) return;
      const offs = (manifest.events ?? []).map((name) =>
        addListener(el, name, (e: CustomEvent) => ctx.bus!.emit(ctx.widgetId!, name, e.detail)));
      const unregs = (manifest.actions ?? []).map((name) =>
        ctx.bus!.register(ctx.widgetId!, name, (payload) => (el as any)[name]?.(payload)));
      return () => { offs.forEach((f) => f()); unregs.forEach((f) => f()); };
    }, [ctx.bus, ctx.widgetId]);

    return <div ref={containerRef} className="h-full w-full" />;
  };
}
```

Points de contrat fixés :

1. **Props/data/user/navigate** : propriétés DOM assignées directement sur
   l'instance (`el.props = …`), jamais d'attributs HTML string. Un objet/
   tableau ne survit pas à un aller-retour JSON à chaque rendu ; les
   propriétés DOM portent des références JS directes, comme React le fait
   déjà pour ses propres éléments.
2. **Thème** : rien à faire dans le pont — les `--gs-*` custom properties du
   conteneur racine (SP-0d) sont héritées par tout descendant DOM, shadow
   DOM inclus. Le `Compteur` WC les consomme directement dans son CSS Lit
   (`color: var(--gs-color-text)`, etc.).
3. **Events (widget → host)** : le widget émet un `CustomEvent` natif sur
   lui-même (`this.dispatchEvent(new CustomEvent("changed", { detail: {
   count } }))`) pour chaque nom listé dans `manifest.events`. `WcHost`
   écoute et relaie vers `ctx.bus.emit(widgetId, name, e.detail)` — même
   sémantique de payload que les widgets React (`bus.emit` prend déjà un
   `payload?: unknown`).
4. **Actions (host → widget)** : pour chaque nom listé dans
   `manifest.actions`, `WcHost` s'enregistre sur le bus
   (`ctx.bus.register(widgetId, name, handler)`, même mécanisme que
   `useBusAction`) et le handler appelle la méthode publique du même nom sur
   l'instance (`el.reset(payload)`). Le widget WC doit exposer une méthode
   publique par action déclarée — documenté dans le guide SP-8c.

### `Compteur` porté en WC de référence

`shell/src/builder/examples/counterWidgetWc.ts` — réimplémentation Lit,
tag `gs-counter` :

- Propriété interne `count` (state Lit), propriété publique `props` (reçoit
  `{ initial: number }` du pont).
- Méthode publique `reset()` : remet `count` à `props.initial`.
- Sur clic « +1 » : incrémente `count`, `dispatchEvent(new CustomEvent(
  "changed", { detail: { count } }))`.
- Même rendu visuel que le `Compteur` React (nombre + bouton), stylé via les
  `--gs-*` custom properties héritées.

Enregistré via `registerWcWidget(counterWcManifest)` dans
`AppBuilderPage.tsx`, **à côté de** `registerCounterExampleWidget()`
(inchangé) — les deux widgets coexistent dans la palette
(« Compteur (exemple SDK) » et « Compteur (WC) ») le temps de SP-8a/8b, pour
comparer le pont à l'original sans risque de régression sur l'existant.

### Limite documentée (pas un bug SP-8a)

`WidgetErrorBoundary` (`WidgetHost.tsx`, `componentDidCatch`) ne peut
rattraper que les erreurs synchrones levées pendant le rendu React du pont
lui-même (ex. `document.createElement` sur un tag jamais défini). Une
exception levée *après* montage, à l'intérieur du JS propre du custom
element (ex. dans un de ses propres event listeners), n'est plus dans
l'arbre de rendu React — elle remonte comme une erreur globale non
capturée par ce boundary. Sans conséquence en SP-8a (le `Compteur` WC est du
code de confiance, écrit et testé ici) ; devient un vrai sujet en SP-8b où
`WidgetHost` accueillera du code tiers potentiellement cassé — traité dans
la spec SP-8b (critère d'acceptation de la feuille de route : « sa
désactivation ne casse pas les apps qui l'utilisaient, placeholder propre »).

## Tests

- **Vitest — `registerWcWidget`/`WcHost`** (`shell/src/builder/wc/`) :
  - le `WidgetDefinition` produit a le bon `type`/`label`/`defaultProps`
    (dérivés de `manifest.props[].default`)/`defaultSize`/`events`/`actions`.
  - le panneau généré rend un champ par prop, du bon type, et appelle
    `onChange` avec la valeur convertie (string/number/boolean).
  - `WcHost` : monte l'élément avec le bon tag ; assigne `props`/`data`/
    `user`/`navigate` comme propriétés DOM (pas d'attribut) à chaque
    changement de `props` ; un `CustomEvent` émis par l'élément déclenche
    `bus.emit(widgetId, name, detail)` ; un `bus.register`/invocation
    d'action appelle la méthode publique correspondante sur l'élément ; le
    nettoyage (`useEffect` cleanup) désinscrit du bus et retire l'élément du
    DOM au démontage.
- **Vitest — `counterWidgetWc`** : équivalent du test existant du `Compteur`
  React (incrément met à jour l'affichage et émet `changed` avec le bon
  `count` ; `reset()` restaure `props.initial`).
- **E2E (Playwright)** : nouvelle spec `wc-widget-bridge.spec.ts` — place le
  `Compteur (WC)` dans le builder (palette → canvas), l'incrémente en mode
  preview/runtime, vérifie que l'event `changed` déclenche une action
  composée câblée en `ActionsPanel` (même patron que
  `action-conditions.spec.ts` déjà vert), vérifie que l'action `reset`
  invoquée par un autre widget remet le compteur à zéro, vérifie que la
  couleur du texte suit le thème de l'app (`--gs-color-text` changé dans
  `ThemePanel` → répercuté sans rechargement). Les 20 specs existantes
  restent vertes — aucune modifiée, `Compteur` React inchangé.

## Critères d'acceptation

- Un widget WC statiquement enregistré (`Compteur` porté) apparaît dans la
  palette, se pose sur le canvas, reçoit ses props (y compris via
  `{ $expr }`), s'affiche stylé selon le thème courant.
- Un clic dans le widget WC émet un event qui déclenche une action composée
  exactement comme le ferait un widget React (même `ActionBus`, même
  `ActionMessage.when`).
- Une action du bus invoquée sur le widget WC appelle sa méthode publique
  correspondante et produit l'effet attendu (`reset`).
- Le panneau de props du widget WC est généré depuis le manifeste, sans
  code React écrit à la main pour ce widget spécifique.
- Aucune régression sur le `Compteur` React existant ni sur les 20 specs E2E
  en place.
