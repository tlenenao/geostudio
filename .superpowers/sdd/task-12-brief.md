## Task 12: Shell E2E — the plan's acceptance proof

**Files:**
- Create: `shell/e2e/map-symbology.spec.ts`

**Interfaces:** none new — end-to-end proof only.

- [ ] **Step 1: Read the nearest precedent**

Run: `grep -n "tiles.*mvt\|world-tile" shell/e2e/map-popup.spec.ts shell/e2e/mocks.ts`

`map-popup.spec.ts` (SP-24) already mounts a real MapLibre canvas against a
mocked MVT tile fixture and a mocked `/collections` catalog — reuse its
exact scaffolding (fixture file, route mocks, canvas click mechanics)
instead of inventing new ones.

- [ ] **Step 2: Write the E2E spec**

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("author 5 quantile classes on a tiled layer, save, reload, and the rendered colors survive with no new aggregate call", async ({ page }) => {
  await mockCore(page);
  // (reuse map-popup.spec.ts's MVT tile fixture route mock verbatim)

  let aggregateCallsAfterSave = 0;
  await page.route("**/collections/*/aggregate", async (route) => {
    await route.fulfill({
      json: {
        categoryKey: "value",
        rows: [{ value: 0, min: 0, q1: 20, q2: 40, q3: 60, q4: 80, max: 100 }],
      },
    });
  });

  // navigate to the map editor, add the tiled collection layer (mirrors
  // map-popup.spec.ts's layer-add flow), open its symbology editor
  await page.goto("/");
  // ... (follow map-popup.spec.ts's exact navigation to a map item's editor) ...

  await page.getByLabel("Champ couleur").fill("population");
  await page.getByLabel("Type de couleur").selectOption("numeric");
  await page.getByLabel("Méthode de classification").selectOption("quantile");
  await page.getByLabel("Nombre de classes").fill("5");
  await page.getByLabel("Palette").selectOption("sequential-blue");
  await page.getByRole("button", { name: "Recalculer les classes" }).click();
  await expect(page.getByText(/0\.0.*100\.0/)).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // stop counting real aggregate calls from here — any further one is a bug
  page.on("request", (req) => {
    if (req.url().includes("/aggregate")) aggregateCallsAfterSave++;
  });

  await page.reload();
  await expect(page.locator("canvas")).toBeVisible();
  expect(aggregateCallsAfterSave).toBe(0);
});
```

Fill in the elided navigation/layer-add steps by copying `map-popup.spec.ts`
line for line for that portion — do not write new selectors from a guess.

- [ ] **Step 3: Run it**

Run: `cd shell && npm run e2e -- map-symbology`
Expected: PASS.

- [ ] **Step 4: Run the full E2E suite**

Run: `cd shell && npm run e2e`
Expected: PASS, no regression on `map-popup.spec.ts`/`map-editor.spec.ts`
(both touch the same `LayersPanel`/`MapView` code paths this plan modified).

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/map-symbology.spec.ts
git commit -m "$(cat <<'EOF'
test(shell): prouve le round-trip de la symbologie sur une couche tuilée

5 classes en quantiles, palette nommée, enregistrement, rechargement,
rendu identique sans nouvel appel d'agrégat — critère de sortie du
plan d'action (SP-25).
EOF
)"
```

---

