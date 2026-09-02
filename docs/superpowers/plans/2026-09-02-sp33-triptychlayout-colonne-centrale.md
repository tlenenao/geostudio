# TriptychLayout : fin de l'affamement de la colonne centrale (SP-33) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `TriptychLayout`'s center column (`work`) a real CSS floor and raise the shared narrow/desktop breakpoint so the three-column grid never renders below the width where all three columns' minimums can coexist — closing the last blocking item before SP-30 can be redeclared closed.

**Architecture:** Two one-line source changes (`TriptychLayout.tsx`'s grid-template-columns, `useNarrowViewport.ts`'s threshold constant), verified empirically against the six previously-broken reference screens using the already-correct settle-poll clip-detector in `shell/e2e/triptych-narrow.spec.ts`, then that spec file and one sibling E2E file are updated to reflect the fix.

**Tech Stack:** React 19, Tailwind v4 (arbitrary-value CSS Grid classes), Vitest + React Testing Library, Playwright.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md`.
- Side-column tracks (`browse`: `minmax(220px,280px)`, `inspect`: `minmax(260px,320px)`) are **unchanged** — only the center track and the shared threshold move.
- Starting hypothesis: center floor `360px`, threshold `(max-width: 899px)`. These two numbers **must move together** (threshold = `220 + center_floor + 260`, rounded up with ~60px margin) and are verified empirically in Task 3 against a real running build, not assumed correct from this plan alone.
- Explicitly out of scope, do not touch: the "Cartes" screen's two other, pre-existing, separately-tracked defects — the `browse` column being too narrow for `LayersPanel`'s own content, and `LayersPanel`'s title-`<span>` zero-width bug (CLAUDE.md, lot « Carte »). Both remain skipped after this plan, just with an updated, accurate count.
- No third "compact desktop" layout mode — the band between the old and new threshold falls back to the existing mobile tabbed mode, already proven correct down to 390px. This was explicitly decided with Tanguy during brainstorming.
- No core/OpenAPI change — this is a pure shell CSS + constant change. Do not regenerate `openapi.json`/`core-schema.d.ts` (there is nothing to regenerate); confirm this explicitly rather than skipping it out of assumption (CLAUDE.md piège n°1 is about the opposite mistake, but the check itself — "did anything under `core/app` change?" — must still be run).
- Shell coverage threshold: 88 (`.coverage-threshold`), measured only after removing `dist/` and `dist-export/` (CLAUDE.md piège documented four times).
- The full E2E suite must be run before this plan is considered done, not just the touched files (CLAUDE.md piège n°6). Read pass/fail counts from `test-results/.last-run.json`, not the truncated tail of the Playwright `list` reporter on a long run (CLAUDE.md, SP-31 entry).
- On completion, update `CLAUDE.md`: remove/close the SP-30 blocking note under `### À venir` and add a `### Livré` entry for SP-33, per the spec's exit criterion 4.

---

### Task 1: Explicit CSS floor on `TriptychLayout`'s center column

**Files:**
- Modify: `shell/src/shell/chrome/TriptychLayout.tsx:24`
- Test: `shell/src/shell/chrome/TriptychLayout.test.tsx`

**Interfaces:**
- Consumes: nothing new — `TriptychLayout` keeps its existing `{ browse, work, inspect, defaultTabId }` props and its existing `useNarrowViewport()` call.
- Produces: the desktop-mode grid container's `className` now contains the literal substring `grid-cols-[minmax(220px,280px)_minmax(360px,1fr)_minmax(260px,320px)]` — Task 3's empirical verification checks the rendered layout this produces, not this string directly.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/shell/chrome/TriptychLayout.test.tsx`, after the existing `"large : les trois volets sont visibles en même temps"` test:

```tsx
test("large : la colonne centrale a un plancher CSS explicite, pas un 1fr nu", () => {
  vi.mocked(useNarrowViewport).mockReturnValue(false);
  const { container } = render(<TriptychLayout {...TABS} />);
  const grid = container.querySelector(".grid");
  expect(grid).not.toBeNull();
  expect(grid?.className).toContain(
    "grid-cols-[minmax(220px,280px)_minmax(360px,1fr)_minmax(260px,320px)]",
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/shell/chrome/TriptychLayout.test.tsx` (from `shell/`)
Expected: FAIL — the new test's `toContain` assertion fails because the current class is `grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)]` (no `minmax(360px,...)` substring). The other four existing tests in the file still PASS.

- [ ] **Step 3: Write minimal implementation**

In `shell/src/shell/chrome/TriptychLayout.tsx`, change line 24:

```diff
-      <div className="grid flex-1 grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)] overflow-hidden">
+      <div className="grid flex-1 grid-cols-[minmax(220px,280px)_minmax(360px,1fr)_minmax(260px,320px)] overflow-hidden">
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/shell/chrome/TriptychLayout.test.tsx` (from `shell/`)
Expected: PASS — all 5 tests in the file green.

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/shell/chrome/TriptychLayout.tsx src/shell/chrome/TriptychLayout.test.tsx
git commit -m "fix(shell): donne un plancher CSS explicite à la colonne centrale de TriptychLayout"
```

---

### Task 2: Raise the shared narrow/desktop threshold

**Files:**
- Modify: `shell/src/shell/chrome/useNarrowViewport.ts`
- Test: `shell/src/shell/chrome/useNarrowViewport.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `NARROW_QUERY` exported as the literal string `"(max-width: 899px)"` — consumed unchanged (by identifier, not by value) by both `TriptychLayout.tsx` and `AppLayout.tsx` via `useNarrowViewport()`. No call site needs editing: both already call the hook, not the constant, directly.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/shell/chrome/useNarrowViewport.test.ts`, after the existing three tests:

```ts
test("NARROW_QUERY correspond au seuil documenté par SP-33 (899px)", () => {
  expect(NARROW_QUERY).toBe("(max-width: 899px)");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/shell/chrome/useNarrowViewport.test.ts` (from `shell/`)
Expected: FAIL — `NARROW_QUERY` is currently `"(max-width: 640px)"`. The other three existing tests still PASS.

- [ ] **Step 3: Write minimal implementation**

Replace the entire comment block and constant in `shell/src/shell/chrome/useNarrowViewport.ts` (lines 4-24):

```diff
-// 640px = le seuil "sm" conventionnel de Tailwind, déjà idiomatique dans ce
-// dépôt. Choisi (2026-09-02, revue transverse SP-30l) après mesure réelle :
-// la grille triptyque trois colonnes de TriptychLayout.tsx clippait du
-// contenu sur toute la bande ~391-540px avec l'ancien seuil de 390px
-// (confirmé clippé à 540px), classant des téléphones réels courants
-// (iPhone 14/15 Plus/Pro Max, Pixel 7/8 Pro, iPhone XR/11) en mode "large"
-// alors qu'ils ne peuvent pas afficher la grille sans casse. Relever le
-// seuil à 640px élimine cette famine-là (la pire, colonne centrale à
-// clientWidth 0), mais NE garantit PAS l'absence de tout clipping au-dessus
-// de 640px sur chaque écran : round 2 de correction (2026-09-02, même date,
-// cf. CLAUDE.md entrée SP-30l) a mesuré, via un check corrigé pour observer
-// l'état stabilisé plutôt que le premier échantillon, un clipping résiduel
-// stable sur 6 des 8 écrans de référence à 641px (Catalogue, Cartes,
-// Apps & sites, Analytique, Administration, Automatisation — cf. shell/e2e/
-// triptych-narrow.spec.ts, WIDE_BOUNDARY_ROOT_CAUSE) — un défaut de
-// TriptychLayout.tsx lui-même (ses colonnes latérales grandissent vers leur
-// maximum combiné, 280+320=600px, avant que la colonne centrale ne reçoive
-// quoi que ce soit), pas de ce seuil. Ce défaut est tracké séparément et
-// n'est PAS corrigé par ce seuil ; SP-30 n'est donc pas déclaré clos tant
-// qu'il ne l'est pas (CLAUDE.md, section "À venir", entrée SP-30).
-export const NARROW_QUERY = "(max-width: 640px)";
+// Seuil de la grille triptyque à trois colonnes vs. le mode mobile (onglets
+// + BottomNav) — partagé avec AppLayout.tsx (bascule DomainBar/BottomNav).
+// Historique : 390px (SP-30) → 640px ("sm" Tailwind, revue transverse
+// SP-30l — corrigeait la pire famine mais laissait la colonne centrale de
+// TriptychLayout.tsx sans plancher réel entre ~641px et ce seuil, mesuré
+// clippé sur 6 des 8 écrans de référence) → 899px (SP-33, spec
+// docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md).
+// SP-33 a donné à la colonne centrale un plancher CSS explicite
+// (minmax(360px,1fr), TriptychLayout.tsx) ; ce seuil est calé juste
+// au-dessus de la somme des trois planchers (browse 220 + centre 360 +
+// inspect 260 = 840px, +~60px de marge) pour que la grille à trois
+// colonnes ne soit jamais rendue en dessous du point où les trois peuvent
+// coexister sans dépassement — sous ce seuil, le mode mobile prend le
+// relais. Deux défauts pré-existants et distincts sur l'écran Cartes
+// (colonne browse trop étroite pour LayersPanel ; <span> de titre
+// LayersPanel à largeur nulle) restent hors périmètre de ce chantier — cf.
+// shell/e2e/triptych-narrow.spec.ts et CLAUDE.md, lot "Carte".
+export const NARROW_QUERY = "(max-width: 899px)";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/shell/chrome/useNarrowViewport.test.ts` (from `shell/`)
Expected: PASS — all 4 tests in the file green.

- [ ] **Step 5: Run the full Vitest suite once before moving on**

Run: `npm run test` (from `shell/`)
Expected: no new failures beyond Tasks 1-2's own files. If any other test hardcodes `640` or `641` against `useNarrowViewport`/`TriptychLayout` behavior (none were found by grep at spec-writing time — `src/builder/grid.ts`/`grid.test.ts` and `src/ui/kit/Splitter.tsx` also contain `640` but are unrelated systems, app-builder widget breakpoints and a `Splitter` default prop, not this hook), investigate before proceeding — do not assume the earlier grep was exhaustive against a codebase that may have changed since.

- [ ] **Step 6: Commit**

```bash
cd shell
git add src/shell/chrome/useNarrowViewport.ts src/shell/chrome/useNarrowViewport.test.ts
git commit -m "fix(shell): relève le seuil étroit/large à 899px (SP-33)"
```

---

### Task 3: Empirically verify and update `triptych-narrow.spec.ts`

**Files:**
- Modify: `shell/e2e/triptych-narrow.spec.ts`

**Interfaces:**
- Consumes: `TriptychLayout` and `useNarrowViewport` as changed by Tasks 1-2 (via the real built app, not mocks — this is an E2E file).
- Produces: nothing consumed by later tasks except the confirmed-correct values of `center_min`/threshold, which Task 4 assumes are final by the time it runs.

- [ ] **Step 1: Run the current file against the new code to see what's real now**

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts`

This rebuilds (`npm run build && npm run preview`) and runs against Tasks 1-2's changes, but the file itself still says `WIDE_BOUNDARY_WIDTH = 641` and still carries `test.skip()` on 6 screens — so this run mostly re-confirms the *old*, now-stale premise (skipped tests stay skipped regardless of the code fix). Read the output only to confirm nothing outside the wide-boundary group broke. Do not draw conclusions about the fix from this run — Step 2 does that for real.

- [ ] **Step 2: Temporarily point the boundary width at the new threshold and un-skip, to observe real offender counts**

Edit `shell/e2e/triptych-narrow.spec.ts` — change:

```diff
-const WIDE_BOUNDARY_WIDTH = 641;
+const WIDE_BOUNDARY_WIDTH = 900;
```

and, for each of the 5 screens **other than Cartes** that currently has a `wideBoundaryKnownIssue` (Catalogue, Apps & sites, Analytique, Automatisation, Administration), comment out (don't delete yet) the `wideBoundaryKnownIssue:` line so the test actually runs instead of skipping.

Run: `npx playwright test e2e/triptych-narrow.spec.ts -g "900 px"`

Read `test-results/.last-run.json` for the authoritative pass/fail count (not the `list` reporter's tail).

- **If all 5 pass**: the `360px`/`899px` hypothesis holds for these screens. Proceed to Step 3.
- **If any fail**: the failure message includes `JSON.stringify(lastOffenders)` (from `expectNoClippedContent`) showing the real remaining offenders. Increase the center floor in `TriptychLayout.tsx` (Task 1, line 24) by 40px increments (e.g. 360→400→440…) and the threshold in `useNarrowViewport.ts` (Task 2) by the same increment each time (899→939→979…, keeping the ~60px margin over the new sum), re-run this same command after each change, until all 5 pass. Record the final numbers actually used — they replace `360`/`899` everywhere in this plan's remaining steps and in Tasks 1-2's committed code (amend those commits' code, not their test files, if the numbers change — the tests assert behavior, not the specific pixel values, except Task 2's Step 1 test literal, which must be updated to match).

- [ ] **Step 3: Run the Cartes screen alone to confirm exactly 2 remaining offenders, not 3**

Temporarily comment out Cartes's `wideBoundaryKnownIssue:` line too, then:

Run: `npx playwright test e2e/triptych-narrow.spec.ts -g "Cartes à 900 px"`

Expected: FAILS (this screen is not fully fixed — two separate, pre-existing, out-of-scope defects remain, per the spec §2). Read the failure's `JSON.stringify(lastOffenders)`:

- Confirm exactly **2** offenders, matching `DIV.overflow-y-auto.border-r.border-rule` (browse column too narrow for `LayersPanel`) and `SPAN.flex-1.truncate` (`LayersPanel` title-span bug) — **not** a `DIV.overflow-hidden` entry (that would be the center-starvation mechanism this plan targets, and its presence would mean the fix did not work for this screen despite Step 2 passing elsewhere).
- If a third offender or a different className shows up, stop and investigate before continuing — do not paper over an unexplained offender by just re-adding the skip.

Re-add `skipClipCheckForTabs: ["Couches"]` (unchanged) and replace Cartes's `wideBoundaryKnownIssue` value with:

```ts
    wideBoundaryKnownIssue:
      'Cartes : 2 offenseurs pré-existants et distincts (colonne browse trop étroite pour LayersPanel ; <span> de titre LayersPanel à largeur nulle) — sans rapport avec la famine de colonne centrale corrigée par SP-33. Trackés CLAUDE.md/lot "Carte" et SP-30l.',
```

- [ ] **Step 4: Remove the now-dead `wideBoundaryKnownIssue` entries and the shared root-cause constant**

For each of Catalogue, Apps & sites, Analytique, Automatisation, Administration: delete the (now commented-out) `wideBoundaryKnownIssue:` line entirely, and replace its preceding comment. Concretely, replace each of these five blocks:

```diff
   {
     name: "Catalogue",
     path: "/",
-    // Mesuré par le check corrigé (round 2, 2026-09-02) : 5 offenseurs
-    // stables à 641px, dont trois <p class="line-clamp-2"> de résumé
-    // d'item à clientWidth 0 (scrollWidth 10-11px, contenu réel invisible)
-    // — la colonne centrale de CatalogPage.tsx n'hérite que de 41px.
-    wideBoundaryKnownIssue: `Catalogue : 5 offenseurs stables mesurés à 641px (résumés d'items à largeur 0). ${WIDE_BOUNDARY_ROOT_CAUSE}`,
+    // SP-33 : les 5 offenseurs mesurés à 641px (résumés d'items à
+    // clientWidth 0) relevaient uniquement de la famine de colonne
+    // centrale, désormais corrigée.
   },
```

```diff
   {
     name: "Apps & sites",
     path: "/apps/1/edit",
-    // Mesuré par le check corrigé (round 2, 2026-09-02) : 2 offenseurs
-    // stables à 641px.
-    wideBoundaryKnownIssue: `Apps & sites : 2 offenseurs stables mesurés à 641px. ${WIDE_BOUNDARY_ROOT_CAUSE}`,
+    // SP-33 : les 2 offenseurs mesurés à 641px relevaient uniquement de la
+    // famine de colonne centrale, désormais corrigée.
   },
```

```diff
   {
     name: "Analytique",
     path: "/analytics/sql",
     before: (p) => mockMe(p, ANALYST_ME),
-    // Mesuré par le check corrigé (round 2, 2026-09-02) : 1 offenseur
-    // stable à 641px.
-    wideBoundaryKnownIssue: `Analytique : 1 offenseur stable mesuré à 641px. ${WIDE_BOUNDARY_ROOT_CAUSE}`,
+    // SP-33 : l'offenseur mesuré à 641px relevait uniquement de la famine
+    // de colonne centrale, désormais corrigée.
   },
```

```diff
   {
     name: "Automatisation",
     path: "/pipelines/new",
     before: (p) =>
       p.route("https://core.test/pipelines/ops", async (route) => {
         await route.fulfill({ json: AUTOMATISATION_OPS_CATALOG });
       }),
-    // Round 2 de correction (2026-09-02) : le mock ci-dessus fait quitter à
-    // la page son état "Chargement…" (cf. commentaire sur
-    // AUTOMATISATION_OPS_CATALOG) — une fois la grille réellement exercée,
-    // le check corrigé y mesure 2 offenseurs stables à 641px, la même
-    // famine de colonne centrale que les autres écrans. Round 1 déclarait
-    // ce test vert pour une raison sans rapport (page jamais chargée) ;
-    // round 2 découvre qu'il aurait dû être rouge pour la vraie raison une
-    // fois corrigé.
-    wideBoundaryKnownIssue: `Automatisation : 2 offenseurs stables mesurés à 641px une fois la page effectivement chargée (round 1 le déclarait vert par un défaut de mock, cf. commentaire AUTOMATISATION_OPS_CATALOG). ${WIDE_BOUNDARY_ROOT_CAUSE}`,
+    // Le mock ci-dessus fait quitter à la page son état "Chargement…" (cf.
+    // commentaire sur AUTOMATISATION_OPS_CATALOG), condition nécessaire
+    // pour atteindre la grille TriptychLayout et l'exercer réellement —
+    // sans rapport avec SP-33. SP-33 : les 2 offenseurs mesurés à 641px
+    // une fois la page chargée relevaient uniquement de la famine de
+    // colonne centrale, désormais corrigée.
   },
```

```diff
   {
     name: "Administration",
     path: "/admin/extensions",
     before: (p) => mockMe(p, ADMIN_ME),
-    // Mesuré par le check corrigé (round 2, 2026-09-02) : 1 offenseur
-    // stable à 641px.
-    wideBoundaryKnownIssue: `Administration : 1 offenseur stable mesuré à 641px. ${WIDE_BOUNDARY_ROOT_CAUSE}`,
+    // SP-33 : l'offenseur mesuré à 641px relevait uniquement de la famine
+    // de colonne centrale, désormais corrigée.
   },
```

Then remove the now-unused shared constant and its comment (it was referenced only by the five `wideBoundaryKnownIssue` values just deleted, plus Cartes's, which no longer references it after Step 3):

```diff
-// Mécanisme partagé derrière tous les `wideBoundaryKnownIssue` ci-dessous
-// (round 2 de correction, 2026-09-02) : TriptychLayout.tsx rend, au-dessus du
-// seuil de useNarrowViewport.ts (640px), une grille
-// `grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)]`. L'algorithme
-// standard de dimensionnement CSS Grid maximise d'abord les pistes non
-// flexibles (les deux colonnes latérales, jusqu'à 280+320=600px combinés,
-// algorithme standard de dimensionnement CSS Grid) avant de donner quoi que
-// ce soit à la piste `fr` (la colonne centrale `work`) — donc à 641px, la
-// colonne centrale n'hérite que de 641-600=41px, quel que soit l'écran qui
-// s'y trouve. Ce n'est pas propre à 641px : toute largeur sous ~600px + la
-// largeur minimale réelle du contenu de la colonne centrale subit la même
-// famine (plausiblement jusqu'à ~1000px+ selon l'écran, ex. une fenêtre
-// desktop en demi-écran) — un vrai chantier de layout sur TriptychLayout
-// lui-même (colonnes latérales/centrale), partagé par les neuf familles
-// SP-30, pas un simple ajustement de seuil. Chaque entrée ci-dessous cite le
-// nombre d'offenseurs réellement mesuré par le check corrigé de cette tâche
-// (settle-poll, pas le premier échantillon) — cf. CLAUDE.md, entrée SP-30l,
-// pour le suivi.
-const WIDE_BOUNDARY_ROOT_CAUSE =
-  "TriptychLayout : la colonne centrale (work) est affamée par les maximums des colonnes latérales (280+320=600px) jusqu'à ce que le viewport les dépasse largement — mécanisme partagé, cf. commentaire WIDE_BOUNDARY_ROOT_CAUSE. Hors périmètre de cette tâche : chantier de layout distinct, tracké CLAUDE.md/SP-30l.";
+// SP-33 (docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md)
+// a donné à la colonne centrale (work) de TriptychLayout.tsx un plancher
+// CSS explicite (minmax(360px,1fr), au lieu d'un `1fr` nu sans plancher
+// réel) et relevé le seuil de useNarrowViewport.ts en conséquence (899px)
+// — la famine de colonne centrale documentée par la revue transverse SP-30l
+// (round 2, 2026-09-02) est corrigée. Seul l'écran Cartes conserve un
+// wideBoundaryKnownIssue, pour deux défauts distincts et pré-existants,
+// sans rapport avec ce mécanisme (cf. son entrée ci-dessous).
```

- [ ] **Step 5: Update the top-of-file constants and their comment**

```diff
 const NARROW_WIDTH = 390;
 const NARROW_HEIGHT = 844;
-// Premier viewport "large" sous le nouveau seuil de useNarrowViewport.ts
-// (NARROW_QUERY = "(max-width: 640px)") — le point de vérification demandé
-// par la revue transverse SP-30l (finding 2) : 640px seul ne prouve rien,
-// il faut vérifier que la grille triptyque tient bien juste au-dessus du
-// seuil, pas seulement loin en-dessous.
-const WIDE_BOUNDARY_WIDTH = 641;
+// Premier viewport "large" sous le seuil de useNarrowViewport.ts
+// (NARROW_QUERY = "(max-width: 899px)", relevé par SP-33 — cf.
+// docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md)
+// — le point de vérification demandé par la revue transverse SP-30l
+// (finding 2), reconduit par SP-33 au nouveau seuil : le seuil seul ne
+// prouve rien, il faut vérifier que la grille triptyque tient bien juste
+// au-dessus, pas seulement loin en-dessous.
+const WIDE_BOUNDARY_WIDTH = 900;
 const WIDE_HEIGHT = 900;
```

(this makes permanent the change already made ad hoc in Step 2)

- [ ] **Step 6: Update the comment block before the wide-boundary test loop**

```diff
 // Revue transverse SP-30l (finding 2) : le seuil est passé de 390px à 640px
 // parce que la grille triptyque desktop clippait encore du contenu de ~391px
-// à ~540px. Ce groupe vérifie que 641px — le premier viewport classé "large"
-// sous le nouveau seuil — rend la grille trois colonnes sans contenu clippé.
-// Pas d'assertion BottomNav/onglets ici : à 641px le mode large (DomainBar +
-// grille) est attendu, pas le mode étroit.
+// à ~540px. Ce groupe vérifie que le premier viewport classé "large" sous
+// le seuil courant rend la grille trois colonnes sans contenu clippé. Pas
+// d'assertion BottomNav/onglets ici : au-dessus du seuil, le mode large
+// (DomainBar + grille) est attendu, pas le mode étroit.
 //
 // Round 2 (2026-09-02) : une fois le check lui-même corrigé pour mesurer
 // l'état stabilisé (cf. expectNoClippedContent ci-dessus) plutôt que le
-// premier échantillon, la majorité de ces tests échouent pour de vrai —
-// cf. wideBoundaryKnownIssue sur chaque écran concerné dans SCREENS
-// ci-dessus pour le nombre d'offenseurs réellement mesuré et le mécanisme
-// partagé (WIDE_BOUNDARY_ROOT_CAUSE). Seuls Tâches/Paramètres (aucune
-// grille TriptychLayout ne s'y rend) passent pour de vraies raisons.
+// premier échantillon, la majorité de ces tests échouaient pour de vrai à
+// l'ancien seuil (640px).
+//
+// SP-33 (docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md) :
+// plancher explicite sur la colonne centrale + seuil relevé à 899px
+// (WIDE_BOUNDARY_WIDTH = 900 ci-dessus) — tous les écrans passent
+// désormais sans wideBoundaryKnownIssue, sauf Cartes (2 offenseurs
+// pré-existants et distincts, sans rapport avec ce chantier, cf. son
+// entrée dans SCREENS) et Tâches/Paramètres (aucune grille
+// TriptychLayout ne s'y rend, jamais concernés).
```

- [ ] **Step 7: Update the mid-band regression test**

```diff
-// Task 3 (round 2 de correction, 2026-09-02) : rien ne protège la valeur du
-// seuil elle-même — sans ce test, revenir NARROW_QUERY à "(max-width: 390px)"
-// (l'ancien seuil) dans useNarrowViewport.ts laisserait toute la suite
-// committée verte, puisque les groupes 390px/641px ci-dessus ne testent
-// jamais un viewport à l'intérieur de la bande 391-640px. 500px est choisi à
-// l'intérieur de cette bande : sous le seuil actuel (640px) il doit rendre
-// le mode ÉTROIT (BottomNav "Navigation" + onglets), pas la grille desktop
-// (DomainBar "Domaines", aucun role="tab"). Si le seuil régressait sous
-// 500px, AppLayout.tsx basculerait sur DomainBar et TriptychLayout.tsx sur
-// sa grille — ce test échouerait pour de vrai (vérifié : DomainBar/BottomNav
-// utilisent des libellés aria-label distincts, "Domaines"/"Navigation",
-// catalog.fr.ts:48-49 — pas une coïncidence de sélecteur).
-test("500 px (bande 391-640, sous le seuil relevé) : mode étroit, pas la grille desktop", async ({
+// Task 3 (round 2 de correction SP-30l, puis SP-33) : rien ne protège la
+// valeur du seuil elle-même — sans ce test, régresser NARROW_QUERY vers son
+// ancienne valeur laisserait toute la suite committée verte, puisque les
+// groupes 390px/900px ci-dessus ne testent jamais un viewport à l'intérieur
+// de la bande 391-899px. 700px est choisi à l'intérieur de cette bande :
+// sous le seuil actuel (899px) il doit rendre le mode ÉTROIT (BottomNav
+// "Navigation" + onglets), pas la grille desktop (DomainBar "Domaines",
+// aucun role="tab"). Si le seuil régressait sous 700px, AppLayout.tsx
+// basculerait sur DomainBar et TriptychLayout.tsx sur sa grille — ce test
+// échouerait pour de vrai (vérifié : DomainBar/BottomNav utilisent des
+// libellés aria-label distincts, "Domaines"/"Navigation",
+// catalog.fr.ts:48-49 — pas une coïncidence de sélecteur).
+test("700 px (bande 391-899, sous le seuil relevé) : mode étroit, pas la grille desktop", async ({
   page,
 }) => {
-  await page.setViewportSize({ width: 500, height: 900 });
+  await page.setViewportSize({ width: 700, height: 900 });
   await mockCore(page);
   await page.goto("/");
```

- [ ] **Step 8: Run the full file one final time**

Run (from `shell/`): `npx playwright test e2e/triptych-narrow.spec.ts`
Expected: every test PASSES except the deliberate `test.skip()` on Cartes's 900px case (and the always-skipped-nothing Tâches/Paramètres, which never had a `wideBoundaryKnownIssue` to begin with — they simply pass, no grid to check). Confirm via `test-results/.last-run.json`.

- [ ] **Step 9: Commit**

```bash
cd shell
git add e2e/triptych-narrow.spec.ts
git commit -m "test(e2e): reflète la correction SP-33 dans triptych-narrow.spec.ts"
```

---

### Task 4: Fix the stale sibling comment, run the full suite, update CLAUDE.md

**Files:**
- Modify: `shell/e2e/item-detail-panels.spec.ts:33-34,49-50`
- Modify: `/home/lenen/projets/geostudio/CLAUDE.md`

**Interfaces:**
- Consumes: the final, verified `center_min`/threshold values from Task 3.
- Produces: nothing — this is the closing task.

- [ ] **Step 1: Fix the two stale comments**

In `shell/e2e/item-detail-panels.spec.ts`, both occurrences of this comment (lines ~33-34 and ~49-50):

```diff
-  // 390px : largeur de téléphone étroit représentative, confortablement
-  // sous le seuil de useNarrowViewport.ts (640px depuis la revue transverse
-  // SP-30l) — pas une borne à défendre au pixel près.
+  // 390px : largeur de téléphone étroit représentative, confortablement
+  // sous le seuil de useNarrowViewport.ts (899px depuis SP-33, cf.
+  // docs/superpowers/specs/2026-09-02-sp33-triptychlayout-colonne-centrale-design.md)
+  // — pas une borne à défendre au pixel près.
```

- [ ] **Step 2: Run the full Vitest suite**

Run (from `shell/`): `rm -rf dist dist-export && npx vitest run --coverage`
Expected: all tests pass, no regressions vs. the pre-SP-33 baseline (222 fichiers/1839 tests + the 2 new unit tests from Tasks 1-2, per CLAUDE.md's last recorded shell count). Coverage ≥ 88.

Run: `node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold`
Expected: exits 0.

- [ ] **Step 3: Run the full Playwright suite (not just the touched files)**

Run (from `shell/`): `npm run e2e`
Expected: no failures beyond the deliberate, documented `test.skip()` count. Read `test-results/.last-run.json` for the authoritative summary — do not trust a truncated `list` reporter tail on a run this long (CLAUDE.md, SP-31 entry, piège méthodologique).

- [ ] **Step 4: Confirm no OpenAPI/TS-types regeneration is needed**

Run (from the repo root): `git diff --stat main -- core/`
Expected: empty output — this plan never touched anything under `core/`, so there is no route or model change and nothing to regenerate (CLAUDE.md piège n°1 is about forgetting a real change, not about running the regen command unconditionally; confirm the premise instead of skipping the check itself).

- [ ] **Step 5: Update CLAUDE.md**

Read the current `### À venir` section's SP-30 entry and `### Livré` section in `/home/lenen/projets/geostudio/CLAUDE.md` immediately before editing (another concurrent session may have touched this file since this plan was written — CLAUDE.md piège n°9). Then:

1. Remove the `**SP-30 n'est PAS clos**` bullet from `### À venir` (the `TriptychLayout` blocker it describes is now fixed).
2. Add a `### Livré` entry for SP-33, in the same style as neighboring entries, summarizing: the center-column CSS floor (`minmax(360px,1fr)` or the final tuned value from Task 3), the raised threshold (`899px` or final tuned value), the explicit exclusion of the two pre-existing Cartes defects, the final E2E/Vitest counts observed in Steps 2-3, and the fact that SP-30 can now be redeclared closed.
3. If nothing else currently blocks SP-30 per the rest of that `### À venir` entry (re-read it fully — it may list other, unrelated open items for SP-30 beyond the layout defect), state explicitly in the new SP-33 entry whether SP-30 is now fully closed or what (if anything) remains.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/e2e/item-detail-panels.spec.ts CLAUDE.md
git commit -m "docs: clôt le blocage SP-30 — SP-33 (colonne centrale TriptychLayout) livré"
```
