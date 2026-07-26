## Task 2: `ExplorerMenu` — the shared `⋮` button

**Files:**
- Create: `shell/src/builder/widgets/ExplorerMenu.tsx`
- Test: `shell/src/builder/widgets/ExplorerMenu.test.tsx`

**Interfaces:**
- Consumes (from Task 1): `useExplorerEnabled()`, `useOpenExplorer()`, `useExplorerTarget()` from `../ExplorerContext`.
- Produces (consumed by Task 3): `function ExplorerMenu({ datasetId, dataSourceId }: { datasetId: string | undefined; dataSourceId: string })`. Renders `null` unless `useExplorerEnabled()` is true and `datasetId` is truthy. Renders a button `aria-label="Explorer"` that toggles a one-item menu; the item `aria-label="Voir les entités"` calls `useOpenExplorer()({ datasetId, dataSourceId })` and closes the menu.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/widgets/ExplorerMenu.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { ExplorerMenu } from "./ExplorerMenu";
import { ExplorerProvider, useExplorerTarget } from "../ExplorerContext";

function TargetProbe() {
  const target = useExplorerTarget();
  return <p>target:{target ? `${target.datasetId}/${target.dataSourceId}` : "none"}</p>;
}

test("renders nothing when the explorer is disabled", () => {
  render(
    <ExplorerProvider enabled={false}>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});

test("renders nothing when there is no datasetId", () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId={undefined} dataSourceId="src1" />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});

test("clicking the button then the menu item opens the explorer with the right target", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
      <TargetProbe />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Voir les entités")).not.toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Voir les entités"));
  expect(screen.getByText("target:ds1/src1")).toBeInTheDocument();
});

test("the menu closes again after selecting the item", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
    </ExplorerProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Voir les entités"));
  expect(screen.queryByLabelText("Voir les entités")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/ExplorerMenu.test.tsx`
Expected: FAIL — `Failed to resolve import "./ExplorerMenu"`.

- [ ] **Step 3: Write minimal implementation**

Create `shell/src/builder/widgets/ExplorerMenu.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useExplorerEnabled, useOpenExplorer } from "../ExplorerContext";

export function ExplorerMenu({
  datasetId, dataSourceId,
}: {
  datasetId: string | undefined;
  dataSourceId: string;
}) {
  const enabled = useExplorerEnabled();
  const open = useOpenExplorer();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!enabled || !datasetId) return null;

  return (
    <div className="absolute right-1 top-1 z-10">
      <button
        type="button"
        aria-label="Explorer"
        className="rounded px-1 text-xs text-[var(--gs-color-muted)] hover:bg-[var(--gs-color-surface)]"
        onClick={() => setMenuOpen((v) => !v)}
      >
        ⋮
      </button>
      {menuOpen && (
        <div className="absolute right-0 top-full mt-1 whitespace-nowrap rounded border border-[var(--gs-color-border)] bg-[var(--gs-color-background)] shadow-sm">
          <button
            type="button"
            aria-label="Voir les entités"
            className="block w-full px-2 py-1 text-left text-xs text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
            onClick={() => {
              setMenuOpen(false);
              open({ datasetId, dataSourceId });
            }}
          >
            Voir les entités
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/ExplorerMenu.test.tsx`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/ExplorerMenu.tsx shell/src/builder/widgets/ExplorerMenu.test.tsx
git commit -m "feat(shell): ExplorerMenu — shared ⋮ button, one item Voir les entités (SP-14d)"
```

---

