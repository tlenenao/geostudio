# SP-5a — Spike + moteur d'expressions + visibleWhen + colonnes calculées : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer la première sous-phase de SP-5 : un spike de validation de `cel-js` (gate d'ouverture, A8), un moteur d'évaluation d'expressions CEL côté shell (`evaluateExpression`/`validateExpression`), `visibleWhen` sur tout widget, une colonne calculée sur le widget Table, et la validation à l'édition (bouton Enregistrer désactivé si une expression du layout est invalide) — cf. [SP-5 — Expressions & actions composées](../specs/2026-07-11-sp5-expressions-actions-composees-design.md) §1-8 (détail SP-5a).

**Architecture:** Un module `shell/src/builder/expr.ts` enveloppe `cel-js` avec deux fonctions (`evaluateExpression`, jamais throw ; `validateExpression`, parse seul). Deux points d'accroche l'appellent : `WidgetHost` pour `visibleWhen` (nouveau champ sur `WidgetItem`) et le widget Table pour une colonne calculée (nouvelle forme `{ label, expr }` en plus des colonnes `string` existantes). Aucune couche réactive/cache — le cycle de rendu React fournit la réactivité. Le vocabulaire (`vars`/`record`/`user`) circule via un `ExprContext` construit à chaque point d'appel ; `user` vient de `useAuth()`, câblé une seule fois dans `WidgetHost` puis propagé dans `WidgetContext`.

**Tech Stack:** React 19 + TypeScript + Vitest (Tasks 2-5), Playwright (Task 6, `VITE_AUTH_MODE=mock`). `cel-js@^0.8.2` (npm, `ChromeGG/cel-js`, MIT).

## Global Constraints

- **cel-js API réelle (vérifiée empiriquement avant l'écriture de ce plan, pas supposée)** : `evaluate(expression: string, context?: Record<string, unknown>): unknown` — **lève une exception JS** (`Error` ou `CelTypeError`) sur tout problème à l'évaluation (identifiant absent à n'importe quelle profondeur, incompatibilité de type). `parse(expression: string): { isSuccess: true; cst } | { isSuccess: false; errors: string[] }` — parse seul, ne lève jamais.
- **`evaluateExpression` ne lève jamais** — retourne `undefined` sur toute erreur (capturée en interne), avec un `console.warn` (pas de swallow silencieux, pas de UI dédiée). `undefined`/falsy pour `visibleWhen` cache le widget ; `undefined` pour une colonne calculée affiche une cellule vide (`""`).
- **`visibleWhen` est ignoré en mode `"edit"`** — un widget reste toujours visible dans le canvas du builder, quelle que soit son expression, pour rester sélectionnable/configurable (cohérent avec `GridCanvas.tsx` qui rend déjà tout widget en édition, seulement non-cliquable via `pointer-events-none`, jamais absent du DOM). Seuls les modes `"preview"` et `"runtime"` respectent `visibleWhen`. **Ceci affine la spec** (qui ne distinguait pas les modes) suite à une inspection de `GridCanvas.tsx` pendant l'écriture de ce plan — sans cette exception, tout widget masqué deviendrait impossible à re-sélectionner dans le builder une fois sa condition fausse.
- **`useAuth()` dans `WidgetHost` casse 4 fichiers de test existants** qui rendent `WidgetHost`/`AppRenderer` transitivement sans mock d'auth (`WidgetHost.test.tsx`, `AppRenderer.test.tsx`, `AppBuilderPage.test.tsx`, `AppRuntimePage.test.tsx` — vérifié par grep avant l'écriture de ce plan, liste exhaustive). La Task 3 ajoute le mock `vi.mock("../auth/useAuth", ...)` (motif déjà utilisé par `AppLayout.test.tsx`/`routes.test.tsx`) à ces 4 fichiers — mécanique, pas une nouvelle couverture de test.
- Aucune couche de cache/réactivité centralisée — un évaluateur fin appelé au point d'usage (décidé en brainstorm).
- Aucun changement côté cœur (Python) — SP-5a est un chantier front pur.
- Aucune régression : `cd shell && npm run test` (332+ tests) et `npm run build` verts après chaque tâche 2-5 ; `cd shell && npm run e2e` vert après la Task 6 (14 specs existantes + la nouvelle = 15).
- Docs et messages utilisateur en français ; code/identifiants en anglais. TDD systématique ; commits conventional en français.

---

## Task 1: Spike `cel-js` (gate d'ouverture)

**Files:**
- Modify: `shell/package.json` (ajoute la dépendance `cel-js`)
- Create: `shell/scripts/spike-cel-js.mjs`

**Interfaces:**
- Produces: un verdict PASS/FAIL documenté par l'exécution du script. **Si FAIL : STOP — escalade humaine** (repli JSONLogic prévu par la spec, syntaxe CEL gardée comme cible — c'est la décision de Tanguy, pas celle de l'exécutant). Les tâches 2+ supposent PASS.

- [ ] **Step 1: Ajouter la dépendance**

Dans `shell/package.json`, dans `"dependencies"`, ajouter (ordre alphabétique, entre `"@tanstack/react-query"` et `"class-variance-authority"`) :

```json
    "cel-js": "^0.8.2",
```

Run: `cd shell && npm install`
Expected: `cel-js@0.8.2` apparaît dans `package-lock.json`, aucune erreur.

- [ ] **Step 2: Écrire le script de spike**

```js
// shell/scripts/spike-cel-js.mjs
// Spike SP-5a (A8) : valide que cel-js couvre le vocabulaire nécessaire à
// SP-5a (vars.x, record.champ, user.name, opérateurs arithmétiques/logiques,
// ternaire) et que les erreurs d'évaluation/parse sont bien catchables en JS
// pur, sans faire planter le process.
//
// Usage : node scripts/spike-cel-js.mjs
// Sort avec le code 0 (PASS) ou 1 (FAIL, échecs listés).
import { evaluate, parse } from "cel-js";

const failures = [];
function check(name, cond) {
  console.log(`  [${cond ? "PASS" : "FAIL"}] ${name}`);
  if (!cond) failures.push(name);
}

check("arithmétique de base", evaluate("1 + 2 * 3") === 7);
check("concaténation de chaînes", evaluate("'a' + 'b'") === "ab");
check("opérateur ternaire", evaluate("1 == 1 ? 'oui' : 'non'") === "oui");

const ctx = { vars: { seuil: "haute" }, record: { gravite: "haute" }, user: { name: "tanguy" } };
check(
  "vocabulaire vars.x / record.champ / user.name",
  evaluate('vars.seuil == "haute" && record.gravite == vars.seuil && user.name != ""', ctx) === true,
);

let evalThrew = false;
try {
  evaluate("record.missingField", ctx);
} catch (err) {
  evalThrew = err instanceof Error;
}
check("une évaluation invalide lève une Error JS catchable (pas de crash process)", evalThrew);

const parseOk = parse("1 + 2");
check("parse() réussit sur une expression valide", parseOk.isSuccess === true);

const parseBad = parse("vars.x ==");
check(
  "parse() échoue proprement sur une expression invalide, avec un message",
  parseBad.isSuccess === false && Array.isArray(parseBad.errors) && parseBad.errors.length > 0,
);

const verdict = failures.length === 0 ? "PASS" : `FAIL (${failures.join(", ")})`;
console.log(`\nRésultat spike : ${verdict}`);
process.exit(failures.length === 0 ? 0 : 1);
```

- [ ] **Step 3: Exécuter et documenter le verdict**

Run: `cd shell && node scripts/spike-cel-js.mjs`
Expected: chaque check `[PASS]`, sortie finale `Résultat spike : PASS`, code retour 0.

**Si un check échoue : STOP.** Rapporter la sortie exacte — ne pas continuer le plan, ne pas improviser de repli JSONLogic sans validation humaine.

- [ ] **Step 4: Commit**

```bash
cd shell
git add package.json package-lock.json scripts/spike-cel-js.mjs
git commit -m "chore(shell): spike cel-js — vocabulaire vars/record/user validé (SP-5a)"
```

---

## Task 2: `shell/src/builder/expr.ts` — moteur d'évaluation

**Files:**
- Create: `shell/src/builder/expr.ts`
- Test: `shell/src/builder/expr.test.ts`

**Interfaces:**
- Produces: `ExprContext = { vars: Record<string, string>; record?: Record<string, unknown>; user: { name: string } }`, `evaluateExpression(expr: string, ctx: ExprContext): unknown` (jamais throw), `validateExpression(expr: string): string | null` (parse seul).
- Consumes: `cel-js` (`evaluate`, `parse`, Task 1).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `shell/src/builder/expr.test.ts` :

```ts
import { afterEach, expect, test, vi } from "vitest";
import { evaluateExpression, validateExpression } from "./expr";

afterEach(() => vi.restoreAllMocks());

const ctx = { vars: { seuil: "haute" }, record: { gravite: "haute", titre: "Fuite" }, user: { name: "tanguy" } };

test("evaluates arithmetic, string concatenation and the ternary operator", () => {
  expect(evaluateExpression("1 + 2 * 3", ctx)).toBe(7);
  expect(evaluateExpression("'a' + 'b'", ctx)).toBe("ab");
  expect(evaluateExpression("1 == 1 ? 'oui' : 'non'", ctx)).toBe("oui");
});

test("resolves vars.x, record.champ and user.name", () => {
  expect(evaluateExpression("vars.seuil", ctx)).toBe("haute");
  expect(evaluateExpression("record.gravite == vars.seuil", ctx)).toBe(true);
  expect(evaluateExpression("user.name", ctx)).toBe("tanguy");
});

test("returns undefined (not throw) when the expression references a missing field", () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(evaluateExpression("record.missingField", ctx)).toBeUndefined();
  expect(console.warn).toHaveBeenCalled();
});

test("returns undefined (not throw) on a type mismatch", () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(evaluateExpression("record.titre > 5", ctx)).toBeUndefined();
});

test("validateExpression returns null for a syntactically valid expression", () => {
  expect(validateExpression("vars.seuil == 'haute'")).toBeNull();
});

test("validateExpression returns an error message for an invalid expression", () => {
  const err = validateExpression("vars.seuil ==");
  expect(err).not.toBeNull();
  expect(typeof err).toBe("string");
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/expr.test.ts`
Expected: FAIL — `Cannot find module './expr'` (le fichier n'existe pas encore).

- [ ] **Step 3: Implémenter**

Créer `shell/src/builder/expr.ts` :

```ts
import { evaluate, parse } from "cel-js";

export type ExprContext = {
  vars: Record<string, string>;
  record?: Record<string, unknown>;
  user: { name: string };
};

export function evaluateExpression(expr: string, ctx: ExprContext): unknown {
  try {
    return evaluate(expr, ctx);
  } catch (err) {
    console.warn(`evaluateExpression: "${expr}" a échoué`, err);
    return undefined;
  }
}

export function validateExpression(expr: string): string | null {
  const result = parse(expr);
  if (result.isSuccess) return null;
  return result.errors.join("; ");
}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/expr.test.ts`
Expected: PASS (7/7)

Run: `cd shell && npm run test && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/expr.ts src/builder/expr.test.ts
git commit -m "feat(shell): moteur d'évaluation d'expressions CEL — evaluateExpression/validateExpression (SP-5a)"
```

---

## Task 3: `visibleWhen` sur `WidgetItem` + `WidgetContext.user` + intégration `WidgetHost`

**Files:**
- Modify: `shell/src/api/types.ts` (`WidgetItem.visibleWhen`)
- Modify: `shell/src/builder/registry.ts` (`WidgetContext.user`)
- Modify: `shell/src/builder/WidgetHost.tsx`
- Modify: `shell/src/builder/WidgetHost.test.tsx` (ajout du mock `useAuth` + nouveaux tests)
- Modify: `shell/src/builder/AppRenderer.test.tsx` (ajout du mock `useAuth`, mécanique)
- Modify: `shell/src/pages/AppBuilderPage.test.tsx` (ajout du mock `useAuth`, mécanique)
- Modify: `shell/src/pages/AppRuntimePage.test.tsx` (ajout du mock `useAuth`, mécanique)

**Interfaces:**
- Produces: `WidgetItem.visibleWhen?: string` ; `WidgetContext.user?: { name: string }`, peuplé par `WidgetHost` depuis `useAuth()` et transmis à tout `Component` de widget (consommé par la Task 4).
- Consumes: `evaluateExpression`, `ExprContext` (Task 2).

- [ ] **Step 1: Ajouter le mock `useAuth` aux 4 fichiers de test affectés**

Ce mock est nécessaire **avant** d'écrire les nouveaux tests, sans quoi les tests existants de ces 4 fichiers plantent dès que `WidgetHost` appelle `useAuth()` (Step 4). Motif déjà utilisé par `shell/src/shell/AppLayout.test.tsx`/`shell/src/shell/routes.test.tsx`.

Dans `shell/src/builder/WidgetHost.test.tsx`, ajouter en tête de fichier (après les imports existants) :

```ts
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false, isAuthenticated: true, username: "tanguy",
  error: null, getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));
```

Répéter exactement le même bloc (mêmes imports, même constante `authState`, même `vi.mock`) en tête de :
- `shell/src/builder/AppRenderer.test.tsx`
- `shell/src/pages/AppBuilderPage.test.tsx`
- `shell/src/pages/AppRuntimePage.test.tsx`

(Chacun de ces 4 fichiers importe déjà `vi` depuis `vitest` — vérifier que l'import existe, l'ajouter à l'import `vitest` existant sinon.)

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx src/builder/AppRenderer.test.tsx src/pages/AppBuilderPage.test.tsx src/pages/AppRuntimePage.test.tsx`
Expected: PASS — ces 4 fichiers passent encore à l'identique (le mock est ajouté par anticipation, `WidgetHost` n'appelle pas encore `useAuth()`).

- [ ] **Step 2: Écrire les tests qui échouent (WidgetHost)**

Dans `shell/src/builder/WidgetHost.test.tsx`, ajouter en fin de fichier :

```tsx
test("hides a widget in runtime mode when visibleWhen evaluates to false", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => <div>visible-content</div> });
  render(<WidgetHost item={{ ...item("ok"), visibleWhen: "1 == 2" }} mode="runtime" />);
  expect(screen.queryByText("visible-content")).not.toBeInTheDocument();
});

test("shows a widget in runtime mode when visibleWhen evaluates to true", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => <div>visible-content</div> });
  render(<WidgetHost item={{ ...item("ok"), visibleWhen: "1 == 1" }} mode="runtime" />);
  expect(screen.getByText("visible-content")).toBeInTheDocument();
});

test("always shows a widget in edit mode regardless of visibleWhen", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => <div>visible-content</div> });
  render(<WidgetHost item={{ ...item("ok"), visibleWhen: "1 == 2" }} mode="edit" />);
  expect(screen.getByText("visible-content")).toBeInTheDocument();
});

test("shows a widget when visibleWhen is absent", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => <div>visible-content</div> });
  render(<WidgetHost item={item("ok")} mode="runtime" />);
  expect(screen.getByText("visible-content")).toBeInTheDocument();
});
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx -t visibleWhen`
Expected: FAIL — Vitest transpile via esbuild (pas de vérification de type à l'exécution), donc l'échec vient des assertions, pas d'une erreur TypeScript : `WidgetHost` ignore encore `item.visibleWhen`, donc le widget s'affiche toujours (le test "hides… when visibleWhen evaluates to false" échoue, `queryByText` trouve le contenu qui ne devrait pas être là).

- [ ] **Step 4: Implémenter**

Dans `shell/src/api/types.ts`, sur `WidgetItem` (actuellement lignes 123-132), ajouter le champ :

```ts
export type WidgetItem = {
  id: string;
  widget: string;
  x: number;
  y: number;
  w: number;
  h: number;
  props: Record<string, unknown>;
  layouts?: Partial<Record<"sm" | "md" | "lg", { x: number; y: number; w: number; h: number }>>;
  visibleWhen?: string;
};
```

Dans `shell/src/builder/registry.ts`, sur `WidgetContext` (actuellement lignes 5-13), ajouter le champ :

```ts
export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
  pages?: Page[];
  variables?: Record<string, string>;
  data?: DataSourceState;
  bus?: ActionBus;
  widgetId?: string;
  user?: { name: string };
};
```

Dans `shell/src/builder/WidgetHost.tsx`, remplacer tout le fichier par :

```tsx
import { Component, type ReactNode } from "react";
import type { Page, RenderMode, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { useDataStates } from "./DataContext";
import { useActionBus } from "./ActionBusContext";
import { useVariables } from "./VariablesContext";
import { useAuth } from "../auth/useAuth";
import { evaluateExpression } from "./expr";

class WidgetErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(err: unknown) {
    console.error("WidgetHost: widget crashed", err);
  }
  render() {
    if (this.state.failed) {
      return <div className="flex h-full items-center justify-center bg-red-50 text-xs text-red-600">Erreur du widget</div>;
    }
    return this.props.children;
  }
}

export function WidgetHost({
  item,
  mode,
  pages = [],
  navigate,
}: {
  item: WidgetItem;
  mode: RenderMode;
  pages?: Page[];
  navigate?: (pageId: string) => void;
}) {
  const states = useDataStates();
  const bus = useActionBus();
  const variables = useVariables();
  const { username } = useAuth();
  const user = { name: username ?? "" };
  const dsId = item.props.dataSourceId as string | undefined;
  const data = dsId ? states[dsId] : undefined;
  const def = getWidget(item.widget);
  if (!def) {
    return <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">Widget inconnu : {item.widget}</div>;
  }
  const visible = mode === "edit" || !item.visibleWhen
    || Boolean(evaluateExpression(item.visibleWhen, { vars: variables, record: data?.records[0]?.properties, user }));
  if (!visible) return null;
  const Widget = def.Component;
  return (
    <WidgetErrorBoundary>
      <Widget props={item.props} ctx={{ mode, data, bus: bus ?? undefined, widgetId: item.id, pages, navigate, variables, user }} />
    </WidgetErrorBoundary>
  );
}
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx src/builder/AppRenderer.test.tsx`
Expected: PASS (tous les tests, y compris les 4 nouveaux)

Run: `cd shell && npm run test`
Expected: PASS (inclut `AppBuilderPage.test.tsx`/`AppRuntimePage.test.tsx` avec le mock ajouté au Step 1)

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd shell
git add src/api/types.ts src/builder/registry.ts src/builder/WidgetHost.tsx \
  src/builder/WidgetHost.test.tsx src/builder/AppRenderer.test.tsx \
  src/pages/AppBuilderPage.test.tsx src/pages/AppRuntimePage.test.tsx
git commit -m "feat(shell): visibleWhen sur WidgetItem — WidgetHost masque un widget en preview/runtime (SP-5a)"
```

---

## Task 4: Table — colonnes calculées

**Files:**
- Modify: `shell/src/builder/widgets/data.tsx`
- Modify: `shell/src/builder/widgets/data.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: `props.columns` du widget Table accepte `(string | { label: string; expr: string })[]` (auparavant `string[]` seul — rétrocompatible, chaque entrée `string` garde son comportement actuel).
- Consumes: `evaluateExpression` (Task 2), `WidgetContext.user`/`variables` (Task 3).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/data.test.tsx`, ajouter en fin de fichier :

```tsx
test("table renders a calculated column evaluated per row against record and vars", () => {
  const Table = getWidget("table")!.Component;
  const ctx = { mode: "runtime", variables: { seuil: "haute" }, data: state({ records: [
    { id: 1, properties: { nom: "A", gravite: "haute" } },
    { id: 2, properties: { nom: "B", gravite: "faible" } },
  ] }) } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: ["nom", { label: "Urgent", expr: "record.gravite == vars.seuil" }] }} ctx={ctx} />);
  expect(screen.getByRole("columnheader", { name: "Urgent" })).toBeInTheDocument();
  const cells = screen.getAllByRole("cell");
  expect(cells[1]).toHaveTextContent("true"); // ligne 1 : gravite == seuil
  expect(cells[3]).toHaveTextContent("false"); // ligne 2 : gravite != seuil
});

test("a calculated column header has no sort button", () => {
  const Table = getWidget("table")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [{ id: 1, properties: { nom: "A" } }] }) } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: [{ label: "Calc", expr: "1 + 1" }] }} ctx={ctx} />);
  expect(screen.queryByRole("button", { name: /Calc/ })).not.toBeInTheDocument();
  expect(screen.getByText("Calc")).toBeInTheDocument();
});

test("table PropsPanel adds a calculated column without disturbing existing plain columns", async () => {
  const Table = getWidget("table")!;
  const onChange = vi.fn();
  render(<Table.PropsPanel props={{ columns: ["nom"] }} onChange={onChange} dataSources={[]} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une colonne calculée" }));
  expect(onChange).toHaveBeenCalledWith({ columns: ["nom", { label: "Nouvelle colonne", expr: "" }] });
});

test("table PropsPanel edits a calculated column's label and expression", async () => {
  const Table = getWidget("table")!;
  const onChange = vi.fn();
  const props = { columns: ["nom", { label: "Nouvelle colonne", expr: "" }] };
  const { rerender } = render(<Table.PropsPanel props={props} onChange={onChange} dataSources={[]} />);
  await userEvent.type(screen.getByLabelText(/Libellé de la colonne calculée/), "!");
  const afterLabel = onChange.mock.calls.at(-1)![0];
  rerender(<Table.PropsPanel props={afterLabel} onChange={onChange} dataSources={[]} />);
  await userEvent.type(screen.getByLabelText(/Expression de la colonne calculée/), "1");
  const afterExpr = onChange.mock.calls.at(-1)![0];
  expect(afterExpr.columns[0]).toBe("nom"); // colonne texte inchangée
  expect(afterExpr.columns[1].expr).toBe("1");
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx -t "calculated"`
Expected: FAIL — `props.columns` n'accepte que des `string`, aucun contrôle « Ajouter une colonne calculée » n'existe.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/data.tsx`, ajouter l'import et le type en tête de fichier (après les imports existants) :

```ts
import { evaluateExpression } from "../expr";

type CalculatedColumn = { label: string; expr: string };
type TableColumn = string | CalculatedColumn;

function isCalculatedColumn(c: TableColumn): c is CalculatedColumn {
  return typeof c === "object" && c !== null;
}
```

Remplacer entièrement le `PropsPanel` du widget `table` (actuellement lignes 64-74) :

```tsx
    PropsPanel: ({ props, onChange, dataSources }) => {
      const columns = (props.columns as TableColumn[] | undefined) ?? [];
      const plainColumns = columns.filter((c): c is string => typeof c === "string");
      const calculatedColumns = columns.filter(isCalculatedColumn);

      function setPlainColumns(next: string[]) {
        onChange({ ...props, columns: [...next, ...calculatedColumns] });
      }
      function addCalculatedColumn() {
        onChange({ ...props, columns: [...plainColumns, ...calculatedColumns, { label: "Nouvelle colonne", expr: "" }] });
      }
      function updateCalculatedColumn(index: number, patch: Partial<CalculatedColumn>) {
        const next = calculatedColumns.map((c, i) => (i === index ? { ...c, ...patch } : c));
        onChange({ ...props, columns: [...plainColumns, ...next] });
      }
      function removeCalculatedColumn(index: number) {
        onChange({ ...props, columns: [...plainColumns, ...calculatedColumns.filter((_, i) => i !== index)] });
      }

      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect value={String(props.dataSourceId ?? "")} dataSources={dataSources}
            onChange={(id) => onChange({ ...props, dataSourceId: id })} />
          <label className="flex flex-col gap-1">Colonnes (séparées par des virgules)
            <input aria-label="Colonnes" className="h-9 rounded-md border border-slate-300 px-2"
              value={plainColumns.join(",")}
              onChange={(e) => setPlainColumns(e.target.value.split(",").map((c) => c.trim()).filter(Boolean))} />
          </label>
          {calculatedColumns.map((col, i) => (
            <div key={i} className="flex flex-col gap-1 rounded border border-slate-200 p-2">
              <label className="flex flex-col gap-1">Libellé
                <input aria-label={`Libellé de la colonne calculée ${i + 1}`} className="h-9 rounded-md border border-slate-300 px-2"
                  value={col.label} onChange={(e) => updateCalculatedColumn(i, { label: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1">Expression
                <input aria-label={`Expression de la colonne calculée ${i + 1}`} className="h-9 rounded-md border border-slate-300 px-2 font-mono"
                  value={col.expr} onChange={(e) => updateCalculatedColumn(i, { expr: e.target.value })} />
              </label>
              <button type="button" className="self-start text-xs text-red-600 underline" onClick={() => removeCalculatedColumn(i)}>
                Supprimer la colonne
              </button>
            </div>
          ))}
          <button type="button" className="self-start rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
            onClick={addCalculatedColumn}>
            Ajouter une colonne calculée
          </button>
        </div>
      );
    },
```

Dans le `Component` du widget `table`, remplacer la ligne de calcul des colonnes (actuellement lignes 88-90) :

```ts
      const rawColumns = (props.columns as TableColumn[] | undefined) ?? [];
      const columns: TableColumn[] = rawColumns.length ? rawColumns : Object.keys(data.records[0]?.properties ?? {});
```

Juste après (avant `const sorted = [...data.records];`), ajouter les trois fonctions de rendu par colonne :

```ts
      function columnKey(c: TableColumn): string {
        return isCalculatedColumn(c) ? c.label : c;
      }
      function columnLabel(c: TableColumn): string {
        return isCalculatedColumn(c) ? c.label : c;
      }
      function cellValue(c: TableColumn, r: (typeof data.records)[number]): string {
        if (!isCalculatedColumn(c)) return String(r.properties[c] ?? "");
        const value = evaluateExpression(c.expr, { vars: ctx.variables ?? {}, record: r.properties, user: ctx.user ?? { name: "" } });
        return value === undefined || value === null ? "" : String(value);
      }
```

Remplacer le bloc d'en-têtes (actuellement lignes 117-125) :

```tsx
              <tr>
                {columns.map((c) => {
                  const key = columnKey(c);
                  return (
                    <th key={key} className="border-b border-[var(--gs-color-border)] p-1">
                      {isCalculatedColumn(c) ? (
                        <span className="font-medium">{columnLabel(c)}</span>
                      ) : (
                        <button type="button" className="flex items-center gap-1 font-medium" onClick={() => toggleSort(key)}>
                          {columnLabel(c)}{sortCol === key ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                        </button>
                      )}
                    </th>
                  );
                })}
              </tr>
```

Remplacer la ligne de cellules (actuellement ligne 134) :

```tsx
                  {columns.map((c) => <td key={columnKey(c)} className="border-b border-[var(--gs-color-border)] p-1">{cellValue(c, r)}</td>)}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx`
Expected: PASS (tous les tests, y compris les préexistants — les colonnes `string` gardent leur comportement, `toggleSort`/tri inchangés pour elles)

Run: `cd shell && npm run test && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/data.tsx src/builder/widgets/data.test.tsx
git commit -m "feat(shell): widget Table — colonne calculée par expression CEL (SP-5a)"
```

---

## Task 5: Builder UI — condition d'affichage + validation à l'édition

**Files:**
- Create: `shell/src/builder/configExpressionErrors.ts`
- Test: `shell/src/builder/configExpressionErrors.test.ts`
- Modify: `shell/src/builder/PropsPanel.tsx`
- Modify: `shell/src/builder/PropsPanel.test.tsx` (ajout de tests, en fin de fichier)
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/AppBuilderPage.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: `getConfigExpressionErrors(config: AppConfig): string[]` (scanne `visibleWhen` et les colonnes calculées de toutes les pages) ; `PropsPanel` gagne la prop `onVisibleWhenChange: (expr: string) => void` ; `AppBuilderPage` désactive **Enregistrer** si des erreurs existent.
- Consumes: `validateExpression` (Task 2), `WidgetItem.visibleWhen` (Task 3), la forme des colonnes calculées de Table (Task 4), `getPages` (existant, `shell/src/builder/pages.ts`).

- [ ] **Step 1: Écrire les tests qui échouent (`getConfigExpressionErrors`)**

Créer `shell/src/builder/configExpressionErrors.test.ts` :

```ts
import { expect, test } from "vitest";
import { getConfigExpressionErrors } from "./configExpressionErrors";
import type { AppConfig } from "../api/types";

function config(items: AppConfig["layout"]["items"]): AppConfig {
  return { kind: "app", theme: {}, dataSources: [], messages: [], layout: { type: "grid", breakpoints: {}, items } };
}

test("returns no errors for a config with no expressions", () => {
  expect(getConfigExpressionErrors(config([{ id: "w1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {} }]))).toEqual([]);
});

test("returns no errors when visibleWhen and a calculated column are valid", () => {
  const items: AppConfig["layout"]["items"] = [
    { id: "w1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {}, visibleWhen: "vars.x == 'a'" },
    { id: "w2", widget: "table", x: 0, y: 2, w: 2, h: 2, props: { columns: ["nom", { label: "C", expr: "1 + 1" }] } },
  ];
  expect(getConfigExpressionErrors(config(items))).toEqual([]);
});

test("reports an invalid visibleWhen with the widget id", () => {
  const items: AppConfig["layout"]["items"] = [
    { id: "w1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {}, visibleWhen: "vars.x ==" },
  ];
  const errors = getConfigExpressionErrors(config(items));
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain("w1");
});

test("reports an invalid calculated column expression with the widget id and column label", () => {
  const items: AppConfig["layout"]["items"] = [
    { id: "w2", widget: "table", x: 0, y: 0, w: 2, h: 2, props: { columns: [{ label: "Mauvaise", expr: "1 +" }] } },
  ];
  const errors = getConfigExpressionErrors(config(items));
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain("w2");
  expect(errors[0]).toContain("Mauvaise");
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/configExpressionErrors.test.ts`
Expected: FAIL — `Cannot find module './configExpressionErrors'`.

- [ ] **Step 3: Implémenter `getConfigExpressionErrors`**

Créer `shell/src/builder/configExpressionErrors.ts` :

```ts
import type { AppConfig } from "../api/types";
import { getPages } from "./pages";
import { validateExpression } from "./expr";

type CalculatedColumn = { label: string; expr: string };

export function getConfigExpressionErrors(config: AppConfig): string[] {
  const errors: string[] = [];
  for (const page of getPages(config)) {
    for (const item of page.layout.items) {
      if (item.visibleWhen) {
        const err = validateExpression(item.visibleWhen);
        if (err) errors.push(`Widget ${item.id} (condition d'affichage) : ${err}`);
      }
      const columns = item.props.columns;
      if (Array.isArray(columns)) {
        for (const col of columns as unknown[]) {
          if (typeof col === "object" && col !== null && "expr" in col) {
            const { label, expr } = col as CalculatedColumn;
            const err = validateExpression(expr);
            if (err) errors.push(`Widget ${item.id}, colonne "${label}" : ${err}`);
          }
        }
      }
    }
  }
  return errors;
}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/configExpressionErrors.test.ts`
Expected: PASS (4/4)

- [ ] **Step 5: Écrire les tests qui échouent (PropsPanel)**

Dans `shell/src/builder/PropsPanel.test.tsx`, ajouter en fin de fichier :

```tsx
test("edits the selected widget's visibleWhen and shows a validation error", async () => {
  const onVisibleWhenChange = vi.fn();
  render(<PropsPanel item={item} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={onVisibleWhenChange} />);
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x ==");
  expect(onVisibleWhenChange).toHaveBeenCalled();
});

test("shows no validation error for a valid visibleWhen", () => {
  const itemWithValidExpr = { ...item, visibleWhen: "vars.x == 'a'" };
  render(<PropsPanel item={itemWithValidExpr} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("shows a validation error for an invalid visibleWhen", () => {
  const itemWithInvalidExpr = { ...item, visibleWhen: "vars.x ==" };
  render(<PropsPanel item={itemWithInvalidExpr} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />);
  expect(screen.getByRole("alert")).toBeInTheDocument();
});
```

- [ ] **Step 6: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/PropsPanel.test.tsx -t visibleWhen`
Expected: FAIL — `PropsPanel` ne rend encore aucun champ « Condition d'affichage » (React ignore silencieusement la prop `onVisibleWhenChange` non consommée), donc `getByLabelText("Condition d'affichage (visibleWhen)")` échoue à trouver l'élément.

- [ ] **Step 7: Implémenter — `PropsPanel.tsx`**

Remplacer tout le contenu de `shell/src/builder/PropsPanel.tsx` :

```tsx
import type { DataSource, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { validateExpression } from "./expr";

export function PropsPanel({
  item,
  dataSources,
  onChange,
  onVisibleWhenChange,
}: {
  item: WidgetItem | null;
  dataSources: DataSource[];
  onChange: (props: Record<string, unknown>) => void;
  onVisibleWhenChange: (expr: string) => void;
}) {
  if (!item) {
    return <p className="text-xs text-slate-400">Aucun widget sélectionné.</p>;
  }
  const def = getWidget(item.widget);
  if (!def) {
    return <p className="text-xs text-slate-400">Widget inconnu : {item.widget}</p>;
  }
  const Panel = def.PropsPanel;
  const visibleWhen = item.visibleWhen ?? "";
  const error = visibleWhen ? validateExpression(visibleWhen) : null;
  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        Condition d'affichage
        <textarea
          aria-label="Condition d'affichage (visibleWhen)"
          className="rounded-md border border-slate-300 p-2 font-mono text-xs"
          value={visibleWhen}
          onChange={(e) => onVisibleWhenChange(e.target.value)}
        />
        {error && <span role="alert" className="text-xs text-red-600">{error}</span>}
      </label>
      <Panel props={item.props} dataSources={dataSources} onChange={(p) => onChange(p)} />
    </div>
  );
}
```

- [ ] **Step 8: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/PropsPanel.test.tsx`
Expected: PASS (5/5 — les 2 tests préexistants + les 3 nouveaux)

- [ ] **Step 9: Écrire les tests qui échouent (AppBuilderPage — Enregistrer désactivé)**

Dans `shell/src/pages/AppBuilderPage.test.tsx`, ajouter en fin de fichier :

```tsx
test("disables Enregistrer and shows the error when a widget's visibleWhen is invalid", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  await userEvent.type(screen.getByLabelText("Condition d'affichage (visibleWhen)"), "vars.x ==");
  expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  expect(screen.getByRole("alert", { name: /condition d'affichage/i })).toBeInTheDocument();
  expect(saveAppConfig).not.toHaveBeenCalled();
});

test("re-enables Enregistrer once the invalid visibleWhen is corrected", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x ==");
  expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  await userEvent.type(area, " 'a'");
  expect(screen.getByRole("button", { name: "Enregistrer" })).not.toBeDisabled();
});
```

- [ ] **Step 10: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx -t "Enregistrer"`
Expected: FAIL — rien ne relie encore `visibleWhen` à `getConfigExpressionErrors`/au bouton, donc **Enregistrer** reste toujours activé et `saveAppConfig` est appelé.

- [ ] **Step 11: Implémenter — `AppBuilderPage.tsx`**

Ajouter l'import, juste après les imports existants :

```ts
import { getConfigExpressionErrors } from "../builder/configExpressionErrors";
```

Ajouter la fonction `updateSelectedVisibleWhen`, juste après `updateSelectedProps` (actuellement lignes 85-91) :

```ts
  function updateSelectedVisibleWhen(expr: string) {
    if (!draft || !selectedId || !activeLayout || !activePage) return;
    setDraft(setPageLayout(draft, activePage, {
      ...activeLayout,
      items: activeLayout.items.map((i) => (i.id === selectedId ? { ...i, visibleWhen: expr || undefined } : i)),
    }));
  }
```

Ajouter, juste avant le `return (` du composant (après la déclaration de `setVariables`) :

```ts
  const expressionErrors = draft ? getConfigExpressionErrors(draft) : [];
```

Remplacer le bouton **Enregistrer** (actuellement ligne 130) :

```tsx
        <Button size="sm" disabled={save.isPending || expressionErrors.length > 0} onClick={() => save.mutate(draft)}>
          Enregistrer
        </Button>
        {expressionErrors.length > 0 && (
          <span role="alert" aria-label="Erreur de condition d'affichage" className="text-sm text-red-600">
            {expressionErrors[0]}
          </span>
        )}
```

Remplacer l'appel à `PropsPanel` (actuellement ligne 166) :

```tsx
            <PropsPanel
              item={selected}
              dataSources={draft.dataSources}
              onChange={updateSelectedProps}
              onVisibleWhenChange={updateSelectedVisibleWhen}
            />
```

- [ ] **Step 12: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: PASS (12/12 — les 10 préexistants + les 2 nouveaux)

Run: `cd shell && npm run test && npm run build`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
cd shell
git add src/builder/configExpressionErrors.ts src/builder/configExpressionErrors.test.ts \
  src/builder/PropsPanel.tsx src/builder/PropsPanel.test.tsx \
  src/pages/AppBuilderPage.tsx src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): builder — condition d'affichage éditable, Enregistrer désactivé si une expression est invalide (SP-5a)"
```

---

## Task 6: E2E — spec « expressions »

**Files:**
- Create: `shell/e2e/expressions.spec.ts`

**Interfaces:**
- Consumes: tout SP-5a (Tasks 1-5). Réutilise la collection mock `villes` (`shell/e2e/mocks.ts`, déjà existante — `{ region: "Nord"|"Sud", annee, pop }`, 4 enregistrements), aucun nouveau mock nécessaire.

- [ ] **Step 1: Écrire la spec**

Créer `shell/e2e/expressions.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un Filtre pilote par expression la visibilité d'un widget et une colonne calculée, sans code", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App expressions");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Source de données : collection "villes" (region: Nord|Sud, annee, pop).
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("villes");

  // Widget Texte, masqué tant que la variable "seuil" ne vaut pas "Nord".
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Région Nord sélectionnée");
  await page.getByLabel("Condition d'affichage (visibleWhen)").fill('vars.seuil == "Nord"');

  // Widget Table, liée à la même source, avec une colonne calculée.
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Colonnes (séparées par des virgules)").fill("region,annee");
  await page.getByRole("button", { name: "Ajouter une colonne calculée" }).click();
  await page.getByLabel(/Libellé de la colonne calculée/).fill("Correspond");
  await page.getByLabel(/Expression de la colonne calculée/).fill("record.region == vars.seuil");

  // Filtre + variable "seuil", câblés Filtre.changed -> Variable(seuil).set.
  await page.getByRole("button", { name: "Filtre" }).click();
  await page.getByLabel("Champ à filtrer").fill("seuil");
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("seuil");

  await page.getByLabel("Widget émetteur").selectOption({ label: "Filtre" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : seuil" });
  await page.getByLabel("Action").selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : "seuil" vaut "" au départ — le Texte est caché, aucune ligne ne correspond.
  await page.goto("/apps/9");
  await expect(page.getByText("Région Nord sélectionnée")).toBeHidden();
  await expect(page.getByRole("cell", { name: "false" })).toHaveCount(4);
  await expect(page.getByRole("cell", { name: "true" })).toHaveCount(0);

  // Taper "Nord" dans le Filtre : le Texte apparaît, la colonne calculée distingue Nord/Sud.
  await page.getByLabel("Valeur du filtre").fill("Nord");
  await expect(page.getByText("Région Nord sélectionnée")).toBeVisible();
  await expect(page.getByRole("cell", { name: "true" })).toHaveCount(2);
  await expect(page.getByRole("cell", { name: "false" })).toHaveCount(2);
});
```

- [ ] **Step 2: Lancer la spec**

Run: `cd shell && npx playwright test expressions.spec.ts`
Expected: PASS — les Tasks 1-5 implémentent déjà tout ce que cette spec exerce ; ce n'est pas un cycle RED/GREEN (contrairement aux tâches précédentes), c'est la confirmation d'intégration bout-en-bout. Si elle échoue, investiguer lequel des maillons (Tasks 1-5) ne s'intègre pas comme supposé — ne pas modifier la spec pour la faire passer sans comprendre pourquoi.

- [ ] **Step 3: Lancer la suite E2E complète**

Run: `cd shell && npm run e2e`
Expected: PASS — 15 specs vertes (14 existantes + `expressions.spec.ts`).

- [ ] **Step 4: Commit**

```bash
cd shell
git add e2e/expressions.spec.ts
git commit -m "test(shell): e2e — Filtre pilote visibleWhen et une colonne calculée par expression (SP-5a)"
```

---

## Couverture spec → tâches (auto-vérification)

- §2 « Langage : cel-js, spike de validation en ouverture » → Task 1.
- §2 « Architecture d'évaluation : évaluateur fin » → Task 2.
- §2 « Vocabulaire : vars/record/user » → Task 2 (type), Task 3 (peuplement de `user` via `useAuth()`), Task 4 (consommation dans Table).
- §2 « Erreurs à l'exécution : undefined + warn » → Task 2.
- §2 « Validation à l'édition : Enregistrer désactivé » → Task 5.
- §2 « visibleWhen sur WidgetItem » → Task 3 (+ exception mode edit, ajoutée pendant l'écriture de ce plan, cf. Global Constraints).
- §2 « Colonnes calculées (Table), rétrocompatible » → Task 4.
- §3 Architecture (diagramme) → Tasks 2-5, mêmes fonctions/points d'accroche.
- §4 Builder UI (PropsPanel visibleWhen, Table PropsPanel colonne calculée, Enregistrer désactivé) → Tasks 4-5.
- §5 Rendu runtime (WidgetHost monte/démonte, Table branche string/objet, pas de tri sur colonne calculée) → Tasks 3-4.
- §6 Stratégie de tests (unitaire + E2E) → Tasks 2-6.
- §7 Critères d'acceptation (dashboard créé sans code, E2E vert ; expression invalide signalée à l'édition ; aucune régression) → Task 6 (E2E), Task 5 (Enregistrer désactivé), toutes tâches (suite verte à chaque commit).
- §8 Risques (cel-js immature ; scope creep) → Task 1 (gate), périmètre de ce plan limité à un seul point d'accroche de champ calculé (Table).
