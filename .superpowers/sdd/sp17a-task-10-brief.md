### Task 10: Mode `exportRender` (chrome d'impression + signal de disponibilité)

> Playwright attend `[data-export-ready="true"]` (posé par la tâche 6 côté cœur) avant de capturer — sans ce signal réel, la capture se ferait sur une page vide/tuiles non chargées. Pour la carte, le signal est l'événement MapLibre `idle` (aucun délai fixe). Pour l'app/dashboard, en l'absence d'un signal par-widget instrumenté (hors périmètre 17a — scope documenté), le signal est « la requête de config a réussi + une frame de peinture » — un signal réel (succès de requête + paint), pas un minuteur arbitraire, mais moins rigoureux que le cas carte pour des widgets non-cartographiques ; documenté comme limite connue plutôt que silencieusement passé sous silence.

**Files:**
- Create: `shell/src/shell/exportReady.ts`
- Create: `shell/src/shell/useIsExportRender.ts`
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Test: `shell/src/map/MapView.test.tsx`, `shell/src/shell/useIsExportRender.test.ts`

**Interfaces:**
- Produces: `markExportReady(): void` (idempotent, pose `document.body.dataset.exportReady = "true"`). `useIsExportRender(): boolean` (lit `useSearchParams().get("exportRender") === "1"`). `MapView` gagne une prop `onReady?: () => void`, appelée dans `map.once("idle", ...)`.

- [ ] **Step 1: Écrire le test de `useIsExportRender`, qui échoue**

```typescript
// shell/src/shell/useIsExportRender.test.ts
import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useIsExportRender } from "./useIsExportRender";

function wrapper(initialPath: string) {
  return ({ children }: { children: React.ReactNode }) => <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>;
}

describe("useIsExportRender", () => {
  it("is false without the query param", () => {
    const { result } = renderHook(() => useIsExportRender(), { wrapper: wrapper("/maps/1") });
    expect(result.current).toBe(false);
  });

  it("is true with exportRender=1", () => {
    const { result } = renderHook(() => useIsExportRender(), { wrapper: wrapper("/maps/1?exportRender=1") });
    expect(result.current).toBe(true);
  });
});
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/shell/useIsExportRender.test.ts`
Expected: FAIL — module inexistant.

- [ ] **Step 3: Implémenter `useIsExportRender` et `exportReady`**

```typescript
// shell/src/shell/useIsExportRender.ts
import { useSearchParams } from "react-router-dom";

export function useIsExportRender(): boolean {
  const [params] = useSearchParams();
  return params.get("exportRender") === "1";
}
```

```typescript
// shell/src/shell/exportReady.ts
// Signal DOM que le worker Playwright (core/app/export/jobs.py) attend via
// page.wait_for_selector('[data-export-ready="true"]') avant de capturer.
// Idempotent : peut être appelé plusieurs fois sans effet de bord.
export function markExportReady(): void {
  document.body.dataset.exportReady = "true";
}
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/shell/useIsExportRender.test.ts`
Expected: PASS

- [ ] **Step 5: Écrire le test de `MapView`, qui échoue**

Ajouter à `shell/src/map/MapView.test.tsx` (inspecter le fichier existant pour le style exact de mock de `maplibre-gl` déjà en place — probablement un mock du module entier avec un faux `Map` émettant des événements) :

```tsx
it("calls onReady once the map fires 'idle'", async () => {
  const onReady = vi.fn();
  const { mapInstance } = renderMapView({ onReady }); // helper existant du fichier, à adapter
  mapInstance.emit("load");
  mapInstance.emit("idle");
  expect(onReady).toHaveBeenCalledTimes(1);
});
```

Adapter précisément au harnais de mock déjà utilisé dans ce fichier de test (nom du helper de rendu, façon d'émettre un événement sur le faux `maplibregl.Map`) — ne pas réinventer un mock parallèle.

- [ ] **Step 6: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: FAIL — prop `onReady` ignorée.

- [ ] **Step 7: Implémenter dans `MapView.tsx`**

Ajouter `onReady?: () => void` à la liste de props du composant (même endroit que `onViewChange`/`onFeatureClick`), un ref stable comme pour les autres callbacks (lignes 129-137), et l'appel dans le handler `load` existant (ligne 154-159) :

```tsx
  const onReadyRef = useRef(onReady);
  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);
```

Dans le `map.on("load", () => { ... })` existant, ajouter à la fin du callback :

```tsx
      map.once("idle", () => onReadyRef.current?.());
```

- [ ] **Step 8: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS

- [ ] **Step 9: Mode `exportRender` dans `MapEditorPage.tsx`**

```tsx
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";
// ...
const isExportRender = useIsExportRender();
// ...
if (isExportRender) {
  return (
    <div className="relative h-full w-full">
      <MapView config={draft} onReady={markExportReady} />
      {draft.printLayout?.title && (
        <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-sm font-medium">{draft.printLayout.title}</div>
      )}
      {draft.printLayout?.showLegend && (
        <ul className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs">
          {draft.layers.filter((l) => l.visible).map((l) => <li key={l.id}>{l.title}</li>)}
        </ul>
      )}
      {draft.printLayout?.cartouche && (
        <div className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs">{draft.printLayout.cartouche}</div>
      )}
    </div>
  );
}
// ... suivi du rendu normal du builder existant
```

Placer ce retour anticipé juste après que `draft` soit garanti non-null (après la garde de chargement existante), avant le rendu normal de l'aside/MapView. La barre d'échelle (`showScaleBar`) et la flèche nord (`showNorthArrow`) sont volontairement **non implémentées visuellement dans cette tâche** — cases conservées dans `PrintLayoutPanel` pour la forme du schéma (accepté par le design), mais leur rendu réel (contrôle MapLibre `ScaleControl` / icône SVG positionnée) est un raffinement futur non bloquant, à documenter comme tel dans le rapport de tâche plutôt que rendu silencieusement inopérant sans trace.

- [ ] **Step 10: Mode `exportRender` dans `AppRuntimePage.tsx`**

```tsx
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";
// ...
const isExportRender = useIsExportRender();
const appQuery = useAppConfig(pk, { mode: "runtime" });
useEffect(() => {
  if (isExportRender && appQuery.isSuccess) {
    requestAnimationFrame(() => markExportReady());
  }
}, [isExportRender, appQuery.isSuccess]);
```

Et, dans le JSX, entourer la barre d'actions existante (« Enregistrer la vue », futur bouton « Exporter » de la Tâche 11) d'une garde `{!isExportRender && ( ... )}` pour qu'elle n'apparaisse pas dans la capture.

- [ ] **Step 11: Vérifier build + suite shell**

Run: `cd shell && npm run build && npm run test`
Expected: PASS, aucune régression.

- [ ] **Step 12: Commit**

```bash
git add shell/src/shell/exportReady.ts shell/src/shell/useIsExportRender.ts shell/src/shell/useIsExportRender.test.ts shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx shell/src/pages/MapEditorPage.tsx shell/src/pages/AppRuntimePage.tsx
git commit -m "feat(shell): SP-17a — mode exportRender (chrome PrintLayout + signal data-export-ready)"
```

---

