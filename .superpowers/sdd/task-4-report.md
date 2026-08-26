# Task 4 report — Rate limiting différencié (3.4)

## Ce qui a été implémenté

Exactement les 7 étapes du brief, avec un écart assumé et documenté sur
l'étape 1 (voir ci-dessous) :

1. `core/app/ratelimit/__init__.py` — package vide (SPDX header seulement,
   même convention que `app/secrets/__init__.py`/`app/alerts/__init__.py`).
2. `core/app/ratelimit/limiter.py` — code du brief copié tel quel :
   - `route_group(path, export_path_re) -> str | None` : classe un chemin
     en `sql` (`^/analytics/sql$`), `llm` (`^/mcp$|^/copilot/turn$`),
     `jobs` (réutilise `_EXPORT_PATH_RE` de `app.main` passé en paramètre,
     pas redéfini) ou `harvest` (`^/harvest/`), sinon `None`.
   - `RateLimiter` : compteur glissant en mémoire, `deque[float]` par
     `(clé, groupe)`, fenêtre de 60s, budgets `sql=10, llm=20, jobs=15,
     harvest=10`.
3. `core/app/main.py` : import `from app.ratelimit.limiter import
   RateLimiter, route_group` ; `rate_limiter = RateLimiter()` créé À
   L'INTÉRIEUR de `create_app()`, juste après `read_only_guard` et avant
   le bloc conditionnel `appexport_cors` ; middleware `rate_limit_guard`
   (`@app.middleware("http")`) qui court-circuite en 429
   `application/problem+json` avec `Retry-After: 60` quand le budget du
   groupe est épuisé pour la clé (en-tête `Authorization` brut).
4. `core/tests/test_ratelimit.py` — 3 tests du brief, avec un helper
   `_client()` ajusté (voir "Écart vs. le brief" ci-dessous).

## Écart vs. le texte littéral du brief (Step 1)

Le code de test fourni par le brief pour `_client()` (`TestClient(create_app())`
avec seulement `CORE_AUTH_MODE=mock`) **crashe** sur le premier
`client.post("/analytics/sql", ...)` : en mode mock, l'utilisateur est
toujours `bootstrap_analyst=True` (donc passe la garde `is_analyst` de
`analytics_sql`), et l'exécution atteint `conn_factory()` →
`get_duckdb_connection_factory()` → `os.environ["S3_ENDPOINT_URL"]` → `KeyError`
non catchée hors de la stack docker (pas de valeur par défaut, aucun test
existant du dépôt ne va nu sur cette route sans override). Starlette's
`ServerErrorMiddleware` envoie bien une réponse 500 via le handler
`Exception` (Task 3) mais **re-raise systématiquement après**
("We always continue to raise the exception" — code source Starlette),
donc `TestClient` (raise_server_exceptions=True par défaut) propage le
`KeyError` et fait planter le test avant même la 11e requête, quel que
soit l'état de l'implémentation du rate limiter.

Fix appliqué (même patron que `tests/test_analytics_sql_routes.py`,
déjà établi dans ce dépôt) : `_client()` override
`features_routes.get_duckdb_connection_factory` sur l'app créée, pour
retourner une factory in-memory DuckDB (`duckdb.connect(":memory:")`),
sans extension supplémentaire — le SQL testé (`"select 1"`) ne référence
aucune table, donc `run_analyst_sql` ne matérialise rien et n'a besoin ni
de `spatial` ni de `httpfs`. Comportement des 3 tests inchangé par
rapport à l'intention du brief ; seul le chemin d'exécution de l'endpoint
`/analytics/sql` devient déterministe et sans dépendance à S3.

Aucun autre écart. La structure de `main.py` (imports, `_EXPORT_PATH_RE`
ligne 56-58, `read_only_guard`, route `/health` ligne ~293-295, mount
`/mcp` en dernier) correspondait exactement à ce que le brief décrivait.

## TDD — RED puis GREEN

RED (avant `app/ratelimit/`, seulement le test avec le fix de l'écart
ci-dessus) :

```
tests/test_ratelimit.py::test_sql_route_rate_limited_after_budget_exhausted FAILED
  assert 200 == 429  # aucune limite n'existe encore
tests/test_ratelimit.py::test_different_callers_have_independent_budgets PASSED  (vacuously)
tests/test_ratelimit.py::test_health_endpoint_not_rate_limited_by_sql_budget PASSED  (vacuously)
1 failed, 2 passed in 2.99s
```

GREEN (après implémentation) :

```
tests/test_ratelimit.py::test_sql_route_rate_limited_after_budget_exhausted PASSED
tests/test_ratelimit.py::test_different_callers_have_independent_budgets PASSED
tests/test_ratelimit.py::test_health_endpoint_not_rate_limited_by_sql_budget PASSED
3 passed in 2.96s
```

## Step 6 — sanity check `/mcp` (raison d'être du middleware)

```
$ uv run python -c "
from app.ratelimit.limiter import route_group
import re
export_re = re.compile(r'^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?\$|^/export\$|^/app-exports\$')
assert route_group('/mcp', export_re) == 'llm'
assert route_group('/copilot/turn', export_re) == 'llm'
assert route_group('/analytics/sql', export_re) == 'sql'
assert route_group('/export', export_re) == 'jobs'
assert route_group('/app-exports', export_re) == 'jobs'
assert route_group('/harvest/sources', export_re) == 'harvest'
assert route_group('/health', export_re) is None
print('all route groups correct')
"
all route groups correct
```

Les 7 assertions passent, y compris `/mcp` → `llm` — confirme que le
routage par groupe fonctionne indépendamment de FastAPI (`route_group`
est une fonction pure de chemin, aucun objet `Request`/DI impliqué), donc
que le middleware couvre bien le mount ASGI brut de `/mcp`, qu'une
dépendance de route ne pourrait jamais atteindre.

## Suite complète core (DB PostGIS réelle)

```
$ CORE_TEST_DATABASE_URL=postgresql://gis:gis@localhost:5433/gis_test uv run pytest -q
...
=================================== FAILURES ===================================
___________________ test_scope_preserves_original_sql_error ____________________
[...]
1 failed, 1886 passed, 5 skipped in 190.71s (0:03:10)
```

Le seul échec est `tests/test_features_rls.py::test_scope_preserves_original_sql_error`
— échec pré-existant, sans rapport avec ce chantier (assertion sur le
message d'erreur SQL exact d'un `RESET ROLE` échoué après une violation
RLS, dépendant du driver/version Postgres), confirmé comme étant le
**seul** échec de toute la suite. Aucune régression introduite par ce
chantier. +3 tests par rapport à la baseline mesurée par le contrôleur
(1883+1 → 1886, cohérent avec les 3 nouveaux tests de ce fichier).

## Lint / type-check / import-contract

```
$ uv run ruff check app/ratelimit/ app/main.py tests/test_ratelimit.py
All checks passed!
$ uv run ruff format --check app/ratelimit/ app/main.py tests/test_ratelimit.py
4 files already formatted   # après une passe de `ruff format` sur test_ratelimit.py
$ uv run mypy --strict app/ratelimit/
Success: no issues found in 2 source files
$ uv run lint-imports
Contracts: 1 kept, 0 broken.
```

`app.ratelimit` n'est volontairement pas ajouté au contrat de couches
import-linter : il n'importe aucun module `app.*` (seulement `re`,
`time`, `collections`), donc n'a rien à violer ; le brief ne demandait
pas cet ajout.

## Fichiers modifiés/créés

- `core/app/ratelimit/__init__.py` (nouveau)
- `core/app/ratelimit/limiter.py` (nouveau)
- `core/app/main.py` (modifié : import + middleware `rate_limit_guard`)
- `core/tests/test_ratelimit.py` (nouveau)

## Self-review

**Complétude** :
- 3 nouveaux tests passent — oui.
- `/mcp` réellement couvert (Step 6) — oui, vérifié par sanity check
  indépendant du serveur MCP réel (`route_group` pure).
- Budgets exacts : `sql=10, llm=20, jobs=15, harvest=10`, fenêtre 60s —
  vérifié dans `limiter.py` (`_BUDGETS`, `_WINDOW_SECONDS = 60.0`).

**Qualité** :
- `rate_limiter = RateLimiter()` est bien créé À L'INTÉRIEUR de
  `create_app()` (ligne juste après `read_only_guard`, avant le bloc
  `if is_appexport_enabled()`), pas au niveau module — vérifié par
  lecture directe du diff. Un test antérieur qui épuiserait un budget ne
  peut donc pas faire trébucher un test sans rapport plus tard dans la
  suite (chaque `create_app()` — donc chaque test qui construit son
  propre `TestClient` — repart avec un `RateLimiter` neuf). Cohérent avec
  le mode d'échec explicitement à éviter d'après la consigne de la
  tâche.
- Forme de la réponse 429 cohérente avec les handlers RFC 7807 de la
  Task 3 : mêmes clés top-level (`type`/`title`/`status`/`detail`),
  même `media_type="application/problem+json"` — même si elle est
  construite à la main dans le middleware (raison documentée dans le
  contexte de la tâche : le middleware tourne hors du dispatch
  route/exception-handler, donc ne peut pas lever `HTTPException` et
  compter sur le handler existant).
- `Retry-After: 60` présent sur la réponse 429 — vérifié par le test 1
  et par lecture du code.

**Discipline** :
- Aucune persistance/Redis/thread de nettoyage ajouté au-delà de ce que
  le brief spécifie — la docstring de `RateLimiter` documente
  explicitement la limite (deque vide qui reste en mémoire indéfiniment
  pour une clé inactive) comme acceptée, pas comme un bug à corriger.
- Aucun fichier hors périmètre modifié — `git add` n'a pris que
  `core/app/ratelimit/`, `core/app/main.py`, `core/tests/test_ratelimit.py`
  (les fichiers `.superpowers/sdd/*.md` modifiés/`deploy/postgis/pg_hba.conf`
  visibles dans `git status` au démarrage de la tâche sont pré-existants,
  d'une autre session, non touchés ici).

## Concerns / points d'attention

- Le test 1 du brief tel que littéralement fourni ne fonctionne pas sans
  l'override de `get_duckdb_connection_factory` (cf. section "Écart"
  ci-dessus) — signalé explicitement pour que le contrôleur puisse
  vérifier que cette déviation est bien celle qu'il attendait, plutôt que
  de la découvrir en aval.
- `route_group()` sur `/mcp` matche n'importe quelle sous-méthode/verbe
  HTTP du protocole MCP (POST/GET/DELETE selon la session streamable-http) —
  c'est le comportement voulu par le brief (budget `llm` unique pour tout
  trafic `/mcp`), pas une lacune.
- Comme documenté dans le docstring du module, la limite ne tient pas en
  cas de multi-process (`--workers` uvicorn) — limite assumée par le
  design SP-26 §3.4, pas un défaut de cette implémentation.
