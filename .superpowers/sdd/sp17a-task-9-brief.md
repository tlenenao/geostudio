### Task 9: `PrintLayoutPanel` + intégration dans les builders

**Files:**
- Create: `shell/src/builder/print/PrintLayoutPanel.tsx`
- Create: `shell/src/builder/print/PrintLayoutPanel.test.tsx`
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`

**Interfaces:**
- Produces: `PrintLayoutPanel({ value, onChange }: { value: PrintLayoutConfig | null; onChange: (next: PrintLayoutConfig | null) => void })` — mêmes conventions de props que `PipelineScheduleEditor` (Tâche 9 du plan SP-15h).

- [ ] **Step 1: Écrire le test qui échoue**

```typescript
// shell/src/builder/print/PrintLayoutPanel.test.tsx
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PrintLayoutPanel } from "./PrintLayoutPanel";

describe("PrintLayoutPanel", () => {
  it("renders defaults when value is null", () => {
    render(<PrintLayoutPanel value={null} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Format")).toHaveValue("a4");
    expect(screen.getByLabelText("Orientation")).toHaveValue("portrait");
  });

  it("calls onChange with an updated title, preserving other fields", () => {
    // fireEvent.change (une seule valeur complète), pas userEvent.type
    // (frappe caractère par caractère) : le composant est entièrement
    // contrôlé et `onChange` ici est un mock qui ne réinjecte jamais la
    // nouvelle valeur dans `value` — avec userEvent.type, React réafficherait
    // `value=""` entre chaque frappe (le prop ne change jamais), et seul le
    // DERNIER caractère tapé survivrait dans le dernier appel à onChange.
    const onChange = vi.fn();
    render(<PrintLayoutPanel value={{ pageSize: "a3", orientation: "landscape", showLegend: false }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Titre"), { target: { value: "Rapport" } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: "a3", orientation: "landscape", showLegend: false, title: "Rapport" }));
  });

  it("toggles showLegend", async () => {
    const onChange = vi.fn();
    render(<PrintLayoutPanel value={{ showLegend: true }} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText("Légende"));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ showLegend: false }));
  });

  it("changing page size to a3 landscape calls onChange with both fields", async () => {
    const onChange = vi.fn();
    render(<PrintLayoutPanel value={null} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText("Format"), "a3");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: "a3" }));
  });
});
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/builder/print/PrintLayoutPanel.test.tsx`
Expected: FAIL — le module n'existe pas.

- [ ] **Step 3: Implémenter**

```tsx
// shell/src/builder/print/PrintLayoutPanel.tsx
import type { PrintLayoutConfig } from "../../api/types";

const DEFAULTS: Required<Pick<PrintLayoutConfig, "pageSize" | "orientation" | "showLegend" | "showScaleBar" | "showNorthArrow">> = {
  pageSize: "a4", orientation: "portrait", showLegend: true, showScaleBar: true, showNorthArrow: false,
};

export function PrintLayoutPanel({
  value, onChange,
}: {
  value: PrintLayoutConfig | null;
  onChange: (next: PrintLayoutConfig | null) => void;
}) {
  const current = { ...DEFAULTS, ...(value ?? {}) };

  function patch(partial: Partial<PrintLayoutConfig>) {
    onChange({ ...current, ...partial });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Mise en page d'impression</p>
      <label className="flex flex-col gap-1 text-sm">
        Format
        <select
          value={current.pageSize}
          onChange={(e) => patch({ pageSize: e.target.value as PrintLayoutConfig["pageSize"] })}
        >
          <option value="a4">A4</option>
          <option value="a3">A3</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Orientation
        <select
          value={current.orientation}
          onChange={(e) => patch({ orientation: e.target.value as PrintLayoutConfig["orientation"] })}
        >
          <option value="portrait">Portrait</option>
          <option value="landscape">Paysage</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Titre
        <input type="text" value={current.title ?? ""} onChange={(e) => patch({ title: e.target.value || null })} />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={current.showLegend} onChange={(e) => patch({ showLegend: e.target.checked })} />
        Légende
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={current.showScaleBar} onChange={(e) => patch({ showScaleBar: e.target.checked })} />
        Barre d'échelle
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={current.showNorthArrow} onChange={(e) => patch({ showNorthArrow: e.target.checked })} />
        Flèche nord
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Cartouche
        <textarea value={current.cartouche ?? ""} onChange={(e) => patch({ cartouche: e.target.value || null })} />
      </label>
    </div>
  );
}
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/builder/print/PrintLayoutPanel.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Intégrer dans `MapEditorPage.tsx`**

Ajouter l'import et un setter fonctionnel (même patron que `setStyle`/`setLayers` déjà présents), puis monter le panneau dans l'aside, après `LayersPanel` et avant le bouton « Enregistrer » :

```tsx
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
// ...
function setPrintLayout(printLayout: PrintLayoutConfig | null) {
  setDraft((d) => (d ? { ...d, printLayout } : d));
}
// ... dans le JSX de l'aside :
<PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
```

Inspecter la forme exacte de `setStyle`/`setLayers` dans `MapEditorPage.tsx` avant d'écrire `setPrintLayout` pour rester rigoureusement cohérent avec leur patron (spread fonctionnel sur `setDraft`, garde `d ?`).

- [ ] **Step 6: Intégrer dans `AppBuilderPage.tsx`**

Même patron, monté dans l'aside `mode === "edit"`, à la suite de la section Thème :

```tsx
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
// ...
function setPrintLayout(printLayout: PrintLayoutConfig | null) {
  setDraft((d) => (d ? { ...d, printLayout } : d));
}
// ...
<p className="mb-1 mt-3 text-xs font-medium text-slate-500">Impression</p>
<PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
```

- [ ] **Step 7: Test de régression du round-trip complet (map)**

Ajouter à `shell/src/pages/MapEditorPage.test.tsx` (mirroir du style des tests déjà présents dans ce fichier — inspecter avant d'écrire) :

```tsx
it("saving after only changing a layer keeps the previously loaded printLayout", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  const client: Partial<ItemClient> = {
    getMapConfig: vi.fn().mockResolvedValue({
      basemap: { style: "s" }, view: { center: [0, 0], zoom: 1 }, layers: [],
      printLayout: { pageSize: "a3", orientation: "landscape" },
    }),
    saveMapConfig,
  };
  renderMapEditorPage({ client, pk: "pk-1" });
  await screen.findByText(/A3/i); // le panneau reflète bien le printLayout chargé
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const [, savedConfig] = saveMapConfig.mock.calls[0];
  expect(savedConfig.printLayout).toEqual({ pageSize: "a3", orientation: "landscape" });
});
```

Adapter `renderMapEditorPage`/le nom exact du helper de rendu déjà présent dans `MapEditorPage.test.tsx`.

- [ ] **Step 8: Vérifier build + tests shell complets**

Run: `cd shell && npx vitest run src/pages/MapEditorPage.test.tsx src/pages/AppBuilderPage.test.tsx && npm run build`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add shell/src/builder/print/PrintLayoutPanel.tsx shell/src/builder/print/PrintLayoutPanel.test.tsx shell/src/pages/MapEditorPage.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/MapEditorPage.test.tsx
git commit -m "feat(shell): SP-17a — PrintLayoutPanel intégré aux builders carte/app"
```

---

