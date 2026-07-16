# Task 2 — Rapport : revue authz — audit complet + comblement des trous réels

## Statut : DONE

## Résumé

Audit exhaustif de la couverture de test authz du cœur : 9 modules REST
(44 endpoints) + 11 outils MCP + les 2 composants transverses de recherche
sémantique (SP-7), sur la liste complète fournie par le brief (~25 fichiers
de test réels, pas la liste illustrative à 8 fichiers de la spec d'origine).
Chaque fichier de test associé a été lu en entier (pas seulement les noms de
fonctions), et le code source de chaque route/outil a été relu pour vérifier
que la garde citée par le test correspond bien à ce que le code fait
réellement.

**Résultat : 0 trou de sécurité réel.** 9 trous de **couverture** trouvés
(un comportement déjà correct, jamais exercé par un test) et comblés — les 9
tests ajoutés ont tous passé du premier coup, confirmant le code existant
plutôt que de révéler un bug. Aucun correctif de code n'a été nécessaire.

La matrice complète endpoint-par-endpoint/outil-par-outil, la liste détaillée
des 9 trous comblés (avec repro) et les points documentés-mais-non-ouverts
(hors budget) sont dans
`docs/superpowers/specs/2026-07-15-sp9-securite-minimale-revue-authz.md` —
ce fichier-ci résume l'exécution, ce fichier-là est la matrice/l'audit
proprement dit.

## Vérification de la liste d'endpoints (Step contexte du brief)

```
grep -rn "@router\.\(get\|post\|put\|patch\|delete\)" app --include="routes.py"
```

exécuté et comparé à la table du brief : identique (44 routes, 9 fichiers
`routes.py`), aucune mise à jour de la matrice nécessaire pour cette raison.

## Méthode suivie

Pour chacun des 9 modules REST + le module `app/mcp/tools.py`, j'ai :

1. Lu en entier le(s) fichier(s) de test associé(s) (pas de survol par nom
   de fonction — les assertions et le contenu des requêtes ont été vérifiés).
2. Lu le code source de la route/l'outil pour identifier la garde réellement
   appliquée (`can()`, `_require_admin`, `get_readable_collection`,
   `_require_access` côté MCP, filtre `tenant_id` en repository).
3. Rempli la matrice (Autorisé / Refusé / Anonyme / Cross-tenant / Trou)
   endpoint par endpoint, en distinguant explicitement les cas « N/A » (le
   critère ne s'applique pas), « Non testé (structurel) » (protégé par
   construction mais non exercé isolément) et « Trou » (vraiment absent).
4. Pour chaque trou identifié, écrit le test dans le fichier existant le
   plus proche, en suivant le patron déjà en place dans ce fichier
   (fixtures `env`/`client`, convention `_as(app, user)`), puis exécuté :
   - S'il passait du premier coup → « couverture ajoutée, pas de trou de
     sécurité réel » (documenté ainsi dans la spec).
   - S'il avait échoué (aucun cas ici) → root-cause puis correctif du code,
     puis re-exécution jusqu'au vert.

## Les 9 trous de couverture comblés (résumé — détail complet + repro dans la spec)

| # | Fichier modifié | Test ajouté | Endpoint/outil concerné |
|---|---|---|---|
| 1 | `tests/test_collections_routes.py` | `test_patch_by_non_owner_without_editor_role_returns_403` | `PATCH /collections/{id}` |
| 2 | `tests/test_collections_sharing_routes.py` | `test_get_sharing_requires_owner_or_admin` | `GET /collections/{id}/sharing` |
| 3 | `tests/test_users_admin_routes.py` | `test_patch_user_cross_tenant_returns_404` | `PATCH /users/{id}` |
| 4 | `tests/test_features_routes_write.py` | `test_non_owner_write_on_private_collection_is_404_not_403` | `POST`/`PUT`/`DELETE /collections/{id}/items…` |
| 5 | `tests/test_ingestion_routes.py` | `test_get_upload_job_cross_tenant_returns_404` | `GET /uploads/{job_id}` |
| 6 | `tests/test_extensions_routes.py` | `test_patch_extension_cross_tenant_returns_404` | `PATCH /extensions/{id}` |
| 7 | `tests/test_mcp_tools_sharing.py` | `test_get_sharing_invisible_to_a_stranger_errors` | outil MCP `get_sharing` |
| 8 | `tests/test_mcp_tools_sharing.py` | `test_set_sharing_by_group_viewer_errors` | outil MCP `set_sharing` |
| 9 | `tests/test_mcp_tools_query_features.py` | `test_query_features_on_private_unshared_collection_errors` (marqué `postgis`) | outil MCP `query_features` |

Chacun a été vérifié individuellement :

```bash
uv run pytest tests/test_collections_routes.py::test_patch_by_non_owner_without_editor_role_returns_403 -v
uv run pytest tests/test_collections_sharing_routes.py::test_get_sharing_requires_owner_or_admin -v
uv run pytest tests/test_users_admin_routes.py::test_patch_user_cross_tenant_returns_404 -v
uv run pytest tests/test_features_routes_write.py::test_non_owner_write_on_private_collection_is_404_not_403 -v
uv run pytest tests/test_ingestion_routes.py::test_get_upload_job_cross_tenant_returns_404 -v
uv run pytest tests/test_extensions_routes.py::test_patch_extension_cross_tenant_returns_404 -v
uv run pytest tests/test_mcp_tools_sharing.py -v
```
→ tous `PASSED` au premier essai (aucun `FAILED`, pas de cycle rouge→vert
car le code était déjà correct — vérifié par lecture avant écriture de
chaque test, cf. citations exactes des lignes de garde dans la spec).

Pour le test #9 (`query_features`, marqué `postgis` comme le reste de son
fichier), la vérification a nécessité un vrai PostGIS+pgvector — voir
§Infra PostGIS ci-dessous.

## Infra PostGIS utilisée pour la validation réelle

`core/tests/conftest.py::pg_engine` saute (`pytest.skip`) sans
`CORE_TEST_DATABASE_URL`. La machine avait déjà un conteneur Postgres
persistant sur le port 5432, mais appartenant à un tout autre projet
(`monitoring-stack`, vérifié via `docker inspect` avant tout usage — je ne
l'ai pas touché). J'ai donc construit et lancé un PostGIS+pgvector jetable
dédié, en suivant exactement la recette de `.github/workflows/ci.yml` (même
`deploy/postgis/Dockerfile`), sur un port différent :

```bash
docker build -t geostudio-postgis-ci-local:latest deploy/postgis
docker run -d --name geostudio-authz-review-pg -e POSTGRES_USER=gis \
  -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis_test -p 15432:5432 \
  geostudio-postgis-ci-local:latest
CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:15432/gis_test" uv run pytest -m postgis
```

→ **65 passed** (les 64 tests `postgis` préexistants + le nouveau
`test_query_features_on_private_unshared_collection_errors`), aucune
régression. Conteneur et image supprimés après usage
(`docker rm -f geostudio-authz-review-pg && docker rmi
geostudio-postgis-ci-local:latest`, vérifié).

## Suite complète — avant/après

- **Avant** (base `dev`, avant cette tâche) : 387 passed / 64 skipped (sans
  `CORE_TEST_DATABASE_URL`).
- **Après** : **395 passed / 65 skipped** (sans `CORE_TEST_DATABASE_URL`,
  +8 tests non-`postgis` +1 test `postgis` qui passe en `skipped` sans DB) —
  et **460 passed / 0 skipped** validé réellement contre le PostGIS jetable
  ci-dessus (387+64=451 avant, 395+65=460 après, arithmétique cohérente).

### `uv run pytest` (sortie complète, sans `CORE_TEST_DATABASE_URL`)

```
======================= 395 passed, 65 skipped in 20.31s =======================
```

### `uv run pytest` (sortie complète, avec `CORE_TEST_DATABASE_URL` réel)

```
============================= 460 passed in 28.41s =============================
```

### `uv run lint-imports`

```
---------
Contracts
---------

Analyzed 76 files, 195 dependencies.
------------------------------------

layered architecture KEPT

Contracts: 1 kept, 0 broken.
```

Clean — cohérent avec le brief (aucune modification de ce plan ne touche les
frontières de modules ; seuls des fichiers de test ont été modifiés).

## Auto-revue

- **Exhaustivité** : les ~25 fichiers de test de la table du brief ont tous
  été lus en entier (pas de survol), ainsi que 3 fichiers non nommés
  explicitement par le brief mais directement responsables de garanties de
  sécurité transverses (`test_items_repository.py`,
  `test_collections_repository.py` pour le filtre permission-avant-scoring
  de la recherche hybride) — mentionnés dans la matrice comme preuve, pas
  ignorés parce qu'absents de la liste du brief.
- **Rigueur** : chaque « Oui » de la matrice cite le nom du test exact ; les
  neuf trous ont chacun été vérifiés en relisant le code de la garde AVANT
  d'écrire le test (pas après), pour prédire correctement qu'ils passeraient
  du premier coup — prédiction confirmée dans les 9 cas.
- **Ce qui n'a délibérément pas été comblé** : une douzaine de combinaisons
  cross-tenant/refus supplémentaires sur des endpoints qui partagent déjà une
  garde éprouvée ailleurs dans le même fichier (ex. `GET
  /collections/{id}/schema` partage `get_readable_collection` avec `GET
  /collections/{id}`, lui-même testé) ont été documentées explicitement dans
  la spec comme choix d'arbitrage assumé plutôt que comme trous ouverts et
  laissés sans suite — la lecture du code source de chacune n'a montré
  aucune garde manquante ou incorrecte.
- **Aucun correctif de code produit** — uniquement des tests ajoutés (9
  fichiers de test modifiés, aucun fichier `app/` touché) + le fichier de
  spec/matrice créé.
- **Limite assumée** : je n'ai pas cherché à tester chacune des ~4
  combinaisons (autorisé/refusé/anonyme/cross-tenant) pour chacun des 44
  endpoints + 11 outils dans l'absolu (ça ferait plus de 200 tests) — j'ai
  ciblé les combinaisons qui, une fois identifiées comme non testées,
  présentaient un risque réel de dérive silencieuse (garde spécifique à
  l'endpoint, pas partagée avec un voisin déjà testé) ; le reste est
  documenté avec sa justification dans la spec plutôt que passé sous
  silence.

## Commit

```
test(core): revue authz — comble les trous réels trouvés dans la couverture existante
```

Fichiers commités : les 7 fichiers de test modifiés (9 tests dans 7
fichiers) + le fichier de spec/matrice créé. Aucun fichier `app/` modifié.

## Concerns

Aucun. Le résultat « 0 trou de sécurité réel » n'est pas un résultat de
complaisance : chaque garde a été relue dans le code source avant d'écrire
le test correspondant (citée par numéro de ligne dans la spec), et les 9
tests ajoutés ont été exécutés individuellement puis dans la suite complète,
y compris contre un vrai PostGIS+pgvector jetable pour le seul test marqué
`postgis`. Le point le plus proche d'un trou réel — `PATCH
/collections/{id}` n'ayant jamais exercé sa propre garde 403 — s'est avéré,
à l'exécution, être un comportement déjà correct.
