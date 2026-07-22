# SP-5b — Actions composées avec condition : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une `ActionMessage` du bus (`ActionBus.ts`) gagne une condition CEL optionnelle (`when`) : le message ne déclenche son action que si l'expression s'évalue à vrai, dans le contexte du payload de l'événement émetteur (`record`), des variables courantes (`vars`) et de l'utilisateur authentifié (`user`) — cf. [SP-5 — Expressions & actions composées](../specs/2026-07-11-sp5-expressions-actions-composees-design.md) §1 (SP-5b).

**Architecture:** Réutilise `evaluateExpression`/`validateExpression` de SP-5a (`shell/src/builder/expr.ts`) sans les modifier. `ActionBus` (classe non-React) gagne un `context: ExprContext` interne, mis à jour par un petit composant pont (`ActionConditionBridge`) monté dans `AppRenderer` — même patron que `VariableBusBridge` existant. `ActionBus.emit()` calcule `record` à partir du payload de l'émetteur et, si `m.when` est défini, saute la cible si `evaluateExpression(m.when, { ...context, record })` est faux. Un message sans `when` se comporte exactement comme avant (aucune régression). L'UI (`ActionsPanel.tsx`) gagne un champ de condition éditable par message ; `getConfigExpressionErrors` (SP-5a) valide aussi ces conditions.

**Découverte pendant la préparation de ce plan (hors périmètre initial de SP-5b, incluse ici avec accord de Tanguy) :** le cœur (`core/app/configs/schemas.py`) valide toute config via `BuilderConfig.model_validate()` puis la re-sérialise via `.model_dump(by_alias=True)` avant stockage (`core/app/configs/repository.py`). `LayoutItem` et `Message` n'ont pas de champ `extra="forbid"` (pas de rejet), mais n'ont pas non plus les champs `visibleWhen`/`when` déclarés — ils sont donc **silencieusement supprimés** à chaque enregistrement réel passant par le vrai cœur (pas détecté par les E2E de SP-5a, qui mockent le réseau via `mockCore` et ne touchent jamais Pydantic). La Task 1 ci-dessous corrige les deux champs en même temps (même fichier, même cause racine) avant que le reste du plan ne s'appuie dessus.

**Tech Stack:** Python/Pydantic v2 (Task 1), React 19 + TypeScript + Vitest (Tasks 2-4), Playwright (Task 5, `VITE_AUTH_MODE=mock`). Aucune nouvelle dépendance.

## Global Constraints

- `evaluateExpression`/`validateExpression` (SP-5a, `shell/src/builder/expr.ts`) ne sont pas modifiés — `evaluateExpression` ne lève jamais, retourne `undefined` sur toute erreur (variable/champ absent, type incompatible), avec un `console.warn`.
- `ActionMessage.when` est **optionnel**. Absent → comportement inchangé (le message fire toujours, comme avant ce plan). Présent et faux/`undefined` → la cible ne reçoit pas l'appel, mais reste enregistrée sur le bus (pas de désinscription).
- Le vocabulaire d'une condition est le même `ExprContext` que SP-5a (`{ vars: Record<string,string>; record?: Record<string,unknown>; user: { name: string } }`) : `record` = le payload de l'événement émetteur (l'objet passé à `emit()`, tel quel — pas de transformation `.properties`, cohérent avec le fait que chaque émetteur choisit déjà la forme de son payload et que l'auteur de la condition écrit l'expression en conséquence), `vars`/`user` = les mêmes valeurs vivantes que celles déjà threadées dans `WidgetHost`/`WidgetContext` (variables courantes de `VariablesContext`, `username` de `useAuth()`).
- Aucun changement à l'architecture d'évaluation : pas de couche réactive/cache centralisée. `ActionBus` garde un état minimal (`context: ExprContext`), mis à jour par un effet React côté `AppRenderer`, lu de façon synchrone à chaque `emit()`.
- Cœur (Python) : uniquement les deux champs optionnels de persistance (Task 1) — aucune évaluation CEL côté serveur (différée à une sous-phase ultérieure, cf. spec SP-5 §1).
- Aucune régression : `cd core && uv run pytest` (293+ tests), `cd shell && npm run test` (356+ tests) et `npm run build` verts après chaque tâche 1-4 ; `cd shell && npm run e2e` vert après la Task 5 (15 specs existantes + la nouvelle = 16).
- Docs et messages utilisateur en français ; code/identifiants en anglais. TDD systématique ; commits conventional en français.

---

## Task 1: Cœur — persister `visibleWhen` et `when`

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_schemas.py`

**Interfaces:**
- Produces: `LayoutItem.visibleWhen: str | None = None`, `Message.when: str | None = None` — les deux round-trippent via `BuilderConfig.model_validate(...)` / `.model_dump(by_alias=True)`.
- Consumes: rien de nouveau (infra Pydantic existante).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `core/tests/test_schemas.py`, ajouter en fin de fichier :

```python
def test_layout_item_visible_when_round_trip():
    payload = _valid_payload("app")
    payload["layout"]["items"][0]["visibleWhen"] = "vars.x == 'a'"
    config = BuilderConfig.model_validate(payload)
    assert config.layout.items[0].visibleWhen == "vars.x == 'a'"
    dumped = config.model_dump(by_alias=True)
    assert dumped["layout"]["items"][0]["visibleWhen"] == "vars.x == 'a'"


def test_layout_item_visible_when_optional():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.layout.items[0].visibleWhen is None


def test_message_when_round_trip():
    payload = _valid_payload("app")
    payload["messages"][0]["when"] = "record.nom == 'A'"
    config = BuilderConfig.model_validate(payload)
    assert config.messages[0].when == "record.nom == 'A'"
    dumped = config.model_dump(by_alias=True)
    assert dumped["messages"][0]["when"] == "record.nom == 'A'"


def test_message_when_optional():
    config = BuilderConfig.model_validate(_valid_payload())
    assert config.messages[0].when is None
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_schemas.py -v`
Expected: `test_layout_item_visible_when_round_trip` et `test_message_when_round_trip` FAIL (`AttributeError: 'LayoutItem' object has no attribute 'visibleWhen'` / idem `Message.when`) ; les deux tests `_optional` passent déjà par accident (l'attribut manquant lève avant l'assertion `is None`, donc ils échouent aussi avec la même `AttributeError` — les 4 nouveaux tests échouent).

- [ ] **Step 3: Implémenter**

Dans `core/app/configs/schemas.py`, sur `LayoutItem` (lignes 14-22), ajouter le champ :

```python
class LayoutItem(BaseModel):
    id: str | None = None
    widget: str
    x: int
    y: int
    w: int
    h: int
    props: dict = Field(default_factory=dict)
    layouts: dict[str, dict] | None = None
    visibleWhen: str | None = None
```

Sur `Message` (lignes 43-49), ajouter le champ :

```python
class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    event: str
    to: str
    action: str
    when: str | None = None
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_schemas.py -v`
Expected: PASS (tous, y compris les 4 nouveaux)

Run: `cd core && uv run pytest`
Expected: PASS (293+ tests — aucune régression ; `test_mcp_tools_configs.py`/`test_mcp_schema.py` ne pinnent pas un schéma exact, donc n'ont pas besoin de mise à jour)

- [ ] **Step 5: Commit**

```bash
cd core
git add app/configs/schemas.py tests/test_schemas.py
git commit -m "fix(core): persiste visibleWhen et when — évitait leur suppression silencieuse à l'enregistrement (SP-5b)"
```

---

## Task 2: `ActionMessage.when` — `ActionBus` conditionne l'émission

**Files:**
- Modify: `shell/src/api/types.ts` (`ActionMessage.when`)
- Modify: `shell/src/builder/ActionBus.ts`
- Modify: `shell/src/builder/ActionBus.test.ts`

**Interfaces:**
- Produces: `ActionMessage.when?: string` ; `ActionBus.setContext(context: ExprContext): void` (nouvelle méthode, remplace le contexte interne, défaut `{ vars: {}, user: { name: "" } }`) ; `ActionBus.emit(widgetId, event, payload?)` — inchangé en signature, mais saute désormais l'appel à la cible d'un message dont `when` est défini et s'évalue à faux contre `{ ...context, record }` (`record` = `payload` casté en objet si c'en est un, sinon `undefined`).
- Consumes: `evaluateExpression`, `ExprContext` (`shell/src/builder/expr.ts`, SP-5a, inchangé).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/ActionBus.test.ts`, ajouter en fin de fichier :

```ts
test("fires the action when the condition evaluates truthy against the payload", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter", when: "record.nom == 'A'" }]);
  bus.emit("filter1", "changed", { nom: "A" });
  expect(handler).toHaveBeenCalledWith({ nom: "A" });
});

test("does not fire the action when the condition evaluates falsy against the payload", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter", when: "record.nom == 'A'" }]);
  bus.emit("filter1", "changed", { nom: "B" });
  expect(handler).not.toHaveBeenCalled();
});

test("a message without a condition always fires (no regression)", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter" }]);
  bus.emit("filter1", "changed", { nom: "anything" });
  expect(handler).toHaveBeenCalledWith({ nom: "anything" });
});

test("evaluates the condition against vars/user set via setContext, not just the payload", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.setContext({ vars: { seuil: "haute" }, user: { name: "tanguy" } });
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter", when: "vars.seuil == 'haute' && user.name == 'tanguy'" }]);
  bus.emit("filter1", "changed", {});
  expect(handler).toHaveBeenCalled();
});

test("a malformed condition never throws and is treated as not matching", () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("list1", "setFilter", handler);
  bus.configure([{ id: "m1", from: "filter1", event: "changed", to: "list1", action: "setFilter", when: "record.missingField.nested" }]);
  expect(() => bus.emit("filter1", "changed", { nom: "A" })).not.toThrow();
  expect(handler).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/ActionBus.test.ts`
Expected: FAIL — TypeScript rejette `when`/`setContext` (propriétés inconnues), et à l'exécution `ActionBus.emit` ignore encore tout `when`, donc le test "does not fire… falsy" échoue (le handler est appelé alors qu'il ne devrait pas).

- [ ] **Step 3: Implémenter**

Dans `shell/src/api/types.ts`, sur `ActionMessage` (actuellement lignes 175-181), ajouter le champ :

```ts
export type ActionMessage = {
  id: string;
  from: string;
  event: string;
  to: string;
  action: string;
  when?: string;
};
```

Remplacer tout le contenu de `shell/src/builder/ActionBus.ts` :

```ts
import type { ActionMessage } from "../api/types";
import { evaluateExpression, type ExprContext } from "./expr";

export type BusHandler = (payload?: unknown) => void;

// Per-app event bus. Widgets emit events and register actions; the renderer
// wires config.messages so emitting an event invokes the target action(s).
// Keys join id + name with a space; ids are UUIDs / fixed literals (no spaces), so keys don't collide in practice.
export class ActionBus {
  private actions = new Map<string, BusHandler>();
  private wiring = new Map<string, ActionMessage[]>();
  private context: ExprContext = { vars: {}, user: { name: "" } };

  configure(messages: ActionMessage[]): void {
    this.wiring.clear();
    for (const m of messages) {
      const key = `${m.from} ${m.event}`;
      const list = this.wiring.get(key) ?? [];
      list.push(m);
      this.wiring.set(key, list);
    }
  }

  // Keeps the vars/user available to a message's `when` condition current.
  // Called by AppRenderer (Task 3) whenever live variables or the
  // authenticated user change.
  setContext(context: ExprContext): void {
    this.context = context;
  }

  register(widgetId: string, action: string, handler: BusHandler): () => void {
    const key = `${widgetId} ${action}`;
    this.actions.set(key, handler);
    return () => {
      if (this.actions.get(key) === handler) this.actions.delete(key);
    };
  }

  emit(widgetId: string, event: string, payload?: unknown): void {
    const list = this.wiring.get(`${widgetId} ${event}`) ?? [];
    const record = payload && typeof payload === "object" ? (payload as Record<string, unknown>) : undefined;
    for (const m of list) {
      if (m.when && !evaluateExpression(m.when, { ...this.context, record })) continue;
      this.actions.get(`${m.to} ${m.action}`)?.(payload);
    }
  }
}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/ActionBus.test.ts`
Expected: PASS (10/10 — les 5 préexistants + les 5 nouveaux)

Run: `cd shell && npm run test && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/api/types.ts src/builder/ActionBus.ts src/builder/ActionBus.test.ts
git commit -m "feat(shell): ActionMessage.when — ActionBus ne déclenche une action que si la condition CEL est vraie (SP-5b)"
```

---

## Task 3: `AppRenderer` — alimente `ActionBus` avec les vars/user courants

**Files:**
- Modify: `shell/src/builder/AppRenderer.tsx`
- Modify: `shell/src/builder/AppRenderer.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: rien de nouveau exporté — câblage interne uniquement (`ActionConditionBridge`, composant privé non exporté).
- Consumes: `ActionBus.setContext` (Task 2), `useVariables` (`shell/src/builder/VariablesContext.tsx`, existant), `useAuth` (`shell/src/auth/useAuth.ts`, existant — déjà mocké dans ce fichier de test depuis SP-5a).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/AppRenderer.test.tsx`, ajouter en fin de fichier :

```tsx
test("a message's condition gates the action on the emitting event's payload", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "status", initialValue: "" }],
    messages: [{ id: "m1", from: "flt1", event: "changed", to: "var:v1", action: "set", when: "record.nom == 'Nord'" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "flt1", widget: "filter", x: 0, y: 0, w: 3, h: 1, props: { field: "nom", label: "Filtre" } },
      { id: "t1", widget: "text", x: 0, y: 1, w: 4, h: 2, props: { text: "Statut: {{var:status}}" } },
    ] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("Statut:")).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "Nord");
  expect(await screen.findByText("Statut: Nord")).toBeInTheDocument();
});

test("a message's condition can reference live vars, not just the payload", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [
      { id: "gate", name: "gate", initialValue: "open" },
      { id: "v1", name: "message", initialValue: "" },
    ],
    messages: [{ id: "m1", from: "flt1", event: "changed", to: "var:v1", action: "set", when: "vars.gate == 'open'" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "flt1", widget: "filter", x: 0, y: 0, w: 3, h: 1, props: { field: "message", label: "Filtre" } },
      { id: "t1", widget: "text", x: 0, y: 1, w: 4, h: 2, props: { text: "Msg: {{var:message}}" } },
    ] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "hi");
  expect(await screen.findByText("Msg: hi")).toBeInTheDocument();
});

test("a message's condition prevents the action from firing when it evaluates falsy", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "message", initialValue: "initial" }],
    messages: [{ id: "m1", from: "flt1", event: "changed", to: "var:v1", action: "set", when: "vars.gate == 'open'" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "flt1", widget: "filter", x: 0, y: 0, w: 3, h: 1, props: { field: "message", label: "Filtre" } },
      { id: "t1", widget: "text", x: 0, y: 1, w: 4, h: 2, props: { text: "Msg: {{var:message}}" } },
    ] },
  };
  // No "gate" variable exists on this config, so vars.gate is undefined → the
  // condition evaluates falsy (evaluateExpression warns + returns undefined).
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "hi");
  expect(screen.getByText("Msg: initial")).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx -t "condition"`
Expected: FAIL — `ActionBus` n'est jamais alimenté en `vars`/`user` (son contexte interne reste `{ vars: {}, user: { name: "" } }` par défaut), donc `record.nom == 'Nord'` et `vars.gate == 'open'` s'évaluent toujours à faux : le premier test échoue (la variable ne se met jamais à jour), le second aussi ; le troisième (condition censée rester fausse) passe déjà par accident.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/AppRenderer.tsx`, modifier les imports (actuellement lignes 1-11) :

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import type { AppConfig, RenderMode, Variable } from "../api/types";
import { GridCanvas } from "./GridCanvas";
import { WidgetHost } from "./WidgetHost";
import { moveItemAt, breakpointForWidth, type Breakpoint } from "./grid";
import { getPages, getPageLayout, setPageLayout } from "./pages";
import { DataProvider } from "./DataContext";
import { ActionBus } from "./ActionBus";
import { ActionBusProvider, useBusAction } from "./ActionBusContext";
import { VariablesProvider, useSetVariable, useVariables } from "./VariablesContext";
import { useAuth } from "../auth/useAuth";
import { themeToCssVars } from "./theme";
```

Juste après `VariableBusBridge` (actuellement lignes 26-32), ajouter :

```tsx
// Keeps ActionBus.context fresh with the live app variables and the
// authenticated user, so an ActionMessage.when condition (SP-5b) can
// reference vars.x/user.name — mirrors VariableBusBridge's live-value wiring.
function ActionConditionBridge({ bus }: { bus: ActionBus }) {
  const variables = useVariables();
  const { username } = useAuth();
  useEffect(() => {
    bus.setContext({ vars: variables, user: { name: username ?? "" } });
  }, [bus, variables, username]);
  return null;
}
```

Dans le JSX du composant `AppRenderer` (actuellement lignes 98-101), monter le pont à l'intérieur de `<VariablesProvider>`, avant les `VariableBusBridge` :

```tsx
        <VariablesProvider variables={config.variables ?? []}>
          <ActionConditionBridge bus={bus} />
          {(config.variables ?? []).map((v) => (
            <VariableBusBridge key={v.id} variable={v} bus={bus} />
          ))}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: PASS (tous, y compris les 3 nouveaux)

Run: `cd shell && npm run test && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/AppRenderer.tsx src/builder/AppRenderer.test.tsx
git commit -m "feat(shell): AppRenderer — alimente ActionBus avec les variables et l'utilisateur courants pour les conditions d'action (SP-5b)"
```

---

## Task 4: Builder UI — condition par action + validation à l'édition

**Files:**
- Modify: `shell/src/builder/ActionsPanel.tsx`
- Modify: `shell/src/builder/ActionsPanel.test.tsx` (ajout de tests, en fin de fichier)
- Modify: `shell/src/builder/configExpressionErrors.ts`
- Modify: `shell/src/builder/configExpressionErrors.test.ts`

**Interfaces:**
- Produces: `ActionsPanel` affiche et édite `ActionMessage.when` par message existant (aucun changement de signature de props) ; `getConfigExpressionErrors` valide aussi chaque `config.messages[].when` (en plus de `visibleWhen`/colonnes calculées de SP-5a).
- Consumes: `validateExpression` (`shell/src/builder/expr.ts`, existant), `ActionMessage.when` (Task 2).

- [ ] **Step 1: Écrire les tests qui échouent (`getConfigExpressionErrors`)**

Dans `shell/src/builder/configExpressionErrors.test.ts`, remplacer la signature du helper `config` (actuellement ligne 5) :

```ts
function config(items: AppConfig["layout"]["items"], messages: AppConfig["messages"] = []): AppConfig {
  return { kind: "app", theme: {}, dataSources: [], messages, layout: { type: "grid", breakpoints: {}, items } };
}
```

(Tous les appels existants ne passent que `items` — `messages` retombe sur `[]` par défaut, aucun test préexistant n'est affecté.)

Ajouter en fin de fichier :

```ts
test("returns no errors when a message's condition is valid", () => {
  const messages: AppConfig["messages"] = [{ id: "m1", from: "w1", event: "clicked", to: "w2", action: "noop", when: "vars.x == 'a'" }];
  expect(getConfigExpressionErrors(config([], messages))).toEqual([]);
});

test("ignores a message without a condition", () => {
  const messages: AppConfig["messages"] = [{ id: "m1", from: "w1", event: "clicked", to: "w2", action: "noop" }];
  expect(getConfigExpressionErrors(config([], messages))).toEqual([]);
});

test("reports an invalid message condition with the message id", () => {
  const messages: AppConfig["messages"] = [{ id: "m1", from: "w1", event: "clicked", to: "w2", action: "noop", when: "vars.x ==" }];
  const errors = getConfigExpressionErrors(config([], messages));
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain("m1");
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/configExpressionErrors.test.ts -t "condition"`
Expected: FAIL — `getConfigExpressionErrors` ne scanne pas encore `config.messages`, donc le test "reports an invalid message condition" échoue (0 erreur au lieu de 1).

- [ ] **Step 3: Implémenter `getConfigExpressionErrors`**

Dans `shell/src/builder/configExpressionErrors.ts`, ajouter juste avant le `return errors;` final (actuellement ligne 27) :

```ts
  for (const m of config.messages) {
    if (!m.when) continue;
    const err = validateExpression(m.when);
    if (err) errors.push(`Action ${m.id} (condition) : ${err}`);
  }
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/configExpressionErrors.test.ts`
Expected: PASS (8/8 — les 5 préexistants + les 3 nouveaux)

- [ ] **Step 5: Écrire les tests qui échouent (`ActionsPanel`)**

Dans `shell/src/builder/ActionsPanel.test.tsx`, ajouter en fin de fichier :

```tsx
test("edits a message's condition", async () => {
  const onChange = vi.fn();
  const messages: ActionMessage[] = [{ id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter" }];
  render(<ActionsPanel items={items} messages={messages} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Condition de l'action m1"), "vars.x ==");
  expect(onChange).toHaveBeenCalled();
  const next = onChange.mock.calls.at(-1)![0] as ActionMessage[];
  expect(next[0].id).toBe("m1");
  expect(typeof next[0].when).toBe("string");
});

test("shows a validation error for an invalid message condition", () => {
  const messages: ActionMessage[] = [{ id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter", when: "vars.x ==" }];
  render(<ActionsPanel items={items} messages={messages} onChange={vi.fn()} />);
  expect(screen.getByRole("alert")).toBeInTheDocument();
});

test("shows no validation error for a valid message condition", () => {
  const messages: ActionMessage[] = [{ id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter", when: "vars.x == 'a'" }];
  render(<ActionsPanel items={items} messages={messages} onChange={vi.fn()} />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
```

- [ ] **Step 6: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/ActionsPanel.test.tsx -t "condition"`
Expected: FAIL — `ActionsPanel` ne rend encore aucun champ de condition par message, donc `getByLabelText("Condition de l'action m1")` échoue à trouver l'élément.

- [ ] **Step 7: Implémenter — `ActionsPanel.tsx`**

Remplacer tout le contenu de `shell/src/builder/ActionsPanel.tsx` :

```tsx
import { useState } from "react";
import type { ActionMessage, Variable, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { validateExpression } from "./expr";

function widgetLabel(items: WidgetItem[], variables: Variable[], id: string): string {
  if (id.startsWith("var:")) {
    const v = variables.find((v) => `var:${v.id}` === id);
    return v ? `Variable : ${v.name}` : id;
  }
  const it = items.find((i) => i.id === id);
  return (it && getWidget(it.widget)?.label) || id;
}
function eventsOf(items: WidgetItem[], id: string): readonly string[] {
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.events ?? [];
}
function actionsOf(items: WidgetItem[], id: string): readonly string[] {
  if (id.startsWith("var:")) return ["set"];
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.actions ?? [];
}
function resolvesOnThisPage(items: WidgetItem[], variables: Variable[], id: string): boolean {
  if (id.startsWith("var:")) return variables.some((v) => `var:${v.id}` === id);
  return items.some((i) => i.id === id);
}

const selectCls = "h-8 rounded border border-slate-300 bg-white text-xs";

export function ActionsPanel({
  items,
  variables = [],
  messages,
  onChange,
}: {
  items: WidgetItem[];
  variables?: Variable[];
  messages: ActionMessage[];
  onChange: (messages: ActionMessage[]) => void;
}) {
  const emitters = items.filter((i) => (getWidget(i.widget)?.events?.length ?? 0) > 0);
  const widgetReceivers = items.filter((i) => (getWidget(i.widget)?.actions?.length ?? 0) > 0);
  const variableReceivers = variables.map((v) => ({ id: `var:${v.id}`, label: `Variable : ${v.name}` }));
  const [from, setFrom] = useState("");
  const [event, setEvent] = useState("");
  const [to, setTo] = useState("");
  const [action, setAction] = useState("");

  const visibleMessages = messages.filter(
    (m) => resolvesOnThisPage(items, variables, m.from) && resolvesOnThisPage(items, variables, m.to),
  );

  function add() {
    if (!from || !event || !to || !action) return;
    onChange([...messages, { id: crypto.randomUUID(), from, event, to, action }]);
    setFrom(""); setEvent(""); setTo(""); setAction("");
  }
  function remove(id: string) {
    onChange(messages.filter((m) => m.id !== id));
  }
  function updateWhen(id: string, when: string) {
    onChange(messages.map((m) => (m.id === id ? { ...m, when: when || undefined } : m)));
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <ul className="flex flex-col gap-1">
        {visibleMessages.map((m) => {
          const when = m.when ?? "";
          const error = when ? validateExpression(when) : null;
          return (
            <li key={m.id} className="flex flex-col gap-1 rounded border border-slate-200 p-1 text-xs">
              <div className="flex items-center justify-between">
                <span>{widgetLabel(items, variables, m.from)}.{m.event} → {widgetLabel(items, variables, m.to)}.{m.action}</span>
                <button type="button" aria-label={`Retirer l'action ${m.id}`} className="text-red-600" onClick={() => remove(m.id)}>✕</button>
              </div>
              <input
                aria-label={`Condition de l'action ${m.id}`}
                placeholder="Condition (optionnel)"
                className="h-7 rounded border border-slate-300 px-1 font-mono"
                value={when}
                onChange={(e) => updateWhen(m.id, e.target.value)}
              />
              {error && <span role="alert" className="text-red-600">{error}</span>}
            </li>
          );
        })}
        {visibleMessages.length === 0 && <li className="text-xs text-slate-400">Aucune action.</li>}
      </ul>
      <select aria-label="Widget émetteur" className={selectCls} value={from}
        onChange={(e) => { setFrom(e.target.value); setEvent(""); }}>
        <option value="">Widget émetteur…</option>
        {emitters.map((i) => <option key={i.id} value={i.id}>{widgetLabel(items, variables, i.id)}</option>)}
      </select>
      <select aria-label="Événement" className={selectCls} value={event} disabled={!from}
        onChange={(e) => setEvent(e.target.value)}>
        <option value="">Événement…</option>
        {eventsOf(items, from).map((ev) => <option key={ev} value={ev}>{ev}</option>)}
      </select>
      <select aria-label="Widget cible" className={selectCls} value={to}
        onChange={(e) => { setTo(e.target.value); setAction(""); }}>
        <option value="">Widget cible…</option>
        {widgetReceivers.map((i) => <option key={i.id} value={i.id}>{widgetLabel(items, variables, i.id)}</option>)}
        {variableReceivers.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
      </select>
      <select aria-label="Action" className={selectCls} value={action} disabled={!to}
        onChange={(e) => setAction(e.target.value)}>
        <option value="">Action…</option>
        {actionsOf(items, to).map((a) => <option key={a} value={a}>{a}</option>)}
      </select>
      <button type="button" className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100" onClick={add}>
        Ajouter une action
      </button>
    </div>
  );
}
```

- [ ] **Step 8: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/ActionsPanel.test.tsx`
Expected: PASS (7/7 — les 4 préexistants + les 3 nouveaux)

Run: `cd shell && npm run test && npm run build`
Expected: PASS (l'extension de `getConfigExpressionErrors` est déjà couverte par `AppBuilderPage.test.tsx` existant via le même mécanisme `expressionErrors.length > 0` — aucun changement requis dans `AppBuilderPage.tsx`, `ActionsPanel` reçoit déjà `messages`/`onChange` directement de ce composant)

- [ ] **Step 9: Commit**

```bash
cd shell
git add src/builder/ActionsPanel.tsx src/builder/ActionsPanel.test.tsx \
  src/builder/configExpressionErrors.ts src/builder/configExpressionErrors.test.ts
git commit -m "feat(shell): builder — condition éditable par action, validée comme les autres expressions du layout (SP-5b)"
```

---

## Task 5: E2E — spec « conditions d'action »

**Files:**
- Create: `shell/e2e/action-conditions.spec.ts`

**Interfaces:**
- Consumes: tout SP-5b (Tasks 1-4). Aucun nouveau mock nécessaire (le scénario n'a besoin d'aucune source de données — Filtre et Texte fonctionnent sans binding).

- [ ] **Step 1: Écrire la spec**

Créer `shell/e2e/action-conditions.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("une condition sur une action ne déclenche celle-ci que si l'expression s'évalue à vrai, sans code", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App conditions");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Filtre sur le champ "region".
  await page.getByRole("button", { name: "Filtre" }).click();
  await page.getByLabel("Champ à filtrer").fill("region");

  // Texte affichant la variable "status".
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Sélection : {{var:status}}");

  // Variable "status".
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("status");

  // Filtre.changed -> Variable(status).set, condition record.region == "Nord".
  await page.getByLabel("Widget émetteur").selectOption({ label: "Filtre" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : status" });
  await page.getByLabel("Action").selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();
  await page.getByLabel(/Condition de l'action/).fill('record.region == "Nord"');

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : rien saisi encore — la variable est vide.
  await page.goto("/apps/9");
  await expect(page.getByText("Sélection :")).toBeVisible();

  // Taper "Nord" : la condition est vraie, l'action se déclenche.
  await page.getByLabel("Valeur du filtre").fill("Nord");
  await expect(page.getByText("Sélection : Nord")).toBeVisible();

  // Taper "Sud" : la condition est fausse, l'action ne se déclenche pas —
  // la variable garde sa valeur précédente ("Nord").
  await page.getByLabel("Valeur du filtre").fill("Sud");
  await expect(page.getByText("Sélection : Nord")).toBeVisible();
});
```

- [ ] **Step 2: Lancer la spec**

Run: `cd shell && npx playwright test action-conditions.spec.ts`
Expected: PASS — les Tasks 1-4 implémentent déjà tout ce que cette spec exerce ; ce n'est pas un cycle RED/GREEN (contrairement aux tâches précédentes), c'est la confirmation d'intégration bout-en-bout à travers un vrai navigateur (sélecteurs ARIA réels, timing réel). Si elle échoue, investiguer lequel des maillons (Tasks 1-4) ne s'intègre pas comme supposé — ne pas modifier la spec pour la faire passer sans comprendre pourquoi.

- [ ] **Step 3: Lancer la suite E2E complète**

Run: `cd shell && npm run e2e`
Expected: PASS — 16 specs vertes (15 existantes + `action-conditions.spec.ts`).

- [ ] **Step 4: Commit**

```bash
cd shell
git add e2e/action-conditions.spec.ts
git commit -m "test(shell): e2e — une condition CEL sur une action ne la déclenche que si elle s'évalue à vrai (SP-5b)"
```

---

## Couverture spec → tâches (auto-vérification)

- §1 SP-5b « `ActionMessage` gagne une condition CEL optionnelle, ne déclenche l'action que si vraie, dans le contexte du payload de l'émetteur » → Task 2 (`ActionBus.emit`), Task 5 (E2E).
- §1 SP-5b « Réutilise le moteur de SP-5a sans le modifier » → confirmé : `expr.ts` n'est touché par aucune tâche de ce plan (Global Constraints).
- Persistance de `when` (et du `visibleWhen` de SP-5a, découvert non persisté) → Task 1.
- `vars`/`user` disponibles à une condition (pas seulement le payload) → Task 3.
- Builder UI (édition de la condition, validation, cohérence avec le bouton Enregistrer de SP-5a qui lit déjà `getConfigExpressionErrors`) → Task 4.
- Aucune régression sur les messages sans condition (comportement SP-4/SP-5a inchangé) → Task 2 (test dédié), Task 5 (les 15 specs E2E existantes, dont `actions.spec.ts`, restent vertes).
