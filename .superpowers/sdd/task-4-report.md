# Task 4 report — Moteur de moissonnage (`service.py`) — SP-12c

Note: this path previously held a stale report from an unrelated SP-12b task
also numbered "Task 4" in a different plan (DCAT-AP routes). Overwritten as
instructed by this task's own report path (SP-12c plan, task 4:
`core/app/harvest/service.py`).

## Résumé

Implémenté `core/app/harvest/service.py` : `harvest_source(session, source, *,
items_fetcher=_default_items_fetcher) -> None`, le cœur intégrateur de SP-12c.
Fetch via `app.harvest.connectors.get_connector(source.type)`, puis upsert
idempotent de chaque `HarvestedRecord` contre `harvest_records`, en deux modes :

- **`reference`** (défaut) : crée/actualise un `Item` `resource_type="external"`,
  `is_published=False`. Un ré-moissonnage avec le même `external_id` met à jour
  l'item existant (titre/résumé/mots-clés) au lieu d'en créer un nouveau, piloté
  par un hash de contenu (`_content_hash`) comparé au `content_hash` déjà stocké.
- **`copy`** : au premier moissonnage d'une collection, fetch les items GeoJSON
  distants (`items_fetcher(rec.items_url)`) et les route vers
  `app.ingestion.importer.run_import` pour créer une collection PostGIS locale.
  Aux moissonnages suivants, **ne ré-importe jamais** un contenu déjà copié
  (limitation documentée : `run_import` ne sait que CRÉER, jamais mettre à jour
  une collection existante) — seule la fraîcheur du mapping (`harvested_at`,
  `is_stale=False`) avance.

Une entité vue lors d'un moissonnage précédent mais absente du fetch courant
est marquée `is_stale=True` par `harvest_repo.mark_missing_as_stale` — jamais
supprimée. `harvest_source` **ne lève jamais** : toute exception de
`connector.fetch(...)` est capturée, `source.last_status="error"` +
`source.last_error` (tronqué à 500 caractères), sans propager.

## TDD — RED puis GREEN

### Step 1-2 : tests écrits, confirmés en échec (RED)

Fichier `core/tests/test_harvest_service.py` créé avec les 4 tests
reference-mode (SQLite always-run) du brief, verbatim.

```
$ cd core && uv run pytest tests/test_harvest_service.py -v
...
ImportError: cannot import name 'service' from 'app.harvest'
Interrupted: 1 error during collection
```

(Le brief anticipait `ModuleNotFoundError` ; le module `app.harvest` existant
déjà comme package, l'échec réel est un `ImportError` sur le sous-module
`service` — même nature d'échec RED, cause identique : `service.py` n'existe
pas encore.)

### Step 3 : implémentation

`core/app/harvest/service.py` créé verbatim depuis le brief (interfaces
vérifiées au préalable contre le code réel des tâches précédentes — voir
Self-Review ci-dessous).

### Step 4 : GREEN (SQLite, sans DB)

```
$ cd core && uv run pytest tests/test_harvest_service.py -v
tests/test_harvest_service.py::test_reference_mode_first_harvest_creates_external_items PASSED
tests/test_harvest_service.py::test_reference_mode_reharvest_updates_without_duplicating PASSED
tests/test_harvest_service.py::test_missing_entity_is_marked_stale_not_deleted PASSED
tests/test_harvest_service.py::test_connector_fetch_failure_sets_error_status_without_raising PASSED
tests/test_harvest_service.py::test_copy_mode_first_harvest_creates_local_collection SKIPPED
tests/test_harvest_service.py::test_copy_mode_reharvest_does_not_reimport SKIPPED
4 passed, 2 skipped in 0.83s
```

### Step 5-6 : tests `copy` (postgis) ajoutés, validés contre PostGIS réel

Un conteneur `postgis-test` (port 5433, `gis`/`gis`/`gis_test`) était déjà
disponible dans l'environnement (issu des sessions précédentes Tasks 1-3).
Exécuté contre lui — preuve plus forte que le simple SKIP local :

```
$ CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:5433/gis_test" \
  uv run pytest tests/test_harvest_service.py -v
tests/test_harvest_service.py::test_reference_mode_first_harvest_creates_external_items PASSED
tests/test_harvest_service.py::test_reference_mode_reharvest_updates_without_duplicating PASSED
tests/test_harvest_service.py::test_missing_entity_is_marked_stale_not_deleted PASSED
tests/test_harvest_service.py::test_connector_fetch_failure_sets_error_status_without_raising PASSED
tests/test_harvest_service.py::test_copy_mode_first_harvest_creates_local_collection PASSED
tests/test_harvest_service.py::test_copy_mode_reharvest_does_not_reimport PASSED
6 passed in 1.27s
```

### Suite complète — aucune régression

Sans DB (skips habituels) :
```
$ cd core && uv run pytest -q
631 passed, 90 skipped in 35.31s
```

Avec PostGIS réel (`CORE_TEST_DATABASE_URL` pointé sur `postgis-test`) :
```
$ CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test uv run pytest -q
721 passed in 47.25s
```

### Frontières de modules (import-linter)

```
$ uv run lint-imports
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

`app.harvest` est déjà positionné au-dessus de `app.ingestion`/`app.items`/
`app.audit` dans le contrat `layers` (posé par une tâche précédente de SP-12c),
donc `service.py` important `run_import`, `items_repo`, `write_audit` ne casse
rien — aucune modification de `pyproject.toml` nécessaire pour cette tâche.

## Fichiers modifiés

- `core/app/harvest/service.py` (nouveau, 137 lignes)
- `core/tests/test_harvest_service.py` (nouveau, 208 lignes)

## Self-review — vérification des interfaces avant écriture

Avant d'écrire le code, j'ai lu le code réel de chaque interface consommée
pour confirmer qu'elle correspond exactement à ce que le brief présuppose
(le brief dit "trust them" mais je les ai quand même vérifiées, la brique
étant le cœur intégrateur de SP-12c) :

- `app/harvest/repository.py` : `create_source`, `get_record`, `create_record`,
  `update_record`, `mark_missing_as_stale` — signatures identiques au brief.
- `app/harvest/models.py` : `HarvestSource`/`HarvestRecord` — champs
  (`tenant_id`, `owner_id`, `mode`, `last_status`, `last_error`, `last_run_at`,
  contrainte unique `(tenant_id, source_id, external_id)`) confirmés.
- `app/harvest/connectors/__init__.py` : `get_connector(source_type: str)`.
- `app/items/repository.py` : `create_item(session, *, tenant_id, owner_id,
  resource_type, title, slug=None)`, `update_item(..., title, abstract,
  keywords, is_published, slug=None)`, `get_item(...)` — signatures identiques.
- `app/ingestion/importer.py` : `run_import(session, *, tenant_id, created_by,
  filename, content, collection_title, lat_field, lon_field, layer_name=None)
  -> ImportResult(.collection_id, .item_id)` — confirmé.
- `app/audit/writer.py` : `write_audit(session, *, tenant_id, actor_id,
  actor_kind, action, object_type, object_id, payload=None)` — confirmé.

Aucun écart trouvé entre le brief et le code réel des tâches précédentes —
le code du brief a été appliqué verbatim, sans adaptation.

## Concerns / points d'attention (non bloquants)

1. **Limitation `copy`-mode documentée par le brief et intentionnelle** :
   un contenu déjà copié n'est jamais ré-importé (seul le mapping de
   fraîcheur avance). Une vraie synchronisation de contenu pour le mode
   `copy` reste hors périmètre SP-12c — commentaire exact du brief conservé
   verbatim dans `_upsert_copy`.
2. `harvest_source`'s `try/except` ne protège que l'étape
   `connector.fetch(...)` (comme le prescrit le brief) — pas la boucle
   `for rec in records` qui suit. Une erreur levée par `items_fetcher(...)`
   ou `run_import(...)` (mode `copy`) pour un item individuel n'est donc PAS
   catchée : elle interromprait toute la boucle sans marquer
   `source.last_status="error"` ni traiter les items restants, contrairement
   au comportement "ne lève jamais" garanti pour l'étape de fetch. C'est le
   comportement exact prescrit par le brief (verbatim), pas une déviation —
   signalé ici comme piste de durcissement possible dans une session
   ultérieure si jugé pertinent, mais strictement hors périmètre de cette
   tâche.
3. Les 2 tests `copy`-mode ont été validés contre un vrai PostGIS (conteneur
   `postgis-test` déjà présent dans l'environnement, réutilisé des sessions
   Tasks 1-3), pas seulement vérifiés SKIP — preuve empirique réelle du
   chemin `run_import`. Suite complète (721 tests) également re-vérifiée
   contre ce même PostGIS réel : aucune régression.

## Commit

`fb84768` — `feat(core): moteur de moissonnage — upsert idempotent, modes reference/copy (SP-12c)`

## Fix de revue (post-fb84768) : capture des erreurs de la boucle par-enregistrement

**Finding (Important)** : le concern #2 ci-dessus a été requalifié en défaut
réel et corrigé — le contrat de `harvest_source` ("ne lève jamais") n'était
tenu que pour l'étape `connector.fetch(...)`. En mode `copy`, `items_fetcher`
(réseau) ou `run_import` (fail-fast, ex. `IngestionParseError` sur un GeoJSON
distant malformé) pouvaient lever et se propager hors de `harvest_source`,
laissant `source.last_status` périmé au lieu de `"error"` — le job
procrastinate de Task 5 dépend de cette garantie pour ne jamais retenter un
job zombie.

### Changement

`core/app/harvest/service.py` : le corps de la boucle `for rec in records`
et l'appel à `mark_missing_as_stale` sont désormais enveloppés dans un
second bloc `try/except Exception`, symétrique à celui du fetch. Toute
exception levée pendant le traitement (upsert par enregistrement,
`items_fetcher`, `run_import`, écritures audit/DB) est capturée,
journalisée (`logger.exception`), et se traduit par
`source.last_status="error"` + `source.last_error=str(exc)[:500]` ;
`harvest_source` retourne normalement (ne lève jamais). Le comportement de
succès est inchangé : sur une exécution intégralement réussie,
`last_run_at`/`last_status="ok"`/`last_error=None` sont posés exactement
comme avant, et `mark_missing_as_stale` continue de tourner sur ce chemin.

**Décision de conception (documentée dans le code)** : en cas d'échec en
cours de boucle, les enregistrements déjà upsertés plus tôt dans la même
boucle restent en base (progrès partiel accepté — le moissonnage suivant
réconcilie), mais `mark_missing_as_stale` n'est PAS appelé et le statut
n'est PAS mis à "ok" : la source passe "error" pour que sa santé soit
surfacée à l'opérateur/à Task 5.

### Test de régression

`core/tests/test_harvest_service.py::test_copy_mode_items_fetch_failure_sets_error_status_without_raising` —
tourne toujours en SQLite (jamais postgis-gated) : source en mode `copy`,
`items_fetcher` qui lève `RuntimeError("network boom")` avant tout appel à
`run_import`. Assertions : `harvest_source` ne lève pas,
`source.last_status == "error"`, `"network boom" in source.last_error`,
aucun `harvest_record` créé (preuve que `mark_missing_as_stale` n'a pas
tourné). Le test préexistant `test_connector_fetch_failure_sets_error_status_without_raising`
est resté intact.

### Commande + résultat

```
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_harvest_service.py -v
```
→ `5 passed, 2 skipped in 0.86s` (les 2 skips sont les tests `copy`-mode
`@pytest.mark.postgis` préexistants, sans `CORE_TEST_DATABASE_URL` — comportement
attendu, inchangé).

### Commit

`fix(core): harvest_source capture aussi les erreurs d'import du loop, jamais de job zombie (SP-12c)`
