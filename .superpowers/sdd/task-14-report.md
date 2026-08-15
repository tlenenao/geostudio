# Task 14 Report: "Autoporté" button on `AppExportPanel`

Date: 2026-08-15
Repo: /home/lenen/projets/geostudio (branch: dev)
Commit: `1a27847`

## What was implemented

Added the third export mode button ("Autoporté") to the `AppExportPanel` component, completing SP-18c Task 14 (final task of 14 in the SP-18c plan).

### Changes made

**File 1: `shell/src/builder/appexport/AppExportPanel.tsx`**

Added a third button to the mode-selection dialog (lines 97-99):
```tsx
<Button type="button" size="sm" onClick={() => onChooseMode("standalone")}>
  Autoporté
</Button>
```

The button:
- Appears in the "Choisir le mode d'export" dialog alongside "Statique" and "Connecté"
- Calls `onChooseMode("standalone")` (reuses existing mechanism)
- Integrates with the existing `pendingWarningMode` guard (form-widget warning) via the already-generalized mechanism from SP-18b Task 8

**File 2: `shell/src/builder/appexport/AppExportPanel.test.tsx`**

Added test at lines 87-103:
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

Verifies:
- Button is rendered and clickable (regex `/autoport/i` matches "Autoporté")
- Clicking triggers `createAppExport` with mode `"standalone"`
- Download link appears once job completes
- All with zero form-widget warnings (config has no form widgets)

## Test results

### Initial run (before implementation)
```
❯ src/builder/appexport/AppExportPanel.test.tsx (5 tests | 1 failed)
  ✓ AppExportPanel > triggers export and shows a download link once done
  ✓ AppExportPanel > warns before export when the config contains a form widget
  ✓ AppExportPanel > triggers a connected export and shows a download link once done
  ✓ AppExportPanel > confirms the write warning with the mode that actually triggered it
  × AppExportPanel > triggers a standalone export and shows a download link once done
    → Unable to find an accessible element with the role "button" and name `/autoport/i`
```

**Result:** Test failed as expected — button did not exist yet.

### After implementation
```
✓ src/builder/appexport/AppExportPanel.test.tsx (5 tests) 292ms

 Test Files  1 passed (1)
      Tests  5 passed (5)
   Start at  20:33:08
   Duration  1.63s
```

**Result:** All 5 tests pass (1 new + 4 pre-existing).

### Full shell test suite
```
 Test Files  144 passed (144)
      Tests  1188 passed (1188)
   Start at  20:33:24
   Duration  46.61s
```

**Result:** 1188 tests pass, 0 failed. No regressions.

### TypeScript type check
```
npx tsc --noEmit
(Bash completed with no output)
```

**Result:** 0 TypeScript errors.

## Deviations from the brief

None. Implementation follows the brief exactly:
- Test code copied verbatim from Step 1 code block
- Button code copied verbatim from Step 3 code block
- Commit message exact match from Step 6
- All steps executed in order (TDD discipline)

## Self-review notes

**Design & correctness:**
- Button reuses the existing `onChooseMode()` function with mode `"standalone"`
- The `"standalone"` mode is already defined in `AppExportMode` union type (from SP-18 infrastructure)
- No duplication of control flow — form-widget warnings handled via existing generalized `pendingWarningMode` mechanism
- Button position (third, after "Connecté") follows dialog convention

**Type safety:**
- No TypeScript errors introduced
- Mode type matches expected API
- Test mocks align with component's actual `ItemClient` interface

**Test coverage:**
- New test covers the happy path (dialog open → click button → poll → download appears)
- Pre-existing tests (4) all pass unchanged, confirming the button integrates seamlessly
- Test assertions are specific (mode must be `"standalone"`, not just any truthy mode)

**Minimal diff:**
- 3 lines added to component (the button)
- 16 lines added to test (new test function)
- 0 lines removed or modified in existing logic
- 0 breaking changes

**No regressions:**
- Full shell test suite: 1188/1188 passing
- No TypeScript errors
- All 4 pre-existing AppExportPanel tests still pass

## Summary

**Status: COMPLETE**

The "Autoporté" button is now present in the `AppExportPanel` export-mode dialog, fully integrated with existing control flow (warning mechanism, polling, download). The component is ready for the backend's `POST /app-exports` route to accept and handle mode `"standalone"` (which will be implemented in the core service).

**Commit details:**
- Hash: `1a27847`
- Message: `feat(shell): AppExportPanel gains an Autoporté button (SP-18c)`
- Files: `shell/src/builder/appexport/AppExportPanel.tsx`, `shell/src/builder/appexport/AppExportPanel.test.tsx`

**Test summary:** 1 new test passing + 4 pre-existing tests passing = 5/5 on component. Full suite: 1188/1188 passing.
