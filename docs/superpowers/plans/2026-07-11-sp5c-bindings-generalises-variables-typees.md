# SP-5c — Bindings CEL généralisés & variables typées : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toute prop de tout widget accepte `{ $expr: "…" }` (résolu récursivement dans `WidgetHost` avant passage au composant) ; `Variable` gagne un type (`string|number|bool|date|record|list`) qui pilote son éditeur dans le builder et la coercion appliquée par `Variable.set` — cf. [SP-5c — Bindings généralisés & variables typées](../specs/2026-07-11-sp5c-bindings-generalises-variables-typees-design.md).

**Architecture:** Un module `shell/src/builder/exprBindings.ts` (`resolveExprBindings`) parcourt récursivement `props`, remplaçant tout objet de forme exacte `{ $expr: string }` par sa valeur évaluée via `evaluateExpression` (SP-5a, inchangé) ; `WidgetHost` l'applique dans les 3 modes avant de monter le widget. `Variable` gagne un champ `type` optionnel (défaut `"string"`, rétrocompatible) ; `VariablesContext`/`ExprContext.vars`/`WidgetContext.variables` s'élargissent de `Record<string,string>` à `Record<string,unknown>` (changement mécanique, aucun comportement modifié pour les variables déjà string) ; `Variable.set` (câblé depuis un émetteur) coerce au type déclaré — extraction par clé du payload pour `string/number/bool/date` (comportement SP-4/5a inchangé), payload entier de l'émetteur pour `record/list`. Aucune migration des mécanismes SP-5a (`visibleWhen`, colonnes calculées du Table) ni fusion avec `{{var:nom}}` (rendu seulement tolérant aux nouveaux types).

**Tech Stack:** Python/Pydantic v2 (Task 1), React 19 + TypeScript + Vitest (Tasks 2-5), Playwright (Task 6, `VITE_AUTH_MODE=mock`).

## Global Constraints

- `evaluateExpression`/`validateExpression` (`shell/src/builder/expr.ts`, SP-5a) ne sont pas modifiés dans leur logique — seule la déclaration de type `ExprContext.vars` s'élargit (Task 4).
- **Aucune migration** : les colonnes calculées du widget Table (`{ label, expr }`) et `visibleWhen` restent inchangés, intacts. `$expr` ne les remplace pas, ne les touche pas (formes différentes, pas de collision possible).
- `$expr` se résout récursivement dans toute la structure de `props` (tableaux et objets imbriqués), dans les 3 modes (edit/preview/runtime) — contrairement à `visibleWhen`, il n'affecte pas la présence DOM du widget, donc pas de restriction au mode edit.
- Un objet est reconnu comme binding `$expr` **seulement** s'il a exactement une clé `$expr` dont la valeur est une chaîne — tout objet avec une clé supplémentaire (ex : `{ label, expr }` des colonnes calculées) n'est jamais traité comme un binding, seulement parcouru récursivement.
- `Variable.type` est optionnel côté shell (`type?: VariableType`), défaut runtime `"string"` — aucune migration de config existante nécessaire.
- `Variable.set` : `string/number/bool/date` gardent l'extraction `payload[variable.name]` (comportement SP-4/5a inchangé, coercée au type déclaré, dégradation silencieuse si non coercible — ne met jamais à jour sur échec, ne plante jamais) ; `record/list` reçoivent le payload entier de l'émetteur (pas d'extraction par clé), ignorés si le payload n'a pas la forme attendue (objet non-tableau pour `record`, tableau pour `list`).
- `{{var:nom}}` (widget Texte) reste le même mécanisme de substitution de token — rendu tolérant aux types non-string à la conversion finale (`String(...)` pour scalaires, `JSON.stringify(...)` pour `record`/`list`), pas fusionné avec `$expr`.
- Aucun changement à l'architecture d'évaluation : pas de couche de cache/réactivité centralisée.
- Cœur (Python) : `Variable.type`/`initialValue` élargi pour persister sans rejet ni suppression silencieuse — aucune évaluation CEL côté cœur.
- Aucune régression : `cd core && uv run pytest` (267+ tests) et `cd shell && npm run test` (371+ tests) + `npm run build` verts après chaque tâche 1-5 ; `cd shell && npm run e2e` vert après la Task 6 (16 specs existantes + la nouvelle = 17).
- Docs et messages utilisateur en français ; code/identifiants en anglais. TDD systématique ; commits conventional en français.

---

## Task 1: Cœur — `Variable.type` + `initialValue` élargi

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_schemas.py`

**Interfaces:**
- Produces: `Variable.type: Literal["string","number","bool","date","record","list"] = "string"` ; `Variable.initialValue: str | bool | float | dict | list | None = ""` — les deux round-trippent via `BuilderConfig.model_validate()`/`.model_dump(by_alias=True)`.
- Consumes: rien de nouveau (infra Pydantic existante).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `core/tests/test_schemas.py`, ajouter en fin de fichier :

```python
def test_variable_type_defaults_to_string():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "message", "initialValue": "salut"}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].type == "string"
    dumped = config.model_dump(by_alias=True)
    assert dumped["variables"][0]["type"] == "string"


def test_variable_type_number_round_trips_non_string_initial_value():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "count", "type": "number", "initialValue": 42}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].initialValue == 42
    dumped = config.model_dump(by_alias=True)
    assert dumped["variables"][0]["initialValue"] == 42


def test_variable_type_bool_round_trips_bool_initial_value():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "gate", "type": "bool", "initialValue": True}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].initialValue is True


def test_variable_type_record_round_trips_dict_initial_value():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "selected", "type": "record", "initialValue": {"nom": "A"}}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].initialValue == {"nom": "A"}
    dumped = config.model_dump(by_alias=True)
    assert dumped["variables"][0]["initialValue"] == {"nom": "A"}


def test_variable_type_list_round_trips_list_initial_value():
    payload = _valid_payload("app")
    payload["variables"] = [{"id": "v1", "name": "items", "type": "list", "initialValue": [1, 2, 3]}]
    config = BuilderConfig.model_validate(payload)
    assert config.variables[0].initialValue == [1, 2, 3]
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_schemas.py -v`
Expected: FAIL — les 5 nouveaux tests échouent (`AttributeError: 'Variable' object has no attribute 'type'` pour le premier ; `ValidationError` pour les 4 autres, `initialValue` n'acceptant qu'une chaîne aujourd'hui).

- [ ] **Step 3: Implémenter**

Dans `core/app/configs/schemas.py`, remplacer la classe `Variable` (actuellement lignes 38-41) :

```python
class Variable(BaseModel):
    id: str
    name: str
    type: Literal["string", "number", "bool", "date", "record", "list"] = "string"
    initialValue: str | bool | float | dict | list | None = ""
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_schemas.py -v`
Expected: PASS (tous, y compris les 5 nouveaux)

Run: `cd core && uv run pytest`
Expected: PASS (267+ tests, 30 skipped postgis) — aucune régression, y compris `test_variables_round_trip`/`test_variables_optional_defaults_empty` (initialValue reste une chaîne valide, matchée par la branche `str` de l'union).

- [ ] **Step 5: Commit**

```bash
cd core
git add app/configs/schemas.py tests/test_schemas.py
git commit -m "feat(core): Variable.type + initialValue élargi — persiste les variables typées sans rejet (SP-5c)"
```

---

## Task 2: `resolveExprBindings` — moteur récursif de résolution `$expr`

**Files:**
- Create: `shell/src/builder/exprBindings.ts`
- Test: `shell/src/builder/exprBindings.test.ts`

**Interfaces:**
- Produces: `resolveExprBindings(value: unknown, ctx: ExprContext): unknown` — jamais throw (délègue à `evaluateExpression`, qui ne lève jamais).
- Consumes: `evaluateExpression`, `ExprContext` (`shell/src/builder/expr.ts`, SP-5a, inchangé à ce stade — `vars` reste `Record<string,string>` jusqu'à la Task 4).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `shell/src/builder/exprBindings.test.ts` :

```ts
import { expect, test } from "vitest";
import { resolveExprBindings } from "./exprBindings";

const ctx = { vars: { seuil: "haute" }, record: { nom: "A" }, user: { name: "tanguy" } };

test("returns a primitive unchanged", () => {
  expect(resolveExprBindings("hello", ctx)).toBe("hello");
  expect(resolveExprBindings(42, ctx)).toBe(42);
  expect(resolveExprBindings(null, ctx)).toBe(null);
  expect(resolveExprBindings(undefined, ctx)).toBe(undefined);
});

test("replaces an { $expr } object with its evaluated value", () => {
  expect(resolveExprBindings({ $expr: "1 + 2" }, ctx)).toBe(3);
  expect(resolveExprBindings({ $expr: "vars.seuil" }, ctx)).toBe("haute");
});

test("does not treat an object with extra keys alongside $expr as a binding", () => {
  const value = { $expr: "1 + 2", label: "x" };
  expect(resolveExprBindings(value, ctx)).toEqual({ $expr: "1 + 2", label: "x" });
});

test("recurses into arrays, resolving each element", () => {
  expect(resolveExprBindings([{ $expr: "1 + 1" }, "plain", { $expr: "2 + 2" }], ctx)).toEqual([2, "plain", 4]);
});

test("recurses into nested plain objects", () => {
  const value = { a: { b: { $expr: "vars.seuil" } }, c: "d" };
  expect(resolveExprBindings(value, ctx)).toEqual({ a: { b: "haute" }, c: "d" });
});

test("does not treat a calculated-column object ({ label, expr }) as a binding", () => {
  const value = { label: "C", expr: "1 + 1" };
  expect(resolveExprBindings(value, ctx)).toEqual({ label: "C", expr: "1 + 1" });
});

test("never throws on an invalid expression, propagating undefined like any other value", () => {
  const value = { a: { $expr: "vars.seuil ==" } };
  expect(() => resolveExprBindings(value, ctx)).not.toThrow();
  expect(resolveExprBindings(value, ctx)).toEqual({ a: undefined });
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/exprBindings.test.ts`
Expected: FAIL — `Cannot find module './exprBindings'` (le fichier n'existe pas encore).

- [ ] **Step 3: Implémenter**

Créer `shell/src/builder/exprBindings.ts` :

```ts
import { evaluateExpression, type ExprContext } from "./expr";

function isExprBinding(value: unknown): value is { $expr: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.keys(value).length === 1 &&
    typeof (value as Record<string, unknown>).$expr === "string"
  );
}

export function resolveExprBindings(value: unknown, ctx: ExprContext): unknown {
  if (isExprBinding(value)) {
    return evaluateExpression(value.$expr, ctx);
  }
  if (Array.isArray(value)) {
    return value.map((v) => resolveExprBindings(v, ctx));
  }
  if (typeof value === "object" && value !== null) {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = resolveExprBindings(v, ctx);
    }
    return out;
  }
  return value;
}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/exprBindings.test.ts`
Expected: PASS (7/7)

Run: `cd shell && npm run test && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/exprBindings.ts src/builder/exprBindings.test.ts
git commit -m "feat(shell): resolveExprBindings — résolution récursive de { \$expr } dans une structure de props (SP-5c)"
```

---

## Task 3: `WidgetHost` intègre `resolveExprBindings`

**Files:**
- Modify: `shell/src/builder/WidgetHost.tsx`
- Modify: `shell/src/builder/WidgetHost.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: `WidgetHost` résout tout binding `{ $expr }` dans `item.props` avant de monter `<Widget>`, dans les 3 modes.
- Consumes: `resolveExprBindings` (Task 2).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/WidgetHost.test.tsx`, ajouter en fin de fichier :

```tsx
test("resolves an { $expr } prop value before passing it to the widget", () => {
  registerWidget({ type: "probe", label: "Probe", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ props }) => <div>value:{String(props.label)}</div> });
  render(<WidgetHost item={item("probe", { label: { $expr: "1 + 1" } })} mode="runtime" />);
  expect(screen.getByText("value:2")).toBeInTheDocument();
});

test("leaves a plain (non-$expr) prop value unchanged", () => {
  registerWidget({ type: "probe", label: "Probe", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ props }) => <div>value:{String(props.label)}</div> });
  render(<WidgetHost item={item("probe", { label: "static" })} mode="runtime" />);
  expect(screen.getByText("value:static")).toBeInTheDocument();
});

test("resolves { $expr } props in edit mode too, unlike visibleWhen", () => {
  registerWidget({ type: "probe", label: "Probe", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ props }) => <div>value:{String(props.label)}</div> });
  render(<WidgetHost item={item("probe", { label: { $expr: "1 + 1" } })} mode="edit" />);
  expect(screen.getByText("value:2")).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx -t "\$expr"`
Expected: FAIL — `WidgetHost` transmet encore `item.props` tel quel, donc le widget reçoit l'objet `{ $expr: "1 + 1" }` littéral et affiche `value:[object Object]` au lieu de `value:2`.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/WidgetHost.tsx`, ajouter l'import (après les imports existants) :

```ts
import { resolveExprBindings } from "./exprBindings";
```

Remplacer les 4 dernières lignes du corps de `WidgetHost` (actuellement lignes 51-56) :

```tsx
  const Widget = def.Component;
  const exprCtx = { vars: variables, record: data?.records[0]?.properties, user };
  const resolvedProps = resolveExprBindings(item.props, exprCtx) as Record<string, unknown>;
  return (
    <WidgetErrorBoundary>
      <Widget props={resolvedProps} ctx={{ mode, data, bus: bus ?? undefined, widgetId: item.id, pages, navigate, variables, user }} />
    </WidgetErrorBoundary>
  );
```

(`exprCtx` factorise le contexte déjà construit inline pour `visibleWhen` à la ligne précédente — même `vars`/`record`/`user`, réutilisé pour la résolution des props.)

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx`
Expected: PASS (tous, y compris les 3 nouveaux)

Run: `cd shell && npm run test && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/WidgetHost.tsx src/builder/WidgetHost.test.tsx
git commit -m "feat(shell): WidgetHost résout les bindings { \$expr } de toute prop avant de monter le widget (SP-5c)"
```

---

## Task 4: Variables typées — `Variable.type`, `VariablesContext` élargi, UI, `interpolate()` tolérant

**Files:**
- Modify: `shell/src/api/types.ts` (`Variable.type`, `Variable.initialValue` élargi)
- Modify: `shell/src/builder/registry.ts` (`WidgetContext.variables`)
- Modify: `shell/src/builder/expr.ts` (`ExprContext.vars`)
- Modify: `shell/src/builder/VariablesContext.tsx`
- Modify: `shell/src/builder/VariablesContext.test.tsx` (ajout de tests, en fin de fichier)
- Modify: `shell/src/builder/VariablesPanel.tsx`
- Modify: `shell/src/builder/VariablesPanel.test.tsx` (ajout de tests, en fin de fichier)
- Modify: `shell/src/builder/widgets/index.tsx` (`interpolate`)
- Modify: `shell/src/builder/widgets/text.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: `VariableType = "string"|"number"|"bool"|"date"|"record"|"list"` ; `Variable.type?: VariableType` (optionnel, défaut runtime `"string"`) ; `Variable.initialValue: string | number | boolean | Record<string, unknown> | unknown[] | null` ; `useVariables(): Record<string, unknown>` (était `Record<string,string>`) ; `useSetVariable(): (name: string, value: unknown) => void` (était `(name, value: string)`) ; `ExprContext.vars`/`WidgetContext.variables` élargis à `Record<string, unknown>`.
- Consumes: rien de nouveau — élargissement de types traversant tout SP-5a/b sans changement de comportement pour les variables déjà string.

**Ce changement est mécaniquement couplé** : `VariablesPanel.tsx` lie aujourd'hui `defaultValue={v.initialValue}` directement sur un `<input>` — élargir le type de `Variable.initialValue` sans retoucher ce fichier casserait la compilation (`defaultValue` n'accepte pas `boolean`/objet/tableau). De même, `interpolate()` construit une chaîne de remplacement depuis `variables[name]` — élargir `WidgetContext.variables` sans le retoucher casserait la compilation (le callback de `.replace()` doit retourner une `string`). Les deux doivent donc être traités dans la même tâche que l'élargissement de type, pas différés.

- [ ] **Step 1: Écrire les tests qui échouent (`VariablesContext`)**

Dans `shell/src/builder/VariablesContext.test.tsx`, ajouter en fin de fichier :

```tsx
test("useVariables and useSetVariable carry non-string values (number, bool, object, array)", async () => {
  function Probe2() {
    const values = useVariables();
    const setVariable = useSetVariable();
    return (
      <div>
        <p>count:{String(values.count)}</p>
        <button onClick={() => setVariable("count", 42)}>set-number</button>
        <button onClick={() => setVariable("selected", { nom: "A" })}>set-record</button>
      </div>
    );
  }
  render(<VariablesProvider variables={[{ id: "v1", name: "count", type: "number", initialValue: 0 }]}><Probe2 /></VariablesProvider>);
  expect(screen.getByText("count:0")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "set-number" }));
  expect(screen.getByText("count:42")).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/VariablesContext.test.tsx`
Expected: FAIL — TypeScript rejette `type: "number"` (propriété inconnue sur `Variable`) et `setVariable("count", 42)` (le second argument doit être `string`).

- [ ] **Step 3: Implémenter le type ripple**

Dans `shell/src/api/types.ts`, remplacer le type `Variable` (actuellement lignes 147-151) :

```ts
export type VariableType = "string" | "number" | "bool" | "date" | "record" | "list";

export type Variable = {
  id: string;
  name: string;
  type?: VariableType;
  initialValue: string | number | boolean | Record<string, unknown> | unknown[] | null;
};
```

Dans `shell/src/builder/registry.ts`, sur `WidgetContext` (actuellement ligne 9), remplacer :

```ts
  variables?: Record<string, unknown>;
```

Dans `shell/src/builder/expr.ts`, sur `ExprContext` (actuellement ligne 4), remplacer :

```ts
  vars: Record<string, unknown>;
```

Remplacer tout le contenu de `shell/src/builder/VariablesContext.tsx` :

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Variable } from "../api/types";

type SetVariable = (name: string, value: unknown) => void;

const VariablesContext = createContext<Record<string, unknown>>({});
const SetVariableContext = createContext<SetVariable>(() => {});

export function VariablesProvider({ variables, children }: { variables: Variable[]; children: ReactNode }) {
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const initial: Record<string, unknown> = {};
    for (const v of variables) initial[v.name] = v.initialValue;
    return initial;
  });

  // Pick up a variable added after this provider mounted (e.g. the editor's
  // VariablesPanel adding one live) without resetting values already
  // changed at runtime for variables that already existed.
  useEffect(() => {
    setValues((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const v of variables) {
        if (!(v.name in next)) {
          next[v.name] = v.initialValue;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [variables]);

  function setVariable(name: string, value: unknown) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <SetVariableContext.Provider value={setVariable}>
      <VariablesContext.Provider value={values}>{children}</VariablesContext.Provider>
    </SetVariableContext.Provider>
  );
}

export function useVariables(): Record<string, unknown> {
  return useContext(VariablesContext);
}

export function useSetVariable(): SetVariable {
  return useContext(SetVariableContext);
}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès (`VariablesContext`)**

Run: `cd shell && npx vitest run src/builder/VariablesContext.test.tsx`
Expected: PASS (4/4 — les 3 préexistants + le nouveau)

Run: `cd shell && npm run build`
Expected: **FAIL encore** — `VariablesPanel.tsx` (`defaultValue={v.initialValue}`) et `widgets/index.tsx` (`interpolate`) ne compilent plus sous les types élargis. C'est attendu à ce stade intermédiaire — poursuivre avec les Steps 5-10 avant de relancer le build.

- [ ] **Step 5: Écrire les tests qui échouent (`VariablesPanel`)**

Dans `shell/src/builder/VariablesPanel.test.tsx`, ajouter en fin de fichier :

```tsx
test("adds a variable defaulting to type string", async () => {
  const onChange = vi.fn();
  render(<VariablesPanel variables={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une variable" }));
  const next = onChange.mock.calls[0][0] as Variable[];
  expect(next[0].type).toBe("string");
});

test("changes a variable's type and resets its initial value to a default for that type", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "count", type: "string", initialValue: "abc" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Type de la variable v1"), "number");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0].type).toBe("number");
  expect(next[0].initialValue).toBe(0);
});

test("edits a number variable's initial value as a number", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "count", type: "number", initialValue: 0 }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Valeur initiale de la variable v1"), "5");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(typeof next[0].initialValue).toBe("number");
});

test("toggles a bool variable's initial value", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "gate", type: "bool", initialValue: false }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Valeur initiale de la variable v1"));
  expect(onChange).toHaveBeenCalledWith([{ id: "v1", name: "gate", type: "bool", initialValue: true }]);
});

test("shows no editable initial value for a record-typed variable", () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "selected", type: "record", initialValue: null }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  expect(screen.queryByLabelText("Valeur initiale de la variable v1")).not.toBeInTheDocument();
  expect(screen.getByText("Définie par câblage d'action")).toBeInTheDocument();
});
```

- [ ] **Step 6: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/VariablesPanel.test.tsx -t "type"`
Expected: FAIL — `VariablesPanel` ne rend encore aucun sélecteur de type (`getByLabelText("Type de la variable v1")` introuvable) ; le build TypeScript est également rouge sur ce fichier (cf. Step 4).

- [ ] **Step 7: Implémenter — `VariablesPanel.tsx`**

Remplacer tout le contenu de `shell/src/builder/VariablesPanel.tsx` :

```tsx
import type { Variable, VariableType } from "../api/types";

const TYPE_LABELS: Record<VariableType, string> = {
  string: "Texte",
  number: "Nombre",
  bool: "Booléen",
  date: "Date",
  record: "Enregistrement",
  list: "Liste",
};

function defaultValueFor(type: VariableType): Variable["initialValue"] {
  switch (type) {
    case "number": return 0;
    case "bool": return false;
    case "record": return null;
    case "list": return [];
    default: return "";
  }
}

export function VariablesPanel({
  variables,
  onChange,
}: {
  variables: Variable[];
  onChange: (variables: Variable[]) => void;
}) {
  function addVariable() {
    const v: Variable = { id: crypto.randomUUID(), name: `Variable ${variables.length + 1}`, type: "string", initialValue: "" };
    onChange([...variables, v]);
  }
  function remove(id: string) {
    onChange(variables.filter((v) => v.id !== id));
  }
  function rename(id: string, name: string) {
    onChange(variables.map((v) => (v.id === id ? { ...v, name } : v)));
  }
  function setType(id: string, type: VariableType) {
    onChange(variables.map((v) => (v.id === id ? { ...v, type, initialValue: defaultValueFor(type) } : v)));
  }
  function setInitialValue(id: string, initialValue: Variable["initialValue"]) {
    onChange(variables.map((v) => (v.id === id ? { ...v, initialValue } : v)));
  }
  return (
    <ul className="flex flex-col gap-1">
      {variables.map((v) => {
        const type = v.type ?? "string";
        return (
          <li key={v.id} className="flex items-center gap-1 rounded border border-slate-200 p-1 text-xs">
            <input
              aria-label={`Renommer la variable ${v.id}`}
              className="w-16 rounded border border-slate-300 px-1"
              defaultValue={v.name}
              onChange={(e) => rename(v.id, e.target.value)}
            />
            <select
              aria-label={`Type de la variable ${v.id}`}
              className="rounded border border-slate-300 px-1"
              value={type}
              onChange={(e) => setType(v.id, e.target.value as VariableType)}
            >
              {(Object.keys(TYPE_LABELS) as VariableType[]).map((t) => (
                <option key={t} value={t}>{TYPE_LABELS[t]}</option>
              ))}
            </select>
            {type === "string" && (
              <input
                aria-label={`Valeur initiale de la variable ${v.id}`}
                className="w-16 rounded border border-slate-300 px-1"
                defaultValue={String(v.initialValue ?? "")}
                onChange={(e) => setInitialValue(v.id, e.target.value)}
              />
            )}
            {type === "number" && (
              <input
                aria-label={`Valeur initiale de la variable ${v.id}`}
                type="number"
                className="w-16 rounded border border-slate-300 px-1"
                defaultValue={Number(v.initialValue ?? 0)}
                onChange={(e) => setInitialValue(v.id, Number(e.target.value))}
              />
            )}
            {type === "bool" && (
              <input
                aria-label={`Valeur initiale de la variable ${v.id}`}
                type="checkbox"
                checked={Boolean(v.initialValue)}
                onChange={(e) => setInitialValue(v.id, e.target.checked)}
              />
            )}
            {type === "date" && (
              <input
                aria-label={`Valeur initiale de la variable ${v.id}`}
                type="date"
                className="rounded border border-slate-300 px-1"
                defaultValue={String(v.initialValue ?? "")}
                onChange={(e) => setInitialValue(v.id, e.target.value)}
              />
            )}
            {(type === "record" || type === "list") && (
              <span className="text-slate-400">Définie par câblage d'action</span>
            )}
            <button type="button" aria-label={`Retirer la variable ${v.id}`} className="text-red-600" onClick={() => remove(v.id)}>✕</button>
          </li>
        );
      })}
      <li>
        <button type="button" className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-100" onClick={addVariable}>
          Ajouter une variable
        </button>
      </li>
    </ul>
  );
}
```

- [ ] **Step 8: Lancer les tests, vérifier le succès (`VariablesPanel`)**

Run: `cd shell && npx vitest run src/builder/VariablesPanel.test.tsx`
Expected: PASS (9/9 — les 4 préexistants + les 5 nouveaux)

- [ ] **Step 9: Écrire les tests qui échouent (`interpolate`)**

Dans `shell/src/builder/widgets/text.test.tsx`, ajouter en fin de fichier :

```tsx
test("text stringifies a number variable inserted via {{var:nom}}", () => {
  const Text = getWidget("text")!.Component;
  render(
    <Text props={{ text: "Total : {{var:count}}" }} ctx={{ mode: "runtime", variables: { count: 42 } } as WidgetContext} />,
  );
  expect(screen.getByText("Total : 42")).toBeInTheDocument();
});

test("text stringifies a bool variable inserted via {{var:nom}}", () => {
  const Text = getWidget("text")!.Component;
  render(
    <Text props={{ text: "Actif : {{var:gate}}" }} ctx={{ mode: "runtime", variables: { gate: true } } as WidgetContext} />,
  );
  expect(screen.getByText("Actif : true")).toBeInTheDocument();
});

test("text JSON-stringifies a record variable inserted via {{var:nom}}", () => {
  const Text = getWidget("text")!.Component;
  render(
    <Text props={{ text: "Sélection : {{var:selected}}" }}
      ctx={{ mode: "runtime", variables: { selected: { nom: "A" } } } as WidgetContext} />,
  );
  expect(screen.getByText('Sélection : {"nom":"A"}')).toBeInTheDocument();
});
```

- [ ] **Step 10: Lancer les tests, vérifier l'échec, puis implémenter**

Run: `cd shell && npx vitest run src/builder/widgets/text.test.tsx -t "stringifies"`
Expected: FAIL — le TypeScript est rouge sur `widgets/index.tsx` (`interpolate` déclare encore `variables: Record<string, string>`, incompatible avec `WidgetContext.variables: Record<string, unknown>` — Vitest transpile via esbuild donc les tests échouent à l'exécution avec `42` affiché comme `undefined`/erreur plutôt que par une erreur de compilation stricte, mais `npm run build`, lui, échoue net).

Dans `shell/src/builder/widgets/index.tsx`, remplacer la fonction `interpolate` (actuellement lignes 12-24) :

```ts
// Replaces {{var:nom}} tokens from ctx.variables (always, regardless of any
// bound source), then {{champ}} tokens from the record's properties (only
// when a source is bound — an unbound Texte still shows {{champ}} verbatim).
function stringifyVariable(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function interpolate(text: string, record: DataRecord | undefined, variables: Record<string, unknown>): string {
  let out = text.replace(/\{\{\s*var:([\w.]+)\s*\}\}/g, (_, name: string) => stringifyVariable(variables[name]));
  if (record) {
    out = out.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key: string) => {
      const v = record.properties[key];
      return v === null || v === undefined ? "" : String(v);
    });
  }
  return out;
}
```

- [ ] **Step 11: Lancer les tests, vérifier le succès, puis la suite complète**

Run: `cd shell && npx vitest run src/builder/widgets/text.test.tsx`
Expected: PASS (tous, y compris les 3 nouveaux)

Run: `cd shell && npm run test && npm run build`
Expected: PASS — le build compile de nouveau (les deux points de rupture intermédiaires du Step 4/10 sont résolus).

- [ ] **Step 12: Commit**

```bash
cd shell
git add src/api/types.ts src/builder/registry.ts src/builder/expr.ts \
  src/builder/VariablesContext.tsx src/builder/VariablesContext.test.tsx \
  src/builder/VariablesPanel.tsx src/builder/VariablesPanel.test.tsx \
  src/builder/widgets/index.tsx src/builder/widgets/text.test.tsx
git commit -m "feat(shell): variables typées — Variable.type, VariablesContext élargi, sélecteur de type, interpolation tolérante (SP-5c)"
```

---

## Task 5: `VariableBusBridge` — coercion typée à `Variable.set`

**Files:**
- Modify: `shell/src/builder/AppRenderer.tsx`
- Modify: `shell/src/builder/AppRenderer.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: `Variable.set` (câblé depuis un émetteur via `ActionBus`) coerce le payload au type déclaré de la variable cible — `string/number/bool/date` extraient `payload[variable.name]` (comportement inchangé) puis coercent ; `record/list` reçoivent le payload entier de l'émetteur.
- Consumes: `Variable.type` (Task 4).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/AppRenderer.test.tsx`, ajouter en fin de fichier :

```tsx
test("a number-typed variable coerces the payload's matching field to a number", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "count", type: "number", initialValue: 0 }],
    messages: [{ id: "m1", from: "flt1", event: "changed", to: "var:v1", action: "set" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "flt1", widget: "filter", x: 0, y: 0, w: 3, h: 1, props: { field: "count", label: "Filtre" } },
      { id: "t1", widget: "text", x: 0, y: 1, w: 4, h: 2, props: { text: "Total : {{var:count}}" } },
    ] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "42");
  expect(await screen.findByText("Total : 42")).toBeInTheDocument();
});

test("a number-typed variable keeps its previous value when the payload is not a valid number", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "count", type: "number", initialValue: 7 }],
    messages: [{ id: "m1", from: "flt1", event: "changed", to: "var:v1", action: "set" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "flt1", widget: "filter", x: 0, y: 0, w: 3, h: 1, props: { field: "count", label: "Filtre" } },
      { id: "t1", widget: "text", x: 0, y: 1, w: 4, h: 2, props: { text: "Total : {{var:count}}" } },
    ] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "abc");
  expect(screen.getByText("Total : 7")).toBeInTheDocument();
});

test("a record-typed variable receives the emitter's whole payload, not an extraction by name", async () => {
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [],
    variables: [{ id: "v1", name: "selected", type: "record", initialValue: null }],
    messages: [{ id: "m1", from: "btn1", event: "clicked", to: "var:v1", action: "set" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "btn1", widget: "button", x: 0, y: 0, w: 2, h: 1, props: { label: "Go" } },
      { id: "t1", widget: "text", x: 0, y: 1, w: 4, h: 2, props: { text: "Sélection : {{var:selected}}" } },
    ] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.click(screen.getByRole("button", { name: "Go" }));
  // Button emits { widgetId: "btn1" } — the whole payload, stored as-is (record type bypasses by-name extraction).
  expect(await screen.findByText('Sélection : {"widgetId":"btn1"}')).toBeInTheDocument();
});

test("a list-typed variable receives the emitter's whole payload when it is an array", async () => {
  _resetRegistry();
  registerBuiltinWidgets();
  registerWidget({
    type: "list-emitter-probe",
    label: "Probe",
    defaultProps: {},
    defaultSize: { w: 2, h: 1 },
    events: ["emitted"],
    PropsPanel: () => null,
    Component: ({ ctx }) => (
      <button onClick={() => ctx.bus?.emit(ctx.widgetId ?? "", "emitted", [1, 2, 3])}>emit</button>
    ),
  });
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [],
    variables: [{ id: "v1", name: "items", type: "list", initialValue: [] }],
    messages: [{ id: "m1", from: "p1", event: "emitted", to: "var:v1", action: "set" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "p1", widget: "list-emitter-probe", x: 0, y: 0, w: 2, h: 1, props: {} },
      { id: "t1", widget: "text", x: 0, y: 1, w: 4, h: 2, props: { text: "Items : {{var:items}}" } },
    ] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.click(screen.getByRole("button", { name: "emit" }));
  expect(await screen.findByText("Items : [1,2,3]")).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx -t "typed variable"`
Expected: FAIL — `VariableBusBridge` stringifie toujours tout via `valueFromPayload` (`String(v)`), donc `count` reste une chaîne `"42"` affichée correctement par coïncidence dans le premier test (l'interpolation stringifie de toute façon) MAIS le test "keeps its previous value when not a valid number" échoue (`"abc"` écrase `7` au lieu d'être ignoré), et le test `record` échoue (`Sélection : [object Object]` au lieu du JSON stringifié — `String({widgetId:"btn1"})` produit `"[object Object]"`, pas `payload` stocké tel quel).

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/AppRenderer.tsx`, remplacer `valueFromPayload` et `VariableBusBridge` (actuellement lignes 14-33) :

```ts
// A message's payload is whatever shape its emitter chose (Button emits
// {widgetId}, Filtre emits {[field]: value}, …). For string/number/bool/date
// variables, extract the payload key matching the variable's own name (e.g.
// a Filtre configured with field === the variable's name) and coerce to the
// declared type — degrade silently (keep the previous value) if not
// coercible, never throw. For record/list variables, the whole emitter
// payload is stored as-is (no by-name extraction) — this is what makes
// wiring e.g. Table.itemSelected into a record variable useful, since its
// payload is already a full DataRecord, not an object keyed by variable name.
function coerceForVariable(payload: unknown, variable: Variable): unknown {
  const type = variable.type ?? "string";
  if (type === "record") {
    return payload && typeof payload === "object" && !Array.isArray(payload) ? payload : undefined;
  }
  if (type === "list") {
    return Array.isArray(payload) ? payload : undefined;
  }
  const raw = payload && typeof payload === "object"
    ? (payload as Record<string, unknown>)[variable.name]
    : payload;
  if (type === "number") {
    const n = Number(raw);
    return Number.isNaN(n) ? undefined : n;
  }
  if (type === "bool") {
    if (typeof raw === "boolean") return raw;
    return ["true", "1"].includes(String(raw ?? "").toLowerCase());
  }
  // string, date
  return raw === null || raw === undefined ? "" : String(raw);
}

function VariableBusBridge({ variable, bus }: { variable: Variable; bus: ActionBus }) {
  const setVariable = useSetVariable();
  useBusAction(bus, `var:${variable.id}`, "set", (payload) => {
    const value = coerceForVariable(payload, variable);
    if (value === undefined) return; // not coercible for this type — keep the previous value, never crash
    setVariable(variable.name, value);
  });
  return null;
}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: PASS (tous, y compris les 4 nouveaux — notamment le test préexistant SP-5a « resolves to empty string, not [object Object] » : Button émet `{widgetId}`, variable `"message"` par défaut `type` absent → `"string"`, `raw = payload["message"]` = `undefined` → retourne `""`, comportement identique à avant.)

Run: `cd shell && npm run test && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/AppRenderer.tsx src/builder/AppRenderer.test.tsx
git commit -m "feat(shell): VariableBusBridge — coercion typée à Variable.set, payload entier pour record/list (SP-5c)"
```

---

## Task 6: E2E — spec « bindings généralisés & variable record »

**Files:**
- Create: `shell/e2e/expr-bindings.spec.ts`

**Interfaces:**
- Consumes: tout SP-5c (Tasks 1-5). Réutilise la collection mock `villes` (`shell/e2e/mocks.ts`, existante — `{ region: "Nord"|"Sud", annee, pop }`, 4 enregistrements).

**Note de conception (pourquoi cette spec sème une config partielle) :** SP-5c ne fournit délibérément aucun éditeur visuel pour saisir `{ $expr }` sur une prop (spec §5, cohérent avec le fait que $expr cible d'abord les configs hand/MCP-authored). Le champ *Libellé du bouton* du builder reste un `<input>` texte ordinaire — on ne peut pas y taper un objet JS. Cette spec construit donc la variable et le câblage d'action **entièrement via l'UI** (comme toutes les specs E2E précédentes), mais sème le widget Bouton portant `{ $expr }` directement dans la réponse mockée du tout premier chargement de la config (avant toute interaction), via une interception Playwright à usage unique qui délègue ensuite (`route.fallback()`) au mock standard `mockCore` pour tous les chargements/sauvegardes suivants — le Bouton semé persiste alors naturellement à travers le cycle normal d'édition/sauvegarde comme n'importe quel autre widget du brouillon.

- [ ] **Step 1: Écrire la spec**

Créer `shell/e2e/expr-bindings.spec.ts` :

```ts
import { test, expect, type Page, type Route } from "@playwright/test";
import { mockCore } from "./mocks";

// Seeds the very first config GET for item 9 with a Bouton whose label is a
// { $expr } binding — no builder UI can produce this today (SP-5c §5), so it
// stands in for a hand- or MCP-authored config. Fires once, then defers
// (route.fallback()) to mockCore's own handler for every later GET/PUT, so
// the seeded widget round-trips normally through the rest of the test.
async function seedExprBoundButton(page: Page) {
  let seeded = false;
  await page.route("**/configs/by-item/**", async (route: Route) => {
    if (seeded || route.request().method() !== "GET" || !route.request().url().endsWith("/9")) {
      await route.fallback();
      return;
    }
    seeded = true;
    await route.fulfill({
      json: {
        id: "cfg-9", itemId: "9", kind: "app",
        config: {
          kind: "app", theme: {}, dataSources: [], messages: [],
          layout: { type: "grid", breakpoints: {}, items: [
            { id: "btn-expr", widget: "button", x: 0, y: 4, w: 2, h: 1,
              props: { label: { $expr: "vars.selected.properties.region" }, href: "" } },
          ] },
        },
      },
    });
  });
}

test("un binding { \$expr } sur une prop non-Texte lit un champ imbriqué d'une variable record, sans code pour le câblage", async ({ page }) => {
  await mockCore(page);
  await seedExprBoundButton(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App bindings");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Le Bouton { $expr } semé est déjà dans le canvas ; vars.selected vaut
  // encore null (variable pas encore créée) donc l'expression échoue en
  // silence et le Bouton retombe sur son libellé par défaut.
  await expect(page.getByRole("button", { name: "Bouton" })).toBeVisible();

  // Source de données : collection "villes" (region: Nord|Sud, annee, pop).
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("villes");

  // Table liée à la source.
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Colonnes (séparées par des virgules)").fill("region,annee");

  // Variable "selected", type "record".
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("selected");
  await page.getByLabel(/Type de la variable/).selectOption("record");

  // Table.itemSelected -> Variable(selected).set.
  await page.getByLabel("Widget émetteur").selectOption({ label: "Table" });
  await page.getByLabel("Événement").selectOption("itemSelected");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : selected" });
  await page.getByLabel("Action").selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("button", { name: "Bouton" })).toBeVisible();

  // Cliquer une ligne "Nord" : Table.itemSelected émet le DataRecord entier,
  // la variable "selected" (record) le reçoit tel quel, le Bouton relit
  // vars.selected.properties.region par expression.
  await page.getByRole("cell", { name: "Nord" }).first().click();
  await expect(page.getByRole("button", { name: "Nord" })).toBeVisible();
});
```

- [ ] **Step 2: Lancer la spec**

Run: `cd shell && npx playwright test expr-bindings.spec.ts`
Expected: PASS — les Tasks 1-5 implémentent déjà tout ce que cette spec exerce ; ce n'est pas un cycle RED/GREEN, c'est la confirmation d'intégration bout-en-bout. Si elle échoue, investiguer lequel des maillons (Tasks 1-5) ne s'intègre pas comme supposé — en particulier vérifier que le Bouton semé apparaît bien dans le canvas après création (l'interception `seedExprBoundButton` doit intercepter le tout premier GET, pas un GET ultérieur) avant de modifier quoi que ce soit d'autre.

- [ ] **Step 3: Lancer la suite E2E complète**

Run: `cd shell && npm run e2e`
Expected: PASS — 17 specs vertes (16 existantes + `expr-bindings.spec.ts`).

- [ ] **Step 4: Commit**

```bash
cd shell
git add e2e/expr-bindings.spec.ts
git commit -m "test(shell): e2e — un binding \$expr sur une prop non-Texte lit un champ imbriqué d'une variable record (SP-5c)"
```

---

## Couverture spec → tâches (auto-vérification)

- §1 « `$expr` récursif, aucune migration des mécanismes SP-5a, 6 types de Variable, record/list sans éditeur littéral, `Variable.set` extraction-par-clé vs payload-entier, `{{var:nom}}` non fusionné » → Tasks 2-5 (chaque décision de cadrage a sa tâche).
- §2 « gap de persistance cœur » → Task 1.
- §3 architecture (diagramme, table de coercion) → Tasks 2, 3, 4 (VariablesContext/interpolate), 5 (coercion `Variable.set`) — mêmes fonctions/signatures.
- §4 cœur → Task 1.
- §5 builder UI (sélecteur de type, pas de nouvel éditeur `$expr`) → Task 4 ; l'absence délibérée d'éditeur `$expr` est documentée et gérée explicitement dans la conception de la Task 6.
- §6 stratégie de tests (unitaire par module, E2E Table.itemSelected → variable record → `$expr` sur prop non-Texte) → Tasks 2-6.
- §7 critères d'acceptation → Task 6 (E2E), Task 1 (round-trip cœur dédié), toutes tâches (suite de régression complète à chaque commit).
- §8 risques (ripple de signature, rejet cœur si le fix est oublié, scope creep) → Task 4 (ripple traité en un seul commit cohérent), Task 1 positionnée en premier (comme SP-5b), périmètre limité tel qu'explicitement acté en §1.
