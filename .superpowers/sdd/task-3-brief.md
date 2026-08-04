## Task 3: `Dialog` gains a `wide` variant

**Files:**
- Modify: `shell/src/ui/dialog.tsx`
- Test: `shell/src/ui/dialog.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Dialog({ open, onClose, title, wide?, children })` — `wide`
  defaults to `false` (unchanged `max-w-md` behavior). Task 6 (`modal`
  widget) depends on this to avoid squeezing a widget grid into a narrow
  dialog.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/ui/dialog.test.tsx`:

```tsx
test("uses a wider max-width when wide is set", () => {
  render(
    <Dialog open onClose={() => {}} title="T" wide>
      <p>body</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-2xl");
});

test("defaults to the standard max-width when wide is omitted", () => {
  render(
    <Dialog open onClose={() => {}} title="T">
      <p>body</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-md");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/ui/dialog.test.tsx`
Expected: FAIL — TypeScript error, `wide` isn't a valid prop yet; both new
assertions fail once that's silenced.

- [ ] **Step 3: Add the `wide` prop**

Replace the full contents of `shell/src/ui/dialog.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";

export function Dialog({
  open,
  onClose,
  title,
  wide = false,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" aria-hidden="true" onClick={onClose} />
      <div
        role="dialog"
        aria-label={title}
        className={`relative z-10 w-full rounded-lg bg-white p-6 shadow-lg ${wide ? "max-w-2xl" : "max-w-md"}`}
      >
        <h2 className="mb-4 text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/ui/dialog.test.tsx`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/ui/dialog.tsx shell/src/ui/dialog.test.tsx
git commit -m "feat(shell): Dialog gains an optional wide variant (SP-14j)"
```

---

