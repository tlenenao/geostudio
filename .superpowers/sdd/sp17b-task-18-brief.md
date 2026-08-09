## Task 18: "Programmer un rapport" entry point on bookmark rows

**Files:**
- Modify: `shell/src/shell/ItemActions.tsx`

**Interfaces:**
- Consumes: `useNavigate` (react-router-dom), `item.resourceType`/`item.pk` (existing `Item` type).
- Produces: one new conditional menu entry, no new exported symbol.

- [ ] **Step 1: Add the menu entry**

In `shell/src/shell/ItemActions.tsx`, add the import:
```tsx
import { useNavigate } from "react-router-dom";
```

Add `const navigate = useNavigate();` at the top of the component body, alongside the existing hooks:
```tsx
export function ItemActions({ item, onDeleted }: { item: Item; onDeleted?: () => void }) {
  const navigate = useNavigate();
  const [panel, setPanel] = useState<Panel>(null);
```

Add the conditional entry in the menu block, right after "Modifier" (before "Publier" — matches the design's "entonnoir contextuel" placement, first action after edit):
```tsx
          <button className="px-3 py-1 text-left hover:bg-slate-100" onClick={() => setPanel("edit")}>
            Modifier
          </button>
          {item.resourceType === "bookmark" && (
            <button
              className="px-3 py-1 text-left hover:bg-slate-100"
              onClick={() => {
                setPanel(null);
                navigate("/reports/new", { state: { bookmarkItemId: item.pk } });
              }}
            >
              Programmer un rapport
            </button>
          )}
```

- [ ] **Step 2: Typecheck**

Run: `cd shell && npm run build`
Expected: passes.

- [ ] **Step 3: Run shell unit tests**

Run: `cd shell && npm run test`
Expected: PASS, no regressions (in particular any existing `ItemActions`/`CatalogPage` tests).

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/shell/ItemActions.tsx
git commit -m "feat(shell): 'Programmer un rapport' entry point on bookmark rows (SP-17b)"
```

---

