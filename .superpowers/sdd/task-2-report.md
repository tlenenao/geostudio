# Task 2 : validation de `collectionId` à la sauvegarde d'un dataset — Rapport

> Note : ce fichier contenait auparavant le rapport d'une autre tâche
> (« Task 2 — module OpenTofu Proxmox », SP-Deploy-e), sans rapport avec
> SP-14a. Écrasé intégralement ci-dessous par le rapport de la tâche courante,
> conformément à l'instruction de la brief.

## Ce qui a été implémenté

TDD strict, suivant le brief `.superpowers/sdd/task-2-brief.md` verbatim :

1. Créé `core/tests/test_create_dataset.py` (contenu transcrit tel quel depuis
   le brief) : 3 tests — création réussie d'un dataset pointant vers une
   collection existante et lisible, rejet 422 à la création (`POST /configs`)
   avec un `collectionId` inexistant, rejet 422 à la mise à jour
   (`PUT /configs/by-item/{item_id}`) avec un `collectionId` inexistant.
2. Lancé les tests avant implémentation : confirmé l'échec attendu — les deux
   tests de rejet obtenaient `201`/`200` au lieu de `422` ; le test du chemin
   heureux passait déjà (rien ne le bloquait), exactement comme prédit par le
   brief.
3. Ajouté `_validate_dataset_payload(session, config, *, user) -> None` dans
   `core/app/configs/routes.py`, juste après `_validate_extension_scope`.
   No-op si `config.kind != "dataset"`. Pour un dataset : résout la collection
   via `app.collections.repository.get_collection(session,
   tenant_id=user.tenant_id, collection_id=payload.collectionId)` ; si `None`,
   lève `HTTPException(422, detail="collection not found")`. Sinon vérifie la
   lisibilité via `app.sharing.authorization.can(session, user_id=user.id,
   action="read", item=get_access_facts(collection), kind="collection",
   actor_is_admin=user.is_admin)` ; si non lisible, lève **exactement le même**
   appel `HTTPException(422, detail="collection not found")` — vérifié par
   construction (les deux branches lèvent l'appel identique dans le code
   source, pas seulement testé sur les deux cas actuellement couverts), afin
   qu'un utilisateur non autorisé ne puisse pas distinguer « collection
   inexistante » de « collection existante mais non partagée avec lui ».
4. Câblé l'appel dans les trois chemins de sauvegarde, juste après chaque
   appel existant à `_validate_extension_scope(...)` :
   - `create_config` (`POST /configs`)
   - `update_config` (`PUT /configs/{config_id}`)
   - `update_config_by_item` (`PUT /configs/by-item/{item_id}`)

Aucun autre fichier modifié.

## Résultats des tests

Commande ciblée (celle du brief) :

```
cd core && uv run pytest tests/test_create_dataset.py tests/test_dataset_config_schema.py tests/test_create_site.py tests/test_configs_extension_permissions.py -v
```

Résultat : **15 passed** — les 3 nouveaux tests, plus les tests préexistants
de schéma dataset, de sites et de permissions d'extension (garde de
non-régression), tous verts.

Suite complète du cœur en contrôle supplémentaire :

```
cd core && uv run pytest -q
```

Résultat : **781 passed, 102 skipped** (les skips sont les tests marqués
`postgis` nécessitant docker — conforme à la base connue documentée dans
CLAUDE.md).

## Écarts par rapport au brief

Aucun. L'implémentation reprend le code du Step 3 du brief au caractère près
(même corps de fonction, mêmes points d'appel, même message d'erreur sur les
deux branches).

## Commit

- `c562404` — `feat(core): validate dataset collectionId on save (SP-14a)`
  (`core/app/configs/routes.py`, `core/tests/test_create_dataset.py`)

Seuls ces deux fichiers ont été stagés et commités. Les autres fichiers
modifiés/non suivis présents dans l'arbre de travail
(`.superpowers/sdd/progress.md`, `task-1-brief.md`, `task-1-report.md`,
`task-2-brief.md`, `docs/superpowers/plans/2026-07-25-sp14a-datasets-partages.md`)
appartiennent au processus d'orchestration ou à d'autres tâches et n'ont pas
été touchés.

## Problèmes ou préoccupations

Aucun dans le périmètre de cette tâche. Un avertissement préexistant et sans
rapport apparaît dans la sortie des tests : une erreur
`procrastinate.exceptions.AppNotOpen` est loggée (pas levée) quand
`items_repo.create_item` tente de mettre en file d'attente un job d'embedding
pendant les tests ; elle est interceptée en interne par
`app.items.repository._enqueue_embedding` et n'affecte ni le résultat des
tests ni le périmètre de cette tâche — laissée telle quelle.

## Fix : couverture du chemin "collection non lisible"

Finding de la review : les tests existants ne couvraient que la branche
« collection inexistante » de `_validate_dataset_payload`
(`core/app/configs/routes.py:67-83`), pas la branche « collection existante
mais illisible par l'appelant » — pourtant la branche la plus sensible côté
sécurité, celle conçue spécifiquement pour ne pas révéler l'existence d'une
collection privée à un utilisateur non autorisé. Aucun changement dans
`routes.py` : l'implémentation était déjà correcte, il manquait juste le test.

Changements dans `core/tests/test_create_dataset.py` :

1. Fixture `client` étendue : création d'un second utilisateur `bob`
   (`oidc_sub="sub-2"`) et d'une seconde collection `id="prives"`
   (`is_public=False`, `owner_id=bob.id`) — sans aucun partage/rôle de groupe
   accordé à `alice`, l'utilisatrice de test habituelle (qui n'est pas admin
   par défaut, `bootstrap_admin` valant `False` dans `get_or_create_user`).
2. Nouveau test `test_create_dataset_collection_non_lisible_rejete_avec_meme_message` :
   POST `/configs` avec `collectionId="prives"` en tant qu'alice ; vérifie
   `status_code == 422` **et** `response.json()["detail"] == "collection not found"`
   — le même message exact que pour une collection inexistante, prouvant que
   les deux échecs sont indiscernables pour l'appelant.

### Résultats des tests

```
cd core && uv run pytest tests/test_create_dataset.py -v
```
→ **4 passed** (les 3 tests préexistants + le nouveau).

```
cd core && uv run pytest tests/test_create_dataset.py tests/test_dataset_config_schema.py tests/test_create_site.py tests/test_configs_extension_permissions.py -v
```
→ **16 passed** (régression complète du périmètre de la tâche, tous verts).

### Commit

- `test(core): cover unreadable-collection branch for dataset validation (SP-14a)`
  (`core/tests/test_create_dataset.py` uniquement).
