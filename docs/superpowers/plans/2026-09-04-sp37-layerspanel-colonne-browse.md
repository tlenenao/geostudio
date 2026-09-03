# LayersPanel : la colonne browse ne clippe plus son contenu (SP-37) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the last open mechanism of the "lot Carte" backlog item — the `browse` column of `TriptychLayout.tsx` clipping `LayersPanel`'s content at 900px — by fixing the two real, falsification-confirmed offenders (an unwrapped flex-row in `PopupEditor.tsx`, and an unconstrained native `<input type="file">` in `MapSymbologyEditor.tsx`), tokenizing two leftover `border-t` in `LayerPicker.tsx` along the way, and retiring the `wideBoundaryKnownIssue` guard on the Cartes screen in `triptych-narrow.spec.ts`.

**Architecture:** Two one-line `className` fixes in two different map editor components (different mechanisms — one is a missing `flex-wrap`, the other a missing `w-full`), each proven by falsification against a real Playwright measurement. One cosmetic two-line fix in a third file (no layout mechanism, just a missing color token). One test file updated to remove a now-resolved known-issue guard and add one new permanent regression test for the offender that generic page-load doesn't reach on its own.

**Tech Stack:** React 19, Tailwind v4, Playwright, Vitest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-04-sp37-layerspanel-colonne-browse-design.md` (as corrected by the follow-up commit `d03f41cf` — the spec's second offender hypothesis, `MapSymbologyEditor.tsx:575`, was written during brainstorming, tested during plan-writing, and found **wrong**; the real second offender, `MapSymbologyEditor.tsx:695`, replaces it in the spec and in this plan).
- No `core/`/OpenAPI change — pure shell CSS + E2E test changes. Confirm explicitly (`git diff --stat main...HEAD -- core/` from the repo root should be empty) rather than assume (CLAUDE.md piège n°1 is about the opposite mistake, but the check itself must still be run).
- Both layout bugs are real-browser artifacts (elements whose rendered box exceeds their container, or whose overflow is silently absorbed by a scrollable ancestor). jsdom does not compute layout, so no Vitest test can reproduce or verify either — reproduction and fixes are proven exclusively through Playwright (E2E) against a real built app, exactly like SP-36.
- **Falsification is mandatory for both fixes** (CLAUDE.md piège n°10): temporarily revert the fix, confirm the relevant Playwright assertion actually fails (not just "the test still exists"), then restore. Both fixes were already falsified once manually while writing the spec — this plan re-does it formally, on the actual committed diff, not on the assumption that the earlier manual check still holds.
- The full E2E suite must be run before this plan is considered done, not just the touched files (CLAUDE.md piège n°6). Read pass/fail counts from `test-results/.last-run.json`, not the truncated tail of the Playwright `list` reporter on a long run (CLAUDE.md, SP-31 entry).
- Shell coverage threshold: 88 (`.coverage-threshold`), measured **after** cleaning `dist/`/`dist-export/` (CLAUDE.md documents this pitfall 4 times). This plan touches `PopupEditor.tsx`, `MapSymbologyEditor.tsx`, `LayerPicker.tsx` — all three already covered by their own `*.test.tsx` files, and none of the changes are behavioral (className-only), so coverage is not expected to move; confirm rather than assume.
- No Vitest/jsdom assertion on the CSS classes added, for the reason above. Each task confirms by direct reading that no existing `PopupEditor.test.tsx`/`MapSymbologyEditor.test.tsx`/`LayerPicker.test.tsx` test asserts an exact `className` that would break — not by trusting this plan's own grep, re-run it.
- On completion, update `CLAUDE.md`: add a `### Livré` entry for SP-37, and this time **fully remove** the "Reste lot **Carte**" bullet under `### À venir` (unlike SP-36, which had to keep half of it — this plan closes the only remaining mechanism, so nothing is left to track there).

---

### Task 1: Fix #1 — `PopupEditor.tsx`'s unwrapped "add field" row

**Files:**
- Modify: `shell/src/map/PopupEditor.tsx:160`
- Modify (temporarily, then restore): `shell/e2e/triptych-narrow.spec.ts` (only to lift a skip guard for falsification — the permanent removal of that guard is Task 4, not this task)

**Interfaces:**
- Consumes: nothing new.
- Produces: the "add field" row's `className` now contains the literal substring `flex-wrap`. Task 4 relies on this fix already being in place (via the real running app) when it removes the `wideBoundaryKnownIssue` guard.

The regression proof for this fix is the **existing** generic "Cartes à 900 px" test in `triptych-narrow.spec.ts` (part of the `for (const screen of SCREENS)` loop) — it already measures this exact offender today, it's just skipped via `wideBoundaryKnownIssue`. No new test is needed for this fix; Task 4 formally un-skips it once both fixes are in.

- [ ] **Step 1: Confirm the current (unfixed) state fails when the skip is lifted**

In `shell/e2e/triptych-narrow.spec.ts`, temporarily comment out the `wideBoundaryKnownIssue` line on the Cartes entry (do not touch anything else in that entry yet):

```diff
     wideBoundaryKnownIssue:
-      'Cartes : 1 offenseur pré-existant (colonne browse trop étroite pour le contenu de LayersPanel) — sans rapport avec la famine de colonne centrale corrigée par SP-33 ; le titre de couche à largeur nulle est corrigé par SP-36. Tracké CLAUDE.md/lot "Carte".',
+      undefined, // SP-37 : temporairement levé pour falsification (Task 1), remis en Task 4
   },
```

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts -g "Cartes à 900"`
Expected: FAIL — `expectNoClippedContent` reports exactly 1 offender: `{ tag: "DIV", className: "overflow-y-auto border-r border-rule", scrollWidth: 290, clientWidth: 249 }` (the failure message includes the JSON — read it, don't assume the numbers).

- [ ] **Step 2: Fix `PopupEditor.tsx`**

```diff
-          <div className="flex items-center gap-2">
+          <div className="flex flex-wrap items-center gap-2">
             <input
               aria-label="Nom du champ à ajouter"
               list={`${listId}-titre`}
               className={`${inputCls} flex-1`}
               value={draftField}
               onChange={(e) => setDraftField(e.target.value)}
             />
             <Button type="button" size="sm" variant="outline" onClick={addDraftField}>
               Ajouter le champ
             </Button>
           </div>
```

- [ ] **Step 3: Run the same test to confirm it now passes**

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts -g "Cartes à 900"`
Expected: PASS — 0 offenders.

- [ ] **Step 4: Revert the temporary skip-lift, confirm the file is back to its pre-Task-1 state**

```bash
cd shell
git diff e2e/triptych-narrow.spec.ts
```

Expected: the only diff shown is the one-line comment-out from Step 1 — revert it:

```bash
git checkout -- e2e/triptych-narrow.spec.ts
git diff --stat e2e/triptych-narrow.spec.ts
```

Expected: no output (empty diff). This file is untouched by this task — Task 4 owns its changes.

- [ ] **Step 5: Confirm no existing Vitest test breaks**

Run (from `shell/`): `npx vitest run src/map/PopupEditor.test.tsx`
Expected: PASS, same test count as before this task. Confirm directly (don't trust the spec's earlier grep) that no test in this file asserts an exact `className` on the row touched:

Run: `grep -n "flex items-center gap-2\"" src/map/PopupEditor.test.tsx`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
cd shell
git add src/map/PopupEditor.tsx
git commit -m "fix(shell): la ligne d'ajout de champ de PopupEditor ne clippe plus la colonne browse (SP-37)"
```

---

### Task 2: Fix #2 — `MapSymbologyEditor.tsx`'s unconstrained icon-upload file input

**Files:**
- Modify: `shell/src/map/MapSymbologyEditor.tsx:695`
- Modify: `shell/e2e/triptych-narrow.spec.ts` (append one new permanent test — this file is otherwise still not touched for the Cartes `SCREENS` entry, that's Task 4)

**Interfaces:**
- Consumes: nothing new.
- Produces: the icon-upload `<input type="file">`'s `className` now contains `w-full`. This offender is **not** reached by the generic Cartes page-load test (it requires opening the icon section) — this task's new test is the only regression guard for it, and must be added as a permanent test, not a throwaway.

This offender is unconditional: it does not need long category values, only the icon section to be open. Use short domain values ("A"/"B") in the test — deliberately, to prove the mechanism is independent of text length (confirmed during spec-writing: this offender reproduces identically with short and long values, unlike a wrapping-text row).

- [ ] **Step 1: Write the new test (will fail — the fix isn't in yet)**

Append to the end of `shell/e2e/triptych-narrow.spec.ts` (after the existing `test("700 px (bande 391-899, sous le seuil relevé)…`):

```ts

// SP-37 (docs/superpowers/specs/2026-09-04-sp37-layerspanel-colonne-browse-design.md) :
// contrairement aux offenseurs génériques mesurés par les deux boucles
// ci-dessus (déclenchés par le simple chargement de la page), celui-ci
// n'apparaît qu'une fois la section "Ajouter des icônes" de
// MapSymbologyEditor.tsx ouverte et un champ icône recalculé — d'où un test
// dédié plutôt qu'une entrée SCREENS générique. Valeurs de domaine COURTES
// ("A"/"B") délibérément : l'offenseur (un <input type="file"> sans classe
// de largeur) est inconditionnel, indépendant de la longueur du texte —
// contrairement à l'offenseur de PopupEditor.tsx (Task 1 de ce plan), pas
// besoin d'un texte long pour le démontrer.
test("Cartes à 900 px : la section icônes de la symbologie ne clippe pas une fois ouverte", async ({
  page,
}) => {
  await page.setViewportSize({ width: WIDE_BOUNDARY_WIDTH, height: WIDE_HEIGHT });
  await mockCore(page);
  await page.route("**/collections/communes/aggregate", async (route) => {
    await route.fulfill({
      json: { categoryKey: "type_zone", rows: [{ type_zone: "A" }, { type_zone: "B" }] },
    });
  });
  await page.goto("/maps/map-1");

  await page.getByRole("button", { name: "Ajouter des icônes" }).click();
  await page.getByLabel("Champ icône").fill("type_zone");
  await page.getByRole("button", { name: "Recalculer les valeurs" }).click();
  await expect(page.getByLabel("Ajouter une icône au tenant (PNG ou SVG)")).toBeVisible();

  await expectNoClippedContent(page);
});
```

- [ ] **Step 2: Run it to confirm it fails on the current (unfixed) code**

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts -g "la section icônes"`
Expected: FAIL — `expectNoClippedContent` reports exactly 1 offender: `{ tag: "DIV", className: "overflow-y-auto border-r border-rule", scrollWidth: 313, clientWidth: 249 }` (exact numbers may differ slightly from the spec's — read the actual failure message, don't assume).

- [ ] **Step 3: Fix `MapSymbologyEditor.tsx`**

```diff
             {uploadCustomIcon && (
               <label className={labelCls}>
                 Ajouter une icône au tenant (PNG ou SVG)
                 <input
                   aria-label="Ajouter une icône au tenant (PNG ou SVG)"
                   type="file"
+                  className="w-full"
                   accept="image/png,image/svg+xml"
                   onChange={(e) => {
```

- [ ] **Step 4: Run the test again to confirm it passes**

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts -g "la section icônes"`
Expected: PASS — 0 offenders.

- [ ] **Step 5: Falsify — temporarily revert the fix and confirm the new test fails**

```diff
                 <input
                   aria-label="Ajouter une icône au tenant (PNG ou SVG)"
                   type="file"
-                  className="w-full"
                   accept="image/png,image/svg+xml"
```

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts -g "la section icônes"`
Expected: FAIL, same offender as Step 2. If it passes, the test isn't exercising the bug — stop and investigate before continuing.

- [ ] **Step 6: Restore the fix**

```diff
                 <input
                   aria-label="Ajouter une icône au tenant (PNG ou SVG)"
                   type="file"
+                  className="w-full"
                   accept="image/png,image/svg+xml"
```

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts -g "la section icônes"`
Expected: PASS.

- [ ] **Step 7: Confirm `MapSymbologyEditor.tsx` has exactly one line changed**

Run (from `shell/`): `git diff --stat src/map/MapSymbologyEditor.tsx`
Expected: `1 file changed, 1 insertion(+)`. If more, the revert-then-restore in Steps 5-6 left something behind — fix before committing.

- [ ] **Step 8: Confirm no existing Vitest test breaks**

Run (from `shell/`): `npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: PASS, same test count as before this task.

Run: `grep -n "Ajouter une icône au tenant" src/map/MapSymbologyEditor.test.tsx`
Confirm none of the matching lines assert an exact `className` on this input (read them, don't just count them).

- [ ] **Step 9: Commit**

```bash
cd shell
git add src/map/MapSymbologyEditor.tsx e2e/triptych-narrow.spec.ts
git commit -m "fix(shell): le champ de fichier d'upload d'icône ne clippe plus la colonne browse (SP-37)"
```

---

### Task 3: Tokenize the two `border-t` in `LayerPicker.tsx`

**Files:**
- Modify: `shell/src/map/LayerPicker.tsx:143`, `:173`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks — purely cosmetic, unrelated to the layout mechanism of Tasks 1-2.

- [ ] **Step 1: Apply both changes**

```diff
-      <div className="border-t pt-2">
+      <div className="border-t border-rule pt-2">
         <p className="mb-1 text-xs font-medium text-ink-2">Ajouter un tileset 3D par URL</p>
```

```diff
-      <div className="border-t pt-2">
+      <div className="border-t border-rule pt-2">
         <p className="mb-1 text-xs font-medium text-ink-2">Ajouter une couche par URL GeoJSON</p>
```

- [ ] **Step 2: Confirm no existing test breaks**

Run (from `shell/`): `npx vitest run src/map/LayerPicker.test.tsx`
Expected: PASS, same test count as before this task.

Run: `grep -n "border-t" src/map/LayerPicker.test.tsx`
Expected: no output (confirms no test asserts this exact className).

- [ ] **Step 3: Clôture grep — confirm no other untokenized `border-t` remains in the three files this plan touches**

Run (from `shell/`): `grep -n "border-t\"" src/map/PopupEditor.tsx src/map/MapSymbologyEditor.tsx src/map/LayerPicker.tsx`
Expected: no output (both `LayerPicker.tsx` occurrences now read `border-t border-rule`, so the exact string `border-t"` no longer matches; `PopupEditor.tsx`/`MapSymbologyEditor.tsx` have none to begin with — confirm, don't assume).

- [ ] **Step 4: Commit**

```bash
cd shell
git add src/map/LayerPicker.tsx
git commit -m "fix(shell): tokenise les deux border-t restants de LayerPicker (SP-37)"
```

---

### Task 4: Retire the `wideBoundaryKnownIssue` guard for the Cartes screen

**Files:**
- Modify: `shell/e2e/triptych-narrow.spec.ts`

**Interfaces:**
- Consumes: the fixes from Tasks 1-2 (already committed and in effect, via the real running app).
- Produces: the final, accurate wording Task 5 copies into `CLAUDE.md` — copy what actually lands here, not the spec's hypothesis.

- [ ] **Step 1: Remove the guard and rewrite the Cartes entry's comment**

```diff
   {
     name: "Cartes",
     path: "/maps/map-1",
-    // SP-36 (docs/superpowers/plans/2026-09-03-sp36-layerspanel-titre-flex-wrap.md) :
-    // le <span> de titre d'une couche vector/feature à largeur de layout
-    // nulle (mécanisme (b), flex-1 truncate + sibling basis-full toujours
-    // déployé) est corrigé — flex-wrap ajouté à la ligne (LayersPanel.tsx).
-    // Ré-mesuré empiriquement (pas supposé) : plus aucun offenseur sur
-    // l'onglet "Couches" à 390px avec la vérification de clip désormais
-    // active. Seul le mécanisme (a) — la colonne browse (~249px de large à
-    // 900px) trop étroite pour le contenu de LayersPanel — persiste, et
-    // seulement dans la grille desktop (900px) : offenseur unique mesuré
-    // DIV.overflow-y-auto.border-r.border-rule (scrollWidth 290 >
-    // clientWidth 249), sans rapport avec la famine de colonne centrale
-    // corrigée par SP-33. À 390px (layout mobile en onglets, la colonne
-    // "Couches" occupe toute la largeur disponible) ce mécanisme ne
-    // reproduit pas.
-    wideBoundaryKnownIssue:
-      'Cartes : 1 offenseur pré-existant (colonne browse trop étroite pour le contenu de LayersPanel) — sans rapport avec la famine de colonne centrale corrigée par SP-33 ; le titre de couche à largeur nulle est corrigé par SP-36. Tracké CLAUDE.md/lot "Carte".',
+    // SP-36 a fermé le mécanisme (b) (titre de couche à largeur nulle).
+    // SP-37 (docs/superpowers/specs/2026-09-04-sp37-layerspanel-colonne-browse-design.md)
+    // ferme le mécanisme (a) restant (colonne browse trop étroite pour le
+    // contenu de LayersPanel) : deux offenseurs distincts trouvés et
+    // corrigés — la ligne d'ajout de champ de PopupEditor.tsx (flex-wrap
+    // manquant) et le champ de fichier d'upload d'icône de
+    // MapSymbologyEditor.tsx (aucune classe de largeur). Ré-mesuré
+    // empiriquement après les deux correctifs : plus aucun offenseur, ni à
+    // 390px ni à 900px. Le lot "Carte" est clos (CLAUDE.md).
   },
```

- [ ] **Step 2: Update the file's header comment block**

```diff
 // SP-33 (docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md)
 // a donné à la colonne centrale (work) de TriptychLayout.tsx un plancher
 // CSS explicite (minmax(360px,1fr), au lieu d'un `1fr` nu sans plancher
 // réel) et relevé le seuil de useNarrowViewport.ts en conséquence (899px)
-// — la famine de colonne centrale documentée par la revue transverse SP-30l
-// (round 2, 2026-09-02) est corrigée. Seul l'écran Cartes conserve un
-// wideBoundaryKnownIssue, pour un défaut pré-existant et sans rapport avec ce
-// mécanisme (colonne browse trop étroite pour LayersPanel — cf. son entrée
-// ci-dessous ; le second défaut historiquement bundlé ici, le titre de
-// couche à largeur nulle, est corrigé par SP-36).
+// — la famine de colonne centrale documentée par la revue transverse SP-30l
+// (round 2, 2026-09-02) est corrigée. SP-36 puis SP-37 ont depuis fermé les
+// deux défauts pré-existants et sans rapport de l'écran Cartes (titre de
+// couche à largeur nulle ; colonne browse trop étroite pour LayersPanel) —
+// plus aucun écran de ce fichier ne porte de wideBoundaryKnownIssue.
```

- [ ] **Step 3: Confirm the `skipClipCheckForTabs`/`wideBoundaryKnownIssue` type fields are still declared (kept for the next screen that needs them, per the existing doctrine comment above the `SCREENS` type) — do not remove the type declaration itself**

Run: `grep -n "wideBoundaryKnownIssue\|skipClipCheckForTabs" shell/e2e/triptych-narrow.spec.ts`
Expected: two hits in the `SCREENS` type declaration (with their explanatory comments, untouched by this task) and zero hits in any screen entry — confirm the Cartes entry no longer has either field.

- [ ] **Step 4: Run the full file**

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts`
Expected: every test PASSES except the one pre-existing, unrelated `test.skip()` (Catalogue, per the file's own comment — confirm it's still exactly Catalogue and nothing else). Read `test-results/.last-run.json` for the exact count, don't trust the `list` reporter's tail.

- [ ] **Step 5: Commit**

```bash
cd shell
git add e2e/triptych-narrow.spec.ts
git commit -m "test(shell): retire le wideBoundaryKnownIssue de l'écran Cartes — lot Carte clos (SP-37)"
```

---

### Task 5: Full suite verification and `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the final, real wording Task 4 committed for the Cartes entry — this task's `CLAUDE.md` edit must match what was actually committed there, not this plan's draft wording.
- Produces: nothing (terminal task).

- [ ] **Step 1: Run the full Vitest suite**

Run (from `shell/`): `npm run test`
Expected: same pass count as `CLAUDE.md`'s last recorded baseline (221 fichiers/1848 tests per the SP-34/SP-36 entries) — no new failures, no new tests (this plan adds no Vitest test). If the count differs, investigate before continuing.

- [ ] **Step 2: Run the full Playwright suite**

Run (from `shell/`): `npm run e2e`
Expected: pass count = the pre-plan baseline (143 tests/138 passed/5 skipped/0 failed per the SP-33/SP-34/SP-36 entries, all "inchangé" since SP-33) **minus the Cartes 900px skip removed by Task 4** (so 5 skipped → 4 skipped, 138 passed → 139 passed) **plus the one new permanent test from Task 2** (144 tests total, 140 passed/4 skipped/0 failed). Read `test-results/.last-run.json` for the authoritative count — if it doesn't match this arithmetic exactly, investigate before writing anything into `CLAUDE.md` below; do not just copy this plan's prediction over the real number.

- [ ] **Step 3: Confirm no `core/` changes**

Run (from the repo root): `git diff --stat main...HEAD -- core/`
Expected: empty output.

- [ ] **Step 4: Clean `dist/`/`dist-export/` and check shell coverage**

Run (from `shell/`):
```bash
rm -rf dist dist-export
npx vitest run --coverage
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```
Expected: coverage ≥88 (threshold), no regression from the last recorded baseline (90,51% per the SP-33 entry — the most recent `### Livré` entry to state a shell coverage percentage; SP-34/SP-35/SP-36 don't restate one) — this plan's changes are className-only in already-covered files, so no meaningful movement is expected; confirm rather than assume.

- [ ] **Step 5: Add the SP-37 `### Livré` entry**

Read the current `### Livré` section's end (around the SP-36 entry) and the "Reste lot **Carte**" bullet under `### À venir` in `CLAUDE.md` immediately before editing — another concurrent session may have touched this file since this plan was written (CLAUDE.md piège n°9). Then insert a new bullet after the SP-36 entry ends (after the line `Vitest shell **inchangé**... la dépendance d'ordre sur le stub `matchMedia`... était déjà documentée comme risque latent — cf. entrée SP-30l). **Ready to merge.**`, before `### Conventions tranchées (2026-09-01)`), in the same dense style as neighboring entries, covering exactly these facts (no more, no less):

1. What this plan closes: the last open mechanism of the "lot Carte" backlog item — the `browse` column of `TriptychLayout.tsx` clipping `LayersPanel`'s content at 900px, tracked since SP-28/measured by SP-36/Task 3.
2. The two real offenders found and fixed, **and the one that was hypothesized wrong first**: the spec's original hypothesis for the second offender (`MapSymbologyEditor.tsx:575`, the icon-value `span`+`button` row) was tested during plan-writing and found not to reproduce (its text wraps, doesn't force width) — the real second offender, `MapSymbologyEditor.tsx:695` (an `<input type="file">` with no width class), was found instead. Name both fixes (`PopupEditor.tsx:160` — `flex-wrap` added to the "add field" row; `MapSymbologyEditor.tsx:695` — `w-full` added to the icon-upload file input) and their distinct mechanisms (one a flex-wrap fix like SP-36, the other a native-control width-floor fix — `min-w-0` alone was tested and found insufficient, `w-full` was required).
3. The trivial, unrelated fix folded in at Tanguy's request: `LayerPicker.tsx`'s two remaining untokenized `border-t` (debt carved out of SP-30c/SP-34) now read `border-t border-rule`.
4. Task 4's **actual, already-committed** wording for the Cartes entry in `triptych-narrow.spec.ts` — copy the real committed text, don't re-derive or paraphrase it.
5. The real E2E delta from Step 2 above (compare to the pre-plan baseline — 143 tests/138 passed/5 skipped/0 failed per the SP-33/SP-34/SP-36 entries) and the real Vitest/coverage numbers from Steps 1 and 4.
6. End with **Ready to merge.**

- [ ] **Step 6: Remove the "Reste lot Carte" bullet under `### À venir`**

Delete the entire bullet (currently the lines starting `- Reste lot **Carte** (bug UI, pas une fonctionnalité manquante) — …` through `…même pipeline que l'éditeur.*`) — read it fresh before deleting (CLAUDE.md piège n°9, same caution as Step 5). Unlike SP-36 (which had to keep half of this bullet because one mechanism remained open), this plan closes the only remaining mechanism — nothing is left to track here, so the bullet is removed in full, not edited.

- [ ] **Step 7: Fix the dangling forward-reference in the SP-30 "Suivis non bloquants" bullet**

That bullet (under `### À venir`, starting `- **Suivis non bloquants pour SP-30 (désormais clos)**…`) currently ends one of its parenthetical clauses with `cf. `### Livré`/SP-33 et le lot **Carte** ci-dessous)`. Once Step 6 removes the "lot Carte" bullet, "ci-dessous" points at nothing. Fix only this dangling reference — do not rewrite the rest of that historical paragraph, which still accurately describes SP-33's own findings at the time:

```diff
-  Tâches/Paramètres ne rendent aucune grille à vérifier (`<EmptyState>`
-  seul), cf. `### Livré`/SP-33 et le lot **Carte** ci-dessous). Reste, par
+  Tâches/Paramètres ne rendent aucune grille à vérifier (`<EmptyState>`
+  seul), cf. `### Livré`/SP-33 — le lot **Carte** est depuis clos par
+  SP-37). Reste, par
```

- [ ] **Step 8: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: clôture le lot Carte dans CLAUDE.md — colonne browse corrigée par SP-37"
```

---

## Self-review notes (for the plan author, not a task)

- Spec coverage: §3 fix #1 (mécanisme, diff) → Task 1. §3 fix #2 (mécanisme, diff) → Task 2. §2 point 3 (`LayerPicker.tsx`) → Task 3. §2 point 4/§4 point 3 (`triptych-narrow.spec.ts` cleanup) → Task 4. §2 point 5/§5 (CLAUDE.md) → Task 5. §4 point 1 (falsification, both fixes) → Task 1 Steps 1-4, Task 2 Steps 2-7. §4 point 2 (reproducing fix #2's state) → Task 2 Step 1. §4 point 4 (no broken Vitest assertions) → Task 1 Step 5, Task 2 Step 8, Task 3 Step 2. §4 points 5-6 (full suite, no OpenAPI regen) → Task 5 Steps 1-4, Global Constraints.
- The spec's §6 risk note ("correction de l'hypothèse initiale") is carried into this plan's Global Constraints and Task 5 Step 5 point 2 — the `### Livré` entry must name the wrong hypothesis explicitly, not silently present the correct fix as if it were the first guess (matches this repo's established practice of disclosing corrected diagnoses, e.g. SP-31/SP-35's entries).
- Type/name consistency: `expectNoClippedContent`, `WIDE_BOUNDARY_WIDTH`, `WIDE_HEIGHT`, `mockCore` are all pre-existing, unchanged symbols from `triptych-narrow.spec.ts`/`mocks.ts` — Task 2's new test uses them exactly as declared in that file, no new helper introduced.
