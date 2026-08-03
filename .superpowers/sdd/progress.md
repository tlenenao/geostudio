# SP-14h — Carte analytique : symbologie pilotée par dataset — Progress Ledger

Plan: docs/superpowers/plans/2026-08-03-sp14h-carte-analytique.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@02cb9a5 (plan + spec SP-14h committés).

Note : ce fichier remplace le ledger SP-14g (complet, revue finale
ready-to-merge, HEAD=5e63346) — même fichier scratch réutilisé par
convention du dépôt ; contenu SP-14g préservé dans l'historique git.

## Pré-vol

Scan des 4 tâches (1: `mapSymbology.ts` pure function — détection géométrie,
expressions de peinture MapLibre, spec de légende ; 2: `MapLayer.renderAs`
additif honoré par `MapView` ; 3: widget `map` — encodings couleur/taille,
requêtes de domaine, overlay légende ; 4: E2E légende catégorielle,
légende numérique couleur+taille, non-régression cross-filter pk, no-op
sans encodings) contre les 8 contraintes globales (zéro changement à
core/itemClient.ts/DataSourcePanel.tsx/LayersPanel.tsx/MapEditorPage.tsx/
MapLegend.tsx — seuls fichiers partagés touchés : types.ts + MapView.tsx ;
`renderAs` optionnel additif, défaut "fill" ; `encodings.size` ne produit
`circle-radius` que pour une géométrie point ; palette fixe 8 couleurs
catégorielle + rampe fixe 2 stops numérique + interpolation linéaire
uniquement, rayon cercle 4-24px, pas de palette configurable ni classes
en v1 ; domaine min===max → constante, jamais un `interpolate` à deux
stops identiques ; requêtes de domaine déclenchées seulement si
`ctx.data.datasetId` présent ; UI en français ; en-tête SPDX ; commits
conventionnels avec suffixe (SP-14h)) : pas de contradiction. Le plan
fournit du code complet et littéral pour chaque tâche (types,
implémentation, tests unitaires, E2E) — transcription + tests, pas de
conception à faire, comme SP-14e/14f/14g. Dépendances d'interface notées :
Task 3 consomme `detectGeometryKind`/`buildMapPaint`/`buildLegend`/types
(Task 1) et `MapLayer.renderAs` (Task 2) ; Task 4 exerce l'UI réelle
produite par Tasks 1-3 (widget "Carte", champs PropsPanel "Champ
couleur"/"Type de couleur"/"Champ taille"). Tâches exécutées dans l'ordre
du plan (1→4). Task 1 et Task 2 sont mutuellement indépendantes d'après
le plan (Task 2 "Consomme: rien de Task 1") mais exécutées séquentiellement
par convention de cette skill (jamais deux implémenteurs en parallèle).

Poursuite sans confirmation utilisateur (scan de contradictions clean).

## Tasks

Base Task 1: 02cb9a5
Task 1: complete (commit 0763e7d, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). `mapSymbology.ts`
(module pur, zéro import) : `detectGeometryKind` (Point/MultiPoint→point,
LineString/MultiLineString→line, sinon→polygon, y compris undefined/null) ;
`buildMapPaint` (match catégoriel avec couleur par défaut en fin de liste,
palette 8 couleurs cyclique via modulo, interpolate linéaire 2 stops pour
numérique, constante si min===max, circle-radius 4-24px uniquement quand
renderAs==="circle") ; `buildLegend` (miroir de buildMapPaint, section size
seulement si geometryKind==="point"). 14/14 tests, sortie propre. 2 Minor
notés (non bloquants) : la branche `renderAs==="line"` → `"line-color"`
n'est pas exercée par un test direct (couverture indirecte seulement) ;
léger écart cosmétique de décompte de lignes dans le rapport de
l'implémenteur (116 vs 117 réel, 127 vs 118 réel).

Base Task 2: 0763e7d
Task 2: complete (commits 99475c6 puis fix 326dd04, 1 round de fix — le
premier passage a trouvé un Important). `MapLayer` (kind "feature") gagne
`renderAs?: "fill"|"circle"|"line"` (types.ts), 3 nouveaux tests MapView
(circle/line/défaut fill). Défaut trouvé en revue : le code littéral
du brief pour MapView.tsx (`map.addLayer({..., type: layer.renderAs ??
"fill", ...})`) ne compile pas — le type `AddLayerObject` de MapLibre est
une union discriminée par la valeur littérale de `type`, et passer une
variable typée union (`"fill"|"circle"|"line"`) échoue `tsc --noEmit`
(TS2345), alors que chaque littéral seul compile. Bug réel dans le code
littéral du plan (pas un choix de conception délibéré), donc corrigé sans
interrompre l'exécution (pas un cas "plan-mandated" au sens du garde-fou
de la skill — la sémantique requise par le plan, `renderAs ?? "fill"` par
défaut, est préservée à l'identique ; seule la mécanique TypeScript
change). Fix : `switch` sur `layer.renderAs ?? "fill"`, un appel
`map.addLayer` par branche avec un littéral de chaîne unique. Re-revue :
✅ spec compliant, Approved, `tsc --noEmit` et 21/21 MapView.test.tsx
re-vérifiés indépendamment par le reviewer. 2 Minor notés (non
bloquants) : duplication cosmétique de `source`/`paint` entre les 3
branches du switch (factorisable via un objet `common` partagé, non
requis) ; le 3e test (défaut fill) était déjà vert avant le changement
(couverture de non-régression, pas preuve de logique nouvelle).

Base Task 3: 326dd04
Task 3: complete (commit e05744e, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). Widget `map`
étendu : PropsPanel avec "Champ couleur"/"Type de couleur"/"Champ taille"
(français, conventions labelCls/inputCls comme pivot.tsx/sliderFilter.tsx) ;
`useNumericDomain` partagé entre couleur numérique et taille (requête
statistics `measures` min/max) ; requête catégorielle séparée (`groupBy`) ;
les 3 `useQuery` toujours appelés avant le early-return d'erreur (pas de
violation de l'ordre des hooks) ; délégation complète à `mapSymbology.ts`
(Task 1) pour `buildMapPaint`/`buildLegend`/`detectGeometryKind` — aucune
réimplémentation locale ; `MapLayer.renderAs`/`paint` (Task 2) consommé
sans cast. Intégration cross-tâche vérifiée par le reviewer (signatures
Task 1 et Task 2 tracées jusqu'aux points d'appel réels). Contrairement à
Task 2, le code littéral du brief a compilé et testé sans aucune
correction (`tsc --noEmit` et 15/15 `mapWidget.test.tsx` re-vérifiés
indépendamment par le reviewer, pas seulement le rapport de
l'implémenteur). 792/792 suite complète. 2 Minor notés (non bloquants) :
aucun test widget n'exerce la légende combinée couleur+taille en même
temps (couverture indirecte seulement via mapSymbology.test.ts de Task 1,
pas un gap sur le comportement requis) ; `detectGeometryKind` n'inspecte
que la géométrie du premier enregistrement (raisonnable pour des couches
GeoJSON homogènes, non documenté par un commentaire local — la
justification vit dans mapSymbology.ts).

Base Task 4: e05744e
Task 4: complete (commit 000f141, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant). 4 scénarios
E2E ajoutés en append-only à `analytics-context.spec.ts` (confirmé par le
reviewer au niveau de l'octet : 1 seul hunk, 0 suppression, 247
insertions) : scénario 22 couleur catégorielle (légende via `groupBy`) ;
scénario 23 couleur+taille numériques (légende à deux domaines
`measures` séparés) ; scénario 24 non-régression cross-filter pk sur
entité stylée ; scénario 25 aucune requête de domaine sans encodings
configurés. **1 déviation divulguée** dans le scénario 24 : le clic figé
à timing fixe du brief courait après le pipeline WebGL asynchrone réel
de MapLibre (le handler `click` ne se déclenche qu'une fois la feature
peinte), causant des timeouts intermittents sous charge parallèle — fix
en boucle de retry bornée (10×1s) dans le test uniquement, jamais dans
l'implémentation (Tasks 1-3). Reviewer a vérifié la solidité de cette
déviation ligne à ligne contre le code réel de cross-filter
(`AnalyticsContext.tsx`) et de handler de clic (`MapView.tsx`) : la
boucle ne peut pas masquer une vraie régression (handler cassé → throw
explicite ; mauvais id → même throw ; clic manqué → idempotent sans
effet ; les assertions finales après la boucle re-vérifient
indépendamment l'état DOM réel, donc un faux succès de boucle serait
quand même intercepté). 1 Minor noté (non bloquant) : la justification
d'idempotence dans le commentaire/rapport survend légèrement (un clic
qui touche réellement une feature déjà peinte peut bien basculer le
toggle `isToggleOff` — la boucle reste sûre en pratique car elle
s'arrête au premier match observé, mais la formulation mériterait d'être
resserrée) ; la déviation dépasse à la lettre la catégorie
"ajustement de sélecteur/assertion" pré-autorisée par le brief mais a
été divulguée de façon transparente. 76/76 E2E complet, 792/792 unitaire,
build propre. 20 exécutions répétées sous charge parallèle sans échec
après le fix.

## SP-14h COMPLET — 4 tâches, 5 commits de tâches (0763e7d, 99475c6,
## 326dd04 [fix], e05744e, 000f141), 1 round de fix (Task 2, bug de
## compilation réel dans le code littéral du plan, corrigé et re-revu).
## HEAD=000f141, prêt pour la revue finale de branche.

## Revue finale de branche (opus, 02cb9a5..000f141, 5 commits) —
## 1 Critical, 0 Important, 2 Minor, PAS prêt à merger (No).
## Bug confirmé : `useNumericDomain` (mapWidget.tsx) envoie des mesures
## `min`/`max` sans `label`, alors que le cœur réel (`aggregate.py`,
## `_measure_label`) calcule la clé d'une mesure non étiquetée comme
## `f"{agg}_{field}"` (ex. `min_montant`), jamais `min`/`max` bruts — la
## couleur numérique et la taille s'effondrent silencieusement en
## constante (domaine {0,0}) contre le vrai backend. Masqué par les deux
## niveaux de mock (unitaire ET E2E) qui renvoient directement la forme
## `{min, max}` sans validation de label. Fix attendu : ajouter
## `label: "min"`/`label: "max"` comme le fait déjà sliderFilter.tsx.
## 2 Minor : scénario E2E 25 ("sans encodings") ne promeut jamais sa
## source donc n'a pas de datasetId — passe pour la mauvaise raison ;
## branche `line-color` de mapSymbology.ts non testée. Dispatch d'un
## fixer unique couvrant les 3 findings (Critical + 2 Minor).

## Fix (commit eadbdd7) : label: "min"/label: "max" ajoutés aux 2
## mesures de useNumericDomain (mapWidget.tsx, un seul helper partagé
## par couleur numérique ET taille — le fix corrige les deux d'un coup) ;
## promoteLastSource(page, 1) ajouté au scénario E2E 25 ; test
## line-color ajouté à mapSymbology.test.ts. 3 fichiers, 18
## insertions/1 suppression. 30 tests ciblés + 793 suite unitaire + 76/76
## E2E + build propres.

## Re-revue finale (opus, 02cb9a5..eadbdd7, 6 commits) — les 3 findings
## re-vérifiés FIXÉS indépendamment (pas seulement le rapport du fixer) :
## label fix confirmé contre le vrai _measure_label du cœur
## (core/app/analytics/aggregate.py:132-133, honore label explicite
## comme clé de réponse) et symétrique (un seul helper useNumericDomain
## partagé par couleur numérique et taille) ; scénario 25 re-exécuté
## isolément (24.7s, vert) et confirmé qu'il teste bien "sans encodings"
## et non "sans dataset" (datasetId vient de la config de source,
## indépendant de la route /configs/by-item/... absente dans ce
## scénario) ; test line-color confirmé non-vacueux (assertion sur
## l'expression match complète). 0 Critical, 0 Important, 1 Minor
## cosmétique (scénario 25 pourrait ajouter la route /configs/by-item/
## dataset-1 par cohérence structurelle avec 22-24, non bloquant).
## READY TO MERGE (Yes, sans réserve).
## SP-14h READY TO MERGE — prêt pour finishing-a-development-branch.
## HEAD=eadbdd7.
