# REV-104/GAP-10 — Animation temporelle (play/pause/vitesse) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer REV-104/GAP-10 (chantier 4.17) documenté par
`docs/superpowers/specs/2026-09-07-rev104-animation-temporelle-design.md` :
ajouter des contrôles Lecture/Pause/Vitesse au widget `dateRangeFilter`
existant, qui font avancer automatiquement la fenêtre `timeRange` du
contexte temps global (A29) par pas de un grain temporel — sans nouveau
widget, sans route ni migration cœur, sans état persisté au-delà du choix
de grain.

**Architecture:** Trois couches ajoutées dans l'ordre : (1) arithmétique de
date pure et testable indépendamment (`shell/src/lib/timeAnimation.ts`),
(2) extension déclarative du widget (`configSchema`/`PropsPanel`, choix de
grain par l'auteur), (3) minuteur d'avancement automatique dans le
`Component` du widget, réutilisant le patron `mountedRef`/`timerRef` +
`setTimeout` auto-reprogrammé déjà posé par SP-60 sur `ExportPanel.tsx`.
Une tâche d'intégration confirme que `derivePatch`/`DataContext` — non
modifiés — propagent déjà l'avancement à tout widget lié au même dataset,
puisque c'est exactement le mécanisme déjà livré par A29. Tâches
strictement séquentielles (chaque tâche dépend du type/de la fonction
posée par la précédente) — pas de parallélisation utile ici.

**Tech Stack:** React 18 + TypeScript, Vitest + `@testing-library/react` +
`@testing-library/user-event`, timers factices Vitest
(`vi.useFakeTimers()`/`vi.advanceTimersByTimeAsync`) — aucune nouvelle
dépendance npm.

## Global Constraints

- Chaque tâche suit TDD strict : test qui échoue → implémentation minimale
  → test qui passe → commit (`CLAUDE.md`).
- Commits conventionnels français (`feat(shell): …`, `test(shell): …`), un
  sujet par commit.
- **Aucun fichier `core/` touché** — chantier shell-only. Un diff non vide
  sur `core/openapi.json`/`shell/src/api/generated/core-schema.d.ts` en fin
  de plan serait le signe d'une régression, pas un oubli à combler (piège
  n°1 CLAUDE.md — ici inversé : le diff attendu est vide).
- **Jamais d'assertion de durée réelle pour prouver une propriété du
  minuteur** (piège n°7 CLAUDE.md) — toujours `vi.useFakeTimers()` +
  `vi.advanceTimersByTimeAsync(ms)`, jamais `setTimeout`/`sleep` réel dans
  un test, jamais de comparaison `Date.now()` avant/après. Patron copié
  depuis `shell/src/builder/print/ExportPanel.test.tsx` (`beforeEach(() =>
  vi.useFakeTimers())`, ligne 137, et le test de démontage en cours de
  sondage, lignes 87-101) — vérifier ce fichier avant d'écrire le premier
  test de la Tâche 3.
- **Patron `mountedRef`/`timerRef` + `setTimeout` auto-reprogrammé, jamais
  `setInterval`** — copié depuis `shell/src/builder/print/ExportPanel.tsx`
  lignes 36-43 (déclaration des refs) et 49-61 (programmation/annulation),
  jamais réinventé.
- **`BucketGranularity` (`shell/src/lib/comparisonWindow.ts:12`) n'est
  jamais modifié** — un nouveau type `AnimationGrain` en est dérivé
  (`Exclude<BucketGranularity, "hour">`), importé, jamais redéfini en
  dur avec les 5 littéraux.
- **Réutiliser les clés i18n existantes** `dataSourcePanel.bucket{Day,Week,
  Month,Quarter,Year}Option` (`shell/src/i18n/catalog.fr.ts`) pour les
  libellés d'options de grain — ne pas dupliquer ces 5 chaînes sous de
  nouvelles clés.
- **Aucune chaîne française codée en dur** dans
  `shell/src/builder/widgets/dateRangeFilter.tsx` — ce répertoire est
  couvert par le garde-fou `shell/scripts/check-i18n-coverage.mjs` depuis
  SP-57a (`npm run lint` échoue sinon).
- **`from`/`to` restent des `<input type="date">`** (précision jour,
  inchangé) — le grain `"hour"` n'est jamais proposé par le sélecteur de ce
  widget (cf. spec §1).
- Nettoyer `dist/`/`dist-export/` avant toute mesure de couverture shell
  (piège documenté 4 fois dans `CLAUDE.md`) si la Tâche 6 mesure la
  couverture.
- Lancer la suite Vitest complète (`npm run test`), `npm run lint` et
  `npm run build` une fois à la toute fin du plan (Tâche 6), conformément à
  `CLAUDE.md` (piège n°6 : régressions cross-tâches visibles seulement à la
  première exécution complète).

---

## File structure

**Create:**
- `shell/src/lib/timeAnimation.ts` (Task 1) — `addGrain`/`initialWindow`/`stepWindow`, type `AnimationGrain`.
- `shell/src/lib/timeAnimation.test.ts` (Task 1).

**Modify:**
- `shell/src/builder/widgets/dateRangeFilter.tsx` (Tasks 2, 3) — `configSchema` + `PropsPanel` (grain), puis `Component` (Lecture/Pause/Vitesse).
- `shell/src/builder/widgets/dateRangeFilter.test.tsx` (Tasks 2, 3).
- `shell/src/i18n/catalog.fr.ts` (Task 4) — nouvelles clés `widgetDateRangeFilter.*`.
- `shell/src/builder/AppRenderer.test.tsx` (Task 5) — test d'intégration inter-widgets (aucun fichier de production touché par cette tâche).

**Read-only reference (jamais modifiés par ce plan) :**
- `shell/src/builder/AnalyticsContext.tsx`
- `shell/src/lib/analyticsPatch.ts`
- `shell/src/builder/DataContext.tsx`
- `shell/src/builder/widgets/mapWidget.tsx`, `shell/src/builder/widgets/chart.tsx`
- `shell/src/lib/comparisonWindow.ts`
- `shell/src/builder/DataSourcePanel.tsx`
- `shell/src/builder/print/ExportPanel.tsx` (patron de référence)

---

### Task 1: Arithmétique de grain pure (`timeAnimation.ts`)

**Files:**
- Create: `shell/src/lib/timeAnimation.ts`
- Test: `shell/src/lib/timeAnimation.test.ts`

**Interfaces:**
- Consumes: `BucketGranularity` (type) from `shell/src/lib/comparisonWindow.ts`.
- Produces (consumed by Tasks 2, 3, 5):
  - `export type AnimationGrain = Exclude<BucketGranularity, "hour">;`
  - `export function addGrain(dateIso: string, grain: AnimationGrain, count?: number): string;`
  - `export function initialWindow(start: string, grain: AnimationGrain): { from: string; to: string };`
  - `export function stepWindow(current: { from: string; to: string }, bounds: { loopStart: string; loopEnd: string }, grain: AnimationGrain): { from: string; to: string };`

- [ ] **Step 1: Write the failing test**

Create `shell/src/lib/timeAnimation.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { addGrain, initialWindow, stepWindow } from "./timeAnimation";

test("addGrain advances by one day", () => {
  expect(addGrain("2026-03-10", "day")).toBe("2026-03-11");
});

test("addGrain advances by one week (7 days)", () => {
  expect(addGrain("2026-03-10", "week")).toBe("2026-03-17");
});

test("addGrain advances by one calendar month, clamping day to month length", () => {
  // 31 janvier + 1 mois -> février n'a que 28 jours en 2026 (non bissextile)
  expect(addGrain("2026-01-31", "month")).toBe("2026-02-28");
});

test("addGrain advances by one calendar month across a leap year", () => {
  expect(addGrain("2028-01-31", "month")).toBe("2028-02-29");
});

test("addGrain advances by one quarter (3 months)", () => {
  expect(addGrain("2026-01-31", "quarter")).toBe("2026-04-30");
});

test("addGrain advances by one year, clamping Feb 29 on a non-leap target", () => {
  expect(addGrain("2028-02-29", "year")).toBe("2029-02-28");
});

test("addGrain supports a count greater than one", () => {
  expect(addGrain("2026-01-01", "day", 5)).toBe("2026-01-06");
});

test("initialWindow returns a one-grain-wide window starting at `start`", () => {
  expect(initialWindow("2026-01-01", "month")).toEqual({
    from: "2026-01-01",
    to: "2026-02-01",
  });
});

test("stepWindow advances both bounds by one grain when still inside the loop", () => {
  const next = stepWindow(
    { from: "2026-01-01", to: "2026-02-01" },
    { loopStart: "2026-01-01", loopEnd: "2026-12-01" },
    "month",
  );
  expect(next).toEqual({ from: "2026-02-01", to: "2026-03-01" });
});

test("stepWindow loops back to loopStart once the window would pass loopEnd", () => {
  const next = stepWindow(
    { from: "2026-11-01", to: "2026-12-01" },
    { loopStart: "2026-01-01", loopEnd: "2026-12-01" },
    "month",
  );
  // La borne de fin de la fenêtre suivante (2027-01-01) dépasse loopEnd
  // (2026-12-01) -> on reboucle sur la fenêtre initiale.
  expect(next).toEqual({ from: "2026-01-01", to: "2026-02-01" });
});

test("stepWindow does not loop when the next window's end lands exactly on loopEnd", () => {
  const next = stepWindow(
    { from: "2026-10-01", to: "2026-11-01" },
    { loopStart: "2026-01-01", loopEnd: "2026-12-01" },
    "month",
  );
  expect(next).toEqual({ from: "2026-11-01", to: "2026-12-01" });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/lib/timeAnimation.test.ts`
Expected: FAIL — `Cannot find module './timeAnimation'` (file does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `shell/src/lib/timeAnimation.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Avancement calendaire d'une fenêtre temporelle par pas de un grain — pour
// la lecture automatique du widget dateRangeFilter (REV-104/GAP-10). Réutilise
// BucketGranularity (comparisonWindow.ts, SP-23) sans le redéfinir ; "hour"
// est exclu ici (le widget consommateur n'a qu'une précision jour, cf.
// spec §1) mais reste un grain valide côté agrégation (DataSourcePanel).
import type { BucketGranularity } from "./comparisonWindow";

export type AnimationGrain = Exclude<BucketGranularity, "hour">;

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
}

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

// `dateIso` est une chaîne "YYYY-MM-DD", parsée par `new Date(...)` comme
// minuit UTC (règle de parsing ISO date-only) — toute l'arithmétique reste
// en UTC pour ne jamais dériver selon le fuseau d'exécution (même
// invariant que comparisonWindow.ts:20-23).
function shiftMonths(d: Date, totalMonths: number): Date {
  const day = d.getUTCDate();
  const totalMonthIndex = d.getUTCFullYear() * 12 + d.getUTCMonth() + totalMonths;
  const year = Math.floor(totalMonthIndex / 12);
  const month = totalMonthIndex % 12;
  return new Date(Date.UTC(year, month, Math.min(day, daysInMonth(year, month))));
}

const MONTHS_PER_GRAIN: Partial<Record<AnimationGrain, number>> = {
  month: 1,
  quarter: 3,
  year: 12,
};

export function addGrain(dateIso: string, grain: AnimationGrain, count = 1): string {
  const d = new Date(dateIso);
  if (grain === "day") {
    return toISODate(new Date(d.getTime() + count * 86_400_000));
  }
  if (grain === "week") {
    return toISODate(new Date(d.getTime() + count * 7 * 86_400_000));
  }
  const monthsPerStep = MONTHS_PER_GRAIN[grain]!;
  return toISODate(shiftMonths(d, monthsPerStep * count));
}

export function initialWindow(
  start: string,
  grain: AnimationGrain,
): { from: string; to: string } {
  return { from: start, to: addGrain(start, grain, 1) };
}

export function stepWindow(
  current: { from: string; to: string },
  bounds: { loopStart: string; loopEnd: string },
  grain: AnimationGrain,
): { from: string; to: string } {
  const nextFrom = addGrain(current.from, grain, 1);
  const nextTo = addGrain(current.to, grain, 1);
  if (new Date(nextTo).getTime() > new Date(bounds.loopEnd).getTime()) {
    return initialWindow(bounds.loopStart, grain);
  }
  return { from: nextFrom, to: nextTo };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/lib/timeAnimation.test.ts`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/lib/timeAnimation.ts src/lib/timeAnimation.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute l'arithmétique de grain pure pour l'animation temporelle

REV-104/GAP-10 (chantier 4.17) : addGrain/initialWindow/stepWindow,
fonctions pures testées indépendamment de tout composant React, socle
de la lecture automatique du contexte temps global A29.
EOF
)"
```

---

### Task 2: `configSchema`/`PropsPanel` — sélecteur de grain d'auteur

**Files:**
- Modify: `shell/src/builder/widgets/dateRangeFilter.tsx`
- Modify: `shell/src/builder/widgets/dateRangeFilter.test.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts` (2 nouvelles clés seulement — le reste des clés d'animation vient en Task 4)

**Interfaces:**
- Consumes: `AnimationGrain` from `shell/src/lib/timeAnimation.ts` (Task 1).
- Produces (consumed by Task 3): `defaultProps.grain: AnimationGrain` (défaut `"day"`), rendu par `PropsPanel` comme un `<select>` à 5 options.

Cette tâche ne touche pas encore au `Component` (pas de lecture automatique
ici) — seulement la déclaration de config et son panneau d'édition.

- [ ] **Step 1: Write the failing test**

Ajouter à `shell/src/builder/widgets/dateRangeFilter.test.tsx` (après les
imports existants, garder les tests déjà présents intacts) :

```ts
test("configSchema declares a grain field defaulting to day, excluding hour", () => {
  const def = getWidget("dateRangeFilter")!;
  expect(def.defaultProps.grain).toBe("day");
  const grainField = def.configSchema?.find((f) => f.name === "grain");
  expect(grainField).toBeDefined();
});

test("PropsPanel renders a grain select with 5 options (no hour)", async () => {
  const def = getWidget("dateRangeFilter")!;
  const onChange = vi.fn();
  render(
    def.PropsPanel({
      props: { label: "Période", grain: "day" },
      onChange,
      dataSources: [],
    }),
  );
  const select = screen.getByLabelText("Grain temporel") as HTMLSelectElement;
  const optionValues = Array.from(select.options).map((o) => o.value);
  expect(optionValues).toEqual(["day", "week", "month", "quarter", "year"]);
  await userEvent.selectOptions(select, "week");
  expect(onChange).toHaveBeenCalledWith({ label: "Période", grain: "week" });
});
```

Ajouter `vi` à l'import Vitest existant (`import { beforeEach, expect, test, vi } from "vitest";`)
et `render, screen` sont déjà importés de `@testing-library/react` — vérifier
qu'ils le sont (sinon les ajouter à l'import existant).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/dateRangeFilter.test.tsx`
Expected: FAIL — `def.defaultProps.grain` is `undefined`, pas de champ
`configSchema` nommé `grain`, `getByLabelText("Grain temporel")` ne trouve
rien.

- [ ] **Step 3: Write minimal implementation**

Ajouter dans `shell/src/i18n/catalog.fr.ts`, à côté des clés
`widgetDateRangeFilter.*` existantes (lignes 770-777) :

```ts
  "widgetDateRangeFilter.grainConfig": "Grain temporel",
  "widgetDateRangeFilter.grainAria": "Grain temporel",
```

Modifier `shell/src/builder/widgets/dateRangeFilter.tsx` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { registerWidget } from "../registry";
import { useSetTimeRange } from "../AnalyticsContext";
import type { AnimationGrain } from "../../lib/timeAnimation";
import { t } from "../../i18n";

// 5 des 6 grains de BucketGranularity (SP-23) — "hour" est délibérément
// exclu : ce widget n'a qu'une précision jour (<input type="date">), cf.
// spec REV-104 §1. Réutilise les clés i18n déjà posées pour le sélecteur
// de bucket d'agrégation (DataSourcePanel.tsx) plutôt que d'en dupliquer
// le texte.
const GRAIN_OPTIONS: { value: AnimationGrain; label: string }[] = [
  { value: "day", label: t("dataSourcePanel.bucketDayOption") },
  { value: "week", label: t("dataSourcePanel.bucketWeekOption") },
  { value: "month", label: t("dataSourcePanel.bucketMonthOption") },
  { value: "quarter", label: t("dataSourcePanel.bucketQuarterOption") },
  { value: "year", label: t("dataSourcePanel.bucketYearOption") },
];

export function registerDateRangeFilterWidget(): void {
  registerWidget({
    type: "dateRangeFilter",
    label: t("widgetDateRangeFilter.paletteLabel"),
    defaultProps: { label: t("widgetDateRangeFilter.periodDefault"), grain: "day" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [
      {
        name: "label",
        type: "string",
        label: t("widgetDateRangeFilter.labelConfig"),
        default: t("widgetDateRangeFilter.periodDefault"),
      },
      {
        name: "grain",
        type: "string",
        label: t("widgetDateRangeFilter.grainConfig"),
        default: "day",
      },
    ],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          {t("widgetDateRangeFilter.labelConfig")}
          <input
            aria-label={t("widgetDateRangeFilter.labelAria")}
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")}
            onChange={(e) => onChange({ ...props, label: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("widgetDateRangeFilter.grainConfig")}
          <select
            aria-label={t("widgetDateRangeFilter.grainAria")}
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.grain ?? "day")}
            onChange={(e) => onChange({ ...props, grain: e.target.value })}
          >
            {GRAIN_OPTIONS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    ),
    Component: ({ props }) => {
      const setTimeRange = useSetTimeRange();
      const [from, setFrom] = useState("");
      const [to, setTo] = useState("");

      function update(nextFrom: string, nextTo: string) {
        setFrom(nextFrom);
        setTo(nextTo);
        setTimeRange(nextFrom && nextTo ? { from: nextFrom, to: nextTo } : null);
      }

      return (
        <div className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <span>{String(props.label ?? t("widgetDateRangeFilter.periodDefault"))}</span>
          <div className="flex gap-2">
            <input
              type="date"
              aria-label={t("widgetDateRangeFilter.startDate")}
              className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={from}
              onChange={(e) => update(e.target.value, to)}
            />
            <input
              type="date"
              aria-label={t("widgetDateRangeFilter.endDate")}
              className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={to}
              onChange={(e) => update(from, e.target.value)}
            />
          </div>
        </div>
      );
    },
  });
}
```

Note : le `Component` ci-dessus est identique à l'original à ce stade (les
contrôles Lecture/Pause arrivent en Task 3) — seul `configSchema`/
`PropsPanel`/`defaultProps` changent dans cette tâche.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/dateRangeFilter.test.tsx`
Expected: PASS (tous les tests, anciens et nouveaux).

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/builder/widgets/dateRangeFilter.tsx src/builder/widgets/dateRangeFilter.test.tsx src/i18n/catalog.fr.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute le choix de grain d'auteur sur dateRangeFilter

REV-104/GAP-10 : nouveau champ configSchema `grain` (5 des 6
BucketGranularity de SP-23, "hour" exclu — précision jour du widget),
sélecteur dans PropsPanel réutilisant les libellés de DataSourcePanel.
Pas encore de lecture automatique (Task suivante).
EOF
)"
```

---

### Task 3: Contrôles Lecture/Pause/Vitesse dans le `Component`

**Files:**
- Modify: `shell/src/builder/widgets/dateRangeFilter.tsx`
- Modify: `shell/src/builder/widgets/dateRangeFilter.test.tsx`

**Interfaces:**
- Consumes: `addGrain`, `initialWindow`, `stepWindow`, `AnimationGrain` from Task 1; `grain` prop from Task 2.
- Produces (consumed by Task 5): the widget's `Component` now calls
  `setTimeRange` repeatedly while playing — Task 5's integration test
  observes this indirectly through `AnalyticsContextProvider`, no new
  exported symbol.

This is the core task. Read `shell/src/builder/print/ExportPanel.tsx` lines
1-90 and `shell/src/builder/print/ExportPanel.test.tsx` lines 1-165 first —
this task copies both the polling-cancellation pattern and its
falsification pattern verbatim.

- [ ] **Step 1: Write the failing test**

Replace the full contents of `shell/src/builder/widgets/dateRangeFilter.test.tsx`
with (keeps the existing 4 tests — 2 original + 2 from Task 2 — and adds
the new ones):

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { AnalyticsContextProvider, useAnalyticsContext } from "../AnalyticsContext";
import { registerDateRangeFilterWidget } from "./dateRangeFilter";
import type { WidgetContext } from "../registry";

beforeEach(() => {
  _resetRegistry();
  registerDateRangeFilterWidget();
});

function TimeRangeProbe() {
  const ctx = useAnalyticsContext();
  return <p>timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>;
}

test("registers with no events/actions (a global control, not a bus-wired source filter)", () => {
  const def = getWidget("dateRangeFilter")!;
  expect(def.events).toBeUndefined();
  expect(def.actions).toBeUndefined();
});

test("sets the time range when both dates are filled, only when interactions is auto", async () => {
  const DateRangeFilter = getWidget("dateRangeFilter")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilter props={{ label: "Période", grain: "day" }} ctx={{ mode: "runtime" } as WidgetContext} />
      <TimeRangeProbe />
    </AnalyticsContextProvider>,
  );
  await userEvent.type(screen.getByLabelText("Date de début"), "2026-01-01");
  await userEvent.type(screen.getByLabelText("Date de fin"), "2026-02-01");
  expect(await screen.findByText("timeRange:2026-01-01..2026-02-01")).toBeInTheDocument();
});

test("is a no-op when interactions is manual", async () => {
  const DateRangeFilter = getWidget("dateRangeFilter")!.Component;
  render(
    <AnalyticsContextProvider interactions="manual">
      <DateRangeFilter props={{ label: "Période", grain: "day" }} ctx={{ mode: "runtime" } as WidgetContext} />
      <TimeRangeProbe />
    </AnalyticsContextProvider>,
  );
  await userEvent.type(screen.getByLabelText("Date de début"), "2026-01-01");
  await userEvent.type(screen.getByLabelText("Date de fin"), "2026-02-01");
  expect(screen.getByText("timeRange:none")).toBeInTheDocument();
});

test("configSchema declares a grain field defaulting to day, excluding hour", () => {
  const def = getWidget("dateRangeFilter")!;
  expect(def.defaultProps.grain).toBe("day");
  const grainField = def.configSchema?.find((f) => f.name === "grain");
  expect(grainField).toBeDefined();
});

test("PropsPanel renders a grain select with 5 options (no hour)", async () => {
  const def = getWidget("dateRangeFilter")!;
  const onChange = vi.fn();
  render(
    def.PropsPanel({
      props: { label: "Période", grain: "day" },
      onChange,
      dataSources: [],
    }),
  );
  const select = screen.getByLabelText("Grain temporel") as HTMLSelectElement;
  const optionValues = Array.from(select.options).map((o) => o.value);
  expect(optionValues).toEqual(["day", "week", "month", "quarter", "year"]);
  await userEvent.selectOptions(select, "week");
  expect(onChange).toHaveBeenCalledWith({ label: "Période", grain: "week" });
});

// --- Contrôles Lecture/Pause/Vitesse (REV-104/GAP-10) ---

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

async function fillRange(user: ReturnType<typeof userEvent.setup>, from: string, to: string) {
  await user.type(screen.getByLabelText("Date de début"), from);
  await user.type(screen.getByLabelText("Date de fin"), to);
}

test("play button is disabled until a valid range (at least one grain wide) is set", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const DateRangeFilter = getWidget("dateRangeFilter")!.Component;
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilter props={{ label: "Période", grain: "day" }} ctx={{ mode: "runtime" } as WidgetContext} />
    </AnalyticsContextProvider>,
  );
  expect(screen.getByRole("button", { name: "Lecture" })).toBeDisabled();
  await fillRange(user, "2026-01-01", "2026-01-01"); // même jour : aucun pas ne tient
  expect(screen.getByRole("button", { name: "Lecture" })).toBeDisabled();
  await user.clear(screen.getByLabelText("Date de fin"));
  await user.type(screen.getByLabelText("Date de fin"), "2026-01-02");
  expect(screen.getByRole("button", { name: "Lecture" })).toBeEnabled();
});

test("play starts advancing the time window by one grain per tick at normal speed", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilterWithProbe grain="day" />
    </AnalyticsContextProvider>,
  );
  await fillRange(user, "2026-01-01", "2026-01-05");
  await user.click(screen.getByRole("button", { name: "Lecture" }));
  expect(screen.getByText("timeRange:2026-01-01..2026-01-02")).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000); // vitesse "normal" = 1000ms/tick
  });
  expect(screen.getByText("timeRange:2026-01-02..2026-01-03")).toBeInTheDocument();
});

test("pause stops advancing without resetting the current window", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilterWithProbe grain="day" />
    </AnalyticsContextProvider>,
  );
  await fillRange(user, "2026-01-01", "2026-01-05");
  await user.click(screen.getByRole("button", { name: "Lecture" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(screen.getByText("timeRange:2026-01-02..2026-01-03")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Pause" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000); // plusieurs ticks auraient dû passer si non en pause
  });
  expect(screen.getByText("timeRange:2026-01-02..2026-01-03")).toBeInTheDocument();
});

test("resuming after pause continues from the paused window, not from loopStart", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilterWithProbe grain="day" />
    </AnalyticsContextProvider>,
  );
  await fillRange(user, "2026-01-01", "2026-01-05");
  await user.click(screen.getByRole("button", { name: "Lecture" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  await user.click(screen.getByRole("button", { name: "Pause" })); // window: 2026-01-02..01-03
  await user.click(screen.getByRole("button", { name: "Lecture" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(screen.getByText("timeRange:2026-01-03..2026-01-04")).toBeInTheDocument();
});

test("changing speed while playing changes the interval used by the next tick", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilterWithProbe grain="day" />
    </AnalyticsContextProvider>,
  );
  await fillRange(user, "2026-01-01", "2026-01-05");
  await user.click(screen.getByRole("button", { name: "Lecture" }));
  await user.selectOptions(screen.getByLabelText("Vitesse de lecture"), "fast"); // 400ms/tick
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
  expect(screen.getByText("timeRange:2026-01-02..2026-01-03")).toBeInTheDocument();
});

test("the window loops back to loopStart once it passes loopEnd", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilterWithProbe grain="day" />
    </AnalyticsContextProvider>,
  );
  await fillRange(user, "2026-01-01", "2026-01-02"); // exactement un grain de large
  await user.click(screen.getByRole("button", { name: "Lecture" }));
  expect(screen.getByText("timeRange:2026-01-01..2026-01-02")).toBeInTheDocument();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000); // le pas suivant dépasserait loopEnd -> boucle
  });
  expect(screen.getByText("timeRange:2026-01-01..2026-01-02")).toBeInTheDocument();
});

test("unmounting mid-playback cancels the pending tick (no update after unmount)", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const { unmount } = render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilterWithProbe grain="day" />
    </AnalyticsContextProvider>,
  );
  await fillRange(user, "2026-01-01", "2026-01-05");
  await user.click(screen.getByRole("button", { name: "Lecture" }));
  unmount();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });
  const reactWarnings = errorSpy.mock.calls.filter((c) =>
    String(c[0]).includes("state update on an unmounted component"),
  );
  expect(reactWarnings).toHaveLength(0);
  errorSpy.mockRestore();
});

test("editing the start or end date while playing stops the playback", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <AnalyticsContextProvider interactions="auto">
      <DateRangeFilterWithProbe grain="day" />
    </AnalyticsContextProvider>,
  );
  await fillRange(user, "2026-01-01", "2026-01-05");
  await user.click(screen.getByRole("button", { name: "Lecture" }));
  await user.clear(screen.getByLabelText("Date de fin"));
  await user.type(screen.getByLabelText("Date de fin"), "2026-03-01");
  expect(screen.getByText("timeRange:2026-01-01..2026-03-01")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Lecture" })).toBeInTheDocument(); // repassé en idle
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });
  expect(screen.getByText("timeRange:2026-01-01..2026-03-01")).toBeInTheDocument(); // pas d'avancée
});

test("playback timer is a silent no-op when interactions is manual", async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <AnalyticsContextProvider interactions="manual">
      <DateRangeFilterWithProbe grain="day" />
    </AnalyticsContextProvider>,
  );
  await fillRange(user, "2026-01-01", "2026-01-05");
  await user.click(screen.getByRole("button", { name: "Lecture" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });
  expect(screen.getByText("timeRange:none")).toBeInTheDocument();
});

function DateRangeFilterWithProbe({ grain }: { grain: string }) {
  const DateRangeFilter = getWidget("dateRangeFilter")!.Component;
  return (
    <>
      <DateRangeFilter props={{ label: "Période", grain }} ctx={{ mode: "runtime" } as WidgetContext} />
      <TimeRangeProbe />
    </>
  );
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/dateRangeFilter.test.tsx`
Expected: FAIL — `getByRole("button", { name: "Lecture" })` finds nothing
(no play button exists yet); the rest of the new tests fail the same way.

- [ ] **Step 3: Write minimal implementation**

Add two i18n keys to `shell/src/i18n/catalog.fr.ts` right after
`widgetDateRangeFilter.grainAria` from Task 2:

```ts
  "widgetDateRangeFilter.play": "Lecture",
  "widgetDateRangeFilter.pause": "Pause",
  "widgetDateRangeFilter.speedAria": "Vitesse de lecture",
  "widgetDateRangeFilter.speedSlow": "Lente",
  "widgetDateRangeFilter.speedNormal": "Normale",
  "widgetDateRangeFilter.speedFast": "Rapide",
```

Replace the `Component` of `shell/src/builder/widgets/dateRangeFilter.tsx`
(everything else in the file — imports up to `PropsPanel` — stays exactly
as Task 2 left it; add the new imports at the top):

```ts
import { useEffect, useRef, useState } from "react";
// … registerWidget, useSetTimeRange, AnimationGrain, t already imported …
import { addGrain, initialWindow, stepWindow } from "../../lib/timeAnimation";

type PlaybackStatus = "idle" | "playing" | "paused";
type PlaybackSpeed = "slow" | "normal" | "fast";

const SPEED_INTERVAL_MS: Record<PlaybackSpeed, number> = {
  slow: 2000,
  normal: 1000,
  fast: 400,
};
```

Then, inside `registerWidget({ ... })`, replace only the `Component` field:

```ts
    Component: ({ props }) => {
      const setTimeRange = useSetTimeRange();
      const [from, setFrom] = useState("");
      const [to, setTo] = useState("");
      const [playback, setPlayback] = useState<PlaybackStatus>("idle");
      const [speed, setSpeed] = useState<PlaybackSpeed>("normal");
      const grain = (props.grain ?? "day") as AnimationGrain;

      const mountedRef = useRef(true);
      const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
      const cursorRef = useRef<{ from: string; to: string } | null>(null);
      const loopBoundsRef = useRef<{ loopStart: string; loopEnd: string } | null>(null);
      const speedRef = useRef(speed);
      speedRef.current = speed;
      const grainRef = useRef(grain);
      grainRef.current = grain;

      useEffect(
        () => () => {
          mountedRef.current = false;
          if (timerRef.current) clearTimeout(timerRef.current);
        },
        [],
      );

      function clearTimer() {
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = null;
      }

      function scheduleNextTick() {
        timerRef.current = setTimeout(() => {
          if (!mountedRef.current || !cursorRef.current || !loopBoundsRef.current) return;
          const next = stepWindow(cursorRef.current, loopBoundsRef.current, grainRef.current);
          cursorRef.current = next;
          setTimeRange(next);
          scheduleNextTick();
        }, SPEED_INTERVAL_MS[speedRef.current]);
      }

      function update(nextFrom: string, nextTo: string) {
        // Éditer les dates pendant la lecture ou la pause arrête l'animation
        // (spec §2.3) et repasse en filtrage manuel direct.
        if (playback !== "idle") {
          clearTimer();
          cursorRef.current = null;
          loopBoundsRef.current = null;
          setPlayback("idle");
        }
        setFrom(nextFrom);
        setTo(nextTo);
        setTimeRange(nextFrom && nextTo ? { from: nextFrom, to: nextTo } : null);
      }

      const canPlay = Boolean(from && to) && addGrain(from, grain, 1) <= to;

      function play() {
        if (!canPlay) return;
        if (playback === "idle") {
          loopBoundsRef.current = { loopStart: from, loopEnd: to };
          const first = initialWindow(from, grain);
          cursorRef.current = first;
          setTimeRange(first);
        }
        setPlayback("playing");
        scheduleNextTick();
      }

      function pause() {
        clearTimer();
        setPlayback("paused");
      }

      return (
        <div className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          <span>{String(props.label ?? t("widgetDateRangeFilter.periodDefault"))}</span>
          <div className="flex gap-2">
            <input
              type="date"
              aria-label={t("widgetDateRangeFilter.startDate")}
              className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={from}
              onChange={(e) => update(e.target.value, to)}
            />
            <input
              type="date"
              aria-label={t("widgetDateRangeFilter.endDate")}
              className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={to}
              onChange={(e) => update(from, e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            {playback === "playing" ? (
              <button
                type="button"
                aria-pressed="true"
                className="h-9 rounded-md border border-[var(--gs-color-border)] px-3"
                onClick={pause}
              >
                {t("widgetDateRangeFilter.pause")}
              </button>
            ) : (
              <button
                type="button"
                aria-pressed="false"
                disabled={!canPlay}
                className="h-9 rounded-md border border-[var(--gs-color-border)] px-3 disabled:opacity-50"
                onClick={play}
              >
                {t("widgetDateRangeFilter.play")}
              </button>
            )}
            <select
              aria-label={t("widgetDateRangeFilter.speedAria")}
              className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
              value={speed}
              onChange={(e) => setSpeed(e.target.value as PlaybackSpeed)}
            >
              <option value="slow">{t("widgetDateRangeFilter.speedSlow")}</option>
              <option value="normal">{t("widgetDateRangeFilter.speedNormal")}</option>
              <option value="fast">{t("widgetDateRangeFilter.speedFast")}</option>
            </select>
          </div>
        </div>
      );
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/dateRangeFilter.test.tsx`
Expected: PASS (all tests — original 2, Task 2's 2, and the new playback
tests).

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/builder/widgets/dateRangeFilter.tsx src/builder/widgets/dateRangeFilter.test.tsx src/i18n/catalog.fr.ts
git commit -m "$(cat <<'EOF'
feat(shell): ajoute Lecture/Pause/Vitesse à dateRangeFilter

REV-104/GAP-10 : la fenêtre timeRange avance automatiquement par pas
de un grain (setTimeout auto-reprogrammé, patron ExportPanel.tsx),
boucle en fin de plage, s'arrête proprement au démontage ou si les
dates sont modifiées manuellement, respecte le no-op existant en mode
interactions="manual". 3 vitesses (lente/normale/rapide), aucun état
de lecture persisté.
EOF
)"
```

---

### Task 4: Vérification i18n (garde-fou existant, aucun code nouveau)

**Files:**
- No new files. Verifies Tasks 2-3 already satisfy the i18n coverage gate.

**Interfaces:** none (verification-only task).

- [ ] **Step 1: Run the i18n coverage check**

Run: `cd shell && node scripts/check-i18n-coverage.mjs`
Expected: exits 0, no hard-coded French string reported in
`src/builder/widgets/dateRangeFilter.tsx` (every label added in Tasks 2-3
goes through `t(...)`).

If it fails, find the offending literal string reported by the script and
wrap it in a `t("widgetDateRangeFilter.<key>")` call, adding the matching
key/value pair to `shell/src/i18n/catalog.fr.ts` (same pattern as Tasks 2-3),
then re-run the check.

- [ ] **Step 2: Run the full lint gate**

Run: `cd shell && npm run lint`
Expected: exits 0 (the i18n check above is one of the checks `npm run lint`
runs; this step confirms it's wired and nothing else regressed — ESLint,
Prettier check, etc.).

- [ ] **Step 3: Commit (only if Step 1 required a fix)**

```bash
cd shell && git add src/builder/widgets/dateRangeFilter.tsx src/i18n/catalog.fr.ts
git commit -m "fix(shell): route une chaîne d'animation temporelle restée en dur vers t()"
```

If Step 1 passed on the first try, skip this commit — there is nothing to
commit.

---

### Task 5: Test d'intégration — propagation à un widget consommateur, sans toucher `derivePatch`/`DataContext`

**Files:**
- Modify: `shell/src/builder/AppRenderer.test.tsx` (add tests only — no production file touched by this task)

**Interfaces:**
- Consumes: `dateRangeFilter` widget (Task 3), `AnalyticsContextProvider`
  (existing, unmodified), `DataContext`/`derivePatch` (existing, unmodified
  — this task proves they don't need to change).

This task proves acceptance criterion 2 of the spec: a second widget bound
to a dataset with `timeField` re-renders on every animation tick, with zero
changes to `DataContext.tsx`, `analyticsPatch.ts`, `mapWidget.tsx`, or
`chart.tsx`. Read `shell/src/builder/AppRenderer.test.tsx` first to match
its existing setup helpers (dataset/config fixtures) before adding to it —
this plan does not restate that file's existing fixtures since they are
read, not written, by this task.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/builder/AppRenderer.test.tsx` (place near other
analytics-context-related tests in that file; import
`vi`/`act`/`userEvent` if not already imported at the top of the file —
check first, this file already imports most testing utilities):

```tsx
test("a chart widget bound to the same time-filtered dataset re-renders on every animation tick, with no changes needed in DataContext/derivePatch", async () => {
  vi.useFakeTimers();
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

  // `datasets` doit déclarer `timeField` pour que derivePatch()
  // (shell/src/lib/analyticsPatch.ts, non modifié par ce plan) traduise
  // ctx.timeRange en filtre __gte/__lte pour CE dataset — même mécanisme
  // que celui déjà exercé par le test existant de dateRangeFilter.
  const config = buildTestAppConfig({
    // réutiliser ici le/les helper(s) de fixture déjà présents dans ce
    // fichier pour construire un AppConfig minimal à deux widgets
    // (dateRangeFilter + chart) partageant le même datasetId, dont le
    // DatasetConfig déclare `timeField: "observed_at"`.
  });

  const queriedTimeRanges: Array<{ from: string; to: string } | null> = [];
  const client = buildTestItemClient({
    // le stub de queryDataSource capture ctx.timeRange effectivement
    // reçu par la requête du widget chart, sans dépendre de sa forme de
    // rendu — ce test observe la PROPAGATION du contexte, pas le rendu
    // visuel du graphique.
    onQueryDataSource: (source) => {
      queriedTimeRanges.push(
        source.query.observed_at__gte
          ? { from: String(source.query.observed_at__gte), to: String(source.query.observed_at__lte) }
          : null,
      );
    },
  });

  render(<AppRenderer config={config} mode="runtime" client={client} />);

  await user.type(screen.getByLabelText("Date de début"), "2026-01-01");
  await user.type(screen.getByLabelText("Date de fin"), "2026-01-05");
  await user.click(screen.getByRole("button", { name: "Lecture" }));

  const afterFirstTick = queriedTimeRanges.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });

  expect(queriedTimeRanges.length).toBeGreaterThan(afterFirstTick);
  expect(queriedTimeRanges.at(-1)).toEqual({ from: "2026-01-02", to: "2026-01-03" });

  vi.useRealTimers();
});
```

Note pour l'implémenteur : les noms exacts `buildTestAppConfig`/
`buildTestItemClient`/le shape du stub `onQueryDataSource` doivent être
alignés sur les helpers réels déjà présents dans
`shell/src/builder/AppRenderer.test.tsx` (ce fichier a probablement déjà un
mock d'`ItemClient` et un constructeur de config de test — les réutiliser
tels quels, ne pas en écrire de nouveaux). Si `AppRenderer.test.tsx` ne
propose aucun crochet pour observer les requêtes `queryDataSource`,
utiliser `vi.fn()` directement sur la méthode `queryDataSource` du mock
`ItemClient` existant et lire `mock.mock.calls` à la place de
`queriedTimeRanges`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx -t "re-renders on every animation tick"`
Expected: FAIL before Tasks 1-3 exist in a fresh checkout; in this plan's
sequential execution it should already PASS once adapted to the file's real
helpers, since Tasks 1-3 are already committed — if it fails here, the
failure must come from a wiring mismatch in this test's own setup (wrong
fixture usage), not from missing production code. Diagnose and fix the
test's fixture wiring, not `dateRangeFilter.tsx`.

- [ ] **Step 3: Adjust the test to the file's real fixtures (no production code change)**

Iterate on the test body only, using the exact helper names found in
`shell/src/builder/AppRenderer.test.tsx`, until it exercises the real
`AnalyticsContextProvider` + `DataContext` + `derivePatch` path end to end.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx -t "re-renders on every animation tick"`
Expected: PASS.

- [ ] **Step 5: Confirm no production file was touched by this task**

Run: `cd shell && git status --porcelain src/lib/analyticsPatch.ts src/builder/DataContext.tsx src/builder/widgets/mapWidget.tsx src/builder/widgets/chart.tsx`
Expected: empty output (nothing staged or modified in these four files) —
this is the acceptance-criterion-2 proof: the integration works with zero
changes to the propagation mechanism.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/builder/AppRenderer.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): prouve la propagation de l'animation temporelle inter-widgets

REV-104/GAP-10, critère d'acceptation 2 : un widget lié au même dataset
(timeField déclaré) se remet à jour à chaque tick de lecture, sans
aucun changement à DataContext.tsx/analyticsPatch.ts/mapWidget.tsx/
chart.tsx — le mécanisme A29 déjà livré (derivePatch) suffit tel quel.
EOF
)"
```

---

### Task 6: Vérification finale de branche

**Files:** none created/modified by this task beyond what verification
finds (expected: none).

**Interfaces:** none — this is the closing verification pass.

- [ ] **Step 1: No new persisted field beyond `grain`**

Run: `cd shell && npx vitest run src/builder/widgets/dateRangeFilter.test.tsx -t "declares a grain field"`
Expected: PASS (already covered by Task 2's test — re-run here to confirm
it still passes after Task 3's changes, since Task 3 only touched
`Component`, not `configSchema`/`defaultProps`).

Additionally, inspect that `playback`/`speed`/cursor state never appear in
`defaultProps` or `configSchema`:

Run: `cd shell && grep -n "playback\|speed\|cursor" src/builder/widgets/dateRangeFilter.tsx`
Expected: every match is inside the `Component` function body (component
state, refs, or local variables) — none inside `defaultProps` or
`configSchema`.

- [ ] **Step 2: Full Vitest suite**

Run: `cd shell && rm -rf dist dist-export && npm run test`
Expected: PASS, 0 failed (compare the total test count before/after this
plan — it must have grown by exactly the number of tests added in Tasks
1, 2, 3, 5, and by nothing else).

- [ ] **Step 3: Lint and build**

Run: `cd shell && npm run lint && npm run build`
Expected: both exit 0. `npm run build` additionally confirms `tsc --noEmit`
passes (new types `AnimationGrain`/`PlaybackStatus`/`PlaybackSpeed` are
sound) and the bundle-size check (`scripts/check-bundle-size.mjs`) does not
regress — this plan adds no new dependency and one small module, unlikely
to move the threshold, but must be confirmed rather than assumed (piège
CLAUDE.md n°3).

- [ ] **Step 4: Confirm zero core/ impact**

Run: `cd /home/lenen/projets/geostudio/.claude/worktrees/agent-ac6f25c63a14c1192 && git diff --stat main -- core/ | cat`
Expected: empty output — no `core/` file touched by this branch.

Run: `cd /home/lenen/projets/geostudio/.claude/worktrees/agent-ac6f25c63a14c1192 && git diff --stat main -- core/openapi.json shell/src/api/generated/core-schema.d.ts | cat`
Expected: empty output — confirms the OpenAPI spec and generated TS types
are untouched (no route/model change), consistent with a shell-only
chantier (spec §4, criterion 12).

- [ ] **Step 5: Final commit (only if any of the above required a fix)**

```bash
cd shell && git add -A
git commit -m "fix(shell): corrige un écart trouvé par la vérification finale de REV-104"
```

If Steps 1-4 all passed without requiring changes, there is nothing to
commit for this task — the branch is ready for
`superpowers:finishing-a-development-branch`.

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- Spec §0 (vérification du code réel) → reflected in Global Constraints and
  Task 3's "read ExportPanel.tsx first" instruction.
- Spec §1 (décision de scope, grain horaire exclu) → Task 2 (`GRAIN_OPTIONS`
  has exactly 5 entries, no `"hour"`).
- Spec §2.1/§2.2 (état, fonctions pures) → Task 1.
- Spec §2.3 (cycle de lecture — idle/playing/paused, boucle, arrêt sur
  édition manuelle, no-op en `interactions="manual"`, annulation au
  démontage) → Task 3, one test per sub-behavior.
- Spec §2.4 (contrôles UI, clés i18n) → Tasks 3-4.
- Spec §3 criteria 1-8, 10-11 → Task 3's tests (playback) and Task 1's
  tests (pure functions) map one-to-one; criterion 2 → Task 5; criterion 9
  → Task 6 Step 1; criterion 12 → Task 6 Step 4.
- Spec §4 (fichiers touchés, exhaustif) → matches this plan's File
  structure section exactly; the "read-only reference" files are never
  modified by any task above.
- Spec §5 (hors périmètre) → no task attempts video export, cross-tab sync,
  arbitrary speed, hour grain, dataset-derived bounds, a stop button,
  persisted playback state, or a second widget — confirmed by inspection of
  Tasks 1-6, none of which touch a second widget file or add a bookmark
  field.

**2. Placeholder scan** — no "TBD"/"handle edge cases"/"similar to Task N"
found; the one intentionally open point (Task 5 Step 1's note about aligning
helper names to the real `AppRenderer.test.tsx` fixtures) is not a
placeholder — it is a deliberate instruction to read an existing file before
finalizing test code, unavoidable since this plan's author has not read
`AppRenderer.test.tsx` in full; Task 5 Steps 2-3 explicitly require running
and fixing before proceeding, so no ambiguity survives past that task.

**3. Type consistency** — `AnimationGrain` (Task 1) is imported unchanged in
Tasks 2 and 3; `props.grain` (Task 2's `defaultProps`/`configSchema`) is the
same field read as `(props.grain ?? "day") as AnimationGrain` in Task 3;
`PlaybackStatus`/`PlaybackSpeed`/`SPEED_INTERVAL_MS` are defined once in
Task 3 and used consistently within that same task (no later task
redeclares them). `addGrain`/`initialWindow`/`stepWindow` signatures match
between Task 1's implementation and Task 3's usage (`stepWindow(current,
bounds, grain)`, `initialWindow(start, grain)`, `addGrain(from, grain, 1)`).
