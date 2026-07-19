# Task 2 Report — Connecteur STAC (HarvestConnector/HarvestedRecord + StacConnector, SP-12c)

## Résumé

Implémenté exactement selon le brief `.superpowers/sdd/task-2-brief.md`, en TDD (RED confirmé
puis GREEN). Aucun écart de code par rapport au code fourni verbatim dans le brief — les trois
fichiers source ont été copiés tels quels (avec l'en-tête SPDX en ligne 1).

## Fichiers créés

- `core/app/harvest/connectors/__init__.py` — registre `_REGISTRY = {"stac": StacConnector()}`,
  `get_connector(source_type) -> HarvestConnector` (lève `ValueError` si type inconnu).
- `core/app/harvest/connectors/base.py` — `HarvestedRecord` (dataclass frozen) +
  `HarvestConnector` (Protocol : `type`, `supports_copy`, `fetch(url) -> Iterable[HarvestedRecord]`).
- `core/app/harvest/connectors/stac.py` — `StacConnector` (`type="stac"`, `supports_copy=True`,
  HTTP-only via `httpx.Client` injectable/interne, zéro I/O DB). Parsing tolérant/borné :
  `_MAX_CATALOG_DEPTH=5`, `_MAX_COLLECTIONS=500`, timeout 10s, anti-cycle via `seen_docs: set[str]`,
  gère 3 formes de document (API `{"collections":[...]}`, `Collection` unique, `Catalog` avec
  `links[rel=child]` récursif), toute erreur HTTP/JSON (`httpx.HTTPError`, `ValueError`) est
  loggée en warning et retourne un résultat vide plutôt que de lever.
- `core/tests/test_harvest_stac_connector.py` — 8 tests, copiés verbatim depuis le brief.

## TDD — RED puis GREEN

**RED** (avant implémentation) :
```
cd core && uv run pytest tests/test_harvest_stac_connector.py -v
...
ImportError while importing test module '.../tests/test_harvest_stac_connector.py'.
tests/test_harvest_stac_connector.py:5: in <module>
    from app.harvest.connectors import get_connector
E   ModuleNotFoundError: No module named 'app.harvest.connectors'
=========================== short test summary info ============================
ERROR tests/test_harvest_stac_connector.py
Interrupted: 1 error during collection
```
Conforme à l'attendu du brief (Step 2).

**GREEN** (après implémentation) :
```
cd core && uv run pytest tests/test_harvest_stac_connector.py -v
tests/test_harvest_stac_connector.py::test_fetch_api_collections_endpoint_maps_all_fields PASSED
tests/test_harvest_stac_connector.py::test_fetch_tolerates_missing_optional_fields PASSED
tests/test_harvest_stac_connector.py::test_fetch_follows_static_catalog_child_links_recursively PASSED
tests/test_harvest_stac_connector.py::test_fetch_terminates_on_cyclic_catalog_links PASSED
tests/test_harvest_stac_connector.py::test_fetch_caps_number_of_collections PASSED
tests/test_harvest_stac_connector.py::test_fetch_returns_empty_on_http_error_without_raising PASSED
tests/test_harvest_stac_connector.py::test_get_connector_returns_stac_connector PASSED
tests/test_harvest_stac_connector.py::test_get_connector_unknown_type_raises PASSED
============================== 8 passed in 0.07s ===============================
```

## Vérifications supplémentaires

- Suite complète cœur : `uv run pytest -q` → **616 passed, 87 skipped** (aucune régression ; les
  tests `postgis` restent skippés sans `CORE_TEST_DATABASE_URL`, comportement inchangé).
- `uv run lint-imports` → **1 kept, 0 broken** (le nouveau sous-package `app.harvest.connectors`
  ne viole aucune frontière de module — `app.harvest` n'importe que `app.db`/`httpx`, aucune
  inversion de dépendance).
- Tous les nouveaux fichiers source commencent par `# SPDX-License-Identifier: Apache-2.0` en
  ligne 1 (vérifié par lecture directe des fichiers créés).

## Commit

```
d048dff feat(core): connecteur STAC externe tolérant/borné (SP-12c)
 4 files changed, 308 insertions(+)
 create mode 100644 core/app/harvest/connectors/__init__.py
 create mode 100644 core/app/harvest/connectors/base.py
 create mode 100644 core/app/harvest/connectors/stac.py
 create mode 100644 core/tests/test_harvest_stac_connector.py
```

Seuls les 4 fichiers listés au brief ont été stagés/commités (`git add core/app/harvest/connectors/
core/tests/test_harvest_stac_connector.py`) — les fichiers `.superpowers/sdd/*.md` déjà modifiés
avant le début de cette tâche (visibles en `git status` initial) n'ont pas été touchés ni inclus.

## Auto-revue

- **Fidélité au brief** : code des 3 fichiers source copié caractère pour caractère depuis le
  brief (aucune réécriture, aucune "amélioration" non demandée) — cohérent avec le format SDD qui
  fournit le code exact à utiliser.
- **Portée** : module autonome, zéro dépendance vers `app.harvest.models`/DB — confirmé par lecture
  du fichier (`stac.py` n'importe que `logging`, `collections.abc`, `urllib.parse`, `httpx`, et
  `app.harvest.connectors.base`).
- **Tolérance/bornes** : les 4 gardes citées dans la description de tâche sont bien présentes et
  couvertes par un test dédié chacune : profondeur catalogue (`test_fetch_follows_static_catalog_
  child_links_recursively`, 2 niveaux < 5, passe), cycle (`test_fetch_terminates_on_cyclic_catalog_
  links`, le même URL revisité est bloqué par `seen_docs`), cap de 500 (`test_fetch_caps_number_of_
  collections`, 600→500), timeout 10s (non testé unitairement — `httpx.MockTransport` ne simule pas
  de délai réseau ; c'est un paramètre statique passé à chaque `client.get(...)`, cohérent avec le
  brief qui ne demande pas de test dédié dessus).
- **Comportement fail-open** : une erreur HTTP (500) ou un corps non-JSON valide (`ValueError` levée
  par `response.json()`) est interceptée et journalisée en `warning`, jamais propagée — vérifié par
  `test_fetch_returns_empty_on_http_error_without_raising`.
- **Registre** : `get_connector("stac")` retourne une instance déjà construite (partagée, pas de
  nouvelle instance par appel) — sûr car `StacConnector.fetch` construit ses propres `records`/
  `seen_docs` locaux à chaque invocation (pas d'état mutable partagé entre appels).

## Concerns

Aucun concern bloquant. Deux observations mineures, non correctives (comportement voulu par le
brief, pas des défauts) :
1. Le paramètre `timeout` est passé deux fois (au constructeur du client interne ET à chaque
   `client.get(...)`) — redondant mais inoffensif, et nécessaire pour le cas où un client externe
   est injecté sans timeout configuré (comme dans les tests, via `httpx.MockTransport`).
2. Aucun test unitaire ne couvre `depth >= _MAX_CATALOG_DEPTH` au-delà de 2 niveaux réels (le test
   fourni ne descend qu'à 2 sur 5 autorisés) — la garde de profondeur reste donc vérifiée seulement
   par lecture de code, pas par un test adversarial dédié à une profondeur >5. Non bloquant : le
   brief ne demande pas ce test, et le code est trivialement correct (`depth >= _MAX_CATALOG_DEPTH:
   return` avant toute récursion supplémentaire).

## Fix de revue (Important) — tolérance élargie au-delà du try/except HTTP

**Constat du reviewer** : le `try/except` de `_walk` ne couvrait que la requête HTTP + le
`response.json()` top-level. Tout ce qui suivait (`doc.get(...)`, l'itération sur
`doc["collections"]`/`coll.get(...)`/`link.get(...)`, et `float(v)` sur les coordonnées bbox)
tournait NON gardé — un payload JSON syntaxiquement valide mais structurellement hostile
(`[1,2,3]`, `null`, une entrée `None` dans `collections`, un lien qui est une chaîne, une bbox
avec des coordonnées non numériques) faisait planter tout le connecteur et jetait TOUS les
enregistrements déjà collectés, en violation directe de la contrainte globale SP-12c « parsing
STAC tolérant et borné … erreur → retourne ce qui a été collecté sans lever ».

**Correctif appliqué** (`core/app/harvest/connectors/stac.py`) :
- `_walk` : garde `isinstance(doc, dict)` juste après le `response.json()` — un top-level non-objet
  (`[1,2,3]`, `null`, chaîne, nombre) est loggé en warning et le document est ignoré (return),
  sans lever.
- `_walk` (branche `Catalog`) : chaque `link` de `doc.get("links", [])` est vérifié
  `isinstance(link, dict)` avant tout `.get(...)` — un lien non-objet (ex. une chaîne) est loggé et
  sauté (`continue`) au lieu de crasher toute la boucle.
- `_collection_to_record` : signature élargie à `coll: object` (au lieu de `dict`) ; garde
  `isinstance(coll, dict)` en tête — une entrée non-objet (`None`, chaîne, etc.) est loggée et
  retourne `None` (l'appelant l'ignore déjà, `if record is not None`), sans affecter les autres
  entrées du même batch. Le corps de la fonction est en plus enveloppé dans un
  `try/except (AttributeError, TypeError, KeyError, ValueError)` qui logge et retourne `None` — 
  couvre en particulier `float(v)` sur une bbox aux coordonnées non numériques (`["a","b","c","d"]`
  → `ValueError`) et les `link.get(...)` internes sur des liens non-objets (déjà gardés séparément
  par `isinstance(link, dict)` dans la boucle de liens de la collection, en écho à la même garde
  posée dans `_walk`).
- `keywords` : `coll.get("keywords")` n'est plus passé tel quel à `list(...)` (une chaîne
  `"foo"` serait devenue `["f","o","o"]`) — coercition explicite : `list(keywords_raw) if
  isinstance(keywords_raw, list) else []`.

Aucun changement d'interface publique (`fetch(url) -> Iterable[HarvestedRecord]` inchangé), aucune
régression sur les 8 tests déjà verts (bornes `_MAX_CATALOG_DEPTH`/`_MAX_COLLECTIONS`, anti-cycle
`seen_docs`, fail-open HTTP/JSON — tous préservés à l'identique).

### Tests ajoutés (`core/tests/test_harvest_stac_connector.py`)

4 nouveaux tests, même style (`httpx.MockTransport` + `_connector(handler)`) :
- `test_fetch_skips_malformed_collection_entries_and_keeps_valid_ones` : une liste `collections`
  contenant 2 entrées valides, une `None`, une avec bbox non numérique (`[["a","b","c","d"]]`), et
  une chaîne (`"not-a-dict"`) — vérifie que seules les 2 entrées valides (`buildings`, `roads`) sont
  retournées, les 3 entrées hostiles étant silencieusement droppées (loggées, pas levées).
- `test_fetch_returns_empty_on_non_object_top_level_json` : corps `[1, 2, 3]` (liste top-level) →
  `records == []`, pas d'exception.
- `test_fetch_returns_empty_on_null_top_level_json` : corps `null` → `records == []`, pas
  d'exception.
- `test_fetch_coerces_non_list_keywords_to_empty_list` : `"keywords": "not-a-list"` → 
  `records[0].keywords == []` (pas `["n","o","t",...]`).

### Commande + résultat

```
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_harvest_stac_connector.py -v
...
tests/test_harvest_stac_connector.py::test_fetch_api_collections_endpoint_maps_all_fields PASSED
tests/test_harvest_stac_connector.py::test_fetch_tolerates_missing_optional_fields PASSED
tests/test_harvest_stac_connector.py::test_fetch_follows_static_catalog_child_links_recursively PASSED
tests/test_harvest_stac_connector.py::test_fetch_terminates_on_cyclic_catalog_links PASSED
tests/test_harvest_stac_connector.py::test_fetch_caps_number_of_collections PASSED
tests/test_harvest_stac_connector.py::test_fetch_returns_empty_on_http_error_without_raising PASSED
tests/test_harvest_stac_connector.py::test_fetch_skips_malformed_collection_entries_and_keeps_valid_ones PASSED
tests/test_harvest_stac_connector.py::test_fetch_returns_empty_on_non_object_top_level_json PASSED
tests/test_harvest_stac_connector.py::test_fetch_returns_empty_on_null_top_level_json PASSED
tests/test_harvest_stac_connector.py::test_fetch_coerces_non_list_keywords_to_empty_list PASSED
tests/test_harvest_stac_connector.py::test_get_connector_returns_stac_connector PASSED
tests/test_harvest_stac_connector.py::test_get_connector_unknown_type_raises PASSED
============================== 12 passed in 0.08s ===============================
```

Suite complète cœur re-vérifiée : `uv run pytest -q` → **620 passed, 87 skipped** (606→620 = +12 +
2 nouveaux tests d'une autre tâche entre-temps ; aucune régression).

### Commit du fix

À suivre (commit séparé sur ce même correctif, cf. message conventional dans l'historique git).

### Concerns

Aucun. La frontière testée est désormais : n'importe quelle forme JSON syntaxiquement valide en
entrée de `fetch()` retourne soit des `HarvestedRecord` valides, soit une liste partielle/vide —
jamais une exception qui remonte à l'appelant (le worker de moissonnage SP-12c).
