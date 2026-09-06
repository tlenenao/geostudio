# SPDX-License-Identifier: Apache-2.0
import duckdb
from fastapi.testclient import TestClient

from app.features import routes as features_routes
from app.main import _EXPORT_PATH_RE, create_app
from app.ratelimit.limiter import _SWEEP_INTERVAL, RateLimiter, route_group


def _fake_duckdb_factory():
    return duckdb.connect(":memory:")


def _client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    # /analytics/sql exécute réellement son endpoint pour les requêtes sous
    # le budget (seule la 11e est court-circuitée par le middleware) — sans
    # cet override, get_duckdb_connection_factory lève un KeyError sur
    # S3_ENDPOINT_URL (non défini hors stack docker), non lié à ce qu'on
    # teste ici. Même patron que tests/test_analytics_sql_routes.py. Le SQL
    # utilisé ("select 1") ne référence aucune table, donc aucune extension
    # DuckDB supplémentaire (spatial/httpfs) n'est nécessaire.
    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: (
        _fake_duckdb_factory
    )
    return TestClient(app)


def test_sql_route_rate_limited_after_budget_exhausted(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": "Bearer same-caller-token"}
    for _ in range(10):
        client.post("/analytics/sql", json={"sql": "select 1"}, headers=headers)
    response = client.post("/analytics/sql", json={"sql": "select 1"}, headers=headers)
    assert response.status_code == 429
    assert "retry-after" in {k.lower() for k in response.headers.keys()}
    assert response.headers["content-type"] == "application/problem+json"


def test_different_callers_have_independent_budgets(monkeypatch):
    client = _client(monkeypatch)
    for _ in range(10):
        client.post(
            "/analytics/sql",
            json={"sql": "select 1"},
            headers={"Authorization": "Bearer caller-a"},
        )
    # caller-a est épuisé, mais caller-b démarre avec un budget frais
    response = client.post(
        "/analytics/sql", json={"sql": "select 1"}, headers={"Authorization": "Bearer caller-b"}
    )
    assert response.status_code != 429


def test_health_endpoint_not_rate_limited_by_sql_budget(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": "Bearer same-caller-token"}
    for _ in range(10):
        client.post("/analytics/sql", json={"sql": "select 1"}, headers=headers)
    response = client.get("/health", headers=headers)
    assert response.status_code != 429


# Revue finale SP-26 (I1) : le budget "harvest" (10/60s) couvrait TOUTES les
# routes /harvest/*, y compris GET /harvest/layers et
# GET /harvest/feature-layers — deux lectures pures (couches déjà
# enregistrées en base, aucun appel réseau externe) que
# shell/src/map/LayerPicker.tsx interroge à chaque frappe, sans debounce.
# Une recherche de 11 caractères épuisait le budget en quelques secondes ;
# Promise.allSettled côté shell avale le 429 en silence, les couches
# externes disparaissent du sélecteur sans erreur visible. Ces deux tests
# épinglent la distinction lecture/écriture désormais faite par méthode
# HTTP dans app.ratelimit.limiter.route_group.


def test_harvest_read_routes_are_not_rate_limited(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": "Bearer same-caller-token"}
    for _ in range(15):
        response = client.get("/harvest/layers", headers=headers)
        assert response.status_code != 429
    for _ in range(15):
        response = client.get("/harvest/feature-layers", headers=headers)
        assert response.status_code != 429


def test_harvest_write_routes_stay_rate_limited(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": "Bearer same-caller-token"}
    body = {
        "type": "stac",
        "url": "https://stac.example.com/collections",
        "mode": "reference",
        "enabled": True,
        "intervalMinutes": 60,
    }
    statuses = [
        client.post("/harvest/sources", json=body, headers=headers).status_code for _ in range(11)
    ]
    assert statuses.count(429) >= 1


def test_route_group_ignores_get_on_harvest_paths():
    assert route_group("/harvest/layers", "GET", _EXPORT_PATH_RE) is None
    assert route_group("/harvest/feature-layers", "GET", _EXPORT_PATH_RE) is None
    assert route_group("/harvest/sources", "GET", _EXPORT_PATH_RE) is None
    assert route_group("/harvest/sources/abc", "GET", _EXPORT_PATH_RE) is None


def test_route_group_covers_harvest_writes():
    assert route_group("/harvest/sources", "POST", _EXPORT_PATH_RE) == "harvest"
    assert route_group("/harvest/sources/abc", "PATCH", _EXPORT_PATH_RE) == "harvest"
    assert route_group("/harvest/sources/abc", "DELETE", _EXPORT_PATH_RE) == "harvest"
    assert route_group("/harvest/sources/abc/run", "POST", _EXPORT_PATH_RE) == "harvest"


def test_route_group_covers_pipeline_webhook_trigger():
    # GAP-24, SP-53 : seule route sans Depends(get_current_user) — son
    # propre groupe de budget, distinct de "jobs"/"harvest".
    assert route_group("/pipelines/abc/trigger", "POST", _EXPORT_PATH_RE) == "webhook-trigger"


def test_route_group_ignores_get_on_pipeline_webhook_trigger():
    assert route_group("/pipelines/abc/trigger", "GET", _EXPORT_PATH_RE) is None


# Revue finale SP-26 (I4) : `_hits` grossissait sans borne sous une vraie
# rotation de jeton OIDC (nouvelle clé d'appelant à chaque refresh, jamais
# réclamée). Ce test prouve qu'une entrée dont la fenêtre expire
# complètement est bien RETIRÉE de `_hits` (pas seulement laissée vide
# dedans) après le balayage périodique — comparaison de taille du dict
# avant/après, pas juste un comportement observable équivalent.
def test_expired_bucket_is_pruned_from_hits(monkeypatch):
    limiter = RateLimiter()
    now = [1000.0]
    monkeypatch.setattr("app.ratelimit.limiter.time.monotonic", lambda: now[0])

    # Une clé qui n'est plus jamais réutilisée après sa fenêtre.
    assert limiter.allow("stale-caller", "harvest") is True
    assert ("stale-caller", "harvest") in limiter._hits

    # La fenêtre de "stale-caller" expire complètement...
    now[0] += 61.0
    # ...puis on déclenche le balayage périodique avec assez d'appels d'un
    # AUTRE appelant (le balayage tourne toutes les _SWEEP_INTERVAL requêtes,
    # peu importe la clé qui les émet).
    for _ in range(_SWEEP_INTERVAL):
        limiter.allow("fresh-caller", "harvest")

    assert ("stale-caller", "harvest") not in limiter._hits
