### Task 14: "Autoporté" button on `AppExportPanel`

**Files:**
- Modify: `shell/src/builder/appexport/AppExportPanel.tsx`
- Modify: `shell/src/builder/appexport/AppExportPanel.test.tsx`

**Interfaces:**
- Produces: same public component signature — a third dialog button next to
  Statique/Connecté. Reuses the `pendingWarningMode: AppExportMode | null`
  mechanism SP-18b already fixed (Task 8 of the SP-18b plan) — no new bug
  class here, `pendingWarningMode` was already generalized past a single
  hardcoded mode.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/appexport/AppExportPanel.test.tsx`:

```tsx


  it("triggers a standalone export and shows a download link once done", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /autoport/i }));
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument());
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "standalone");
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: FAIL — no "Autoporté" button exists yet.

- [ ] **Step 3: Add the button in `AppExportPanel.tsx`**

In `shell/src/builder/appexport/AppExportPanel.tsx`, replace the dialog's
button row:

```tsx
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={() => onChooseMode("static")}>
            Statique
          </Button>
          <Button type="button" size="sm" onClick={() => onChooseMode("connected")}>
            Connecté
          </Button>
        </div>
```

with:

```tsx
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={() => onChooseMode("static")}>
            Statique
          </Button>
          <Button type="button" size="sm" onClick={() => onChooseMode("connected")}>
            Connecté
          </Button>
          <Button type="button" size="sm" onClick={() => onChooseMode("standalone")}>
            Autoporté
          </Button>
        </div>
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the shell's full check suite**

Run: `cd shell && npm run test && npx tsc --noEmit`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/appexport/AppExportPanel.tsx shell/src/builder/appexport/AppExportPanel.test.tsx
git commit -m "feat(shell): AppExportPanel gains an Autoporté button (SP-18c)"
```

---

## Self-review notes

- **Spec coverage:** design §3.1 (snapshot production, CDC-compatible
  layout) → Task 4. §3.2 (mini-server, same CORS-enumerated path allowlist,
  serves the shell bundle from the same origin) → Tasks 5/6. §3.3 (guard:
  connected-style `is_public` leniency + static-style widget allowlist) →
  Task 1. §3.4 (ghcr.io distribution, `:latest`, documented unverified-pull
  gap, E2E builds locally) → Tasks 10/11/12 + Global Constraints. §3.5
  (artifact shape: data/ + generated compose + README) → Task 7. §4 (no
  writes, no auto-refresh, no third-party widgets) → enforced by Task 1's
  guard and the mini-server never exposing a write route (Task 6). §5 (real
  E2E, cold container, no Postgres/Keycloak/MinIO in the generated compose)
  → Task 12.
- **Placeholder scan:** none found — every step has complete, runnable code
  or an exact command with an expected result.
- **Type consistency:** `CollectionSnapshotEntry` defined once in Task 3's
  `manifest.py`, constructed identically in Task 4 (`snapshot.py`) and
  consumed identically in Task 6 (`main.py`, via `read_manifest`) — same
  field names (`id`, `tenant_id`, `collection_json`, `schema_json`,
  `table_info`) throughout. `select_features`/`get_feature`'s
  `(conn, *, base_uri, tenant_id, collection_id, table_info, ...)` signature
  from Task 5 is called identically in Task 6. `build_standalone_bundle_zip(config,
  *, snapshot_dir)` defined in Task 7, called identically in Task 8 and
  Task 12. `AppExportMode` widened in Task 13, used identically in Task 14
  (`onChooseMode("standalone")`) — no shell code elsewhere hardcodes the
  two-mode union (verified against SP-18b's Task 6/8, which already
  generalized `pendingWarningMode` past a single mode).
