## Task 2: `WidgetPalette` gains an `exclude` filter

**Files:**
- Modify: `shell/src/builder/WidgetPalette.tsx`
- Test: `shell/src/builder/WidgetPalette.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `WidgetPalette({ onAdd, exclude? }: { onAdd: (type: string) => void; exclude?: string[] })`.
  Task 4 (`LayoutEditor`) depends on this to keep container kinds out of a
  nested palette.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/WidgetPalette.test.tsx`:

```tsx
test("excludes the given widget types from the list", () => {
  const onAdd = vi.fn();
  render(<WidgetPalette onAdd={onAdd} exclude={["image", "button"]} />);
  expect(screen.getByRole("button", { name: "Texte" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Image" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Bouton" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/WidgetPalette.test.tsx`
Expected: FAIL — `exclude` prop doesn't exist yet, all widgets (including
"Image"/"Bouton") are listed.

- [ ] **Step 3: Implement the filter**

Replace the full contents of `shell/src/builder/WidgetPalette.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { listWidgets } from "./registry";

export function WidgetPalette({
  onAdd,
  exclude = [],
}: {
  onAdd: (type: string) => void;
  exclude?: string[];
}) {
  return (
    <ul className="flex flex-col gap-1">
      {listWidgets()
        .filter((def) => !exclude.includes(def.type))
        .map((def) => (
          <li key={def.type}>
            <button
              type="button"
              className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-left text-sm hover:bg-slate-100"
              onClick={() => onAdd(def.type)}
            >
              {def.label}
            </button>
          </li>
        ))}
    </ul>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/WidgetPalette.test.tsx`
Expected: PASS (all tests, including the pre-existing "lists widgets and
emits the type on click").

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/WidgetPalette.tsx shell/src/builder/WidgetPalette.test.tsx
git commit -m "feat(shell): WidgetPalette gains an exclude filter (SP-14j)"
```

---

