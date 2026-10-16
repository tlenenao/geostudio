# Triage des REV avant clôture (lot 0) — 2026-10-15

Méthode : `pytest tests/audit` contre `postgis-test` (port 5433) + `vitest src/audit`, puis lecture directe du code pour les REV sans reproducteur (piège n°12). Tête de migration Alembic : **0068** (le plan parlait de « après 0066 »).

## Résultat des reproducteurs

- Core : 13 passed, **24 xfailed, 0 XPASS** — aucun des bugs n'est déjà corrigé.
- Shell : 4 expected fail, 0 XPASS.
- `test_audit_lot4.py` n'a aucun `xfail` et ses 9 tests passent : **REV-354 et REV-355 sont déjà corrigées** (`docker-compose.prod.yml:259` déclare `CORE_BASE_URL` sur le worker ; `scripts/install.sh:254-255` pose les deux flags). À fermer par simple mise à jour du backlog, avec le commit qui les a corrigées à retrouver par `git log -S`.

## Tableau

| REV | Lot | Statut réel | Preuve | Action |
|---|---|---|---|---|
| 332 | 1 | à corriger (xfail) | `test_audit_lot2::test_s3_secret_not_readable_after_lock_down` | `CREATE SECRET` + verrou sandbox |
| 334 | 1 | à corriger (xfail) | `test_audit_lot0::test_profile_route_*`, `test_mcp_profile_dataset_*` | garde unique `run_collection_profile` |
| 336 | 1 | à corriger (xfail) | `test_audit_lot0::test_analytic_routes_have_a_rate_limit_group` | groupe `sql` |
| 337 | 1 | à corriger (xfail) | `test_audit_lot0::test_writer_replace_*` | refuser `replace` si champs masqués |
| 338-341 | 1 | à corriger (xfail) | `test_audit_lot1` (5 tests) | gardes d'egress |
| 342 | 1 | à corriger, **test non écrit** | `test_audit_lot1::test_alert_config_write_checks_secret_usage_by_editor` est un placeholder xfail « non testable unitairement » | écrire le test HTTP réel (Task 1.5) |
| 331 | 1 | à corriger, pas de reproducteur | `config_validation.py::_validate_node` | Task 1.5 |
| 329 | 1 | **confirmé réel** | `_SIDECAR_SAFE_OPS` contient `transform.httpCall` (kind `transform`) | retirer de la liste |
| 360, 361 | 1 | à corriger | `ComplianceAdminPage.tsx:53-60` (pas de confirmation), `ShareForm.tsx:100-108` (pas de `isError`) ; 4 `it.fails` shell | Task 1.7 |
| 366 | 1 | à vérifier au démarrage du lot | `apikeys/routes.py` n'a que `/api-keys` utilisateur, pas de route admin | Task 1.6 |
| 343, 344, 345, 346, 347, 348 | 2 | à corriger (xfail) | `test_audit_lot2` et `lot3` | Tasks 2.2-2.4 |
| 354, 355 | 2 | **déjà corrigées** | `test_audit_lot4` vert, compose + install.sh | fermer dans le backlog |
| 358 | 2 | à vérifier | exemption d'export dans `main.py` (regex `:101-102`), aucun test | écrire le test d'abord |
| 281, 267 | 2 | partielles, reliquats listés dans l'entrée | — | Task 2.6 |
| 349, 350, 351 | 3 | à corriger (xfail) | `test_audit_lot3` | lot 3 |
| 282, 283, 280 | 3 | partielles | entrées du backlog | lot 3 |
| 357 | 4 | à corriger (xfail) | `test_audit_lot5` (2 tests) | `int` → `float` |
| 362, 363 | 4 | à corriger | `it.fails` shell | lot 4 |
| 364, 365, 367 | 4 | listes de Minor à vider point par point | entrées du backlog | lot 4 |
| 304, 278, 284, 286 | 4 | partielles | entrées du backlog | lot 4 |
| 325-328, 330 | 5 | à corriger, sans reproducteur | 328 confirmé : `sidecar/app.py:48` écrit `os.environ` | lot 5 |
| 275, 276, 277 | 5 | partielles | entrées du backlog | lot 5 |
| 318, 319, 321, 164 | 6 | rejeu requis | — | lot 6 |
| 284(d), 286(c), 269, ADR 0013/0015 | 7 | décisions / automatismes | `main` non protégée (`gh api` → 404) | lot 7 |
| 119 | 8 | spécification requise | `2026-10-11-rev119-constat.md` | lot 8 |

## Écarts avec le plan maître

1. REV-354 et REV-355 : **retirées du lot 2** (déjà corrigées). La Task 2.1 devient une simple clôture documentaire.
2. Migrations : numéroter à partir de **0069**.
3. Les `reason=` des `xfail` portent « REV-audit », pas un numéro REV ; la correspondance REV ↔ test ci-dessus a été faite à la main depuis les chemins `fichier:ligne` du backlog. Le script `triage_xfail.py` de la Task 0.1 n'apporte donc rien : abandonné (YAGNI), la commande `pytest -rxXs` suffit.
4. Ces tests s'exécutent seulement avec `CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test` et `--basetemp` dans le scratchpad (`/tmp/pytest-of-lenen` n'appartient pas à l'utilisateur courant).
5. Les conteneurs `core`, `worker` et `martin` de la stack de dev sont en boucle de redémarrage ; cela n'affecte pas les tests unitaires mais compte pour le lot 6 (rejeu).
