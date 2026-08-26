## Task 7: Shell — `MapSymbologyEditor`

**Files:**
- Create: `shell/src/map/MapSymbologyEditor.tsx`
- Create: `shell/src/map/MapSymbologyEditor.test.tsx`

**Interfaces:**
- Consumes: `LayerSymbology`, `ColorClassification`, `PaletteId`,
  `computeColorDomain`, `computeSizeDomain`, `StatQueryFn`, `SampleFieldFn`
  from `../builder/widgets/mapSymbology`; `CURATED_PALETTES` from
  `../builder/widgets/palette`; `ThemeColors` from `../api/types`.
- Produces: `MapSymbologyEditor` component, mounted by `LayersPanel` (Task
  8) and `mapWidget.tsx`'s `PropsPanel` (Task 10).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/map/MapSymbologyEditor.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { MapSymbologyEditor } from "./MapSymbologyEditor";
import type { LayerSymbology } from "../builder/widgets/mapSymbology";

test("no color field selected: shows the field picker only", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={["population", "region"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Champ couleur")).toBeInTheDocument();
  expect(screen.queryByLabelText("Méthode de classification")).not.toBeInTheDocument();
});

test("theme-primary palette option is absent without a theme", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={[]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByLabelText("Palette") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(false);
});

test("theme-primary palette option is present with a theme", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={[]}
      themeColors={{ primary: "#2563eb" }}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByLabelText("Palette") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(true);
});

test("classification method selector is hidden in categorical mode and shown in numeric mode", async () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <MapSymbologyEditor
      value={{ color: { field: "region", mode: "categorical", palette: "categorical-a", domain: { kind: "categorical", values: [] }, computedAt: "" } }}
      availableFields={["region"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  expect(screen.queryByLabelText("Méthode de classification")).not.toBeInTheDocument();

  rerender(
    <MapSymbologyEditor
      value={{ color: { field: "pop", mode: "numeric", palette: "sequential-blue", domain: { kind: "numeric", min: 0, max: 1 }, computedAt: "" } }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  expect(screen.getByLabelText("Méthode de classification")).toBeInTheDocument();
});

test("class count selector is hidden when the method is continuous", () => {
  render(
    <MapSymbologyEditor
      value={{ color: { field: "pop", mode: "numeric", palette: "sequential-blue", domain: { kind: "numeric", min: 0, max: 1 }, computedAt: "" } }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.queryByLabelText("Nombre de classes")).not.toBeInTheDocument();
});

test("recompute button calls runStatistics and writes domain + computedAt via onChange", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]);
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{ color: { field: "pop", mode: "numeric", palette: "sequential-blue", domain: { kind: "numeric", min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));

  expect(runStatistics).toHaveBeenCalled();
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      color: expect.objectContaining({
        domain: { kind: "numeric", min: 0, max: 100 },
        computedAt: expect.any(String),
      }),
    }),
  );
});

test("recompute button for the size field calls runStatistics and writes size domain", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 1, max: 9 } }]);
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{ size: { field: "montant", domain: { min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["montant"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Recalculer la taille" }));

  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      size: expect.objectContaining({ domain: { min: 1, max: 9 }, computedAt: expect.any(String) }),
    }),
  );
});

test("computed breaks are shown as text", () => {
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          classification: { method: "quantile", classes: 2 },
          palette: "sequential-blue",
          domain: { kind: "numeric-classed", breaks: [0, 50, 100] },
          computedAt: "2026-08-23T10:00:00Z",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByText(/0.*50.*100/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `shell/src/map/MapSymbologyEditor.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import {
  computeColorDomain,
  computeSizeDomain,
  type ColorClassification,
  type LayerSymbology,
  type SampleFieldFn,
  type StatQueryFn,
} from "../builder/widgets/mapSymbology";
import type { PaletteId } from "../builder/widgets/palette";
import type { ThemeColors } from "../api/types";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-8 rounded-md border border-slate-300 px-2 text-sm";

const PALETTE_OPTIONS: { id: Exclude<PaletteId, "theme-primary">; label: string }[] = [
  { id: "categorical-a", label: "Catégorielle A" },
  { id: "categorical-b", label: "Catégorielle B" },
  { id: "sequential-blue", label: "Séquentielle bleue" },
  { id: "sequential-warm", label: "Séquentielle chaude" },
];

function formatDomain(domain: LayerSymbology["color"] extends infer C
  ? C extends { domain: infer D }
    ? D
    : never
  : never): string {
  if (domain.kind === "categorical") return domain.values.join(", ");
  if (domain.kind === "numeric-classed") return domain.breaks.map((b) => b.toFixed(1)).join(" – ");
  return `${domain.min} – ${domain.max}`;
}

// Éditeur partagé par les DEUX surfaces (éditeur de cartes et PropsPanel du
// widget carte) — même précédent que PopupEditor.tsx (SP-24). Les deux
// hôtes ne diffèrent que par comment `runStatistics`/`sampleField`
// résolvent (collectionId direct vs datasetId), jamais par l'UI elle-même.
export function MapSymbologyEditor({
  value,
  availableFields,
  themeColors,
  runStatistics,
  sampleField,
  onChange,
}: {
  value: LayerSymbology | undefined;
  availableFields: string[];
  themeColors: ThemeColors | undefined;
  runStatistics: StatQueryFn;
  sampleField: SampleFieldFn;
  onChange: (value: LayerSymbology | undefined) => void;
}) {
  const [busy, setBusy] = useState<"color" | "size" | null>(null);
  const color = value?.color;
  const size = value?.size;

  function setColorField(patch: Partial<NonNullable<LayerSymbology["color"]>>) {
    onChange({
      ...value,
      color: {
        field: color?.field ?? "",
        mode: color?.mode ?? "categorical",
        classification: color?.classification,
        palette: color?.palette ?? "categorical-a",
        domain: color?.domain ?? { kind: "categorical", values: [] },
        computedAt: color?.computedAt ?? "",
        ...patch,
      },
    });
  }

  async function recomputeColor() {
    if (!color?.field) return;
    setBusy("color");
    try {
      const domain = await computeColorDomain(
        { field: color.field, mode: color.mode, classification: color.classification },
        { runStatistics, sampleField },
      );
      onChange({ ...value, color: { ...color, domain, computedAt: new Date().toISOString() } });
    } finally {
      setBusy(null);
    }
  }

  async function recomputeSize() {
    if (!size?.field) return;
    setBusy("size");
    try {
      const domain = await computeSizeDomain(size.field, { runStatistics });
      onChange({ ...value, size: { ...size, domain, computedAt: new Date().toISOString() } });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <label className={labelCls}>
        Champ couleur
        <input
          aria-label="Champ couleur"
          list="map-symbology-fields"
          className={inputCls}
          value={color?.field ?? ""}
          onChange={(e) => setColorField({ field: e.target.value })}
        />
      </label>
      <datalist id="map-symbology-fields">
        {availableFields.map((f) => (
          <option key={f} value={f} />
        ))}
      </datalist>
      {color?.field && (
        <>
          <label className={labelCls}>
            Type de couleur
            <select
              aria-label="Type de couleur"
              className={inputCls}
              value={color.mode}
              onChange={(e) =>
                setColorField({
                  mode: e.target.value as "categorical" | "numeric",
                  classification: e.target.value === "categorical" ? undefined : color.classification,
                })
              }
            >
              <option value="categorical">Catégoriel</option>
              <option value="numeric">Numérique</option>
            </select>
          </label>
          {color.mode === "numeric" && (
            <>
              <label className={labelCls}>
                Méthode de classification
                <select
                  aria-label="Méthode de classification"
                  className={inputCls}
                  value={color.classification?.method ?? "continuous"}
                  onChange={(e) => {
                    const v = e.target.value;
                    setColorField({
                      classification:
                        v === "continuous"
                          ? undefined
                          : ({ method: v, classes: color.classification?.classes ?? 5 } as ColorClassification),
                    });
                  }}
                >
                  <option value="continuous">Continu (dégradé)</option>
                  <option value="quantile">Quantiles</option>
                  <option value="equalInterval">Intervalles égaux</option>
                  <option value="jenks">Seuils naturels (Jenks)</option>
                </select>
              </label>
              {color.classification && (
                <label className={labelCls}>
                  Nombre de classes
                  <input
                    aria-label="Nombre de classes"
                    type="number"
                    min={2}
                    max={9}
                    className={inputCls}
                    value={color.classification.classes}
                    onChange={(e) =>
                      setColorField({
                        classification: {
                          ...color.classification!,
                          classes: Math.min(9, Math.max(2, Number(e.target.value) || 2)),
                        },
                      })
                    }
                  />
                </label>
              )}
            </>
          )}
          <label className={labelCls}>
            Palette
            <select
              aria-label="Palette"
              className={inputCls}
              value={color.palette}
              onChange={(e) => setColorField({ palette: e.target.value as PaletteId })}
            >
              {PALETTE_OPTIONS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
              {themeColors?.primary && <option value="theme-primary">Thème du site</option>}
            </select>
          </label>
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={busy === "color"}
            onClick={() => void recomputeColor()}
          >
            {busy === "color" ? "Calcul…" : "Recalculer les classes"}
          </button>
          {color.computedAt && (
            <p className="text-xs text-slate-500">
              Classes calculées le {new Date(color.computedAt).toLocaleString()} : {formatDomain(color.domain)}
            </p>
          )}
        </>
      )}
      <label className={labelCls}>
        Champ taille
        <input
          aria-label="Champ taille"
          list="map-symbology-fields"
          className={inputCls}
          value={size?.field ?? ""}
          onChange={(e) =>
            onChange({
              ...value,
              size: { field: e.target.value, domain: size?.domain ?? { min: 0, max: 0 }, computedAt: size?.computedAt ?? "" },
            })
          }
        />
      </label>
      {size?.field && (
        <>
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={busy === "size"}
            onClick={() => void recomputeSize()}
          >
            {busy === "size" ? "Calcul…" : "Recalculer la taille"}
          </button>
          {size.computedAt && (
            <p className="text-xs text-slate-500">
              Taille calculée le {new Date(size.computedAt).toLocaleString()} : {size.domain.min} – {size.domain.max}
            </p>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: PASS. If the `formatDomain` conditional type is rejected by
`tsc`, replace it with a concrete union type
(`ColorDomain` imported from `mapSymbology.ts`) instead of the derived
`infer` gymnastics shown above — that inline type was written for
readability of intent in this plan, not guaranteed to compile verbatim;
prefer `import type { ColorDomain } from "../builder/widgets/mapSymbology";
function formatDomain(domain: ColorDomain): string { ... }`.

- [ ] **Step 5: Full shell gates**

Run: `cd shell && npm run lint && npm run format:check && npx vitest run && npm run build`
Expected: green, count ≥ previous + 9.

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): éditeur de symbologie partagé (MapSymbologyEditor)

Monté ensuite sur LayersPanel et le widget carte — même précédent que
PopupEditor.tsx (SP-24).
EOF
)"
```

---

