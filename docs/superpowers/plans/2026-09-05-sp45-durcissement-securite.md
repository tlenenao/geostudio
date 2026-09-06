# SP-45 — Durcissement sécurité immédiat : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refermer 7 manques de sécurité/disponibilité bon marché identifiés
par la revue SP-42 (GAP-02, GAP-41, GAP-58, GAP-61, GAP-77, GAP-78, GAP-79),
chacun vérifié indépendamment contre le code réel avant d'écrire ce plan
(cf. spec associée pour le détail des vérifications et des deux corrections
apportées au texte de `analyse-gaps.md`).

**Architecture:** 7 tâches = les 7 manques, dans un ordre arbitraire (aucune
dépendance entre elles — exécutables en parallèle si plusieurs agents sont
disponibles). Les Tâches 1 à 5 sont du code, TDD, avec filet posé avant le
fix. Les Tâches 6 et 7 sont des opérations manuelles hors code
(réécriture d'historique git, réglage GitHub) — pas de TDD applicable,
procédure de vérification avant/après à la place.

**Tech Stack:** Python/FastAPI + pytest (cœur) ; `docker-compose.yml`/
`.env.example`/`scripts/bootstrap-env.sh` (infra) ; `git`/`gh` (opérations
manuelles, Tâches 6-7).

**Document source :**
`docs/superpowers/specs/2026-09-05-sp45-durcissement-securite-design.md`.

## Global Constraints

- **TDD / filet-avant-code** : chaque tâche de code pose son test (nouveau,
  vérifié rouge) **avant** de toucher le code qu'il protège.
- **Falsification obligatoire** (piège CLAUDE.md n°10) : pour chaque test
  ajouté, confirmer qu'il échoue sur le code non corrigé avant de committer
  le fix qui le fait passer — jamais supposer.
- Commits **conventional**, un sujet par commit, français
  (`fix(core): ...`, `test(core): ...`, `chore(deploy): ...`,
  `docs(git): ...`).
- **Suite complète rejouée avant de clore chaque tâche** (piège CLAUDE.md
  n°6) : `cd core && uv run pytest` — jamais un sous-ensemble de fichiers.
- **Régénérer la spec OpenAPI + types TS** seulement si constaté nécessaire
  (piège CLAUDE.md n°1) : aucune des 7 tâches ne change de route ni de forme
  de réponse — diff **vide** attendu à la Tâche 5 (clôture), vérifié
  explicitement plutôt que supposé.
- **Tâches 6 et 7 (git history / réglages GitHub) : accord explicite de
  Tanguy requis avant exécution.** Ce sont des opérations irréversibles
  (réécriture d'historique public, changement de réglage sur le dépôt
  GitHub réel) — jamais prises sur le seul jugement d'une session, même
  quand ce plan les décrit en détail. Les préparer (commandes exactes,
  vérifications avant/après) mais s'arrêter avant l'étape destructive tant
  que l'accord n'est pas confirmé.
- **`postgis-test` non tracké par Alembic** : sans objet ici (aucune tâche
  de ce plan n'ajoute de colonne ni de migration).
- Aucune tâche ne dépend de SP-43 (refactorisation structurelle) ni n'y
  touche.

---

## Task 1 : garde d'egress SSRF sur l'appel LLM sortant du copilote (GAP-02)

**Fichiers touchés :** nouveau `core/app/copilot/egress.py` ; nouveau
`core/tests/test_copilot_egress.py` ; `core/app/copilot/llm_provider.py`
(modifié) ; `core/tests/test_copilot_llm_provider.py` (test ajouté) ;
`core/app/copilot/routes.py` (modifié, mapping d'erreur) ;
`core/tests/test_copilot_routes.py` (test ajouté).

### Étape 1 : filet — garde elle-même (avant tout code de production)

Créer `core/tests/test_copilot_egress.py`, calqué sur
`core/tests/test_harvest_egress.py` (même liste de cibles bloquées) :

```python
# SPDX-License-Identifier: Apache-2.0
import socket

import pytest

from app.copilot.egress import EgressBlockedError, assert_egress_allowed


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://[::1]/x",
        "http://[fc00::1]/x",
        "http://0.0.0.0/x",
    ],
)
def test_assert_blocks_internal_ip_literals_without_dns(url):
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed(url)


def test_assert_allows_public_ip_literal():
    assert_egress_allowed("https://93.184.216.34/x")


def test_assert_blocks_non_http_scheme():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("file:///etc/passwd")


def test_assert_blocks_hostname_resolving_to_internal(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://evil.example.com/x")


def test_assert_respects_allowlist(monkeypatch):
    monkeypatch.setenv("CORE_LLM_EGRESS_ALLOWLIST", "llm.example.com")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    assert_egress_allowed("https://llm.example.com/v1/chat")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://other.example.com/v1/chat")
```

Confirmer rouge (`app.copilot.egress` n'existe pas encore) :

```bash
cd core && uv run pytest tests/test_copilot_egress.py -v
```

### Étape 2 : créer `core/app/copilot/egress.py`

Dupliquer la structure de `core/app/harvest/egress.py`
(`EgressBlockedError`, `_allowlist()`, `_is_internal()`,
`assert_egress_allowed()` — code identique, seule `_ALLOWLIST_ENV` change),
avec un docstring qui explique le choix de duplication plutôt que d'import
(spec §1 : `app.copilot` est légalement au-dessus d'`app.harvest` dans le
contrat de couches, mais réutiliser `assert_egress_allowed` de
`app.harvest.egress` coiffrerait l'allowlist du copilote sur celle du
moissonnage — raison de correction, pas de convention). Ajouter en plus,
absent des 3 gardes existantes :

```python
class _GuardedAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport):
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert_egress_allowed(str(request.url))
        return await self._inner.handle_async_request(request)


def build_guarded_async_client(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=_GuardedAsyncTransport(httpx.AsyncHTTPTransport()), timeout=timeout
    )
```

`_ALLOWLIST_ENV = "CORE_LLM_EGRESS_ALLOWLIST"` (nommée d'après les 3
variables `CORE_LLM_*` déjà existantes — `CORE_LLM_API_URL`,
`CORE_LLM_API_KEY`, `CORE_LLM_MODEL`, `CORE_LLM_PROVIDER`).

Rejouer l'Étape 1 : vert.

### Étape 3 : câbler la garde dans `OpenAICompatibleLLMProvider`

Dans `core/app/copilot/llm_provider.py`, remplacer :

```python
        if self._client is not None:
            response = await self._client.post(self._api_url, headers=headers, json=payload)
        else:
            async with httpx.AsyncClient(timeout=LLM_CALL_TIMEOUT_SECONDS) as client:
                response = await client.post(self._api_url, headers=headers, json=payload)
```

par :

```python
        if self._client is not None:
            response = await self._client.post(self._api_url, headers=headers, json=payload)
        else:
            async with build_guarded_async_client(timeout=LLM_CALL_TIMEOUT_SECONDS) as client:
                response = await client.post(self._api_url, headers=headers, json=payload)
```

avec `from app.copilot.egress import build_guarded_async_client` en tête de
fichier. Le chemin `self._client is not None` (injecté, seulement utilisé
par les tests) reste délibérément non gardé — c'est le seul chemin qui ne
tourne jamais en production (`get_llm_provider()` ne passe jamais
`http_client`).

Ajouter dans `core/tests/test_copilot_llm_provider.py` :

```python
@pytest.mark.anyio
async def test_openai_compatible_provider_blocks_ssrf_target_when_unguarded():
    # http_client=None : chemin réellement emprunté en production, celui
    # que get_llm_provider() construit.
    provider = OpenAICompatibleLLMProvider(
        api_url="http://169.254.169.254/latest/meta-data/",
        api_key="test-key",
        model="gpt-4o-mini",
    )
    from app.copilot.egress import EgressBlockedError

    with pytest.raises(EgressBlockedError):
        await provider.chat(messages=[], tools=[])
```

Falsifier : commenter temporairement le remplacement (revenir à
`httpx.AsyncClient` nu), confirmer que ce test échoue différemment (timeout
réseau ou connexion refusée, pas `EgressBlockedError`) — puis restaurer.

```bash
cd core && uv run pytest tests/test_copilot_llm_provider.py -v
```

### Étape 4 : mapper `EgressBlockedError` en 502 dans `_run_turn`

Dans `core/app/copilot/routes.py`, `_run_turn`, entourer l'appel
`await provider.chat(messages, all_tools)` (dans la boucle
`for _ in range(MAX_TOOL_ITERATIONS):`) :

```python
        try:
            turn: LLMTurn = await provider.chat(messages, all_tools)
        except EgressBlockedError as exc:
            raise HTTPException(
                status_code=502, detail=f"garde d'egress LLM : cible bloquée ({exc})"
            ) from exc
```

avec `from app.copilot.egress import EgressBlockedError` en tête de fichier.

Ajouter dans `core/tests/test_copilot_routes.py` (même patron que les tests
existants qui monkeypatchent `routes_module.get_llm_provider`) :

```python
def test_copilot_turn_maps_egress_blocked_to_502(monkeypatch, ...):
    from app.copilot.egress import EgressBlockedError

    class _BlockedProvider:
        async def chat(self, messages, tools):
            raise EgressBlockedError("cible interne bloquée")

    monkeypatch.setattr(routes_module, "get_llm_provider", lambda: _BlockedProvider())
    response = client.post("/copilot/turn", json={...}, headers=...)
    assert response.status_code == 502
```

(reprendre exactement les fixtures/headers du client déjà utilisées par les
tests voisins de ce fichier — ne pas les redéfinir).

Falsifier : retirer temporairement le `try/except` ajouté, confirmer que ce
test échoue (500 au lieu de 502) — puis restaurer.

```bash
cd core && uv run pytest tests/test_copilot_routes.py -v
```

### Étape 5 : suite complète + qualité

```bash
cd core && uv run pytest
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles \
  && uv run lint-imports
```

Commit : `fix(core): garde d'egress SSRF sur l'appel LLM sortant du copilote (GAP-02)`.

---

## Task 2 : retirer `MARTIN_SECRET`, variable orpheline (GAP-41)

**Fichiers touchés :** `scripts/bootstrap-env.sh` ; `.env.example` ;
`core/tests/test_deployability.py`.

### Étape 1 : filet — verrouiller l'absence de la variable

Ajouter dans `core/tests/test_deployability.py`, à côté des tests
existants sur `.env.example`/`bootstrap-env.sh` :

```python
def test_martin_secret_is_fully_removed():
    """GAP-41 : MARTIN_SECRET était générée par bootstrap-env.sh et
    documentée dans .env.example sans jamais être consommée par le service
    martin (docker-compose.yml) — dérive connue depuis SP-1d3, jamais
    corrigée avant ce test. Retirée plutôt que câblée : l'accès à Martin
    est déjà protégé par admin-auth@docker (forwardAuth Traefik), une
    seconde protection par secret partagé serait redondante et n'aurait
    jamais rien protégé de plus (spec SP-45 §2)."""
    assert "MARTIN_SECRET" not in ENV_EXAMPLE.read_text()
    assert "MARTIN_SECRET" not in BOOTSTRAP_ENV_SH.read_text()
    assert "MARTIN_SECRET" not in DOCUMENTED_BUT_UNWIRED_EXEMPTIONS
```

Confirmer rouge (`MARTIN_SECRET` présente dans les 3 emplacements
aujourd'hui) :

```bash
cd core && uv run pytest tests/test_deployability.py::test_martin_secret_is_fully_removed -v
```

### Étape 2 : retirer la variable des 3 emplacements

- `scripts/bootstrap-env.sh` ligne 17 : `for var in PG_PASSWORD
  MINIO_PASSWORD KC_PASSWORD MARTIN_SECRET; do` → `for var in PG_PASSWORD
  MINIO_PASSWORD KC_PASSWORD; do`.
- `.env.example` : retirer les 8 lignes du bloc `# ─── Martin (orpheline
  connue...` à `MARTIN_SECRET=martin-client-secret` inclus.
- `core/tests/test_deployability.py` : retirer l'entrée `"MARTIN_SECRET"`
  (et son commentaire) de `DOCUMENTED_BUT_UNWIRED_EXEMPTIONS` — le set
  devient vide ; si le linter/mypy se plaint d'un set vide inutile,
  conserver la déclaration avec un commentaire expliquant qu'elle reste le
  point d'extension pour une future dérive de même classe (ne pas retirer
  le mécanisme, seulement son unique occupant actuel).

### Étape 3 : vérifier que les tests existants sur bootstrap-env.sh restent verts

`test_bootstrap_env_generates_a_well_formed_core_secrets_master_key` ne
référence pas `MARTIN_SECRET` — doit rester vert sans changement. Rejouer
explicitement pour le confirmer (piège CLAUDE.md n°4 : un correctif sur une
tâche peut casser un test voisin non touché directement).

```bash
cd core && uv run pytest tests/test_deployability.py -v
cd core && uv run pytest
```

Commit : `chore(deploy): retire MARTIN_SECRET, jamais consommée par martin (GAP-41)`.

---

## Task 3 : rate-limit dédié sur `POST /collections/empty` (GAP-58)

**Fichiers touchés :** `core/app/ratelimit/limiter.py` ;
`core/tests/test_ratelimit.py` ; `core/tests/test_collections_empty_route.py`.

### Étape 1 : filet — unité pure sur `route_group()`

Dans `core/tests/test_ratelimit.py` :

```python
def test_route_group_covers_collections_empty():
    assert route_group("/collections/empty", "POST", _EXPORT_PATH_RE) == "collections_empty"


def test_route_group_ignores_get_on_collections_empty_path():
    # Défensif : la route elle-même n'expose que POST, mais route_group()
    # ne doit pas non plus limiter un verbe qui n'existe pas sur ce chemin.
    assert route_group("/collections/empty", "GET", _EXPORT_PATH_RE) is None
```

Confirmer rouge (`"collections_empty"` inconnu de `route_group()` —
`KeyError`/`None` selon l'implémentation actuelle) :

```bash
cd core && uv run pytest tests/test_ratelimit.py -k collections_empty -v
```

### Étape 2 : filet — intégration réelle (429 après budget épuisé)

Dans `core/tests/test_collections_empty_route.py`, réutiliser exactement la
fixture `pg_app` existante (marquée `pytest.mark.postgis`) :

```python
def test_rate_limited_after_budget_exhausted(pg_app):
    # Budget "collections_empty" = 5/60s (limiter.py) — la 6e création en
    # boucle serrée doit être coupée, DDL réel ou pas.
    for i in range(5):
        resp = pg_app.post(
            "/collections/empty",
            json={"title": f"Requête {i}", "columns": [{"name": "x", "sqlType": "text"}]},
        )
        assert resp.status_code == 201
    resp = pg_app.post(
        "/collections/empty",
        json={"title": "Requête 6", "columns": [{"name": "x", "sqlType": "text"}]},
    )
    assert resp.status_code == 429
```

Confirmer rouge (aucune limite aujourd'hui, la 6e requête réussit aussi en
201) :

```bash
cd core && uv run pytest tests/test_collections_empty_route.py -k rate_limited -v
```

### Étape 3 : fix — nouveau groupe dans `limiter.py`

```python
_COLLECTIONS_EMPTY_RE = re.compile(r"^/collections/empty$")

_BUDGETS = {
    "sql": 10,
    "llm": 20,
    "jobs": 15,
    "harvest": 10,
    "collections_empty": 5,
}


def route_group(path: str, method: str, export_path_re: re.Pattern[str]) -> str | None:
    if _SQL_RE.match(path):
        return "sql"
    if _LLM_RE.match(path):
        return "llm"
    if export_path_re.match(path):
        return "jobs"
    if method == "POST" and _COLLECTIONS_EMPTY_RE.match(path):
        return "collections_empty"
    if _HARVEST_RE.match(path) and method != "GET":
        return "harvest"
    return None
```

Rejouer les Étapes 1 et 2 : vertes.

Falsifier le test d'intégration : commenter temporairement la branche
`collections_empty` de `route_group()`, confirmer que le test de l'Étape 2
échoue à nouveau (6e requête en 201 au lieu de 429) — puis restaurer.

```bash
cd core && uv run pytest tests/test_ratelimit.py tests/test_collections_empty_route.py -v
cd core && uv run pytest
```

Commit : `fix(core): rate-limit dédié sur POST /collections/empty (GAP-58)`.

---

## Task 4 : rate limiter — 3 correctifs (GAP-61)

**Fichiers touchés :** `core/app/main.py` ; `core/app/ratelimit/limiter.py` ;
`core/app/harvest/live_query.py` ; `core/tests/test_ratelimit.py` ;
`core/tests/test_harvest_live_query.py`.

Sous-tâche indépendante de la Task 3, mais touche le même fichier
`limiter.py` — **exécuter Task 3 et Task 4 en séquence, jamais en
parallèle sur le même arbre**, pour éviter un conflit d'édition sur
`_BUDGETS`/`route_group()`.

### Étape 1 : filet — clé d'appelant anonyme distincte par IP

Dans `core/tests/test_ratelimit.py` :

```python
from app.ratelimit.limiter import caller_key


def test_caller_key_uses_authorization_header_when_present():
    assert caller_key("Bearer abc", "1.2.3.4") == "Bearer abc"


def test_caller_key_falls_back_to_client_host_when_anonymous():
    assert caller_key(None, "1.2.3.4") != caller_key(None, "5.6.7.8")


def test_caller_key_anonymous_never_collides_with_a_real_token():
    # La chaîne vide ne doit plus être une clé partagée par tout le monde.
    assert caller_key(None, "1.2.3.4") != ""
```

Confirmer rouge (`caller_key` n'existe pas encore) :

```bash
cd core && uv run pytest tests/test_ratelimit.py -k caller_key -v
```

Ajouter aussi un test d'intégration bout-en-bout (nécessite le middleware de
l'Étape 3 ci-dessous pour passer — rouge tant qu'il n'est pas câblé) :

```python
def test_anonymous_callers_have_independent_budgets_by_ip(monkeypatch):
    client = _client(monkeypatch)
    for _ in range(10):
        client.post(
            "/analytics/sql",
            json={"sql": "select 1"},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
    # 1.2.3.4 est épuisé, mais 5.6.7.8 démarre avec un budget frais — sans
    # le fix, les deux partagent la même clé (chaîne vide) et le 2e appel
    # échoue aussi en 429.
    response = client.post(
        "/analytics/sql",
        json={"sql": "select 1"},
        headers={"X-Forwarded-For": "5.6.7.8"},
    )
    assert response.status_code != 429
```

### Étape 2 : fix — `caller_key()` dans `limiter.py`

```python
def caller_key(auth_header: str | None, client_host: str | None) -> str:
    """Clé d'appelant pour le compteur glissant : l'en-tête Authorization
    brut s'il existe (comportement inchangé pour tout appelant authentifié),
    sinon l'IP réelle du visiteur (nécessite ProxyHeadersMiddleware côté
    app.main, cf. commentaire dédié) — jamais la chaîne vide partagée par
    tous les anonymes (GAP-61.a)."""
    if auth_header:
        return auth_header
    return f"anon:{client_host or 'unknown'}"
```

Dans `core/app/main.py`, `rate_limit_guard` :

```python
            caller_key_value = caller_key(
                request.headers.get("authorization"),
                request.client.host if request.client else None,
            )
            if not rate_limiter.allow(caller_key_value, group):
```

(import `caller_key` aux côtés de `RateLimiter, route_group`).

### Étape 3 : fix — `ProxyHeadersMiddleware` pour que `request.client` reflète l'IP réelle

Dans `core/app/main.py`, imports :

```python
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
```

À la fin de `create_app()`, **après** tous les `@app.middleware("http")`
déjà déclarés (Starlette empile en ordre inverse de déclaration — le
dernier `add_middleware` devient le plus extérieur, celui qui voit la
requête en premier ; vérifié empiriquement avant d'écrire ce plan, cf. spec
§4.a), juste avant `return app` :

```python
    # GAP-61.a : sans cette couche, request.client reflète l'IP du
    # conteneur Traefik (seul point d'entrée réseau vers ce service — `core`
    # n'expose aucun port hôte direct), identique pour tous les visiteurs,
    # ce qui viderait caller_key() de son utilité pour les appelants
    # anonymes. trusted_hosts="*" est sûr ici : gis-net est un réseau Docker
    # interne, aucun tiers non maîtrisé ne peut y injecter X-Forwarded-For.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
```

Rejouer l'Étape 1 : vertes, y compris le test d'intégration bout-en-bout.

Falsifier : commenter temporairement `app.add_middleware(...)`, confirmer
que `test_anonymous_callers_have_independent_budgets_by_ip` échoue à nouveau
(429 sur le 2e appelant) — puis restaurer.

```bash
cd core && uv run pytest tests/test_ratelimit.py -v
```

### Étape 4 : filet — les 2 routes ArcGIS live-query manquantes

Dans `core/tests/test_ratelimit.py` :

```python
def test_route_group_covers_arcgis_live_query_regardless_of_method():
    assert route_group("/datasets/abc/arcgis/items", "GET", _EXPORT_PATH_RE) == "harvest"
    assert route_group("/datasets/abc/arcgis/aggregate", "POST", _EXPORT_PATH_RE) == "harvest"


def test_route_group_arcgis_export_routes_still_map_to_jobs():
    # Non-régression : ces 2 routes étaient DÉJÀ couvertes (via
    # _EXPORT_PATH_RE, groupe "jobs") avant ce correctif — l'analyse
    # GAP-61 les comptait à tort parmi les 4 échappées (spec SP-45 §4).
    assert route_group("/datasets/abc/arcgis/export", "POST", _EXPORT_PATH_RE) == "jobs"
    assert route_group("/datasets/abc/arcgis/export/items", "GET", _EXPORT_PATH_RE) == "jobs"
```

Confirmer : le 2e test est déjà vert aujourd'hui (non-régression, à ne pas
casser) ; le 1er est rouge (`route_group` retourne `None` pour les deux
chemins aujourd'hui).

```bash
cd core && uv run pytest tests/test_ratelimit.py -k arcgis_live -v
```

### Étape 5 : fix — regex + branche dans `route_group()`

```python
_ARCGIS_LIVE_QUERY_RE = re.compile(r"^/datasets/[^/]+/arcgis/(items|aggregate)$")


def route_group(path: str, method: str, export_path_re: re.Pattern[str]) -> str | None:
    if _SQL_RE.match(path):
        return "sql"
    if _LLM_RE.match(path):
        return "llm"
    if export_path_re.match(path):
        return "jobs"
    if method == "POST" and _COLLECTIONS_EMPTY_RE.match(path):  # posé par Task 3
        return "collections_empty"
    if _ARCGIS_LIVE_QUERY_RE.match(path):
        return "harvest"
    if _HARVEST_RE.match(path) and method != "GET":
        return "harvest"
    return None
```

Rejouer l'Étape 4 : vertes.

### Étape 6 : filet — sweep du cache module-global de `live_query.py`

Fichier de test existant du module, confirmé : `core/tests/test_harvest_live_query.py`.
Ajouter, en reprenant le patron de
`test_expired_bucket_is_pruned_from_hits` (`test_ratelimit.py`) :

```python
def test_expired_cache_entry_is_pruned_even_if_never_requeried(monkeypatch):
    from app.harvest import live_query

    now = [1000.0]
    monkeypatch.setattr(live_query.time, "monotonic", lambda: now[0])
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"features": []})
    ))

    live_query.fetch_query(client, "https://arcgis.example.com/svc", {"stale": "1"})
    key = live_query._cache_key("https://arcgis.example.com/svc", {"stale": "1"})
    assert key in live_query._cache

    now[0] += live_query._CACHE_TTL_SECONDS + 1.0
    # Balayage périodique déclenché par d'AUTRES clés, jamais celle qui a
    # expiré — reproduit le patron de l'appelant réel qui ne revient jamais
    # sur les mêmes params.
    for i in range(live_query._SWEEP_INTERVAL):
        live_query.fetch_query(client, "https://arcgis.example.com/svc", {"fresh": str(i)})

    assert key not in live_query._cache
```

Confirmer rouge (`live_query._SWEEP_INTERVAL` n'existe pas encore, et sans
sweep la clé périmée reste dans `_cache`).

### Étape 7 : fix — sweep périodique dans `live_query.py`

```python
_SWEEP_INTERVAL = 50
_calls_since_sweep = 0


def _sweep(now: float) -> None:
    stale_keys = [key for key, (expires_at, _) in _cache.items() if now >= expires_at]
    for key in stale_keys:
        del _cache[key]


def fetch_query(client: httpx.Client, external_url: str, params: dict[str, str]) -> dict:
    global _calls_since_sweep
    key = _cache_key(external_url, params)
    cached = _cache.get(key)
    if cached is not None:
        expires_at, value = cached
        if time.monotonic() < expires_at:
            return value
        del _cache[key]
    response = client.get(f"{external_url}/query", params=params)
    response.raise_for_status()
    data = response.json()
    _cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, data)
    _calls_since_sweep += 1
    if _calls_since_sweep >= _SWEEP_INTERVAL:
        _sweep(time.monotonic())
        _calls_since_sweep = 0
    return data
```

Rejouer l'Étape 6 : vert.

Falsifier : commenter temporairement l'appel à `_sweep(...)`, confirmer que
le test de l'Étape 6 échoue à nouveau — puis restaurer.

### Étape 8 : suite complète

```bash
cd core && uv run pytest
cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
```

Commit : `fix(core): rate limiter — clé anonyme par IP, 2 routes ArcGIS manquantes, sweep du cache live_query (GAP-61)`.

---

## Task 5 : `restart: unless-stopped` sur `traefik` (GAP-79)

**Fichiers touchés :** `docker-compose.yml` ; `core/tests/test_deployability.py`.

### Étape 1 : filet

```python
def test_traefik_has_a_restart_policy():
    """GAP-79 : traefik (point d'entrée public unique) était le seul
    service durablement actif sans restart:, dans docker-compose.yml comme
    dans son overlay prod (hérité, non redéclaré) — un crash de l'ingress
    laissait toute l'instance publique indisponible jusqu'à intervention
    manuelle."""
    assert services(BASE)["traefik"].get("restart") == "unless-stopped"
```

Confirmer rouge :

```bash
cd core && uv run pytest tests/test_deployability.py::test_traefik_has_a_restart_policy -v
```

### Étape 2 : fix

Dans `docker-compose.yml`, service `traefik`, après `networks: [gis-net]` :

```yaml
    networks: [gis-net]
    restart: unless-stopped
```

Rejouer l'Étape 1 : vert. Vérifier que `docker-compose.prod.yml` en hérite
sans édition (fusion Compose — clé non réécrite par l'overlay) :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config \
  | python3 -c "import sys, yaml; d = yaml.safe_load(sys.stdin); print(d['services']['traefik'].get('restart'))"
```

(nécessite un `.env`/`.env.prod` minimal pour que `docker compose config`
résolve sans erreur de substitution manquante — utiliser
`scripts/bootstrap-env.sh` si besoin, ou passer les variables requises en
ligne de commande le temps de la vérification, sans les committer.)

```bash
cd core && uv run pytest
```

Commit : `fix(deploy): restart: unless-stopped sur traefik (GAP-79)`.

---

## Task 6 : purge de l'historique git de la clé `age` de test (GAP-77)

**Opération manuelle, hors code — accord explicite de Tanguy requis avant
la Sous-étape 3 (irréversible, réécrit l'historique public).** Aucun fichier
du dépôt de travail n'est modifié par cette tâche (le mirror réécrit est un
clone séparé, jetable en cas d'échec).

### Sous-étape 1 : vérifier avant

```bash
git log --all -p -S "AGE-SECRET-KEY" --oneline | grep -c "^commit"
git grep -n "AGE-SECRET-KEY-REDACTED-VOIR-REV-171" $(git rev-list --all) 2>/dev/null | head -5
```

Documenter le nombre de commits touchés dans le ledger de session.

### Sous-étape 2 : préparer le mirror (pas de risque, aucune écriture sur origin)

```bash
git clone --mirror https://github.com/tlenenao/geostudio.git /tmp/geostudio-mirror-purge
cd /tmp/geostudio-mirror-purge
pip install --user git-filter-repo  # ou: uv tool install git-filter-repo
git filter-repo --replace-text <(echo "AGE-SECRET-KEY-REDACTED-VOIR-REV-171==>AGE-SECRET-KEY-REDACTED")
```

### Sous-étape 3 : vérifier après, sur le mirror réécrit (avant tout push)

```bash
cd /tmp/geostudio-mirror-purge
git log --all -p -S "AGE-SECRET-KEY-REDACTED-VOIR-REV-171" | wc -l
# attendu : 0
```

**Arrêt obligatoire ici tant que Tanguy n'a pas confirmé l'accord explicite
pour la suite (push --force et coordination des clones existants).**

### Sous-étape 4 (seulement après accord) : push --force + coordination

```bash
cd /tmp/geostudio-mirror-purge
git push --force --all origin
git push --force --tags origin
```

Puis, avant de continuer tout travail sur le clone de travail principal de
cette session :

```bash
cd /home/lenen/projets/geostudio
git fetch origin
git status  # confirmer l'état après réécriture, ne pas `pull` sur un historique divergent
```

Avertir toute autre session concurrente connue de re-cloner plutôt que
`pull` (piège CLAUDE.md n°9 — sessions concurrentes sur le même arbre).

### Sous-étape 5 : purge du cache GitHub

Contacter le support GitHub (dépôt public) pour demander l'expiration du
cache des objets Git contenant le secret — les objets détachés par
`filter-repo` restent atteignables par hash jusqu'à garbage-collection côté
GitHub, un push force seul ne les retire pas de leur CDN de cache
immédiatement.

Pas de commit associé (aucun fichier du dépôt de travail n'est modifié).
Documenter l'exécution (avant/après, accord obtenu, date) dans le ledger de
session — ne pas ajouter de ligne `### Livré` dans CLAUDE.md tant que la
Sous-étape 5 n'est pas confirmée côté GitHub.

---

## Task 7 : activer secret scanning + Dependabot security updates (GAP-78)

**Opération manuelle, hors code — accord explicite de Tanguy requis avant
la Sous-étape 2 (change un réglage réel sur le dépôt GitHub public).**

### Sous-étape 1 : vérifier avant

```bash
gh api repos/tlenenao/geostudio | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['security_and_analysis'], indent=2))"
```

Documenter la sortie (les 3 champs à `"disabled"`) dans le ledger de
session.

### Sous-étape 2 (seulement après accord) : bascule

```bash
gh api --method PATCH repos/tlenenao/geostudio --input - <<'EOF'
{
  "security_and_analysis": {
    "secret_scanning": {"status": "enabled"},
    "secret_scanning_push_protection": {"status": "enabled"},
    "dependabot_security_updates": {"status": "enabled"}
  }
}
EOF
```

### Sous-étape 3 : vérifier après

```bash
gh api repos/tlenenao/geostudio | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['security_and_analysis'], indent=2))"
```

Attendu : les 3 champs nommés par GAP-78 à `"enabled"`.

Pas de commit associé (aucun fichier du dépôt de travail n'est modifié).
Documenter l'exécution (avant/après, date) dans le ledger de session.

---

## Clôture de plan

- [ ] **Suite complète finale** (Tâches 1 à 5 uniquement — 6 et 7 sont hors
  code) :

```bash
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles \
  && uv run lint-imports \
  && uv run pytest \
  && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```

- [ ] **Diff OpenAPI/types TS vide, vérifié explicitement** (piège CLAUDE.md
  n°1 — aucune des 5 tâches de code ne change de route ni de schéma) :

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff core/openapi.json  # attendu : vide
cd ../shell && npm run gen:api-types
git diff shell/src/api/generated/core-schema.d.ts  # attendu : vide
```

- [ ] **Statut des Tâches 6 et 7** (git history purge, réglages GitHub) :
  documenter explicitement dans le suivi de clôture si l'accord de Tanguy a
  été obtenu et l'opération exécutée, ou si elles restent en attente —
  jamais les marquer closes sans vérification après (Sous-étape 3/Sous-étape 3
  respectives).
- [ ] **Mettre à jour CLAUDE.md** (`### Livré`) avec une ligne SP-45 résumant
  les 7 correctifs (GAP-02 garde d'egress LLM, GAP-41 MARTIN_SECRET retirée,
  GAP-58 rate-limit sur collections/empty, GAP-61 clé anonyme par IP + 2
  routes ArcGIS + sweep du cache, GAP-79 restart traefik ; GAP-77/GAP-78
  seulement si effectivement exécutées avec accord — sinon les laisser dans
  `### Suivis et dette non bloquante` avec leur statut réel).
