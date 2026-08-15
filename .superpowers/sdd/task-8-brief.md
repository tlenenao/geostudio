### Task 8: second "Connecté" button + fix the write-warning mode bug

**Files:**
- Modify: `shell/src/builder/appexport/AppExportPanel.tsx`
- Modify: `shell/src/builder/appexport/AppExportPanel.test.tsx`

**Interfaces:**
- Produces: same public component signature. Internally, `showWriteWarning:
  boolean` is replaced by `pendingWarningMode: AppExportMode | null` — this
  also fixes a latent bug in the SP-18a code: the "Exporter quand même"
  confirm button always called `runExport("static")` regardless of which
  mode's button had triggered the warning; with only one mode that bug was
  invisible, but it would silently export Static instead of Connecté the
  moment a second button existed.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/appexport/AppExportPanel.test.tsx` (the
existing two tests stay as-is, but the second one's `getByRole("button", {
name: /statique/i })` click now also has a sibling "Connecté" button to
disambiguate from — no change needed there since `/statique/i` still
matches only one button):

```tsx


  it("triggers a connected export and shows a download link once done", async () => {
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
    await userEvent.click(screen.getByRole("button", { name: /connect/i }));
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument());
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "connected");
  });

  it("confirms the write warning with the mode that actually triggered it", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config(true)} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /connect/i }));
    expect(screen.getByText(/écriture.*désactivée/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /quand même/i }));
    await waitFor(() => expect(client.createAppExport).toHaveBeenCalledWith("item1", "connected"));
  });
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: both new tests FAIL — no "Connecté" button exists yet
(`getByRole("button", { name: /connect/i })` throws), and the confirm
button always sends `"static"`.

- [ ] **Step 3: Update `AppExportPanel.tsx`**

In `shell/src/builder/appexport/AppExportPanel.tsx`, replace the
`showWriteWarning` state declaration:

```tsx
  const [showWriteWarning, setShowWriteWarning] = useState(false);
```

with:

```tsx
  const [pendingWarningMode, setPendingWarningMode] = useState<AppExportMode | null>(null);
```

Replace `runExport`'s first line:

```tsx
  async function runExport(mode: AppExportMode) {
    setShowWriteWarning(false);
```

with:

```tsx
  async function runExport(mode: AppExportMode) {
    setPendingWarningMode(null);
```

Replace `onChooseMode`:

```tsx
  function onChooseMode(mode: AppExportMode) {
    const hasWriteWidget = [...collectWidgetTypes(config)].some((t) => WRITE_CAPABLE_WIDGET_TYPES.has(t));
    if (hasWriteWidget) {
      setDialogOpen(false);
      setShowWriteWarning(true);
      return;
    }
    void runExport(mode);
  }
```

with:

```tsx
  function onChooseMode(mode: AppExportMode) {
    const hasWriteWidget = [...collectWidgetTypes(config)].some((t) => WRITE_CAPABLE_WIDGET_TYPES.has(t));
    if (hasWriteWidget) {
      setDialogOpen(false);
      setPendingWarningMode(mode);
      return;
    }
    void runExport(mode);
  }
```

Replace the dialog's button row:

```tsx
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={() => onChooseMode("static")}>
            Statique
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
        </div>
```

Replace the warning block:

```tsx
      {showWriteWarning && (
        <div role="alert" className="rounded border border-amber-400 bg-amber-50 p-2 text-sm">
          <p>
            Cette app contient un widget Formulaire — toute écriture sera
            désactivée dans l&apos;export statique faute de backend.
          </p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => runExport("static")}>
              Exporter quand même
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowWriteWarning(false)}>
              Annuler
            </Button>
          </div>
        </div>
      )}
```

with:

```tsx
      {pendingWarningMode && (
        <div role="alert" className="rounded border border-amber-400 bg-amber-50 p-2 text-sm">
          <p>
            Cette app contient un widget Formulaire — toute écriture sera
            désactivée dans l&apos;export faute de session authentifiée.
          </p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => runExport(pendingWarningMode)}>
              Exporter quand même
            </Button>
            <Button size="sm" variant="outline" onClick={() => setPendingWarningMode(null)}>
              Annuler
            </Button>
          </div>
        </div>
      )}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/appexport/AppExportPanel.tsx shell/src/builder/appexport/AppExportPanel.test.tsx
git commit -m "feat(shell): AppExportPanel gains a Connecté button, fixes write-warning mode bug (SP-18b)"
```

---

