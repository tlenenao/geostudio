# SP-25 — Symbologie dans l'éditeur de cartes — Progress Ledger

Plan: docs/superpowers/plans/2026-08-23-sp25-symbologie.md
Spec: docs/superpowers/specs/2026-08-23-sp25-symbologie-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).

## Note de reprise

Ledger précédent trouvé au démarrage : SP-20 (clos depuis longtemps,
CLAUDE.md à jour jusqu'à SP-24 inclus). Repartant de zéro pour SP-25.
`git log` confirme aucun commit d'implémentation SP-25 (seuls la spec et
le plan sont committés : 401deec, bb3806f). Fichiers non liés trouvés
modifiés dans l'arbre de travail au démarrage (`.superpowers/sdd/task-13-*`,
`task-14-*`) : contamination résiduelle d'une session SP-23 antérieure,
non commitée, sans rapport avec SP-25 — ignorés, pas touchés tant que
cette exécution n'atteint pas ses propres tâches 13/14 (le script
task-brief les écrasera alors avec le contenu SP-25 correct).

## Pre-flight plan review

13 tâches. Le plan documente lui-même 4 déviations vis-à-vis de la spec
committée, déjà tranchées dans le texte du plan (§Global Constraints) —
pas des contradictions à re-soumettre. Aucune contradiction supplémentaire
trouvée entre tâches ou avec les Global Constraints. Task 13 est un
"validation gate" (pas de code) qui recouvre la revue finale de branche du
process de cette skill — ordre retenu : Tasks 1-12 (implémenteur+reviewer),
puis revue finale de branche (code-reviewer), fixes, re-revue, puis Task 13
en dernier (elle re-vérifie tout, y compris les fixes de la revue finale,
et rédige l'entrée CLAUDE.md qui doit refléter cette revue finale aussi).

## Tâches

Task 1: complete (commits bb3806f..d98a3ef, review clean après 1 passe de
fix). `core/app/analytics/aggregate.py` : capacité `sample` sur
`AggregateRequestBody`/`run_collection_aggregate` (`USING SAMPLE n ROWS`,
validation 1-2000, exclusif de groupBy/bins), fix latent trouvé par
l'implémenteur en chemin (category_key mal calculé pour bins/sample sur
collection vide). 2 Important en revue : (1) évidence de suite complète
manquante dans le rapport — le premier fix a rejoué la suite sans
`CORE_TEST_DATABASE_URL`, skippant silencieusement les 162 tests
`@postgis` (1714/167 au lieu de 1876/5) ; corrigé directement par le
contrôleur avec le bon DSN (`localhost:5433`, le conteneur postgis-test
était déjà up) — **1876 passed, 5 skipped, exactement +8 vs la référence
SP-24 (1868/5), 0 régression**. (2) test plan-mandaté
`test_sample_excludes_non_castable_values` ne testait pas ce que son nom
affirmait (fixtures parquet ne peuvent pas produire une valeur non
castable) — renommé, lacune du chemin `TRY_CAST(...) IS NOT NULL`
documentée par un commentaire plutôt que masquée par un faux test.

Task 2: complete (commits d98a3ef..4dc12ae, review clean après correction
d'évidence). `core/app/configs/schemas.py` : `MapLayer.symbology: dict |
None = None`, même précédent que `paint`/`popup`. L'implémenteur a
correctement suivi l'instruction du brief de trouver et reproduire le
vrai test de round-trip `popup` (SP-24, pas de route/HTTP — validation
Pydantic directe) plutôt que le contrat HTTP deviné du plan. 1 Important
en revue : décompte de suite finale incohérent (rapporté 1877 = 1876+1
alors que le diff ajoute 2 tests, pas 1) — vérifié directement par le
contrôleur : **1878 passed, 5 skipped, 0 régression**. Au passage,
2 exécutions manuelles successives de la suite complète (Task 1 puis
Task 2) contre le même conteneur `postgis-test` persistant ont pollué
son état (tables à nom fixe non nettoyées par
`test_pipeline_runtime.py::test_writer_dataset_*`/`test_use_case_3_*`,
sans rapport avec ce SP) — base de test réinitialisée
(`DROP/CREATE DATABASE gis_test` + extensions postgis/vector). **Leçon
retenue pour la suite de cette exécution : ne pas relancer la suite
complète du cœur de manière répétée contre ce même conteneur sans
nécessité — préférer se fier aux nombres rapportés par
l'implémenteur/reviewer et ne faire une vérification contrôleur complète
qu'aux points de contrôle naturels (fin de tâche en cas de doute réel,
revue finale de branche, Task 13).**

Task 3: complete (commit 6fc47cd, review clean — 0 issues). Régénération
mécanique `core/openapi.json` + `shell/src/api/generated/core-schema.d.ts`
(uniquement `sample`/`symbology` ajoutés, rien d'autre n'a dérivé, vérifié
par le reviewer champ par champ). Core reproduit exactement la référence
(1878 passed, 5 skipped, 0 failed) — base de test propre depuis la
réinitialisation de Task 2.

Task 4: complete (commit cef8385, review clean — 0 Critical/Important,
2 Minor cosmétiques : mauvaise étiquette "banker's rounding" dans le
rapport pour ce qui est en réalité un round-half-up JS standard ; n≤0 et
categorical n=1 non testés explicitement, corrects par inspection).
`shell/src/builder/widgets/palette.ts` : palettes curatées, rampe
séquentielle dérivée du thème, lerp RGB maison. Écart auto-résolu par
l'implémenteur (vérifié indépendamment par le reviewer, calcul rejoué à
la main) : le littéral de test du plan (`#7f7f7f`) contredisait le code
du plan lui-même (`Math.round(127.5)` en JS vaut 128, pas 127) — test
corrigé à `#808080` plutôt que le code, jugé non-escaladable (aucune
décision produit/design en jeu, transcription arithmétique du plan,
documenté explicitement dans le rapport). 160 fichiers / 1393 tests.

Task 5: complete (commit ece97e5, review clean — 0 issues, tout vérifié
contre le code réel par le reviewer, aucun écart). `ItemClient.sampleCollectionField`
(interface + implémentation réelle via `request<T>`/POST `/collections/
{id}/aggregate` + rejet `StaticItemClient` via `unsupported()`, même
gabarit que ~20 méthodes sœurs). Discipline de périmètre respectée : rien
de `LayerSymbology`/`mapSymbology.ts` (réservé à Task 6) dans ce diff.
Scaffolding de test réel (MSW), pas le sketch fetch-mock deviné du plan.
160 fichiers / 1395 tests.

Task 6: complete (commit c96aff8, review clean — 0 Critical/Important,
2 Minor non bloquants : croissance de fichier à 378 lignes déjà assumée
par le plan ; pas de test direct sur `jenksBreaks`/`computeColorDomain`
avec classes proche de la taille de l'échantillon, hors périmètre du
brief). Tâche la plus grosse/risquée du plan (l'algorithme Jenks/Fisher
en DP, extension de `buildMapPaint`/`buildLegend` existants). Reviewer a
vérifié indépendamment : Jenks DP rejoué dans un script Node isolé →
résultats identiques aux tests (`[1,2,52,102]`, ordre-invariant) ;
`buildMapPaint`/`buildLegend` structurellement additifs (chemin
`palette` undefined byte-identique au comportement pré-Task-6) ; les 15
tests préexistants intouchés dans le diff ; `npx vitest run` (31/31) et
`tsc --noEmit` rejoués par le reviewer lui-même, pas pris sur parole.
1 correction de valeur de test auto-résolue par l'implémenteur
(`#7f7f7f`→`#808080`), même précédent Task 4 (arrondi JS half-up),
re-vérifiée indépendamment, jugée non-bloquante. `MapLayer.symbology`
ajouté via `import(...)` type-only (pas de cycle de valeur). 160
fichiers / 1411 tests.

Task 7: complete (commit fc2808a, review clean — 0 Critical/Important,
2 Minor : import `LayerSymbology` non utilisé du plan silencieusement
retiré du fichier de test, correct mais non documenté ; asymétrie
structurelle mineure `PALETTE_OPTIONS`/branche `theme-primary` séparée).
`shell/src/map/MapSymbologyEditor.tsx` : éditeur partagé, host-agnostic
(aucun `ItemClient`/`useQuery` interne — vérifié par grep), même
précédent que `PopupEditor.tsx`. 1 contradiction réelle trouvée par
l'implémenteur entre le JSX illustratif du plan (sélecteur Palette
imbriqué dans `{color?.field && ...}`) et les tests littéraux du même
plan (tests 2/3 rendent sans field et attendent le label "Palette")
— rendue inconditionnelle, jugé correctement résolu par le reviewer
(même précédent Tasks 4/6 : le test littéral l'emporte sur le sketch
JSX, changement strictement plus permissif, documenté par un
commentaire de code pour les tâches 8/11). 161 fichiers / 1419 tests.

Task 8: complete (commit d07c64e, review clean — 0 Critical/Important,
1 Minor : légère simplification excessive dans le rapport sur le
mécanisme React exact du revert d'input contrôlé). `LayersPanel.tsx` :
`LayerSymbologyEditor`, même gabarit que `LayerPopupEditor` (SP-24),
limitation de périmètre assumée par le plan (couche `feature`/`vector`
sans `collectionId` → `null`) vérifiée correcte. 1 test littéral du plan
cassé par construction (onChange `vi.fn()` nu sur une interaction
multi-étapes qui suppose un round-trip d'état réel) — corrigé par un
petit wrapper `SymbologyHost` (useState) en scaffolding de test
seulement, code de production intouché, idiome RTL standard déjà établi
dans ce dépôt (`PopupEditor.test.tsx`), vérifié mécanisme par mécanisme
par le reviewer contre le vrai host de prod (`MapEditorPage.tsx`) — jugé
non-escaladable. 161 fichiers / 1420 tests.

Task 9: complete (commit bb34450, review clean -- 0 Critical/Important,
1 Minor documente explicitement, pas un defaut a corriger ici : une
couche vector a geometrie mixte/inconnue avec symbology ne stylise
que sa sous-couche polygon, jamais point/line en meme temps -- car
effectivePaint() calcule un seul objet paint pour un seul renderAs
devine, exactement ce que la prose de l'etape 4 du plan decrit et
accepte, pas une regression du reviewer). MapView.tsx :
effectivePaint() (le paint effectif d'une couche vient de sa
symbology compilee quand elle est presente, sinon layer.paint
inchange -- zero appel reseau, domaine deja fige), cable dans les
branches vector ET feature sans toucher au decoupage en
sous-couches par type de geometrie de SP-24 (I1). Ecart du placeholder
litteral du plan (geometryKind fixe a "polygon" pour feature)
suivi par sa propre prose plutot que son code, verifie par le reviewer
comme l'inverse exact du mapping interne de buildMapPaint
(round-trip confirme dans les deux sens). 161 fichiers / 1421 tests.

Task 10: complete (commit c82f442, review clean -- 0 issues). Deux
chemins de theme threades : editeur (AppBuilderPage -> PropsPanel ->
def.PropsPanel, draft.theme) et rendu (AppRenderer -> WidgetHost ->
WidgetContext.theme -> def.Component, config.theme). Discipline de
perimetre verifiee independamment par le reviewer (grep sur tout le
depot des sites <WidgetHost>/<PropsPanel> : exactement 5 et 2, seuls
les deux sites top-level nommes par le brief portent theme= ; tabs/
drawer/modal/LayoutEditor intouches). Chainage bout-en-bout confirme
sans maillon intermediaire manquant. Flake signale par l'implementeur
(MapEditorPage.test.tsx, cas exportRender) verifie sans lien causal
possible (zero import des fichiers touches) -- flake pre-existant,
pas une regression. 161 fichiers / 1423 tests.

Task 11: complete (commit e2a0a74, review clean -- 0 Critical/Important,
1 Minor : pas de test mapWidget.test.tsx dedie a la nouvelle branche de
legende "classed", couverte seulement au niveau unitaire buildLegend --
gap reel mais bas risque, note non bloquant). Deuxieme plus gros
chantier du plan, changement cassant assume (une config deja publiee
avec props.encodings perd sa symbologie au prochain chargement).
mapWidget.tsx : PropsPanel/Component reecrits, props.encodings/
useNumericDomain/les deux useQuery de domaine supprimes (verifie par
grep, zero occurrence residuelle). Trois points a haut risque
verifies independamment par le reviewer, pas pris sur parole : (1)
zero appel reseau au rendu -- Component ne lit que props.symbology
gele, seul queryDataSource restant est dans PropsPanel (auteur, sur
clic) ; (2) round-trip theme-primary reellement fonctionnel entre
apercu editeur et rendu reel, prouve par un test non-vacueux (mock
MapView serialise le paint calcule) ; (3) Jenks leve une erreur
visible (role="alert") sans jamais bloquer le bouton (finally
toujours execute) -- ajout retroactif d'un etat error a
MapSymbologyEditor.tsx (Task 7), les 8 tests d'origine confirmes
byte-identiques (diff purement additif). 161 fichiers / 1426 tests.

Task 12: E2E spec written (shell/e2e/map-symbology.spec.ts) and merged
via 3 commits (52bd33e fix, ffaf0ac test, 318dd3d test-fix), NOT YET
REVIEWED (checkpoint interrupt -- review package written to
.superpowers/sdd/review-e2a0a74..318dd3d.diff, reviewer not yet
dispatched). Summary of what happened: implementer went BLOCKED on a
real production bug found empirically -- toFrontLayer() (itemClient.ts
read path for GET /configs/{id}) never carried MapLayer.symbology back
to the front end, unlike popup/collectionId/geometryKind/pkColumn (same
bug class as SP-24's popup fix). Fixed (52bd33e) + regression test
(RED->GREEN verified via git stash). E2E spec then passed and committed
(ffaf0ac). Full E2E run then surfaced a SECOND real regression,
unrelated to the fix above: 3 pre-existing analytics-context.spec.ts
(SP-14h) tests broke because Task 11's breaking change (props.encodings
-> props.symbology, explicit "Recalculer les classes"/"Recalculer la
taille" required before domain is frozen) was never exercised against
this E2E file by Task 11 itself (only unit tests were run there).
Root-caused (categorical domain stays {values:[]} without an explicit
recompute click -> degenerate MapLibre paint expression -> layer
silently fails to render, per this repo's existing try/catch pattern),
confirmed via disposable worktree at e2a0a74 that the failures pre-date
Task 12's own work, then fixed by adding the missing recompute clicks
to the 3 stale tests (318dd3d) -- production code untouched, only the
E2E interaction sequence updated to match the intentional new UX.
**Full E2E suite restored to 108 passed, 4 skipped, 0 failed** (SP-24
baseline 107 + this plan's new spec = 108, exact match). Unit suite 161
files / 1427 tests, build clean.

Task 12: complete (commits e2a0a74..318dd3d, review clean -- spec ✅,
task quality Approved, 0 Critical/Important). Reviewer independently
verified: 318dd3d touches only shell/e2e/analytics-context.spec.ts (23
insertions, 0 deletions, test-only, no assertion weakened -- new clicks
added on top of untouched pre-existing final assertions); 52bd33e's
RawMapLayer.symbology fix mirrors the SP-24 popup/collectionId/
geometryKind/pkColumn conditional-spread pattern exactly, same
inline import(...) typing discipline as the sibling popup field; the
new E2E spec matches the brief's acceptance criteria with real
(non-fabricated) selectors verified against MapSymbologyEditor.tsx/
LayerPicker.tsx/map-editor.spec.ts; the itemClient.test.ts regression
test is non-vacuous (full LayerSymbology round-trip, toEqual on the
whole layer, real RED->GREEN evidence via git stash). Full E2E suite
restored to 108 passed, 4 skipped, 0 failed (SP-24 baseline 107 + new
spec = 108). Task 12 alone found and fixed 2 real bugs beyond its own
scope (both invisible to any task-by-task review before it, since it's
the first point in the plan that runs full E2E): the toFrontLayer read
bug (same class as SP-24 popup) and the analytics-context.spec.ts
SP-14h regression (Task 11's own breaking change never exercised
against that E2E file).

## Final whole-branch review (bb3806f..318dd3d, opus)

1 Critical (C1) + 6 Important (I1-I6) + 11 Minor (M1-M11). C1: an
unrecomputed/degenerate color-or-size symbology domain (empty categorical,
cleared field with stale domain, or duplicate breaks from tied/constant
data) made buildMapPaint emit a MapLibre expression that throws at
addLayer, silently removed by MapView's own try/catch -- whole layer
vanishes, zero user signal. I1: quantileBreaksFromRow/jenksBreaks produced
NaN/undefined breaks on empty/small collections, silently serialized as
null. I2: MapSymbologyEditor's datalist id was a global constant, breaking
field autocomplete with 2+ styled layers (same class as SP-23 I2 -- a
guard written on one surface, not carried to its twin, PopupEditor already
had useId()). I3: recomputeSize had no catch (recomputeColor did). I4:
effectivePaint computed one paint object per layer for a guessed geometry
kind, so a mixed-geometry tiled layer (SP-24 I1's 3-sublayer split) only
ever got fill-* paint -- circle-/line- sublayers silently unstyled. I5:
mapWidget's runStatistics hardcoded layer:"" and had no fallback when
datasetId is absent (a plain collection-backed source), and offered Jenks
where it can't work (no collectionId wiring on that host, plan-sanctioned
scope limit, but the option should've been hidden). I6: a ~25%-flaky
MapEditorPage.test.tsx (unrelated to SP-25, pre-existing, but a red gate on
this branch's merge).

Also reviewer-verified as solid: sample capability's SQL-injection-safe
field validation + row bounds, OpenAPI/TS types genuinely regenerated
(re-ran export_openapi.py independently, zero diff), backward-compat
strategy in mapSymbology.ts (all 15 pre-existing tests byte-identical),
Task 12's own two-bug discovery.

**Fix round 1** (commit 014bd04): all 7 (C1+I1-I6) addressed in one pass.
161 files / 1454 tests (+27), tsc/eslint/prettier/build clean, E2E
108/4/0 (baseline match), RED->GREEN evidence for C1 via targeted git
stash of mapSymbology.ts (17 failures pre-fix -> 0 post-fix), I6's flake
re-run 10/10 green in a loop.

**Re-review** (opus): 6/7 CLOSED correctly (I1-I6). C1 PARTIALLY CLOSED --
found a boundary hole in round 1's own normalizeDomain dedup: a domain that
collapses to exactly 2 distinct breaks (1 class) still passed the guard
(only "<2 breaks" was rejected, not "<3"), and buildMapPaint turned that
into a MapLibre step expression with 2 arguments (minimum 4 required) --
reproduced empirically by the re-reviewer against the real
@maplibre/maplibre-gl-style-spec parser, same original C1 symptom via C1's
own trigger #3 (tied/constant data), realistic (any count/rating column
with enough values at the minimum). Also flagged 2 new Minor (N2: a
recompute that succeeds but yields an unusable domain, e.g. short jenks
sample, clears the "not yet computed" hint with no other signal; N3:
continuous numeric domains bypass normalizeDomain entirely, NaN min/max
serializes as null via JSON.stringify, same class as I1 on a different
code path) -- both logged, not fixed, same disposition as the Minor list
from the first pass.

**Fix round 2** (commit cacddb9, C-new only): normalizeDomain's dedup
threshold raised from <2 to <3 distinct breaks (Option A -- the shared
gate both buildMapPaint and buildLegend already call, so the fix is
symmetric by construction without touching buildLegend separately).
161 files / 1461 tests (+7), tsc/eslint/build clean. New tests reproduce
the re-reviewer's exact repro AND validate the produced/rejected paint
expression against the real @maplibre/maplibre-gl-style-spec
(createExpression), not just a shape assertion -- confirmed by the
controller reading the diff directly (minimal, 2 files, threshold change
+ comment update in mapSymbology.ts, 6 new non-tautological tests in
mapSymbology.test.ts). E2E not re-run for this narrow pure-function fix
(no DOM-visible surface), explicitly noted as such.

**0 Critical/Important open at this point.** Minor list carried forward
to Task 13's CLAUDE.md entry: M1-M11 from round 1 plus N2/N3 from the
re-review.

NEXT STEP ON RESUME: Task 13 (final validation gate + CLAUDE.md entry) --
re-verify everything including both fix rounds, then write the CLAUDE.md
entry, which must reflect: the 13 plan tasks, Task 12's two-bug discovery,
the final review's C1+I1-I6, both fix rounds (round 1 closing 6/7 + round
2 closing C1's boundary hole), and the carried-forward Minor list.
