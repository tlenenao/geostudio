# v01 — Vérificateur S1/S2 (rejeu 2026-09-30, stack OIDC réinitialisée)

## Périmètre couvert
80 findings S1/S2 `confidence=verified` de `merged.jsonl`, rejoués par leur `repro` : 79 confirmed, 1 not-reproduced (j01-004).

## Non couvert / réserves
- Aucun reset ni modification de la stack. Aucun repro rendu `changed`.
- j01-004 : le 500 « permission denied for schema public » venait de l'ACL du schéma recréé par le reset précédent ; le test passe maintenant (artefact d'environnement, pas défaut produit).
- j06-001 et j11-015 (test-gap) : « confirmed » = la lacune de couverture existe toujours (ETL désactivé -> 404 ; e2e-oidc sans copilote).
- c08-002 : le repro littéral enchaîne `cd core` deux fois ; la 2e partie (probe_schema.py) a été rejouée depuis core/.
- c06-003 : la formulation « loader YAML ignorant !reset/!override » a été réalisée avec un constructeur multi-tag ; résultat : backup, tunnel, traefik sans healthcheck.
- Les repros pytest/python du cœur utilisent SQLite (sans effet sur la stack).

## Méthode
Les specs `shell/e2e/journeys/` ont été copiées telles quelles dans `shell/e2e/journeys/v01/` (arbre complet, sauf chemin des fixtures j03), avec `test.fixme(` -> `test(` (équivalent du « retrait du fixme » demandé) ; les specs à variable (J04/T01/T02_VERIFY=1) tournent avec la variable. Un run Playwright par dossier de parcours (1 worker, `-g` sur les ids concernés), TMPDIR neuf (caches de seed périmés ignorés). Un test fixme qui ÉCHOUE = défaut confirmé (il encode le comportement attendu). Aucun timeout général : pas de relance nécessaire.

## Commandes
`npx playwright test -c playwright.journeys.config.ts e2e/journeys/v01/<jNN|tNN> -g '<ids>'` (J04_VERIFY/T01_VERIFY/T02_VERIFY=1 pour j04, t01, t02) ; les repros c0x/j11-015 via `bash -c` littéral, SCRATCH fixé. Sorties brutes : `evidence/`.
