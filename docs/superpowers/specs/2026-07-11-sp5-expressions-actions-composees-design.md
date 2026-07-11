# GeoStudio SP-5 — Expressions & actions composées

> Design / spec. Couvre tout SP-5 tel que défini par la feuille de route
> (§SP-5) : logique légère sans code — visibilité conditionnelle, champs
> calculés, filtres dynamiques, actions composées, puis l'extension de
> périmètre 2026-07-09 (bindings CEL généralisés + variables typées).
> L'exécution se fera en plusieurs plans datés (SP-5a/b/c, §1) — cette
> spec ne préjuge pas du découpage en tâches, seulement de la vision
> d'ensemble et du détail complet de SP-5a (la sous-phase qui s'exécute en
> premier).
>
> Date : 2026-07-11. Statut : design approuvé (SP-5a).
> Prérequis : SP-4 (a+b+c) livré et clos.

---

## 1. Contexte, périmètre et sous-phases

La feuille de route (§SP-5, arbitrage A8) fixe l'objectif : un langage
d'expressions no-code (CEL, spike de validation en ouverture, repli
JSONLogic si le spike échoue) avec un vocabulaire commun (`vars.x`,
`record.champ`, `user.name`, fonctions math/texte/date/logique), branché
sur des points d'accroche dans les configs (`visibleWhen`, champs
calculés, valeurs par défaut de formulaire, filtres de data sources), puis
des actions composées conditionnelles. L'extension de périmètre du
brainstorm Analytics (2026-07-09) ajoute des bindings CEL généralisés
(`{ $expr: … }` sur toute prop de tout widget, évalués dans `WidgetHost`)
et des variables typées (string|number|bool|date|record|list) en
remplacement des variables string actuelles.

Cette spec couvre l'ensemble ; l'exécution se fera en 3 plans datés,
chacun un incrément testable et livrable seul :

- **SP-5a — Spike + moteur + premiers points d'accroche (cette spec, en
  détail — §2 à §8 ci-dessous).** Spike cel-js (gate d'ouverture), moteur
  d'évaluation client (`evaluateExpression`/`validateExpression`),
  `visibleWhen` sur tout `WidgetItem`, colonnes calculées sur le widget
  Table, validation à l'édition (bouton Enregistrer désactivé si une
  expression du layout est invalide).
- **SP-5b — Actions composées avec condition.** Une `ActionMessage` du
  bus (`ActionBus.ts`) gagne une condition CEL optionnelle : le message ne
  déclenche son action que si l'expression s'évalue à vrai, dans le
  contexte du payload de l'événement émetteur. Réutilise le moteur de
  SP-5a sans le modifier.
- **SP-5c — Bindings CEL généralisés + variables typées.** Toute prop de
  tout widget accepte `{ $expr: "…" }`, évalué dans `WidgetHost` avant
  passage au composant (remplace/étend les bindings `{{champ}}`/
  `{{var:nom}}` actuels, compatibilité assurée). `Variable` gagne un type
  (`string|number|bool|date|record|list`) ; `visibleWhen` et les champs
  calculés de SP-5a en deviennent des cas particuliers de ce mécanisme
  général. Sous-phase la plus large — sera re-cadrée dans son propre
  brainstorm avant plan, une fois SP-5a/b livrées et le retour d'usage
  disponible.

**Hors périmètre de SP-5a spécifiquement (§1 liste les sous-phases qui
couvrent le reste) :**
- Évaluation côté serveur (cel-python dans le cœur, validation à
  l'enregistrement d'une config, usage MCP) — différée à une sous-phase
  ultérieure explicite, pas cachée dans SP-5a. Le vocabulaire reste conçu
  pour être portable côté serveur plus tard (§2), mais rien n'est exécuté
  côté cœur en SP-5a.
- Champs calculés sur Texte/Indicateur, valeurs par défaut de formulaire
  par expression, filtres de data sources par expression — un seul point
  d'accroche (colonnes Table) suffit à démontrer et tester le moteur ;
  les autres suivent le même patron et sont différés pour rester dans un
  incrément livrable seul (confirmé en session — cf. décision de cadrage
  du brainstorm : scope tel quel, sans élargissement).
- Actions composées avec condition (SP-5b), bindings généralisés et
  variables typées (SP-5c).

## 2. Décisions de cadrage (SP-5a)

| Sujet | Décision |
|---|---|
| Langage | CEL, via le package npm `cel-js` (`ChromeGG/cel-js`, MIT). Spike de validation en ouverture de tâche 1 — verdict PASS/FAIL documenté, repli JSONLogic (syntaxe CEL gardée comme cible) si FAIL. |
| Architecture d'évaluation | Approche « évaluateur fin, appelé au point d'usage » (pas de couche réactive centralisée avec cache/graphe de dépendances) — un module `shell/src/builder/expr.ts` exposant `evaluateExpression`/`validateExpression`, appelé directement par chaque consommateur (`WidgetHost` pour `visibleWhen`, le widget Table pour une colonne calculée). Le cycle de rendu React fournit la réactivité, comme `{{var:nom}}` aujourd'hui. Pas de prématuré pour SP-5c : si un besoin de cache apparaît à l'usage, il sera traité dans cette sous-phase avec des preuves, pas anticipé ici. |
| Vocabulaire | `ExprContext = { vars: Record<string, string>; record?: Record<string, unknown>; user: { name: string } }` — correspond exactement à `vars.x`/`record.champ`/`user.name` de la feuille de route. `vars` vient de `VariablesContext` existant (string-only, inchangé en SP-5a) ; `record` est le record déjà disponible au point d'appel (premier record lié pour `visibleWhen`, ligne courante pour une colonne Table) ; `user` vient du contexte d'auth déjà threadé. |
| Erreurs à l'exécution | `evaluateExpression` ne lève jamais — retourne `undefined` sur toute erreur d'évaluation (variable absente, type incompatible, etc.), avec un `console.warn` (pas de swallow silencieux, pas de UI dédiée). `undefined`/falsy pour `visibleWhen` cache le widget ; `undefined` pour une colonne calculée affiche une cellule vide. |
| Validation à l'édition | `validateExpression` fait un parse seul (pas d'évaluation), retourne un message d'erreur ou `null`. Le bouton **Enregistrer** du builder (`AppBuilderPage.tsx`) se désactive dès qu'une expression du layout entier (tous les `visibleWhen`, toutes les colonnes calculées de toute la page active) est invalide — pas seulement celle du widget sélectionné — avec le détail de l'erreur affiché à côté du bouton. Décidé en session (alternative « bouton cliquable, échec au clic » écartée). |
| `visibleWhen` | Nouveau champ optionnel sur `WidgetItem` (`shell/src/api/types.ts`), sibling de `props` — s'applique uniformément à tout type de widget, pas une prop spécifique à un widget. `WidgetHost` l'évalue avant de monter `<Widget>` ; widget caché = ne monte pas (ne reçoit donc pas ses actions du bus tant qu'il est caché — accepté, cohérent avec le périmètre minimal). |
| Colonnes calculées (Table) | `props.columns` passe de `string[]` à `(string | { label: string; expr: string })[]`. Les entrées `string` gardent exactement le comportement actuel (nom de champ = en-tête = clé de lecture) — rétrocompatible avec toute config existante, y compris le gabarit « Application de saisie » de SP-4c. Une entrée calculée porte un `label` et un `expr` CEL, évalué par ligne contre `{ record: row.properties, vars, user }`. |
| Persistance de config | Aucun changement au schéma `BuilderConfig` du cœur — `visibleWhen` et les colonnes calculées vivent dans le JSON de config du shell (`WidgetItem`/`props`), interprétés côté shell uniquement, comme tout le reste du builder. |

## 3. Architecture

```
cel-js (spike-validé, package npm)
  │
  ▼
shell/src/builder/expr.ts
  evaluateExpression(expr, ctx: ExprContext): unknown   // jamais throw, undefined + warn sur erreur
  validateExpression(expr): string | null                // parse seul, pour l'édition
  │
  ├─▶ WidgetHost.tsx — avant de monter <Widget>, si item.visibleWhen est
  │     défini : evaluateExpression(item.visibleWhen, ctx) falsy → ne
  │     monte pas le widget.
  │
  ├─▶ widgets/data.tsx (Table) — par ligne, pour chaque colonne calculée :
  │     evaluateExpression(col.expr, { record: row.properties, vars, user }).
  │
  └─▶ PropsPanel.tsx / data.tsx PropsPanel — validateExpression() sur
        chaque champ d'expression, à la frappe ; AppBuilderPage.tsx scanne
        tout le draft (getConfigExpressionErrors) pour activer/désactiver
        Enregistrer.
```

Le moteur n'introduit aucun nouveau mécanisme de câblage — il se branche
sur les points d'extension déjà présents (`WidgetHost` monte/démonte déjà
les widgets, `PropsPanel`/`AppBuilderPage` déjà le point de mutation du
draft de config). SP-5b (actions composées) et SP-5c (bindings généralisés)
réutiliseront `evaluateExpression`/`validateExpression` tels quels.

## 4. Builder UI

- `PropsPanel.tsx` gagne une zone « Condition d'affichage » (textarea,
  `aria-label="Condition d'affichage (visibleWhen)"`) au-dessus du panneau
  spécifique au widget, visible pour tout widget sélectionné. Mutation via
  un nouveau callback `onVisibleWhenChange`, propagé par une nouvelle
  fonction `updateSelectedVisibleWhen` dans `AppBuilderPage.tsx`
  (parallèle à `updateSelectedProps` existante).
- Le `PropsPanel` du widget Table (`data.tsx`) gagne un contrôle « Ajouter
  une colonne calculée » (deux champs : libellé, expression) qui ajoute
  une entrée `{ label, expr }` à `props.columns`, en plus (pas en
  remplacement) du champ existant « Colonnes (séparées par des
  virgules) ».
- `AppBuilderPage.tsx` : le bouton **Enregistrer** est désactivé si
  `getConfigExpressionErrors(draft).length > 0` (nouvelle fonction,
  scanne tous les `visibleWhen` et toutes les colonnes calculées de
  `draft.layout.items`, plus `draft.pages?.[].layout.items` si présent) ;
  le(s) message(s) d'erreur s'affiche(nt) à côté du bouton.

## 5. Rendu (runtime)

- `WidgetHost.tsx` (actuellement ligne 47, `<Widget props=... ctx=... />`) :
  calcule `visible = !item.visibleWhen || Boolean(evaluateExpression(item.visibleWhen, ctx))`
  avant de monter — widget non visible = `null` rendu, pas de montage
  différé caché (pas de `display: none`, cohérent avec le fait qu'un
  widget caché ne doit pas recevoir d'actions du bus).
- Table (`widgets/data.tsx`) : le rendu des colonnes (actuellement lignes
  88-90 et la boucle d'en-têtes/cellules) distingue `typeof c === "string"`
  (comportement actuel inchangé) de l'entrée calculée (`label` en en-tête,
  `evaluateExpression` en cellule, pas de tri sur une colonne calculée en
  v1 — le tri reste réservé aux colonnes de champ direct, simplification
  assumée).

## 6. Stratégie de tests

- **Cœur.** Aucun changement — SP-5a est un chantier front pur (§1, hors
  périmètre : évaluation serveur).
- **Shell, unitaire.** `expr.ts` : vocabulaire complet (`vars.x`,
  `record.champ`, `user.name`, fonctions math/texte/date/logique de base),
  erreur runtime → `undefined` + pas de throw, `validateExpression` sur
  expression syntaxiquement invalide. `WidgetHost` : widget monté/démonté
  selon `visibleWhen` vrai/faux/absent/erroné. Table : rendu d'une colonne
  calculée, cohabitation avec des colonnes `string` existantes (non-
  régression), tri désactivé sur colonne calculée. `PropsPanel`/
  `AppBuilderPage` : bouton Enregistrer désactivé avec message si une
  expression est invalide, réactivé une fois corrigée.
- **Shell, E2E Playwright** (nouvelle spec — règle du projet : chaque
  feature visible a sa spec E2E). Scénario de référence de la feuille de
  route : un Filtre piloté par une variable contrôle par expression la
  visibilité d'un widget et une colonne calculée d'un Table, construit
  sans code ; une expression invalide saisie dans le builder désactive
  Enregistrer avec un message, corrigée elle réactive le bouton.

## 7. Critères d'acceptation (SP-5a)

- Un dashboard où un Filtre pilote par expression la visibilité d'un
  widget et une colonne calculée, créé sans code, E2E vert.
- Une expression invalide est signalée à l'édition (bouton Enregistrer
  désactivé, message affiché) — pas seulement détectée à l'exécution.
- Aucune régression : toute config existante avec des colonnes Table en
  `string[]` continue de fonctionner à l'identique (les 14 specs E2E
  restent vertes).

## 8. Risques

- **cel-js immature (A8).** Spike d'1 journée en ouverture de la tâche 1
  du plan SP-5a — verdict PASS/FAIL documenté avant toute autre tâche ;
  repli JSONLogic (syntaxe CEL gardée comme cible) décidé d'avance si le
  spike échoue. Aucune tâche de SP-5a en dépend structurellement autrement
  que par le nom du package évalué — `evaluateExpression`/
  `validateExpression` gardent la même signature quel que soit le moteur
  choisi.
- **Scope creep Retool (SP-4/SP-5 sans fin)** — risque déjà nommé par la
  feuille de route. Mitigation : SP-5a limité à un seul point d'accroche
  de champ calculé (Table), les autres (Texte, Indicateur, valeurs par
  défaut de formulaire, filtres de data source) explicitement différés à
  une sous-phase ultérieure, pas ajoutés en cours de route.
