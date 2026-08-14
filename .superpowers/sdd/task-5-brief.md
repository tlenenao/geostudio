### Task 5: `LayerPicker.tsx` — add a 3D Tiles layer by URL

**Files:**
- Modify: `shell/src/map/LayerPicker.tsx` (full file)
- Test: `shell/src/map/LayerPicker.test.tsx`

**Interfaces:**
- Consumes: `MapLayer` (Task 2, `kind: "tiles3d"` variant), `Button` from `shell/src/ui/button.tsx`.
- Produces: no new exports — `LayerPicker`'s existing `onAdd` prop is now also called with a `tiles3d` layer from the new inline form.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/map/LayerPicker.test.tsx` (after the last existing test, `"has a search field that calls listLayerSources with q"`):

```ts
test("adds a tiles3d layer from the manual URL form", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  await userEvent.type(screen.getByLabelText("Titre du tileset 3D"), "Bâtiments");
  await userEvent.type(screen.getByLabelText("URL du tileset.json"), "https://example.test/tileset.json");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le tileset 3D" }));
  expect(onAdd).toHaveBeenCalledTimes(1);
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "tiles3d",
    title: "Bâtiments",
    visible: true,
    url: "https://example.test/tileset.json",
  });
  expect(typeof layer.id).toBe("string");
  expect(layer.id.length).toBeGreaterThan(0);
});

test("disables the tiles3d add button until both title and URL are filled", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const button = screen.getByRole("button", { name: "Ajouter le tileset 3D" });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Titre du tileset 3D"), "Bâtiments");
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("URL du tileset.json"), "https://example.test/tileset.json");
  expect(button).toBeEnabled();
});

test("clears the tiles3d form after adding", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const titleInput = screen.getByLabelText("Titre du tileset 3D") as HTMLInputElement;
  const urlInput = screen.getByLabelText("URL du tileset.json") as HTMLInputElement;
  await userEvent.type(titleInput, "Bâtiments");
  await userEvent.type(urlInput, "https://example.test/tileset.json");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le tileset 3D" }));
  expect(titleInput.value).toBe("");
  expect(urlInput.value).toBe("");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run test -- src/map/LayerPicker.test.tsx`
Expected: FAIL — no element with label "Titre du tileset 3D"/"URL du tileset.json" or button "Ajouter le tileset 3D" exists yet.

- [ ] **Step 3: Implement**

Replace the full contents of `shell/src/map/LayerPicker.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useLayerSources } from "../api/hooks";
import type { LayerSource, MapLayer } from "../api/types";
import { Button } from "../ui/button";

function toMapLayer(source: LayerSource): MapLayer {
  const id = crypto.randomUUID();
  if (source.kind === "vector") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "vector",
      tilesUrl: source.tilesUrl ?? "",
      sourceLayer: source.sourceLayer ?? "",
    };
  }
  if (source.kind === "raster") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "raster",
      tilesUrl: source.tilesUrl ?? "",
      opacity: 1,
    };
  }
  return { id, title: source.title, visible: true, kind: "feature", url: source.url ?? "" };
}

export function LayerPicker({ onAdd }: { onAdd: (layer: MapLayer) => void }) {
  const [q, setQ] = useState("");
  const [tiles3dTitle, setTiles3dTitle] = useState("");
  const [tiles3dUrl, setTiles3dUrl] = useState("");
  const { data, isLoading, isError, refetch } = useLayerSources({ q: q || undefined });

  function addTiles3D() {
    if (!tiles3dTitle.trim() || !tiles3dUrl.trim()) return;
    onAdd({ id: crypto.randomUUID(), title: tiles3dTitle, visible: true, kind: "tiles3d", url: tiles3dUrl });
    setTiles3dTitle("");
    setTiles3dUrl("");
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        type="search"
        role="searchbox"
        aria-label="Rechercher une source de couche"
        placeholder="Rechercher…"
        className="h-8 rounded-md border border-slate-300 px-2 text-sm"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {isLoading && <p className="text-sm text-slate-500">Chargement des sources…</p>}
      {isError && (
        <div className="text-sm text-red-600">
          <p role="alert">Impossible de charger les sources de couches.</p>
          <button type="button" className="underline" onClick={() => refetch()}>
            Réessayer
          </button>
        </div>
      )}
      {!isLoading && !isError && (!data || data.length === 0) && (
        <p className="text-sm text-slate-500">Aucune source disponible.</p>
      )}
      {!isLoading && !isError && data && data.length > 0 && (
        <ul className="flex flex-col gap-1">
          {data.map((source) => (
            <li key={`${source.service}:${source.id}`}>
              <button
                type="button"
                className="w-full rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100"
                onClick={() => onAdd(toMapLayer(source))}
              >
                {source.title}
                <span className="ml-2 text-xs text-slate-400">{source.kind}</span>
                {typeof source.featureCount === "number" && (
                  <span className="ml-2 text-xs text-slate-400">
                    {source.featureCount} entités
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="border-t pt-2">
        <p className="mb-1 text-xs font-medium text-slate-500">Ajouter un tileset 3D par URL</p>
        <div className="flex flex-col gap-1">
          <input
            aria-label="Titre du tileset 3D"
            type="text"
            placeholder="Titre"
            className="h-8 rounded-md border border-slate-300 px-2 text-sm"
            value={tiles3dTitle}
            onChange={(e) => setTiles3dTitle(e.target.value)}
          />
          <input
            aria-label="URL du tileset.json"
            type="text"
            placeholder="https://…/tileset.json"
            className="h-8 rounded-md border border-slate-300 px-2 text-sm"
            value={tiles3dUrl}
            onChange={(e) => setTiles3dUrl(e.target.value)}
          />
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!tiles3dTitle.trim() || !tiles3dUrl.trim()}
            onClick={addTiles3D}
          >
            Ajouter le tileset 3D
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm run test -- src/map/LayerPicker.test.tsx`
Expected: PASS, all tests in the file green (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add shell/src/map/LayerPicker.tsx shell/src/map/LayerPicker.test.tsx
git commit -m "feat(shell): LayerPicker permet d'ajouter un tileset 3D par URL"
```

---

