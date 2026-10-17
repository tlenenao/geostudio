# Baseline cœur — 2026-10-16

Lecture seule sur le code ; aucun fichier source modifié, aucun commit.

## Résultats

| Porte | Résultat |
|---|---|
| pytest (`core/`, postgis réel) | **5643 passés, 0 échoué, 0 erreur, 23 skippés** en 46 min 53 s |
| Couverture | **93,59 %** (seuil `core/.coverage-threshold` = 85 ; `scripts/check_coverage.py` OK). Plus bas modules : cdc 85,0, tenants 85,3, webhooks 85,3, quality 85,6 |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 1090 fichiers déjà formatés |
| `mypy --strict` (app/auth secrets analytics copilot admin_tools roles net_pin.py) | Success, 40 fichiers |
| `lint-imports` | 1 contrat, 0 rompu (428 fichiers, 1930 dépendances) |

Aucun échec : rien à rejouer en isolation.

## Skips (23) — aucun skip postgis
- `tests/test_helm_chart.py` : 17 skips, `helm absent` (lignes 105-251). Le chart Helm (ARC-29) n'est donc jamais validé sur ce poste.
- `tests/test_pipeline_connector_runtime.py:622` Snowflake, `:2046` Redshift, `:2055` Databricks : DSN de test non définis (manuels, REV-110, GAP-16).
- `tests/test_s3_public_storage.py:80` : `CORE_TEST_S3_ENDPOINT` non défini, test MinIO réel non joué.

## Environnement : 3 pièges rencontrés (preuves)
1. **`/tmp/pytest-of-lenen` appartient à root** (`drwxr-xr-x root root`, uid courant 1000) : pytest échoue en `OSError: The temporary directory ... is not owned by the current user` sur tout test utilisant `tmp_path` (erreurs en cascade). Contournement : `--basetemp=<dossier utilisateur>`.
2. **Schéma périmé de `gis_test` dans `postgis-test`** : `UndefinedColumn: column "origin" of relation "group_members" does not exist` (INSERT group_members, `tests/audit/test_audit_lot0.py::test_profile_route_refuses_geo_limited_user`). `conftest.py:72-73` construit le schéma par `create_all`, qui n'altère pas les tables existantes (piège SP-42 documenté). Je n'ai pas touché à `gis_test` : j'ai créé une base jetable `gis_baseline_audit` dans le même conteneur (extensions postgis, vector, pg_trgm, btree_gist), utilisée pour la run, puis supprimée. Conséquence : **la suite telle quelle sur `gis_test` échoue** tant qu'on ne la recrée pas ou ne fait pas l'ALTER.
   Piège voisin : sans `CREATE EXTENSION postgis` dans la base, `type "geometry" does not exist`.
3. **Chaque test qui défère un job attend 60 s si `DATABASE_URL` n'est pas exporté** : 10 tests à ~60,5 s dans `--durations` (`tests/test_mcp_tools_run_analytics_query.py`, `test_mcp_tools_profile_dataset.py`, `test_mcp_tools_create_form_app.py`, `tests/audit/test_audit_lot0.py::test_mcp_profile_dataset_refuses_geo_limited_user`). Trace faulthandler : blocage dans `app/collections/repository.py:44` (`_defer`) appelé depuis `app/jobs/after_commit.py:24` (`_fire`). `app/jobs/__init__.py:42-50` lit `DATABASE_URL` à l'import (repli `postgresql://localhost/geostudio_dev`) et construit le connecteur procrastinate à ce moment (`:81`) ; le `monkeypatch.setenv("DATABASE_URL", ...)` des tests (`test_mcp_tools_create.py:26`, `test_mcp_tools_query_features.py:37`) arrive trop tard. Rien n'écoute sur 5432 ici. Preuve : le même test passe de 60,72 s à 0,58 s avec `DATABASE_URL=$CORE_TEST_DATABASE_URL` exporté (2 passés en 5,4 s). Les tests passent dans les deux cas : ~10 min de la suite sont de l'attente pure. En CI `.github/workflows/ci.yml:22` exporte `DATABASE_URL=...localhost:5432/gis` (base réelle sur 5432) : le piège est propre à un poste où le postgis de test est sur 5433 sans `DATABASE_URL`.

## Commande reproductible
```
docker exec postgis-test psql -U gis -d postgres -c "CREATE DATABASE gis_x"
# + CREATE EXTENSION postgis, vector, pg_trgm, btree_gist dans gis_x
U=postgresql+psycopg://gis:gis@localhost:5433/gis_x
cd core && DATABASE_URL=$U CORE_TEST_DATABASE_URL=$U uv run pytest -q -p no:cacheprovider --basetemp=<dir> --cov=app --cov-report=xml:<dir>/cov.xml
```
(La run mesurée n'avait pas `DATABASE_URL`, d'où les 47 min.)
