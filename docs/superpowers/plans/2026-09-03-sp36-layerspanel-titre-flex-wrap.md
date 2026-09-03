# LayersPanel : le titre de couche ne s'effondre plus à largeur 0 (SP-36) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the zero-width title-`<span>` bug on `vector`/`feature` layer rows in `LayersPanel.tsx` (a single missing `flex-wrap`), prove it with real E2E assertions instead of the workaround that has stood in for it since SP-28, and close the "lot Carte" backlog item in `CLAUDE.md` accurately (only the part this plan actually fixes).

**Architecture:** One Tailwind class added to the `<li>` in `LayersPanel.tsx`. Two existing E2E specs are updated to assert the title's visibility directly instead of a proxy (the "Retirer …" button); the fix is falsified (temporarily reverted, confirmed the new assertions fail, restored) before being trusted. A third E2E spec (`triptych-narrow.spec.ts`, the Cartes screen's known-issue tracking) is updated to reflect exactly what changed and what didn't, based on real measurement, not assumption.

**Tech Stack:** React 19, Tailwind v4, Playwright.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-03-sp36-layerspanel-titre-flex-wrap-design.md`.
- No core/OpenAPI change — pure shell CSS + E2E test changes. Confirm explicitly (`git diff --stat` scoped to this branch should show zero files under `core/`) rather than skip the check out of assumption (CLAUDE.md piège n°1 is about the opposite mistake, but the check itself must still be run).
- This bug is a real-browser layout artifact (an element rendered at 0×0 px, present in the DOM). jsdom does not compute layout, so `LayersPanel.test.tsx` (Vitest) cannot reproduce or verify it — the reproduction and the fix are proven exclusively through Playwright (E2E), against a real built app.
- **Known correction to the spec's exit criterion 4**: the spec says "le lot « Carte » est retiré de `### À venir`". That is only half true. `CLAUDE.md`'s "lot Carte" entry and the cross-references to it from the SP-30l/SP-33 `### Livré` entries actually track **two independent, pre-existing defects** on the Cartes screen: (a) the `browse` column being too narrow for `LayersPanel`'s own content (out of scope for this plan, confirmed persisting at every width probed by SP-33), and (b) this title-`<span>` zero-width bug (in scope, fixed by this plan). Task 4 below **updates** the "lot Carte" bullet to mark (b) resolved and keep (a) open — it does not delete the bullet, because defect (a) has no other tracking location in `CLAUDE.md`. This is a deliberate, documented deviation from the spec's literal wording, not an oversight — flag it in the task's commit/report.
- The full E2E suite must be run before this plan is considered done, not just the touched files (CLAUDE.md piège n°6). Read pass/fail counts from `test-results/.last-run.json`, not the truncated tail of the Playwright `list` reporter on a long run (CLAUDE.md, SP-31 entry).
- Shell coverage threshold: 88 (`.coverage-threshold`) — this plan touches no `src/` files covered by Vitest coverage other than `LayersPanel.tsx` (already covered by `LayersPanel.test.tsx`, unaffected by a className-only change), so coverage is not expected to move; confirm rather than assume.
- On completion, update `CLAUDE.md`: add a `### Livré` entry for SP-36, and update (not delete) the "lot Carte" bullet under `### À venir`, per the correction above.

---

### Task 1: Fix the bug and prove it on the `feature` (GeoJSON URL) case

**Files:**
- Modify: `shell/src/map/LayersPanel.tsx:164`
- Modify: `shell/e2e/map-feature-layer-symbology.spec.ts`

**Interfaces:**
- Consumes: nothing new — `LayersPanel` keeps its existing `{ layers, onChange }` props.
- Produces: the layer-row `<li>`'s `className` now contains the literal substring `flex-wrap`. Task 2 and Task 3 both rely on this fix already being in place (via the real running app, not a mock) when they run their own E2E checks.

- [ ] **Step 1: Rewrite the existing workaround into a real assertion (still failing at this point)**

In `shell/e2e/map-feature-layer-symbology.spec.ts`, replace the first occurrence (mid-test, right after adding the layer):

```diff
   await page.getByLabel("Titre de la couche GeoJSON").fill("Points d'intérêt");
   await page.getByLabel("URL du GeoJSON").fill("https://external.test/poi.geojson");
   await page.getByRole("button", { name: "Ajouter la couche" }).click();
-  // On confirme l'ajout via le bouton "Retirer <titre>" plutôt que le texte
-  // du titre lui-même : pour une couche vector/feature (éditeur toujours
-  // déplié, pas d'accordéon), la ligne <li> est un flex-row sans retour à la
-  // ligne où le panneau d'édition (`basis-full`) revendique toute la largeur
-  // disponible — le <span class="truncate"> du titre, seul élément flexible
-  // avec min-width auto ramené à 0 par `overflow: hidden`, se retrouve
-  // rendu à une largeur de 0px (visible dans le DOM, invisible à l'écran).
-  // C'est un détail de mise en page préexistant, partagé avec les couches
-  // "vector" (ex. "Communes" dans map-symbology.spec.ts, qui ne teste jamais
-  // la visibilité du titre après ajout) — hors périmètre de cette tâche.
-  // Le bouton "Retirer …" porte le même titre dans son aria-label et n'est
-  // pas soumis à cet écrasement (il n'est pas flex-1).
-  await expect(page.getByRole("button", { name: "Retirer Points d'intérêt" })).toBeVisible();
+  // SP-36 (docs/superpowers/specs/2026-09-03-sp36-layerspanel-titre-flex-wrap-design.md) :
+  // le <span class="truncate"> du titre de couche s'effondrait à une largeur
+  // de 0px pour les couches vector/feature (flex-wrap manquant sur le <li>
+  // parent de LayersPanel.tsx) — corrigé. Assertion directe, plus besoin du
+  // bouton "Retirer …" comme preuve indirecte.
+  await expect(page.getByText("Points d'intérêt", { exact: true })).toBeVisible();
```

And the second occurrence, near the end of the same test (after `page.reload()`):

```diff
   await page.reload();
   await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
-  await expect(page.getByRole("button", { name: "Retirer Points d'intérêt" })).toBeVisible();
+  await expect(page.getByText("Points d'intérêt", { exact: true })).toBeVisible();
 });
```

- [ ] **Step 2: Run the test to confirm it fails on the current (unfixed) code**

Run (from `shell/`): `npx playwright test e2e/map-feature-layer-symbology.spec.ts`
Expected: FAIL — the first new assertion (`getByText("Points d'intérêt", { exact: true })`) times out because the element's bounding box is 0×0 (Playwright's `toBeVisible()` requires a non-empty box). This confirms the test now actually exercises the bug, unlike the workaround it replaces.

- [ ] **Step 3: Fix `LayersPanel.tsx`**

```diff
-          <li key={layer.id} className="flex items-center gap-2 text-sm">
+          {/* flex-wrap : sans lui, le bloc `basis-full` (édition inline,
+          ci-dessous) ne peut jamais passer à la ligne — il écrase le titre à
+          largeur 0 à la place (SP-36). */}
+          <li key={layer.id} className="flex flex-wrap items-center gap-2 text-sm">
```

- [ ] **Step 4: Run the test again to confirm it passes**

Run (from `shell/`): `npx playwright test e2e/map-feature-layer-symbology.spec.ts`
Expected: PASS.

- [ ] **Step 5: Run `LayersPanel.test.tsx` (Vitest) to confirm the className change breaks nothing there**

Run (from `shell/`): `npx vitest run src/map/LayersPanel.test.tsx`
Expected: PASS, same test count as before this task (no test in that file asserts an exact `className` on the `<li>` — confirmed by `grep -n "className" src/map/LayersPanel.test.tsx` returning nothing at spec-writing time; re-confirm here rather than trust that grep is still accurate).

- [ ] **Step 6: Commit**

```bash
cd shell
git add src/map/LayersPanel.tsx e2e/map-feature-layer-symbology.spec.ts
git commit -m "fix(shell): le titre d'une couche vector/feature ne s'effondre plus à largeur 0 (SP-36)"
```

---

### Task 2: Extend coverage to the `vector` case and falsify both specs together

**Files:**
- Modify: `shell/e2e/map-symbology.spec.ts`
- Modify (temporarily, then restore): `shell/src/map/LayersPanel.tsx`

**Interfaces:**
- Consumes: the `flex-wrap` fix from Task 1 (already committed and in effect).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the missing assertion for the "Communes" (`kind: "vector"`) layer**

In `shell/e2e/map-symbology.spec.ts`, right after the layer is added:

```diff
   await page.getByRole("button", { name: /Communes/ }).click();
+  // SP-36 : couvre le cas partagé jamais testé avant ce plan — couche
+  // "vector" (pas seulement "feature" comme dans
+  // map-feature-layer-symbology.spec.ts). exact:true est nécessaire : le
+  // bouton source du LayerPicker ci-dessus a pour texte accessible complet
+  // "Communes vector" (le kind est concaténé au titre dans le bouton),
+  // jamais "Communes" seul — pas d'ambiguïté avec le titre affiché dans
+  // LayersPanel une fois la couche ajoutée.
+  await expect(page.getByText("Communes", { exact: true })).toBeVisible();
 
   // Configurer la symbologie via l'UI réelle (MapSymbologyEditor.tsx).
```

- [ ] **Step 2: Run the test to confirm it passes (fix already in place from Task 1)**

Run (from `shell/`): `npx playwright test e2e/map-symbology.spec.ts`
Expected: PASS. This alone does not prove the assertion is meaningful — Step 3 does.

- [ ] **Step 3: Falsify — temporarily revert the fix and confirm both specs fail**

In `shell/src/map/LayersPanel.tsx`, temporarily undo Task 1's change:

```diff
-          {/* flex-wrap : sans lui, le bloc `basis-full` (édition inline,
-          ci-dessous) ne peut jamais passer à la ligne — il écrase le titre à
-          largeur 0 à la place (SP-36). */}
-          <li key={layer.id} className="flex flex-wrap items-center gap-2 text-sm">
+          <li key={layer.id} className="flex items-center gap-2 text-sm">
```

Run (from `shell/`): `npx playwright test e2e/map-feature-layer-symbology.spec.ts e2e/map-symbology.spec.ts`

Expected: both files report a failure. `map-feature-layer-symbology.spec.ts`'s single test fails at its **first** `getByText("Points d'intérêt", { exact: true })` assertion (the test stops there — Playwright's `expect()` throws on failure — so the second, post-reload occurrence of the same assertion is never reached in this run; that's expected and not a gap, since both occurrences use the identical selector/assertion and the mechanism under test is unchanged between them). `map-symbology.spec.ts`'s test fails at the new `getByText("Communes", { exact: true })` assertion. If either file passes despite the revert, stop and investigate — the assertion is not exercising the bug and needs a different locator.

- [ ] **Step 4: Restore the fix**

```diff
-          <li key={layer.id} className="flex items-center gap-2 text-sm">
+          {/* flex-wrap : sans lui, le bloc `basis-full` (édition inline,
+          ci-dessous) ne peut jamais passer à la ligne — il écrase le titre à
+          largeur 0 à la place (SP-36). */}
+          <li key={layer.id} className="flex flex-wrap items-center gap-2 text-sm">
```

Run (from `shell/`): `npx playwright test e2e/map-feature-layer-symbology.spec.ts e2e/map-symbology.spec.ts`
Expected: both PASS again.

- [ ] **Step 5: Confirm `LayersPanel.tsx` is byte-identical to Task 1's committed version before committing this task**

Run: `git diff --stat src/map/LayersPanel.tsx` (from `shell/`)
Expected: no output (empty diff) — the revert-then-restore in Steps 3-4 must leave the file exactly as Task 1 committed it. If there is a diff, fix it before proceeding; do not commit an accidental second change to this file under this task.

- [ ] **Step 6: Commit**

```bash
cd shell
git add e2e/map-symbology.spec.ts
git commit -m "test(shell): couvre le titre d'une couche vector dans map-symbology.spec.ts (SP-36)"
```

---

### Task 3: Empirically re-measure the Cartes screen in `triptych-narrow.spec.ts`

**Files:**
- Modify: `shell/e2e/triptych-narrow.spec.ts`

**Interfaces:**
- Consumes: the `flex-wrap` fix from Tasks 1-2 (already committed and in effect), via the real built app.
- Produces: nothing consumed by later tasks except the confirmed-accurate wording Task 4 copies into `CLAUDE.md`.

The Cartes screen entry currently carries two guards, both covering **two** pre-existing, distinct defects bundled together: the `browse` column being too narrow for `LayersPanel`'s content (mechanism (a), out of scope for this plan) and this title-`<span>` bug (mechanism (b), fixed by Tasks 1-2). This task measures what's real now and updates the guards to describe only what's still true — it does not assume mechanism (a) behaves identically at every width just because SP-33's spec said so for the desktop-grid case specifically.

- [ ] **Step 1: Baseline run — confirm nothing broke outside what this task will touch**

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts -g "Cartes"`
Expected: 3 tests match (`"Cartes à 390 px : …"`, `"Cartes à 900 px (juste au-dessus du seuil relevé) : …"`, plus any others matching the regex — check the actual count in the output rather than assume). The 390px test PASSES (it still skips the "Couches" tab's clip check internally via `skipClipCheckForTabs`). The 900px test is SKIPPED (its `test.skip(screen.wideBoundaryKnownIssue !== undefined, ...)` guard is still active).

- [ ] **Step 2: Temporarily lift both guards to observe real offender counts**

In `shell/e2e/triptych-narrow.spec.ts`, comment out (don't delete yet) both lines on the Cartes entry:

```diff
     name: "Cartes",
     path: "/maps/map-1",
     // CLAUDE.md, lot "Carte" (bug UI connu, pré-existant, hors périmètre de
     // tout plan SP-30) : dans LayersPanel.tsx, le <span> de titre d'une
     // couche vector/feature peut avoir une largeur de layout nulle
     // (flex-1 truncate + sibling basis-full) — scrollWidth > clientWidth (0)
     // pour de vrai, mais c'est le défaut déjà tracké, pas un effet du seuil
     // de useNarrowViewport que cette tâche corrige. Confirmé par
     // investigation (page.evaluate ciblé) avant d'écarter cet onglet ici,
     // pas supposé.
-    skipClipCheckForTabs: ["Couches"],
-    wideBoundaryKnownIssue:
-      'Cartes : 2 offenseurs pré-existants et distincts (colonne browse trop étroite pour LayersPanel ; <span> de titre LayersPanel à largeur nulle) — sans rapport avec la famine de colonne centrale corrigée par SP-33. Trackés CLAUDE.md/lot "Carte" et SP-30l.',
+    // skipClipCheckForTabs: ["Couches"],
+    // wideBoundaryKnownIssue: "SP-36 investigation — temporarily lifted",
```

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts -g "Cartes"`

Read `test-results/.last-run.json` for the authoritative pass/fail count (not the `list` reporter's tail on a run this size).

- [ ] **Step 3: Interpret the 900px result and decide the new `wideBoundaryKnownIssue` wording**

The failure message (if any) includes `JSON.stringify(lastOffenders)` from `expectNoClippedContent` — read it.

- **If the 900px test now FAILS with exactly 1 offender**, and that offender's `className` matches the `browse` column container (`DIV.overflow-y-auto.border-r.border-rule`, the same one SP-33's Task 3 identified for mechanism (a)) — this confirms mechanism (b) is fully resolved and only mechanism (a) remains. Set:

  ```ts
      wideBoundaryKnownIssue:
        'Cartes : 1 offenseur pré-existant (colonne browse trop étroite pour le contenu de LayersPanel) — sans rapport avec la famine de colonne centrale corrigée par SP-33 ; le titre de couche à largeur nulle est corrigé par SP-36. Tracké CLAUDE.md/lot "Carte".',
  ```

- **If the 900px test now PASSES (0 offenders)** — mechanism (a) does not manifest at this specific viewport/tab combination after all. Remove `wideBoundaryKnownIssue` entirely for Cartes and replace the comment with a note that both known mechanisms are resolved or do not reproduce here, citing this plan.

- **If the 900px test FAILS with 2 or more offenders, or an offender whose `className` doesn't match the `browse` column** — the fix from Tasks 1-2 did not fully resolve mechanism (b), or a third defect exists. Stop and investigate before writing any CLAUDE.md claim; do not guess.

- [ ] **Step 4: Interpret the 390px result and decide the `skipClipCheckForTabs` entry**

- **If the 390px test still PASSES with the "Couches" tab's clip check now active** (i.e., mechanism (a) does not reproduce in the narrow/mobile tab layout, only in the desktop grid's fixed-width `browse` column) — remove `skipClipCheckForTabs: ["Couches"]` entirely for Cartes.
- **If the 390px test FAILS on the "Couches" tab** — read the offenders. If they match mechanism (a) (the same `browse`-column-shaped defect, now manifesting under the narrow layout too — a fact not previously known, since SP-33 only probed it at desktop widths), keep `skipClipCheckForTabs: ["Couches"]` and note in the comment that mechanism (a) also reproduces at 390px, not just ≥900px. If the offender is a different, unexplained element, stop and investigate before continuing.

- [ ] **Step 5: Write the final Cartes entry**

Assemble the Cartes block from Steps 3 and 4's actual decisions, not from the hypothesis in Step 3's bullet list:

- `skipClipCheckForTabs`: present with `["Couches"]` only if Step 4 found the 390px "Couches" tab still fails; omitted otherwise.
- `wideBoundaryKnownIssue`: present with the exact string Step 3 decided on (either the "1 offenseur" wording, or omitted if Step 3 found 0 offenders) only if Step 3 found the 900px test still fails; omitted otherwise.
- The comment above these fields: rewritten to state (a) mechanism (b) is fixed, citing SP-36 and this spec's path, and (b) mechanism (a)'s exact remaining reproduction conditions per Steps 3-4 — not the pre-plan assumption that it's desktop-only. If both guards end up omitted (both mechanisms resolved), the Cartes entry becomes a plain `{ name: "Cartes", path: "/maps/map-1" }` with a short comment noting both previously-tracked mechanisms are now resolved/non-reproducing, same style as the other five screens' entries above it in this file.

- [ ] **Step 6: Run the full file once more to confirm the final state is green (or correctly skipped)**

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts`
Expected: every test PASSES except any `test.skip()` still legitimately in place for mechanism (a) — read `test-results/.last-run.json` for the exact count and compare it to the pre-Task-3 baseline (Step 1) plus/minus exactly what Steps 3-4 changed.

- [ ] **Step 7: Commit**

```bash
cd shell
git add e2e/triptych-narrow.spec.ts
git commit -m "test(shell): re-mesure l'écran Cartes après le correctif LayersPanel (SP-36)"
```

---

### Task 4: Full suite verification and `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the final, real wording Task 3 produced for the Cartes entry (Step 5 of Task 3) — this task's `CLAUDE.md` edit must match what was actually committed there, not the plan's hypothesis.
- Produces: nothing (terminal task).

- [ ] **Step 1: Run the full Vitest suite**

Run (from `shell/`): `npm run test`
Expected: same pass count as `CLAUDE.md`'s last recorded baseline (221 fichiers/1848 tests per the SP-34 entry) — no new failures. If the count differs, investigate before continuing.

- [ ] **Step 2: Run the full Playwright suite**

Run (from `shell/`): `npm run e2e`
Expected: no failures beyond the pre-existing, documented skips (`connected-export.spec.ts`, `static-export.spec.ts` ×3 per the SP-33 entry, plus whatever `triptych-narrow.spec.ts` legitimately still skips per Task 3). Read `test-results/.last-run.json` for the authoritative count, not the `list` reporter's truncated tail (CLAUDE.md piège, SP-31 entry).

- [ ] **Step 3: Confirm no `core/` changes**

Run: `git diff --stat main...HEAD -- core/` (from the repo root)
Expected: empty output. If anything shows, stop — this plan's scope explicitly excludes `core/`.

- [ ] **Step 4: Add the SP-36 `### Livré` entry**

Read the current `### Livré` section's end (around the SP-35 entry) and the "lot Carte" bullet under `### À venir` in `CLAUDE.md` immediately before editing — another concurrent session may have touched this file since this plan was written (CLAUDE.md piège n°9). Then insert a new bullet after the SP-35 entry ends (after the line `failed. **10 commits au total.** **Ready to merge.**`, before `### Conventions tranchées (2026-09-01)`), in the same dense style as neighboring entries, and covering exactly these facts (no more, no less):

1. What changed: `flex-wrap` added to the `<li>` in `LayersPanel.tsx:164`; the mechanism (one sentence: `basis-full` couldn't wrap onto its own line without it, so the title `<span>` — the only sibling with a zero automatic min-width, via `overflow: hidden`/`truncate` — absorbed the shrink instead).
2. Which spec/plan this closes: `docs/superpowers/specs/2026-09-03-sp36-layerspanel-titre-flex-wrap-design.md`; referme la partie "titre à largeur nulle" du lot "Carte" ouvert depuis SP-28.
3. The two E2E specs updated (`map-feature-layer-symbology.spec.ts` — replaces the "Retirer …" workaround with a direct title assertion; `map-symbology.spec.ts` — adds the first-ever title assertion for the `vector` case) and the fact the fix was falsified (temporarily reverted, both specs confirmed failing, restored) before being trusted.
4. Task 3's **actual, already-committed** finding about `triptych-narrow.spec.ts`'s Cartes entry — copy the real wording from that commit, don't re-derive or paraphrase it here.
5. The real E2E delta (compare Step 2's count to the pre-plan baseline — 143 tests/133 passed/10 skipped per the SP-33 entry, adjusted for whatever Task 3 actually changed) and confirmation Vitest shell is unchanged (221 fichiers/1848 tests per the SP-34 entry — this plan adds no Vitest test).
6. End with **Ready to merge.**

- [ ] **Step 5: Update the "lot Carte" bullet under `### À venir`**

Rewrite the existing "Reste lot **Carte**" bullet (currently describing only the now-fixed title-`<span>` bug) so that it:

1. States the title-`<span>` bug (mechanism (b)) is resolved, pointing to the new `### Livré`/SP-36 entry from Step 4.
2. Keeps the `browse`-column-too-narrow-for-`LayersPanel` defect (mechanism (a)) open, since this plan does not fix it and it has no other tracking location in this file — describe it using Task 3's **actual** finding (Task 3 Step 3/4) about exactly which widths/layouts it reproduces at, not the pre-plan assumption that it only affects desktop widths ≥900px. If Task 3 found it also reproduces at 390px, say so explicitly here — that would be new information this plan surfaced, not previously documented anywhere.
3. Keeps the two existing footnote sentences about symbology/Jenks being resolved elsewhere (SP-28, SP-27/Task 19) — they're unrelated to either mechanism and still accurate.
4. Drops the now-obsolete sentence about the `browse` column rendering as narrow as ~250px in the 900-959px band (SP-33) being a caveat for "a future fix" — this plan *is* that future fix for mechanism (b); if mechanism (a) is still being kept open, fold that caveat into its description instead of leaving it as a dangling forward-reference.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: clôt partiellement le lot Carte dans CLAUDE.md — titre de couche résolu par SP-36"
```

---

## Self-review notes (for the plan author, not a task)

- Spec coverage: §3 (the fix) → Task 1. §2 point 2/§4 points 1-3 (E2E updates + falsification) → Tasks 1-2. §2 point 4/§4 point 4 (`triptych-narrow.spec.ts`) → Task 3. §2 point 5/§5 point 4 (`CLAUDE.md`) → Task 4, with the correction noted in Global Constraints. §4 point 5 (`LayersPanel.test.tsx` doesn't break) → Task 1 Step 5. §4 point 6 (no OpenAPI regen) → Global Constraints + Task 4 Step 3.
- The spec's exit criterion 4 ("le lot « Carte » est retiré de `### À venir`") is knowingly not followed literally — see Global Constraints for why, and Task 4 Step 5 for what actually happens instead.
