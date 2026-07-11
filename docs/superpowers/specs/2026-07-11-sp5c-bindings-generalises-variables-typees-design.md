# GeoStudio SP-5c — Bindings CEL généralisés & variables typées

> Design / spec. Détaille SP-5c tel que délimité par la spec SP-5 (§1) et
> re-cadré par son propre brainstorm, comme prévu, une fois SP-5a et SP-5b
> livrées et mergées (2026-07-11). Périmètre confirmé en session : les deux
> volets (bindings généralisés `{ $expr }` + variables typées) traités
> ensemble dans un seul incrément, motivés par l'achèvement de la vision de
> la feuille de route (aucun besoin bloquant concret identifié pendant
> SP-5a/b — cf. §5).
>
> Date : 2026-07-11. Statut : design approuvé (session de brainstorm).
> Prérequis : SP-5a (livré, PR #21 mergée) et SP-5b (livré, PR #22 en
> cours) — réutilise `evaluateExpression`/`validateExpression`
> (`shell/src/builder/expr.ts`) sans les modifier.

---

## 1. Contexte et périmètre

La spec SP-5 (§1) prévoyait SP-5c comme « toute prop de tout widget accepte
`{ $expr: "…" }`, évalué dans `WidgetHost` avant passage au composant… ;
`Variable` gagne un type (`string|number|bool|date|record|list`) » et
notait explicitement que c'était la sous-phase la plus large, à re-cadrer
dans son propre brainstorm une fois SP-5a/b livrées et le retour d'usage
disponible. Ce document est ce re-cadrage.

**Décisions de cadrage actées en session (ne pas rediscuter en exécution) :**

- Les deux volets sont livrés ensemble (pas de découpage SP-5c1/SP-5c2).
- `$expr` s'évalue **récursivement** dans toute la structure de `props`
  (pas seulement au premier niveau de chaque clé).
- **Aucune migration** : les colonnes calculées du widget Table (SP-5a,
  forme `{ label, expr }`) et `visibleWhen` (SP-5a, champ string dédié)
  restent inchangés, intacts, non touchés par ce plan. `$expr` est un
  mécanisme général **supplémentaire**, pas un remplacement de ce qui
  marche déjà. Aucune forme de collision possible : les colonnes calculées
  n'ont pas de clé `$expr`, `visibleWhen` n'est pas dans `props`.
- Les 6 types de `Variable` (`string|number|bool|date|record|list`) sont
  tous dans le périmètre. `record`/`list` n'ont pas d'éditeur de valeur
  littérale dans le builder — ils démarrent vides et ne sont peuplés que
  par câblage d'action.
- L'interpolation `{{var:nom}}`/`{{champ}}` du widget Texte (SP-0) **reste
  le même mécanisme de substitution de token dans une chaîne** — non
  fusionnée avec `$expr` — rendue seulement tolérante aux nouveaux types
  de variable à la conversion finale en texte.
- `Variable.set` (l'action câblée depuis un émetteur) garde le
  comportement actuel (extraction `payload[nom_de_la_variable]`, coercée
  au type déclaré) pour `string`/`number`/`bool`/`date` ; pour
  `record`/`list`, la variable reçoit **le payload entier de l'émetteur**,
  sans extraction par clé (c'est ce qui rend `Table.itemSelected →
  Variable(type=record).set` utile : le payload est déjà un `DataRecord`
  complet, pas un objet avec une clé nommée comme la variable).

**Hors périmètre (explicitement différé, pas oublié) :**

- Pas de valeur initiale calculée par expression sur `Variable` elle-même
  (`initialValue` reste une valeur littérale ou vide, jamais
  `{ $expr }` — une « valeur initiale réactive » est une fonctionnalité
  différente, non demandée).
- Pas de fonctions CEL spécifiques aux dates au-delà de la comparaison de
  chaînes ISO — pas d'objet `Date` runtime dans le pipeline `vars`.
- Pas de couche de cache/réactivité centralisée pour `$expr` — même
  philosophie « évaluateur fin au point d'usage » que SP-5a/b.
- Pas d'évaluation côté cœur (Python) — le cœur ne fait que persister
  correctement les nouveaux champs (§4), comme pour SP-5a/b.

## 2. Découverte pendant le brainstorm : gap de persistance côté cœur

Comme pour SP-5a (`visibleWhen`) et SP-5b (`ActionMessage.when`), le cœur
valide toute config via `BuilderConfig.model_validate()` puis la
re-sérialise via `.model_dump(by_alias=True)` avant stockage
(`core/app/configs/repository.py`). Le modèle `Variable` actuel
(`core/app/configs/schemas.py:38-41`) est :

```python
class Variable(BaseModel):
    id: str
    name: str
    initialValue: str
```

`initialValue` y est **strictement typé `str`, obligatoire**. Une
`Variable` typée `number`/`bool`/`record`/`list` dont `initialValue` est
un nombre/booléen/objet/tableau JSON ferait échouer la validation Pydantic
au moment de l'enregistrement (Pydantic v2 ne coerce pas silencieusement
un `int`/`dict`/`list` vers `str`) — **rejet net à l'enregistrement**,
plus sévère que le silent-drop de SP-5a puisque `str` est obligatoire sans
`| None`. Ce plan doit donc élargir ce modèle (§4), sans quoi la
fonctionnalité shell ne survivrait pas à un vrai passage par le cœur.

## 3. Architecture

```
cel-js / evaluateExpression / validateExpression (SP-5a, inchangés)
  │
  ├─▶ shell/src/builder/exprBindings.ts (NOUVEAU)
  │     resolveExprBindings(value: unknown, ctx: ExprContext): unknown
  │     Parcourt récursivement une valeur : si c'est un objet de forme
  │     exacte { $expr: string } (et rien d'autre), le remplace par
  │     evaluateExpression($expr, ctx) ; si c'est un tableau, applique
  │     récursivement à chaque élément ; si c'est un objet « normal »,
  │     applique récursivement à chaque valeur ; sinon (primitive),
  │     retourne tel quel. Jamais throw (délègue à evaluateExpression,
  │     qui ne lève jamais).
  │
  ├─▶ WidgetHost.tsx — resolveExprBindings(item.props, ctx) avant de
  │     construire le ctx transmis à <Widget props=... />. Évalué dans
  │     les 3 modes (edit/preview/runtime) — contrairement à visibleWhen,
  │     ceci ne change pas la présence DOM du widget, donc pas de
  │     restriction au mode edit nécessaire (cohérent avec {{var:nom}}
  │     qui s'évalue déjà dans tous les modes aujourd'hui).
  │
  ├─▶ shell/src/builder/VariablesContext.tsx — la valeur interne devient
  │     Record<string, unknown> (était Record<string, string>) ;
  │     useSetVariable() prend désormais (name: string, value: unknown).
  │
  ├─▶ shell/src/builder/expr.ts — ExprContext.vars devient
  │     Record<string, unknown> (était Record<string, string>) —
  │     changement de signature mécanique, propagé à tous les points
  │     d'appel existants (WidgetHost, colonne calculée Table,
  │     ActionBus/AppRenderer) sans changement de comportement pour les
  │     variables déjà string.
  │
  ├─▶ AppRenderer.tsx (VariableBusBridge) — coercion typée au moment du
  │     Variable.set : string/number/bool/date extraient
  │     payload[variable.name] comme aujourd'hui puis coercent au type
  │     déclaré (dégradation silencieuse si non coercible, jamais de
  │     crash) ; record/list reçoivent le payload entier de l'émetteur.
  │
  └─▶ widgets/index.tsx (interpolate, widget Texte) — la conversion finale
        d'une valeur de variable en texte gère explicitement
        number/bool/date (String(...)) et record/list (JSON.stringify(...))
        en plus du cas string déjà géré ; le mécanisme de substitution de
        token lui-même est inchangé.
```

### Détail de la coercion `Variable.set` par type

| Type déclaré | Source de la valeur | Comportement si non coercible |
|---|---|---|
| `string` | `String(payload[variable.name] ?? "")` (inchangé) | n/a (toujours coercible) |
| `number` | `Number(payload[variable.name])` | `NaN` → ne met pas à jour (garde la valeur précédente) |
| `bool` | payload booléen tel quel, sinon chaîne `"true"`/`"1"` (insensible à la casse) → `true`, tout le reste → `false` | toujours coercible (jamais d'échec) |
| `date` | `String(payload[variable.name] ?? "")` (chaîne ISO attendue, aucune validation de format en SP-5c) | n/a |
| `record` | le payload entier de l'émetteur si c'est un objet non-tableau, sinon ne met pas à jour | payload non-objet → ignoré |
| `list` | le payload entier de l'émetteur si c'est un tableau, sinon ne met pas à jour | payload non-tableau → ignoré |

## 4. Cœur (Python) — persistance uniquement

```python
class Variable(BaseModel):
    id: str
    name: str
    type: Literal["string", "number", "bool", "date", "record", "list"] = "string"
    initialValue: str | float | bool | dict | list | None = ""
```

Toute config existante (sans champ `type`) reste valide (`type` par défaut
`"string"`, `initialValue` reste `str`). Aucune migration de données
nécessaire. Comme pour SP-5a/b, aucune évaluation CEL côté cœur — le champ
`type` n'est pas interprété par le cœur, seulement persisté et resservi
tel quel.

## 5. Builder UI

- `shell/src/builder/VariablesPanel.tsx` gagne un `<select>` "Type" par
  variable (les 6 valeurs). L'éditeur de valeur initiale devient
  conditionnel au type : champ texte (`string`), `<input type="number">`
  (`number`), case à cocher (`bool`), `<input type="date">` (`date`) ;
  pour `record`/`list`, l'éditeur de valeur initiale est remplacé par un
  texte indicatif (« définie par câblage d'action ») — pas de champ
  éditable.
- Aucun nouveau contrôle nécessaire pour `$expr` lui-même : un auteur de
  config tape `{ $expr: "…" }` comme valeur de n'importe quelle prop
  existante via les mécanismes déjà en place (ou, pour un agent MCP, via
  l'écriture directe de la config JSON) — pas de nouvel éditeur visuel
  dans cette sous-phase (cohérent avec le fait que `$expr` cible d'abord
  les cas non couverts par les panneaux de props existants ; un éditeur
  UI dédié par prop resterait un chantier ultérieur si le besoin se
  confirme à l'usage).

## 6. Stratégie de tests

- **Cœur.** Round-trip `type`/`initialValue` élargi sur `Variable`, même
  patron que les tests SP-5b sur `visibleWhen`/`when`
  (`core/tests/test_schemas.py`).
- **Shell, unitaire.** `resolveExprBindings` : primitive inchangée, `{
  $expr }` remplacé par sa valeur évaluée, récursion dans un tableau et
  un objet imbriqué, jamais de throw (expression invalide → `undefined`
  via `evaluateExpression`, propagé tel quel comme n'importe quelle autre
  valeur de prop). `VariableBusBridge`/coercion : chaque type de la table
  §3, y compris les cas de dégradation (nombre non coercible, payload
  non-objet pour `record`, etc.). `interpolate()` (widget Texte) :
  substitution correcte pour une variable `number`/`bool`/`record`/`list`.
  `WidgetHost` : une prop `{ $expr }` remplacée par sa valeur dans les 3
  modes.
- **Shell, E2E Playwright** (nouvelle spec). Scénario de référence :
  `Table.itemSelected` câblé vers une `Variable` de type `record` ; un
  widget **non-Texte** (Bouton, prop `label`) est lié via `{ $expr:
  "vars.selected.properties.nom" }` — démontre la capacité nouvelle
  (accéder à un champ imbriqué d'une donnée structurée depuis une prop
  qui ne pouvait pas être dynamique avant SP-5c), sans code, à travers un
  vrai navigateur.

## 7. Critères d'acceptation

- Une prop d'un widget autre que Texte (ex : le libellé d'un Bouton) peut
  être liée par expression CEL à une variable, y compris à un champ
  imbriqué d'une variable de type `record`, créé sans code, E2E vert.
- Une `Variable` de type `record`/`list` se peuple correctement depuis le
  payload entier d'un événement câblé (`itemSelected` d'un Table/Liste),
  sans extraction par clé.
- Aucune régression : les 16 specs E2E existantes (SP-0 à SP-5b) restent
  vertes ; toute config existante (variables sans `type`, colonnes
  calculées, `visibleWhen`) continue de fonctionner à l'identique.
- Le cœur persiste `Variable.type`/`initialValue` élargi sans rejet ni
  suppression silencieuse (test de round-trip dédié).

## 8. Risques

- **Ripple de signature `ExprContext.vars`/`VariablesContext`** (`string`
  → `unknown`) traverse tous les points d'appel de SP-5a/b. Mitigation :
  changement mécanique et non comportemental pour les variables déjà
  string (couvert par la suite de régression complète à chaque tâche,
  comme SP-5a/b) ; pas de nouvelle sémantique introduite pour les
  consommateurs existants.
- **Rejet de config au cœur si le fix Pydantic (§4) est oublié ou mal
  ordonné dans le plan d'exécution** — même classe de risque que SP-5a
  (silent-drop) mais plus sévère ici (rejet net, pas juste une perte
  silencieuse), car `initialValue: str` est aujourd'hui obligatoire sans
  `| None`. Mitigation : le fix cœur doit être la première tâche du plan
  d'exécution, comme SP-5b l'a fait pour `visibleWhen`/`when`.
- **Scope creep** (risque déjà nommé pour SP-4/SP-5 dans son ensemble).
  Mitigation : `$expr` s'arrête à la résolution de props avant rendu — pas
  d'éditeur UI dédié par prop, pas de fusion avec `{{var:nom}}`, pas de
  migration des mécanismes SP-5a existants. Chaque limite listée en §1 a
  été actée explicitement en session, pas laissée implicite.
