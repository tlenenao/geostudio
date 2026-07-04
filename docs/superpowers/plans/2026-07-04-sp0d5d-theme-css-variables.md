# GeoStudio SP-0d.5d — Thème (variables CSS) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to invoke this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `AppConfig.theme` actually apply — an app's colors, font, corner radius and spacing render as CSS custom properties on the single `AppRenderer` root (identical in edit/preview/runtime), builtin widgets consume them via Tailwind arbitrary values, and a `ThemePanel` lets the editor set them and persist them.

**Architecture:** `theme.ts` exposes one pure function, `themeToCssVars(theme: Theme): CSSProperties`, that maps a sparse `Theme` (colors/font/radius/space, all optional) onto a fixed set of `--gs-*` CSS custom properties, filling any gap with a documented default. `AppRenderer` applies the result as an inline `style` on its existing root container — since every mode (edit/preview/runtime) renders through that one component, theming is "free" everywhere once wired. Widgets read the tokens the same way any CSS reads a custom property: Tailwind arbitrary-value classes like `bg-[var(--gs-color-primary)]`. A `ThemePanel` (color pickers + selects, mirroring the existing `DataSourcePanel`/`ActionsPanel` panel pattern) edits `AppConfig.theme` in the builder's left rail.

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library + Playwright; Tailwind CSS v4 (arbitrary-value classes, no config file — CSS-first, no change needed there). No new dependency. Backend: **no change** — `builder-service/app/schemas.py:76` already types `theme: dict = Field(default_factory=dict)`, so any shape defined here round-trips as-is.

## Global Constraints

- Additive/back-compatible: `AppConfig.theme` narrows from `Record<string, unknown>` to a precise `Theme` type, but every field is optional, so the existing default `theme: {}` (used by `createConfigItem` and the E2E mocks' `DEFAULT_APP_CONFIG`) remains a valid `Theme` and renders with the documented defaults.
- One rendering engine: theme is applied once, in `AppRenderer`, so edit/preview/runtime are visually identical — no mode-specific theming code anywhere else.
- Front: no new service URL, no new dependency. Existing patterns: pure logic in small builder-local modules (`grid.ts`, `ActionBus.ts`) importing types from `../api/types`; panels are `{value, onChange}`-style components wired from `AppBuilderPage`.
- Tailwind v4 project has no config file (`@import "tailwindcss"` in `shell/src/index.css`) — arbitrary-value classes (`bg-[var(--x)]`) work out of the box, no config edit needed.
- Commits end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`. Run front-end commands from `shell/` (`cd shell && ...`).

**Scope note:** This task wires the theme mechanism and applies it to a representative, visible slice of the chrome — the canvas backdrop, the Bouton widget, and the Texte widget — proving the token flows end-to-end from `ThemePanel` → saved config → runtime-rendered widget. Extending the same `bg-[var(--gs-color-*)]`/`text-[var(--gs-color-*)]` pattern to the remaining builtin widgets (Liste, Table, Indicateur, Carte, Filtre, Graphique) is a mechanical, additive follow-up — each is a one-line className swap with no interface change — and is intentionally left out of this slice to keep it reviewable.

---

### Task 1: `Theme` type + `themeToCssVars` pure function

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Create: `shell/src/builder/theme.ts`
- Test: `shell/src/builder/theme.test.ts`

**Interfaces:**
- Produces:
  - `ThemeColors = { primary?: string; background?: string; surface?: string; text?: string; muted?: string; border?: string }`
  - `Theme = { colors?: ThemeColors; font?: string; radius?: string; space?: string }`
  - `AppConfig.theme: Theme` (was `Record<string, unknown>`)
  - `DEFAULT_THEME_COLORS: Required<ThemeColors>`, `DEFAULT_FONT: string`, `DEFAULT_RADIUS: string`, `DEFAULT_SPACE: string` (exported from `theme.ts`, single source of truth for both the CSS mapping and the `ThemePanel`'s prefill values built in Task 4)
  - `themeToCssVars(theme: Theme): CSSProperties` — maps to CSS custom properties `--gs-color-primary`, `--gs-color-background`, `--gs-color-surface`, `--gs-color-text`, `--gs-color-muted`, `--gs-color-border`, `--gs-font`, `--gs-radius`, `--gs-space`; any field absent in `theme` falls back to the matching default.

- [ ] **Step 1: Add the `Theme`/`ThemeColors` types and retype `AppConfig.theme`**

Edit `shell/src/api/types.ts`. Add near `DataSource`/`ActionMessage` (before `AppConfig`):

```ts
export type ThemeColors = {
  primary?: string;
  background?: string;
  surface?: string;
  text?: string;
  muted?: string;
  border?: string;
};

export type Theme = {
  colors?: ThemeColors;
  font?: string;
  radius?: string;
  space?: string;
};
```

Change `AppConfig.theme` from `theme: Record<string, unknown>;` to `theme: Theme;`.

- [ ] **Step 2: Fix the one call site the retype breaks**

Edit `shell/src/api/itemClient.ts`. Add `Theme` to the type import from `./types` (alongside `ActionMessage`, `AppConfig`, etc.). In `getAppConfig`, the local raw-response shape currently declares `theme?: Record<string, unknown>;` — change it to `theme?: Theme;` (the surrounding line `theme: c.theme ?? {},` is unchanged and now type-checks against `AppConfig.theme: Theme`).

- [ ] **Step 3: Write the failing `themeToCssVars` tests**

Create `shell/src/builder/theme.test.ts`:

```ts
import { expect, test } from "vitest";
import { themeToCssVars, DEFAULT_THEME_COLORS, DEFAULT_FONT, DEFAULT_RADIUS, DEFAULT_SPACE } from "./theme";

test("an empty theme resolves to all documented defaults", () => {
  const vars = themeToCssVars({});
  expect(vars).toMatchObject({
    "--gs-color-primary": DEFAULT_THEME_COLORS.primary,
    "--gs-color-background": DEFAULT_THEME_COLORS.background,
    "--gs-color-surface": DEFAULT_THEME_COLORS.surface,
    "--gs-color-text": DEFAULT_THEME_COLORS.text,
    "--gs-color-muted": DEFAULT_THEME_COLORS.muted,
    "--gs-color-border": DEFAULT_THEME_COLORS.border,
    "--gs-font": DEFAULT_FONT,
    "--gs-radius": DEFAULT_RADIUS,
    "--gs-space": DEFAULT_SPACE,
  });
});

test("a partial theme overrides only the fields it sets", () => {
  const vars = themeToCssVars({ colors: { primary: "#ff0000" }, radius: "1rem" });
  expect(vars).toMatchObject({
    "--gs-color-primary": "#ff0000",
    "--gs-color-background": DEFAULT_THEME_COLORS.background, // untouched
    "--gs-radius": "1rem",
    "--gs-space": DEFAULT_SPACE, // untouched
  });
});

test("a fully specified theme is passed through verbatim", () => {
  const theme = {
    colors: { primary: "#111111", background: "#222222", surface: "#333333", text: "#444444", muted: "#555555", border: "#666666" },
    font: "Georgia, serif",
    radius: "0px",
    space: "1rem",
  };
  expect(themeToCssVars(theme)).toEqual({
    "--gs-color-primary": "#111111",
    "--gs-color-background": "#222222",
    "--gs-color-surface": "#333333",
    "--gs-color-text": "#444444",
    "--gs-color-muted": "#555555",
    "--gs-color-border": "#666666",
    "--gs-font": "Georgia, serif",
    "--gs-radius": "0px",
    "--gs-space": "1rem",
  });
});
```

- [ ] **Step 4: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/theme.test.ts`
Expected: FAIL — module `./theme` does not exist.

- [ ] **Step 5: Implement `theme.ts`**

Create `shell/src/builder/theme.ts`:

```ts
import type { CSSProperties } from "react";
import type { Theme, ThemeColors } from "../api/types";

export const DEFAULT_THEME_COLORS: Required<ThemeColors> = {
  primary: "#2563eb",
  background: "#ffffff",
  surface: "#f8fafc",
  text: "#0f172a",
  muted: "#64748b",
  border: "#e2e8f0",
};
export const DEFAULT_FONT = "system-ui, sans-serif";
export const DEFAULT_RADIUS = "0.375rem";
export const DEFAULT_SPACE = "0.5rem";

// Maps a sparse Theme onto the fixed set of --gs-* custom properties the
// renderer applies on its root container, filling any absent field with its
// documented default so widgets can always resolve every variable.
export function themeToCssVars(theme: Theme): CSSProperties {
  const colors = { ...DEFAULT_THEME_COLORS, ...theme.colors };
  return {
    "--gs-color-primary": colors.primary,
    "--gs-color-background": colors.background,
    "--gs-color-surface": colors.surface,
    "--gs-color-text": colors.text,
    "--gs-color-muted": colors.muted,
    "--gs-color-border": colors.border,
    "--gs-font": theme.font ?? DEFAULT_FONT,
    "--gs-radius": theme.radius ?? DEFAULT_RADIUS,
    "--gs-space": theme.space ?? DEFAULT_SPACE,
  } as CSSProperties;
}
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/theme.test.ts`
Expected: PASS (3/3).

- [ ] **Step 7: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds (the `AppConfig.theme` retype only touched `itemClient.ts`'s `getAppConfig`, already fixed in Step 2).

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/builder/theme.ts shell/src/builder/theme.test.ts
git commit -m "feat(shell): Theme type + themeToCssVars pure mapping to --gs-* variables

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Apply the theme on `AppRenderer`'s root

**Files:**
- Modify: `shell/src/builder/AppRenderer.tsx`
- Test: `shell/src/builder/AppRenderer.test.tsx` (extend)

**Interfaces:**
- Consumes: `themeToCssVars` (Task 1).
- Produces: `AppRenderer`'s existing root `<div ref={containerRef}>` (already present for the breakpoint `ResizeObserver`) gains `style={themeToCssVars(config.theme)}`. No prop/signature change to `AppRenderer` itself.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/AppRenderer.test.tsx` (the file already imports `render`, `screen`, `AppConfig`, `Wrapper`, `config`; add nothing new):

```tsx
test("applies theme CSS variables on the root container, falling back to defaults", () => {
  const cfg: AppConfig = { ...config, theme: { colors: { primary: "#ff0000" } } };
  const { container } = render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  const root = container.firstChild as HTMLElement;
  expect(root.style.getPropertyValue("--gs-color-primary")).toBe("#ff0000");
  expect(root.style.getPropertyValue("--gs-color-background")).toBe("#ffffff"); // default, untouched
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: FAIL — root container has no `--gs-*` inline styles yet.

- [ ] **Step 3: Apply the theme in `AppRenderer`**

Edit `shell/src/builder/AppRenderer.tsx`. Add the import:

```tsx
import { themeToCssVars } from "./theme";
```

Change the root container's opening tag from:

```tsx
    <div ref={containerRef} className="h-full w-full">
```

to:

```tsx
    <div ref={containerRef} className="h-full w-full" style={themeToCssVars(config.theme)}>
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: PASS. (Existing `AppRenderer` tests use `theme: {}` in their fixture — `themeToCssVars({})` returns only the documented defaults, so nothing about their rendering changes.)

- [ ] **Step 5: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/AppRenderer.tsx shell/src/builder/AppRenderer.test.tsx
git commit -m "feat(shell): apply theme CSS variables on the AppRenderer root (edit/preview/runtime)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Consume the theme tokens — canvas backdrop, Bouton, Texte

**Files:**
- Modify: `shell/src/builder/GridCanvas.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`
- Test: `shell/src/builder/GridCanvas.test.tsx` (extend), `shell/src/builder/widgets/button.test.tsx` (extend), `shell/src/builder/widgets/text.test.tsx` (extend)

**Interfaces:**
- Consumes: the `--gs-*` custom properties applied by Task 2 (any ancestor sets them; the widgets below only reference them via Tailwind arbitrary-value classes, no new props).
- Produces: `GridCanvas`'s grid container uses `bg-[var(--gs-color-surface)]` instead of `bg-slate-50`; the Bouton widget's button uses `bg-[var(--gs-color-primary)]` and `rounded-[var(--gs-radius)]` instead of `bg-slate-800`/`rounded-md`; the Texte widget's paragraph gains `text-[var(--gs-color-text)]`.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/GridCanvas.test.tsx`:

```tsx
test("the canvas backdrop uses the surface theme token", () => {
  const { container } = renderCanvas();
  expect(container.firstChild).toHaveClass("bg-[var(--gs-color-surface)]");
});
```

Append to `shell/src/builder/widgets/button.test.tsx`:

```tsx
test("button uses the primary color and radius theme tokens", () => {
  const Button = getWidget("button")!.Component;
  render(<Button props={{ label: "Go" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByRole("button", { name: "Go" })).toHaveClass(
    "bg-[var(--gs-color-primary)]",
    "rounded-[var(--gs-radius)]",
  );
});
```

Append to `shell/src/builder/widgets/text.test.tsx`:

```tsx
test("text uses the text color theme token", () => {
  const Text = getWidget("text")!.Component;
  render(<Text props={{ text: "Salut" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("Salut")).toHaveClass("text-[var(--gs-color-text)]");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx src/builder/widgets/button.test.tsx src/builder/widgets/text.test.tsx`
Expected: FAIL — none of the three elements carry the new classes yet.

- [ ] **Step 3: Swap the canvas backdrop class**

Edit `shell/src/builder/GridCanvas.tsx`. Change:

```tsx
      className="grid h-full w-full gap-1 bg-slate-50"
```

to:

```tsx
      className="grid h-full w-full gap-1 bg-[var(--gs-color-surface)]"
```

- [ ] **Step 4: Swap the Bouton widget's classes**

Edit `shell/src/builder/widgets/index.tsx`. In the `button` widget's `Component`, change:

```tsx
        className="rounded-md bg-slate-800 px-3 py-1.5 text-sm text-white"
```

to:

```tsx
        className="rounded-[var(--gs-radius)] bg-[var(--gs-color-primary)] px-3 py-1.5 text-sm text-white"
```

- [ ] **Step 5: Add the text-color class to the Texte widget**

Edit `shell/src/builder/widgets/index.tsx`. In the `text` widget's `Component`, change:

```tsx
      return <p className="whitespace-pre-wrap">{text}</p>;
```

to:

```tsx
      return <p className="whitespace-pre-wrap text-[var(--gs-color-text)]">{text}</p>;
```

- [ ] **Step 6: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx src/builder/widgets/button.test.tsx src/builder/widgets/text.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/GridCanvas.tsx shell/src/builder/GridCanvas.test.tsx shell/src/builder/widgets/index.tsx shell/src/builder/widgets/button.test.tsx shell/src/builder/widgets/text.test.tsx
git commit -m "feat(shell): canvas/Bouton/Texte consume theme tokens via Tailwind arbitrary values

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `ThemePanel` + integrate into `AppBuilderPage`

**Files:**
- Create: `shell/src/builder/ThemePanel.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/builder/ThemePanel.test.tsx`, `shell/src/pages/AppBuilderPage.test.tsx` (extend)

**Interfaces:**
- Consumes: `Theme`/`ThemeColors` (Task 1), `DEFAULT_THEME_COLORS`/`DEFAULT_FONT`/`DEFAULT_RADIUS`/`DEFAULT_SPACE` (Task 1, for prefill values).
- Produces: `ThemePanel({ theme: Theme, onChange: (theme: Theme) => void })` — six `<input type="color">` color pickers (aria-labels below) plus three `<select>`s for font/radius/space; `AppBuilderPage` renders it in the left rail below `ActionsPanel` and persists `draft.theme` on save.

- [ ] **Step 1: Write the failing `ThemePanel` tests**

Create `shell/src/builder/ThemePanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { Theme } from "../api/types";
import { ThemePanel } from "./ThemePanel";
import { DEFAULT_THEME_COLORS, DEFAULT_FONT, DEFAULT_RADIUS, DEFAULT_SPACE } from "./theme";

test("prefills every control from theme defaults when the theme is empty", () => {
  render(<ThemePanel theme={{}} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Couleur primaire")).toHaveValue(DEFAULT_THEME_COLORS.primary);
  expect(screen.getByLabelText("Couleur de fond")).toHaveValue(DEFAULT_THEME_COLORS.background);
  expect(screen.getByLabelText("Couleur de surface")).toHaveValue(DEFAULT_THEME_COLORS.surface);
  expect(screen.getByLabelText("Couleur du texte")).toHaveValue(DEFAULT_THEME_COLORS.text);
  expect(screen.getByLabelText("Couleur atténuée")).toHaveValue(DEFAULT_THEME_COLORS.muted);
  expect(screen.getByLabelText("Couleur de bordure")).toHaveValue(DEFAULT_THEME_COLORS.border);
  expect(screen.getByLabelText("Police")).toHaveValue(DEFAULT_FONT);
  expect(screen.getByLabelText("Arrondi")).toHaveValue(DEFAULT_RADIUS);
  expect(screen.getByLabelText("Espacement")).toHaveValue(DEFAULT_SPACE);
});

test("changing the primary color emits an updated theme, other fields untouched", async () => {
  const onChange = vi.fn();
  const theme: Theme = { colors: { primary: "#2563eb" }, radius: "1rem" };
  render(<ThemePanel theme={theme} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Couleur primaire"));
  // jsdom's <input type="color"> doesn't support user-event typing directly;
  // fire the change event with fireEvent instead.
  const { fireEvent } = await import("@testing-library/react");
  fireEvent.change(screen.getByLabelText("Couleur primaire"), { target: { value: "#ff0000" } });
  expect(onChange).toHaveBeenCalledWith({ colors: { primary: "#ff0000" }, radius: "1rem" });
});

test("changing the radius select emits an updated theme", async () => {
  const onChange = vi.fn();
  render(<ThemePanel theme={{}} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Arrondi"), "1rem");
  expect(onChange).toHaveBeenCalledWith({ radius: "1rem" });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/ThemePanel.test.tsx`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `ThemePanel`**

Create `shell/src/builder/ThemePanel.tsx`:

```tsx
import type { Theme } from "../api/types";
import { DEFAULT_THEME_COLORS, DEFAULT_FONT, DEFAULT_RADIUS, DEFAULT_SPACE } from "./theme";

const FONTS: [string, string][] = [
  ["system-ui, sans-serif", "Système"],
  ["Georgia, serif", "Serif"],
  ["\"Courier New\", monospace", "Monospace"],
];
const RADII: [string, string][] = [
  ["0px", "Carré"],
  ["0.25rem", "Léger"],
  ["0.375rem", "Standard"],
  ["0.75rem", "Arrondi"],
  ["1rem", "Très arrondi"],
];
const SPACES: [string, string][] = [
  ["0.25rem", "Compact"],
  ["0.5rem", "Standard"],
  ["1rem", "Aéré"],
];

const COLOR_FIELDS: [keyof NonNullable<Theme["colors"]>, string][] = [
  ["primary", "Couleur primaire"],
  ["background", "Couleur de fond"],
  ["surface", "Couleur de surface"],
  ["text", "Couleur du texte"],
  ["muted", "Couleur atténuée"],
  ["border", "Couleur de bordure"],
];

export function ThemePanel({
  theme,
  onChange,
}: {
  theme: Theme;
  onChange: (theme: Theme) => void;
}) {
  function setColor(key: keyof NonNullable<Theme["colors"]>, value: string) {
    onChange({ ...theme, colors: { ...theme.colors, [key]: value } });
  }
  return (
    <div className="flex flex-col gap-2 text-sm">
      {COLOR_FIELDS.map(([key, label]) => (
        <label key={key} className="flex items-center justify-between gap-2">
          {label}
          <input
            type="color"
            aria-label={label}
            value={theme.colors?.[key] ?? DEFAULT_THEME_COLORS[key]}
            onChange={(e) => setColor(key, e.target.value)}
          />
        </label>
      ))}
      <label className="flex flex-col gap-1">
        Police
        <select
          aria-label="Police"
          className="h-9 rounded-md border border-slate-300 px-2"
          value={theme.font ?? DEFAULT_FONT}
          onChange={(e) => onChange({ ...theme, font: e.target.value })}
        >
          {FONTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        Arrondi
        <select
          aria-label="Arrondi"
          className="h-9 rounded-md border border-slate-300 px-2"
          value={theme.radius ?? DEFAULT_RADIUS}
          onChange={(e) => onChange({ ...theme, radius: e.target.value })}
        >
          {RADII.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        Espacement
        <select
          aria-label="Espacement"
          className="h-9 rounded-md border border-slate-300 px-2"
          value={theme.space ?? DEFAULT_SPACE}
          onChange={(e) => onChange({ ...theme, space: e.target.value })}
        >
          {SPACES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/ThemePanel.test.tsx`
Expected: PASS (3/3).

- [ ] **Step 5: Integrate into `AppBuilderPage`**

Edit `shell/src/pages/AppBuilderPage.tsx`. Add the import:

```tsx
import { ThemePanel } from "../builder/ThemePanel";
```

Add a `setTheme` helper next to `setSources`/`setMessages`:

```tsx
  const setTheme = (theme: typeof draft.theme) =>
    setDraft((d) => (d ? { ...d, theme } : d));
```

In the left rail (inside the `mode === "edit"` `<aside>`, after the `ActionsPanel` block), add:

```tsx
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Thème</p>
            <ThemePanel theme={draft.theme} onChange={setTheme} />
```

- [ ] **Step 6: Extend the `AppBuilderPage` test**

Append to `shell/src/pages/AppBuilderPage.test.tsx` (reuses the existing `renderPage`, `config`, `userEvent`, `waitFor`, `screen`):

```tsx
test("edits the theme's primary color and persists it", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(config),
    saveAppConfig,
    featuresUrl: vi.fn().mockReturnValue(""),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });
  await screen.findByLabelText("Couleur primaire");
  const { fireEvent } = await import("@testing-library/react");
  fireEvent.change(screen.getByLabelText("Couleur primaire"), { target: { value: "#ff0000" } });
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1];
  expect(saved.theme.colors.primary).toBe("#ff0000");
});
```

- [ ] **Step 7: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/ThemePanel.test.tsx src/pages/AppBuilderPage.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/ThemePanel.tsx shell/src/builder/ThemePanel.test.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): add ThemePanel and wire it into the app builder

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: E2E — set a theme color in the editor, see it applied in the runtime

**Files:**
- Create: `shell/e2e/theme.spec.ts`

**Interfaces:**
- Consumes: the stateful by-item mock store + `mockGeoNode` (existing), the `ThemePanel` (`aria-label="Couleur primaire"`), the Bouton widget's theme-driven class from Task 3.
- Produces: an E2E that creates an app, adds a Bouton widget, sets the theme's primary color, saves, opens the runtime, and asserts the Bouton's real computed background color is the one that was set (proving the CSS variable actually resolves in a real browser, not just that the class string is present).

- [ ] **Step 1: Write the E2E**

Create `shell/e2e/theme.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("setting a theme color in the editor applies it in the runtime", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App thème");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a Bouton widget (its background is driven by --gs-color-primary).
  await page.getByRole("button", { name: "Bouton" }).click();

  // Set the theme's primary color to a distinctive value.
  await page.getByLabel("Couleur primaire").fill("#ff0000");

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: the button's real computed background reflects the theme.
  await page.goto("/apps/9");
  const button = page.getByRole("button", { name: "Bouton" });
  await expect(button).toBeVisible();
  const bg = await button.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).toBe("rgb(255, 0, 0)");
});
```

- [ ] **Step 2: Run the new E2E**

Run: `cd shell && npx playwright test theme`
Expected: PASS — the runtime button's computed background is `rgb(255, 0, 0)`.

- [ ] **Step 3: Run the full E2E suite**

Run: `cd shell && npx playwright test`
Expected: all specs pass (catalog + map-editor + app-builder + data-widget + actions + chart + responsive + theme).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/theme.spec.ts
git commit -m "test(shell): E2E theme color set in the editor applies in the runtime

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (design 0d.5 §5d « Thème (variables CSS) »):** `theme` typed + `themeToCssVars` mapping to `--gs-*` custom properties, with documented defaults → Task 1. Applied once on the single `AppRenderer` root so edit/preview/runtime are identical → Task 2. Builtin widgets consuming tokens via Tailwind arbitrary values (`bg-[var(--gs-color-primary)]`, `text-[var(--gs-color-text)]`) → Task 3 (canvas backdrop, Bouton, Texte — representative slice, remaining widgets documented as an additive follow-up in the Scope note). `ThemePanel` (color pickers + selects) editing `theme`, wired into the builder → Task 4. End-to-end proof (editor → save → runtime, real computed style) → Task 5.
- **Placeholder scan:** none — every step carries complete code or an exact edit against a quoted anchor.
- **Type consistency:** `Theme`/`ThemeColors` defined once in `api/types.ts`, consumed identically by `theme.ts` (`themeToCssVars`, defaults), `AppRenderer` (`config.theme`), `ThemePanel` (`theme`/`onChange`), and `AppBuilderPage` (`draft.theme`/`setTheme`). `DEFAULT_THEME_COLORS`/`DEFAULT_FONT`/`DEFAULT_RADIUS`/`DEFAULT_SPACE` are the single source of truth reused by both `themeToCssVars` (Task 1/2) and `ThemePanel`'s prefill (Task 4) — no duplicated default values to drift apart. The nine `--gs-*` variable names are identical across `theme.ts`, the `AppRenderer`/`GridCanvas` tests, and the widget classNames in Task 3.
- **Backward compatibility:** `AppConfig.theme` narrows from `Record<string, unknown>` to `Theme`, but every field is optional, so the existing default payload `theme: {}` (in `createConfigItem` and the E2E mocks' `DEFAULT_APP_CONFIG`) is still a valid `Theme` and resolves to the documented defaults — visually near-identical to the previous hardcoded Tailwind colors (`slate-50`/`slate-800`/near-black text), so no existing test asserting rendered content (not classNames) breaks. The one call site the retype affects (`itemClient.ts`'s `getAppConfig` raw shape) is fixed in Task 1 Step 2.
- **Façade discipline:** no network access added; theme is a pure client-side rendering concern flowing through the existing `getAppConfig`/`saveAppConfig` façade methods unchanged.
- **Engine unity:** the CSS variables are set once on `AppRenderer`'s root (present in edit, preview, and runtime alike, per Task 2), so no mode ever needs its own theming logic.
- **Backend:** confirmed no change needed — `builder-service/app/schemas.py:76` already types `BuilderConfig.theme: dict = Field(default_factory=dict)`, an unconstrained dict that accepts and round-trips the `Theme` shape as-is.
