### Task 4: Route + nav link

**Files:**
- Modify: `shell/src/shell/routes.tsx:1-17,86-98` (import + route)
- Modify: `shell/src/shell/AppLayout.tsx:1-50` (conditional nav link)
- Test: `shell/src/shell/AppLayout.test.tsx`

**Interfaces:**
- Consumes: `SqlLabPage` (Task 3, `shell/src/pages/SqlLabPage.tsx`) ; `meQuery.data?.isAnalyst` (already available via `useMe()`, already used for `isAdmin` at `shell/src/shell/AppLayout.tsx:37`).
- Produces: route `/analytics/sql` reachable in the app ; nav link `<Link to="/analytics/sql">SQL Lab</Link>` rendered only when `isAnalyst === true`. Task 5 (E2E) navigates to this route and asserts on this link.

- [ ] **Step 1: Write the failing tests**

In `shell/src/shell/AppLayout.test.tsx`, append these two tests at the end of the file:

```tsx
test("shows the SQL Lab link only when the current user is an analyst", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false, isAnalyst: true }),
    ),
  );
  renderLayout();
  expect(await screen.findByRole("link", { name: "SQL Lab" })).toBeInTheDocument();
});

test("hides the SQL Lab link for a non-analyst user", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByRole("link", { name: "SQL Lab" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/shell/AppLayout.test.tsx`
Expected: FAIL — the first new test cannot find a "SQL Lab" link (the second new test passes trivially already, but run the file to confirm the first fails before implementing).

- [ ] **Step 3: Add the route**

In `shell/src/shell/routes.tsx`, add the import after the existing `DatasetEditPage` import (line 11):

```tsx
import { DatasetEditPage } from "../pages/DatasetEditPage";
import { SqlLabPage } from "../pages/SqlLabPage";
```

Add the route inside `<Route element={<ProtectedLayout />}>`, after the `/datasets/:pk/edit` route (line 94):

```tsx
        <Route path="/datasets/:pk/edit" element={<DatasetEditRoute />} />
        <Route path="/analytics/sql" element={<SqlLabPage />} />
        <Route path="/admin/extensions" element={<AdminExtensionsPage />} />
```

- [ ] **Step 4: Add the nav link**

In `shell/src/shell/AppLayout.tsx`, the nav block currently reads (lines 33-50):

```tsx
        <nav className="w-48 border-r border-slate-200 p-4">
          <Link to="/" className="text-sm font-medium hover:underline">
            Catalogue
          </Link>
          {meQuery.data?.isAdmin === true && (
            <>
              <Link to="/admin/extensions" className="mt-2 block text-sm font-medium hover:underline">
                Extensions
              </Link>
              <Link to="/admin/collections" className="mt-1 block text-sm font-medium hover:underline">
                Collections
              </Link>
              <Link to="/admin/harvest" className="mt-1 block text-sm font-medium hover:underline">
                Moissonnage
              </Link>
            </>
          )}
        </nav>
```

Change it to add the analyst-only link, independent of the `isAdmin` block:

```tsx
        <nav className="w-48 border-r border-slate-200 p-4">
          <Link to="/" className="text-sm font-medium hover:underline">
            Catalogue
          </Link>
          {meQuery.data?.isAdmin === true && (
            <>
              <Link to="/admin/extensions" className="mt-2 block text-sm font-medium hover:underline">
                Extensions
              </Link>
              <Link to="/admin/collections" className="mt-1 block text-sm font-medium hover:underline">
                Collections
              </Link>
              <Link to="/admin/harvest" className="mt-1 block text-sm font-medium hover:underline">
                Moissonnage
              </Link>
            </>
          )}
          {meQuery.data?.isAnalyst === true && (
            <Link to="/analytics/sql" className="mt-2 block text-sm font-medium hover:underline">
              SQL Lab
            </Link>
          )}
        </nav>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/shell/AppLayout.test.tsx`
Expected: PASS, all tests in the file green.

- [ ] **Step 6: Run the full unit suite to check for regressions**

Run: `cd shell && npm test`
Expected: PASS, all files green (no regression from the additive route/link).

- [ ] **Step 7: Type-check and build**

Run: `cd shell && npm run build`
Expected: no TypeScript errors, build succeeds.

- [ ] **Step 8: Commit**

```bash
cd shell && git add src/shell/routes.tsx src/shell/AppLayout.tsx src/shell/AppLayout.test.tsx
git commit -m "feat(shell): route /analytics/sql et lien nav SQL Lab pour les analystes (SP-14i)"
```

---

