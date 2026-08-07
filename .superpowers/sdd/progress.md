# SP-16a — Export serveur CSV/XLSX/GeoJSON/GPKG — Progress Ledger

Plan: docs/superpowers/plans/2026-08-07-sp16a-export-serveur.md
Spec: docs/superpowers/specs/2026-08-07-sp16a-export-serveur-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).
Base globale: dev@08b9342 (HEAD au lancement, immédiatement après commit du plan).

## Pré-vol

Scan des 13 tâches + Global Constraints contre l'état réel du repo (lecture
directe, pas confiance dans le plan seul) avant dispatch :
- `core/pyproject.toml` : `dependencies = [` ligne 6, entrée `duckdb>=1.0`
  ligne 51 confirmée comme point d'ancrage (Task 1).
- `core/app/analytics/duckdb_conn.py` : contenu intégral lu, `open_connection`
  confirmé, aucun `open_spatial_connection` existant (Task 1).
- `core/app/features/routes.py` : imports confirmés — `get_current_user` déjà
  importé ligne 20 (le plan anticipait de devoir l'ajouter, en fait déjà là),
  `RESERVED_QUERY_PARAMS` ligne 41, `aggregate_features`/`return
  {"categoryKey"...}` lignes 192/213 confirmées comme point d'insertion
  (Tasks 3/4).
- `core/app/harvest/routes.py` : imports fastapi/analytics confirmés,
  `get_dataset_arcgis_aggregate`/`return {"categoryKey"...}` lignes 268/300,
  `_MAX_LIMIT=1000`, `_resolve_arcgis_dataset`, `EgressBlockedError` tous
  confirmés présents (Tasks 5/6).
- `core/app/main.py` : `_AGGREGATE_PATH_RE` ligne 36, garde `read_only_guard`
  ligne 66-72 confirmés identiques au texte "avant" du plan (Task 7).
- `shell/src/api/types.ts` : `queryDataSource`/`featuresUrl` lignes 152-153,
  `DataSourceState` ligne 367 confirmés (Task 8).
- `shell/src/api/itemClient.ts` : `buildAggregateBody`/`_queryParams`/
  `resolveDataset`/`queryDataSource`/`getCollectionSchema` tous confirmés
  présents aux noms attendus (Task 8).
- `shell/src/builder/DataContext.tsx` : bloc `pkByCollection` confirmé
  identique au texte "avant" du plan (Task 9).
- `shell/src/builder/widgets/ExplorerMenu.tsx` : contenu intégral lu,
  confirmé identique au texte "avant" du plan, aucune prop
  resolvedSource/hasGeometry existante (Task 10).
- Les 6 call sites `<ExplorerMenu ... />` dans chart.tsx (x2)/data.tsx
  (x2)/indicator.tsx/mapWidget.tsx/pivot.tsx tous confirmés présents et
  identiques au texte "avant" du plan (Task 11).
- `shell/src/pages/DatasetEditPage.tsx` : `useItemClient`, `schemaQuery`,
  `draft.source`, section "Enregistrer les colonnes" confirmés présents
  (Task 12).

Aucune contradiction trouvée entre tâches ni avec les Global Constraints.
Poursuite sans confirmation utilisateur (scan clean).

Note : ledger précédent (SP-15h, déjà mergé sur dev, cf. commits
89bfc9f/dd74053/abd9b6c) écrasé ici — SP-15h est clos, ce fichier suit
maintenant SP-16a.

## Tasks (13 + final check)

1. `openpyxl` + `open_spatial_connection` — core
2. `app.analytics.export` (sérialisation CSV/XLSX/GeoJSON/GPKG) — core
3. `POST /collections/{id}/export` (agrégé) — core
4. `GET /collections/{id}/export/items` (entités brutes, 4 formats) — core
5. `POST /datasets/{id}/arcgis/export` (agrégé) — core
6. `GET /datasets/{id}/arcgis/export/items` (entités brutes, 4 formats) — core
7. Garde lecture-seule démo — exempte les routes d'export — core
8. `ItemClient.exportDataSource()` — shell
9. `DataContext` expose `resolvedSource`/`hasGeometry` — shell
10. `ExplorerMenu` gagne des entrées d'export — shell
11. Branche `resolvedSource`/`hasGeometry` sur les 6 widgets — shell
12. `DatasetEditPage` section Export — shell
13. E2E `dataset-export.spec.ts` — shell
14. Vérification finale + mise à jour CLAUDE.md

Base Task 1: 08b9342
Task 1: complete (commit 248bf92, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important, 2 Minor
négligeables (duplication de 2 lignes avec open_connection, choix
délibéré pour ne pas partager de base commune ; test env-vars ne prouve
pas que la fonction les ignorerait si présentes)). `openpyxl>=3.1` +
`open_spatial_connection()` (aucun accès disque/S3/env var) confirmés
verbatim contre le brief. 2/2 tests passing.

Base Task 2: 248bf92
Task 2: complete (commit 4b025d4, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important, 2 Minor
négligeables héritées verbatim du brief (DictWriter lève sur des rows
hétérogènes ; test GPKG round-trip écrit un chemin fixe /tmp sans
cleanup)). 1 déviation du code littéral du brief identifiée ET vérifiée
par le reviewer (pas du scope creep) : `ALTER TABLE t DROP COLUMN
OGC_FID` avant COPY vers GPKG — reviewer a reproduit indépendamment que
le code littéral du brief échoue réellement (IOException DuckDB, OGC_FID
auto-généré par ST_Read), confirmé que le DROP ne peut jamais supprimer
un champ utilisateur réel (un champ nommé pareil ferait déjà planter
CREATE TABLE une ligne plus tôt). 11/11 tests passing.

Base Task 3: 4b025d4
Task 3: complete (commit 684379e, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important, 3 Minor
négligeables (import features_to_format inutilisé jusqu'à Task 4 même
fichier, brief-mandaté ; RESERVED_QUERY_PARAMS+="format" sans effet sur
cette route précise, brief-mandaté ; _category_key jamais lu, style)). 1
déviation du texte littéral du brief identifiée ET vérifiée
indépendamment par le reviewer (bug du plan, pas de l'implémenteur) :
test `denies_a_user_without_read_access` attendait 403, corrigé en 404 —
`get_readable_collection` (core/app/collections/routes.py:133-151)
renvoie 404 aussi bien pour "collection absente" que "lisible refusée"
par construction ("404 avant 403"), reviewer a lu le code réel plutôt que
de faire confiance au rapport. Format validé avant tout accès
DB/DuckDB, audit_log écrit uniquement en cas de succès avec le payload
exact {"format", "mode": "aggregate"}. 6/6 nouveaux tests, suite complète
1192 passed/131 skipped.

Base Task 4: 684379e
Task 4: complete (commit caaeeec, review clean — ✅ spec compliant, task
quality Approved, 0 Critical/Important, 3 Minor négligeables (pas de
test à la borne exacte 10000 succès, seulement au-dessus via
monkeypatch ; pas de test multi-page réel, MAX_LIMIT=1000 jamais
dépassé par les fixtures ; docblock un peu long)). 3 déviations du texte
littéral du brief (DONE_WITH_CONCERNS), toutes vérifiées indépendamment
par le reviewer contre le code réel (pas seulement le rapport) : (1)
`"type": "Feature"` manquant dans les payloads POST du brief —
validate_feature() rejette sans, confirmé + comparé à d'autres fichiers
de test existants ; (2) champ `"pop"` manquant dans le test de cap —
requis par le fixture INFO, confirmé ; (3) fixture env étendue avec
`make_fake_items_repo()` + overrides get_features_repo/get_rls_scope
(RLS réel utilise set_config, absent de SQLite) — confirmé sans effet
sur les tests Task 3 (routes différentes, aucune dépendance partagée),
confirmé fidèle au comportement réel (pagination/cap testés pour de
vrai), confirmé reproduire fidèlement un patron déjà établi dans
test_features_routes_read.py (même forme SimpleNamespace, même
commentaire sur set_config). Boucle de pagination + cap 413
avant-troncature vérifiés ligne à ligne par le reviewer, borne exacte
correcte par inspection. 11/11 tests (fichier complet), suite 1197
passed/131 skipped.

Base Task 5: caaeeec
Task 5: complete (commit d1ad7eb, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important, 4 Minor
négligeables (client.close() jamais appelé sur les sorties d'erreur
précoces — préexistant dans la route sœur get_dataset_arcgis_aggregate,
pas une régression ; import features_to_format inutilisé jusqu'à Task 6 ;
~25 lignes dupliquées avec la route sœur, brief-mandaté ; un test
n'affirme que le status code sans la forme du détail d'erreur)). Aucune
déviation du texte littéral du brief cette fois (contrairement à Tasks
3/4) — reviewer spécifiquement mis en garde de rester sceptique, a
vérifié indépendamment chaque contrainte globale (auth, payload audit
exact, pas de nouveau flag, pas de nouvelle logique d'autorisation,
séparation de couches features/harvest respectée). 3/3 nouveaux tests,
suite complète 1200 passed/131 skipped.

Base Task 6: d1ad7eb
Task 6: complete (commit 41ecc9e + fix 102f7a4, 1 round de fix). Review
initiale : ✅ spec compliant (route clone fidèle de get_dataset_arcgis_items
+ queue export d'export_dataset_arcgis_aggregate, cap-avant-troncature
vérifié par trace manuelle), 1 Important labellisé plan-mandated — aucun
test ne forçait une seconde page réelle (offset += limit jamais exercé,
un bug d'incrémentation serait passé inaperçu). Décision : fix pur
additif (nouveau test, aucun changement de route/du texte du plan) donc
pas besoin d'arbitrage utilisateur, contrairement aux fixes Tasks 4/5 de
SP-15h qui changeaient un comportement. Fix : nouveau test
`test_export_items_continues_past_a_full_page` forçant 2 appels HTTP
réels (page pleine 1000 puis page courte 1), assertant resultOffset=0
puis resultOffset=1000 et 1001 features accumulées. RED confirmé contre
un bug injecté offset+=0 (413 au lieu de 200), GREEN confirmé contre le
code réel. Re-revue confirmée : route non touchée par le commit de fix,
assertions prouvent réellement l'incrémentation d'offset (pas seulement
"un second appel a eu lieu"). 8/8 tests (fichier), suite complète 1205
passed/131 skipped.

Base Task 7: 102f7a4
Task 7: complete (commit d35f46b, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important, 2 Minor
négligeables (nouveau test n'exerce que la forme /export nue, pas
/export/items — conforme au brief ; drift de numéros de ligne dans le
rapport, cosmétique)). Reviewer a vérifié la regex `_EXPORT_PATH_RE` à la
main caractère par caractère contre les 4 formes réelles de route +
contre des routes d'écriture qui doivent rester bloquées (POST
/collections, /collections/foo/export2) — tout correct. Aucun nouveau
flag de capacité introduit. 12 tests read-only-mode, suite complète 1206
passed/131 skipped.

## BACKEND (Tasks 1-7) COMPLET. Passage aux tâches shell/frontend (Tasks
8-13).

Base Task 8: d35f46b
Task 8: complete (commit a8444cc, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important, 1 Minor
négligeable (polyfill Blob.text() test-only, jsdom@25.0.1 n'implémente
pas Blob.prototype.text/arrayBuffer — reviewer a reproduit
indépendamment le trou avec un script node, confirmé guardé par
feature-detection donc jamais actif en navigateur réel, confirmé
scopé au seul fichier de test)). Dispatch statistics/items et
arcgis/collection vérifié ligne à ligne contre le code réel (pas
seulement le rapport), aucun autre implémenteur structurel d'ItemClient
trouvé (grep indépendant). 115/115 tests (fichier), suite complète
978/978, build tsc+vite propre.

Base Task 9: a8444cc
Task 9: complete (commit a798525, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important, 1 Minor
négligeable (pas de test pour "aucun dataset" → hasGeometry=false,
chemin simple à faible risque)). arcgis toujours true (schema jamais
appelé, vérifié par assertion .not.toHaveBeenCalled()), collection
dérivé par collection via hasGeometryByCollection (pas de divergence
possible entre sources partageant une collection), resolvedSource
réutilise la variable `merged` déjà calculée. 7/7 tests (fichier), suite
complète 980/980, tsc clean.

Base Task 10: a798525
Task 10: complete (commit 09326bf, review clean — ✅ spec compliant, task
quality Approved, 0 Critical/Important, 2 Minor négligeables (formats
restent cliquables si client jamais null en pratique — cas
hypothétique ; pas de commentaire inline dans ExplorerMenu.tsx expliquant
le choix useOptionalItemClient, seulement dans le rapport)). 1 déviation
du texte littéral du brief (DONE_WITH_CONCERNS, 3e fichier touché hors
périmètre déclaré) vérifiée à 4 niveaux par le reviewer : (a) bug réel
confirmé — useItemClient() lève sans provider, appelé
inconditionnellement avant le early-return, cassait les 4 tests
préexistants + le propre 5e test du brief ; (b) useOptionalItemClient
purement additif, aucune fonction existante modifiée ; (c) App.tsx
enveloppe bien toute l'app dans ItemClientProvider (lu directement, hors
diff) donc impact production nul ; (d) garde handleExport sûre, aucun cas
réel où client===null avec resolvedSource présent. 9/9 tests (fichier,
5 nouveaux + 4 anciens), suite complète 985/985, build propre.

Base Task 11: 09326bf
Task 11: complete (commit 48ec20a, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important/Minor). Edits avaient
déjà été appliquées par une session interrompue (fichiers non commités au
resume) ; réimplémenteur a vérifié verbatim contre le brief plutôt que de
réécrire, testé, commité. Les 7 accesseurs (`data.x`/`data?.x`/`ctx.data?.x`)
confirmés cohérents avec le narrowing préexistant à chaque site par le
reviewer. 985/985 tests, build tsc+vite propre.

Base Task 12: 48ec20a
Task 12: complete (commit a2a7748, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important, 1 Minor négligeable
(vi.stubGlobal("URL",...) jamais explicitement unstubbed dans le nouveau
test, inoffensif car Vitest isole les globals par fichier et le test suivant
ne touche pas URL)). Les deux observations remontées par l'implémenteur
(warning jsdom navigation, pas de gestion d'erreur sur exportDataSource
rejeté) évaluées indépendamment par le reviewer : la première est un non-
défaut (même motif déjà présent dans ExplorerMenu.tsx depuis 09326bf), la
seconde un vrai gap UX mais qui reproduit fidèlement le motif déjà établi
dans ExplorerMenu (pas une régression propre à cette tâche) — noté comme
suivi transverse SP-16a possible, pas bloquant. RED confirmé (2 failed/5
passed) puis GREEN (7/7), suite complète 987/987, build propre.

Base Task 13: a2a7748
Task 13: complete (commit cf97844, review clean on first pass — ✅ spec
compliant, task quality Approved, 0 Critical/Important, 3 Minor/info
(léger écart de comptage 45 vs 43 fichiers E2E dans le rapport — sans
impact ; pas de commentaire inline sur le header CORS ajouté ; vérification
finale du plan explicitement pas couverte par cette tâche — reste à faire,
cf. Task 14)). 1 déviation du texte littéral du brief identifiée ET vérifiée
en profondeur par le reviewer (pas du scope creep) : ajout de
`Access-Control-Expose-Headers: Content-Disposition` sur les 2 routes
mockées de la nouvelle spec — confirmé fix test-only (core n'a aucune
config CORS, prod sert shell+core same-origin via Traefik `/api`), premier
test à exercer un téléchargement piloté par Content-Disposition lu en JS
(fetch+Blob), aucun précédent contredit. Helpers copiés verbatim
d'analytics-context.spec.ts, sélecteurs vérifiés contre le code réel. Spec
seule 2/2, suite E2E complète 91/91.

