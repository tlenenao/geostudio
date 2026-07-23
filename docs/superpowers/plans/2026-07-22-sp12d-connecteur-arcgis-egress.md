# SP-12d — Connecteur ArcGIS FS + durcissement egress SSRF — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un connecteur de moissonnage ArcGIS Feature Service (référence + copie GeoJSON paginée) au moteur SP-12c, et une garde d'egress SSRF partagée par tous les connecteurs réseau.

**Architecture:** Zéro nouvelle route, zéro nouvelle table, zéro nouveau modèle d'autorisation. On étend l'abstraction `HarvestConnector` (SP-12c) d'une méthode `fetch_copy_geojson`, on remplace le seam `items_fetcher(url)->bytes` du moteur par `connector.fetch_copy_geojson(rec, http_get=guarded_get)`, on ajoute `ArcgisConnector` au registre, et on insère une garde d'egress (`app/harvest/egress.py`) dans le client HTTP par défaut de tous les connecteurs. Trois suivis SP-12c (cap `_MAX_DOCUMENTS` STAC, skip `running` du sweep, masquage démo shell) sont repliés.

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy / httpx / pyproj (existant SP-6b) / procrastinate ; React / TypeScript / react-query / Playwright.

## Global Constraints

- **Copier verbatim les valeurs et invariants du spec** `docs/superpowers/specs/2026-07-22-sp12d-connecteur-arcgis-egress-design.md`.
- **Le moteur `harvest_source` NE LÈVE JAMAIS** — toute erreur (fetch, import, egress bloqué) → `source.last_status="error"`, `last_error` tronqué à 500 chars, aucun item créé, jamais de job zombie. La garde lève **dans** le connecteur/getter, capturée par les `try` déjà en place (§3 spec).
- **Parsing tolérant et borné** partout côté connecteur : un service distant malformé/cyclique/géant/hostile ne fait jamais tomber le moissonnage ni ne bloque le worker. Champs manquants → replis documentés ; réponse non-JSON/non-objet → `logger.warning`, jamais d'exception qui fuite.
- **Reprojection bbox = enveloppe seule** (coins reprojetés via pyproj), approximation de catalogue suffisante ; jamais d'exception qui fuite → repli bbox monde `[-180.0, -90.0, 180.0, 90.0]`.
- **Auth distante hors périmètre** : services ArcGIS **publics seulement** en v0, aucun token/OAuth vers le distant.
- **Frontière import-linter** : `app.harvest` est déjà au-dessus de `app.ingestion` dans `layers` (core/pyproject.toml). `httpx`/`pyproj`/`socket`/`ipaddress` sont des libs tierces, hors contrat. Le contrat `layers` reste **inchangé** — `uv run lint-imports` doit rester clean.
- **En-tête SPDX** `# SPDX-License-Identifier: Apache-2.0` en première ligne de tout nouveau fichier `core/app/**` et `core/tests/**` ; `// SPDX-License-Identifier: Apache-2.0` pour tout nouveau `shell/src/**`.
- **Commandes de test.** Core : `cd core && uv run pytest` (SQLite, always-run) ; tests `@pytest.mark.postgis` : `cd core && CORE_TEST_DATABASE_URL=<dsn> uv run pytest -m postgis` contre un PostGIS+pgvector réel. Shell : `cd shell && npm test` (Vitest) ; `npm run e2e` (Playwright) ; `npm run build` (tsc + vite). Lint imports : `cd core && uv run lint-imports`.
- **Régénération OpenAPI/types** (Task 5 uniquement, car le schéma change réellement) : `cd core && uv run python scripts/export_openapi.py openapi.json` puis `cd shell && npm run gen:api-types`. Le job CI `api-types-drift` doit rester vert.
- **Ne pas toucher** aux 44 specs E2E existantes ; en ajouter **une** (`harvest-arcgis.spec.ts`).

---

## File Structure

**Cœur — nouveau :**
- `core/app/harvest/egress.py` — `EgressBlockedError`, `assert_egress_allowed`, `build_guarded_client`, `guarded_get`.
- `core/app/harvest/connectors/arcgis.py` — `ArcgisConnector`.
- `core/tests/test_harvest_egress.py`, `core/tests/test_harvest_arcgis_connector.py`, `core/tests/test_harvest_arcgis_integration.py`.

**Cœur — modifié :**
- `core/app/harvest/connectors/base.py` — `HarvestConnector` gagne `fetch_copy_geojson`.
- `core/app/harvest/connectors/stac.py` — implémente `fetch_copy_geojson`, ajoute `_MAX_DOCUMENTS`, client par défaut gardé.
- `core/app/harvest/connectors/__init__.py` — enregistre `ArcgisConnector`.
- `core/app/harvest/service.py` — remplace le seam `items_fetcher` par `connector.fetch_copy_geojson`.
- `core/app/harvest/repository.py` — `list_due_sources` saute `running` avec reclaim par âge.
- `core/app/harvest/schemas.py` — `type` accepte `"arcgis"`.
- `core/openapi.json` — régénéré (Task 5).
- `core/tests/test_harvest_service.py`, `core/tests/test_harvest_stac_connector.py`, `core/tests/test_harvest_repository.py` — adaptés au nouveau seam.

**Shell — modifié :**
- `shell/src/api/types.ts` — `HarvestSourceType` gagne `"arcgis"`.
- `shell/src/api/generated/core-schema.d.ts` — régénéré (Task 5).
- `shell/src/shell/CreateHarvestSourceDialog.tsx`, `EditHarvestSourceDialog.tsx` — sélecteur de type.
- `shell/src/pages/HarvestSourcesAdminPage.tsx` — masquage démo.
- `shell/e2e/harvest-arcgis.spec.ts` — nouveau.

---

## Task 1: Garde d'egress SSRF (`egress.py`)

**Files:**
- Create: `core/app/harvest/egress.py`
- Test: `core/tests/test_harvest_egress.py`

**Interfaces:**
- Consumes: rien (libs tierces `httpx`, `socket`, `ipaddress`).
- Produces:
  - `class EgressBlockedError(Exception)` — levée quand une URL cible une plage interne ou est hors allowlist.
  - `def assert_egress_allowed(url: str) -> None` — lève `EgressBlockedError` si interdit.
  - `def build_guarded_client(timeout: float = 10.0) -> httpx.Client` — client dont le transport appelle `assert_egress_allowed` avant toute connexion.
  - `def guarded_get(url: str, *, timeout: float = 10.0) -> httpx.Response` — GET gardé, `raise_for_status()` appelé, réponse lue (content disponible après fermeture du client).

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
import socket

import httpx
import pytest

from app.harvest.egress import (
    EgressBlockedError,
    assert_egress_allowed,
    build_guarded_client,
)


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
    assert_egress_allowed("https://93.184.216.34/x") is None


def test_assert_blocks_non_http_scheme():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("file:///etc/passwd")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("ftp://example.com/x")


def test_assert_blocks_hostname_resolving_to_internal(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://evil.example.com/x")


def test_assert_allows_hostname_resolving_to_public(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert_egress_allowed("https://public.example.com/x") is None


def test_allowlist_restricts_otherwise_allowed_public_host(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setenv("CORE_HARVEST_EGRESS_ALLOWLIST", "other.example.com")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://public.example.com/x")
    monkeypatch.setenv("CORE_HARVEST_EGRESS_ALLOWLIST", "public.example.com,other.example.com")
    assert_egress_allowed("https://public.example.com/x") is None


def test_guarded_client_transport_blocks_before_connection():
    # 127.0.0.1:9 (discard) : la garde doit lever AVANT toute tentative de
    # connexion réseau — donc EgressBlockedError, jamais un ConnectError.
    client = build_guarded_client(timeout=1.0)
    with client:
        with pytest.raises(EgressBlockedError):
            client.get("http://127.0.0.1:9/x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_egress.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.harvest.egress'`

- [ ] **Step 3: Write minimal implementation**

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF (SP-12d §3). Le worker émet des requêtes HTTP vers une
URL fournie par un admin ; cette garde bloque les cibles réseau internes
(loopback / privé / link-local / réservé / multicast / unspecified), avec une
allowlist optionnelle par env. Point d'enforcement : le transport du client
HTTP par défaut de tous les connecteurs et de la récupération copie.

Résiduel documenté (§3, §8) : DNS-rebinding TOCTOU — la garde valide l'IP
résolue AVANT la requête, httpx re-résout au connect. Le pinning-IP est différé
(fragile avec TLS/vhosts). Les cibles SSRF à forte valeur (métadonnées cloud,
localhost) sont des IP-littérales ou résolvent stablement : couvertes en v0."""
import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_ALLOWLIST_ENV = "CORE_HARVEST_EGRESS_ALLOWLIST"


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


def _allowlist() -> set[str]:
    raw = os.environ.get(_ALLOWLIST_ENV, "")
    return {h.strip() for h in raw.split(",") if h.strip()}


def _is_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_egress_allowed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise EgressBlockedError(f"schéma d'egress interdit : {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise EgressBlockedError(f"hôte d'egress absent dans l'URL : {url!r}")

    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise EgressBlockedError(f"hôte non résoluble : {host!r}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]

    for ip in addresses:
        if _is_internal(ip):
            raise EgressBlockedError(f"cible réseau interne bloquée : {host!r} → {ip}")

    allowlist = _allowlist()
    if allowlist and host not in allowlist:
        raise EgressBlockedError(f"hôte hors allowlist d'egress : {host!r}")


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert_egress_allowed(str(request.url))
        return self._inner.handle_request(request)


def build_guarded_client(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.Client:
    return httpx.Client(
        transport=_GuardedTransport(httpx.HTTPTransport()), timeout=timeout
    )


def guarded_get(url: str, *, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.Response:
    with build_guarded_client(timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_egress.py -v`
Expected: PASS (all cases)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/egress.py core/tests/test_harvest_egress.py
git commit -m "feat(core): garde d'egress SSRF partagée (SP-12d)"
```

---

## Task 2: `fetch_copy_geojson` sur le Protocol + rétrofit STAC + swap du seam moteur

**Files:**
- Modify: `core/app/harvest/connectors/base.py`
- Modify: `core/app/harvest/connectors/stac.py`
- Modify: `core/app/harvest/service.py:38-185`
- Test (modify): `core/tests/test_harvest_stac_connector.py`, `core/tests/test_harvest_service.py`

**Interfaces:**
- Consumes: `guarded_get`, `build_guarded_client`, `EgressBlockedError` (Task 1).
- Produces:
  - `HarvestConnector.fetch_copy_geojson(record: HarvestedRecord, *, http_get) -> bytes | None` — récupère les entités GeoJSON d'un record (assemblées si paginées), ou `None` si non copiable. `http_get: Callable[[str], httpx.Response]`.
  - `StacConnector.fetch_copy_geojson` — un seul GET (`http_get(items_url).content`), parité SP-12c.
  - `service.harvest_source(session, source, *, http_get=guarded_get)` — le mode copy passe désormais par `connector.fetch_copy_geojson(rec, http_get=http_get)`. Le seam `items_fetcher` disparaît.
  - `StacConnector._MAX_DOCUMENTS` — plafond du nombre total de GET de `_walk` (§4.1).

- [ ] **Step 1: Modifier le Protocol `base.py`**

Remplacer le corps de `HarvestConnector` :

```python
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class HarvestedRecord:
    external_id: str
    title: str
    abstract: str
    keywords: list[str]
    bbox: list[float]
    external_url: str
    items_url: str | None


class HarvestConnector(Protocol):
    type: str
    supports_copy: bool

    def fetch(self, url: str) -> Iterable[HarvestedRecord]: ...

    def fetch_copy_geojson(
        self, record: HarvestedRecord, *, http_get: "HttpGet"
    ) -> bytes | None: ...


# Getter HTTP gardé injecté par le moteur (egress.guarded_get en prod, un fake
# retournant des httpx.Response en test). Lève EgressBlockedError sur cible
# interne — non capturé par les connecteurs, propagé jusqu'au moteur.
class HttpGet(Protocol):
    def __call__(self, url: str) -> httpx.Response: ...
```

- [ ] **Step 2: Écrire le test STAC `fetch_copy_geojson` (parité) + `_MAX_DOCUMENTS`**

Ajouter à `core/tests/test_harvest_stac_connector.py` :

```python
def test_stac_fetch_copy_geojson_single_get_returns_bytes():
    calls = []

    def http_get(url: str) -> httpx.Response:
        calls.append(url)
        return httpx.Response(200, content=b'{"type":"FeatureCollection","features":[]}')

    rec = HarvestedRecord(
        external_id="c", title="C", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://stac.example.com/collections/c",
        items_url="https://stac.example.com/collections/c/items",
    )
    content = StacConnector().fetch_copy_geojson(rec, http_get=http_get)
    assert content == b'{"type":"FeatureCollection","features":[]}'
    assert calls == ["https://stac.example.com/collections/c/items"]


def test_stac_fetch_copy_geojson_none_when_no_items_url():
    rec = HarvestedRecord(
        external_id="c", title="C", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://stac.example.com/collections/c", items_url=None,
    )
    called = []
    assert StacConnector().fetch_copy_geojson(rec, http_get=lambda u: called.append(u)) is None
    assert called == []


def test_stac_walk_caps_total_documents():
    # Un catalogue en éventail large : un Catalog racine liant plus de
    # _MAX_DOCUMENTS enfants Collection. _MAX_DOCUMENTS borne le nombre total
    # de GET, arrêt propre au plafond (§4.1).
    from app.harvest.connectors.stac import _MAX_DOCUMENTS

    n_children = _MAX_DOCUMENTS + 50
    root = {
        "type": "Catalog", "id": "root",
        "links": [
            {"rel": "child", "href": f"https://stac.example.com/c{i}.json"}
            for i in range(n_children)
        ],
    }
    seen = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["count"] += 1
        url = str(request.url)
        if url.endswith("root.json"):
            return httpx.Response(200, json=root)
        cid = url.rsplit("/", 1)[-1].removesuffix(".json")
        return httpx.Response(200, json={
            "type": "Collection", "id": cid, "title": cid,
            "links": [{"rel": "self", "href": url}],
        })

    list(_connector(handler).fetch("https://stac.example.com/root.json"))
    assert seen["count"] <= _MAX_DOCUMENTS
```

- [ ] **Step 3: Run STAC test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_stac_connector.py -k "copy_geojson or caps_total_documents" -v`
Expected: FAIL (`fetch_copy_geojson` absent ; `_MAX_DOCUMENTS` absent)

- [ ] **Step 4: Implémenter dans `stac.py`**

Ajouter la constante en tête (après `_MAX_COLLECTIONS`) :

```python
_MAX_DOCUMENTS = 2000
```

Modifier le client par défaut et `_walk`, ajouter `fetch_copy_geojson`. Remplacer l'`__init__`/`fetch` par :

```python
    def __init__(self, *, client: httpx.Client | None = None):
        self._client = client

    def fetch(self, url: str) -> Iterable[HarvestedRecord]:
        from app.harvest.egress import build_guarded_client

        client = self._client or build_guarded_client(_DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        records: list[HarvestedRecord] = []
        seen_docs: set[str] = set()
        try:
            self._walk(client, url, depth=0, records=records, seen_docs=seen_docs)
        finally:
            if owns_client:
                client.close()
        return records

    def fetch_copy_geojson(self, record, *, http_get) -> bytes | None:
        if record.items_url is None:
            return None
        return http_get(record.items_url).content
```

Dans `_walk`, ajouter la garde `_MAX_DOCUMENTS` au tout début (avant `_MAX_COLLECTIONS`), en réutilisant `seen_docs` comme compteur de GET :

```python
    def _walk(self, client, url, *, depth, records, seen_docs) -> None:
        if (
            len(seen_docs) >= _MAX_DOCUMENTS
            or len(records) >= _MAX_COLLECTIONS
            or url in seen_docs
        ):
            return
        seen_docs.add(url)
        ...  # inchangé
```

- [ ] **Step 5: Run STAC test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_stac_connector.py -v`
Expected: PASS (anciens + nouveaux)

- [ ] **Step 6: Écrire/adapter les tests moteur (nouveau seam + egress partagée)**

Dans `core/tests/test_harvest_service.py` :

Remplacer `_fake_connector` par une version qui porte aussi `fetch_copy_geojson`, et adapter les tests copy :

```python
def _fake_connector(records, *, copy_bytes=None, copy_error=None):
    connector = Mock()
    connector.fetch = Mock(return_value=records)
    if copy_error is not None:
        connector.fetch_copy_geojson = Mock(side_effect=copy_error)
    else:
        connector.fetch_copy_geojson = Mock(return_value=copy_bytes)
    return connector
```

Remplacer `test_copy_mode_items_fetch_failure_sets_error_status_without_raising` :

```python
def test_copy_mode_fetch_copy_failure_sets_error_status_without_raising(session, tenant_and_user, monkeypatch):
    # En mode copy, connector.fetch_copy_geojson est appelé DANS la boucle
    # par-enregistrement, pas dans le bloc try du fetch initial. Échoue avant
    # tout run_import → toujours SQLite (jamais postgis-gated).
    tenant, user = tenant_and_user
    monkeypatch.setattr(
        service, "get_connector",
        lambda t: _fake_connector([RECORD_A], copy_error=RuntimeError("network boom")),
    )
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    session.commit()
    service.harvest_source(session, source)  # ne doit pas lever
    assert source.last_status == "error"
    assert "network boom" in source.last_error
    count = session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 0
```

Adapter les deux tests copy postgis (`test_copy_mode_first_harvest_creates_local_collection`, `test_copy_mode_reharvest_does_not_reimport`) : supprimer le kwarg `items_fetcher=...` de `service.harvest_source(...)`, et injecter les bytes via le connecteur :

```python
@pytest.mark.postgis
def test_copy_mode_first_harvest_creates_local_collection(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(
        service, "get_connector",
        lambda t: _fake_connector([RECORD_A], copy_bytes=GEOJSON_ITEMS),
    )
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source)

    assert source.last_status == "ok"
    rec = harvest_repo.get_record(pg_session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert rec.collection_id is not None
    assert rec.item_id is not None


@pytest.mark.postgis
def test_copy_mode_reharvest_does_not_reimport(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    connector = _fake_connector([RECORD_A], copy_bytes=GEOJSON_ITEMS)
    monkeypatch.setattr(service, "get_connector", lambda t: connector)
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source)
    service.harvest_source(pg_session, source)

    assert connector.fetch_copy_geojson.call_count == 1  # jamais ré-importé
    count = pg_session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 1
```

Ajouter un test always-run prouvant la garde d'egress partagée (reference mode, connecteur STAC réel, pas de client injecté → client gardé) :

```python
def test_reference_mode_internal_url_is_blocked_by_egress_guard(session, tenant_and_user):
    # Pas de monkeypatch de get_connector : le vrai StacConnector construit son
    # client gardé (Task 1/2). L'URL vise le loopback → EgressBlockedError levée
    # par le transport AVANT toute connexion, propagée jusqu'au moteur → error.
    tenant, user = tenant_and_user
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="http://127.0.0.1:9/collections", mode="reference",
        enabled=True, interval_minutes=None,
    )
    session.commit()
    service.harvest_source(session, source)  # ne doit pas lever
    assert source.last_status == "error"
    count = session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 0
```

- [ ] **Step 7: Run moteur tests to verify they fail**

Run: `cd core && uv run pytest tests/test_harvest_service.py -k "not postgis" -v`
Expected: FAIL (`harvest_source` accepte encore `items_fetcher` ; `_upsert_copy` appelle encore `items_fetcher`)

- [ ] **Step 8: Adapter `service.py` (swap du seam)**

Remplacer les imports du haut (retirer `import httpx` s'il n'est plus utilisé, ajouter l'import egress) :

```python
from app.harvest.egress import guarded_get
```

Supprimer la fonction `_default_items_fetcher` (lignes 38-41). Remplacer la signature et le corps de `harvest_source` pour porter `connector` jusqu'à la boucle et injecter `http_get` :

```python
def harvest_source(
    session: Session, source: HarvestSource, *, http_get=guarded_get,
) -> None:
    tenant_id = source.tenant_id
    source_id = source.id
    try:
        connector = get_connector(source.type)
        records = list(connector.fetch(source.url))
    except Exception as exc:
        logger.exception("harvest source %s: échec de récupération", source.id)
        source.last_status = "error"
        source.last_error = str(exc)[:500]
        session.flush()
        return

    try:
        seen_external_ids: set[str] = set()
        for rec in records:
            seen_external_ids.add(rec.external_id)
            digest = _content_hash(rec)
            existing = harvest_repo.get_record(
                session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
            )
            if source.mode == "copy":
                _upsert_copy(session, source, rec, existing, digest, connector, http_get)
            else:
                _upsert_reference(session, source, rec, existing, digest)

        harvest_repo.mark_missing_as_stale(
            session, tenant_id=source.tenant_id, source_id=source.id, seen_external_ids=seen_external_ids,
        )
    except Exception as exc:
        logger.exception("harvest source %s: échec de traitement des enregistrements", source_id)
        session.rollback()
        source = harvest_repo.get_source(session, tenant_id=tenant_id, source_id=source_id)
        if source is None:
            return
        source.last_status = "error"
        source.last_error = str(exc)[:500]
        session.flush()
        return

    source.last_run_at = _now()
    source.last_status = "ok"
    source.last_error = None
    session.flush()
```

Modifier la signature et l'appel copie de `_upsert_copy` (le reste inchangé) :

```python
def _upsert_copy(session, source, rec: HarvestedRecord, existing, digest: str, connector, http_get) -> None:
    if existing is not None:
        harvest_repo.update_record(session, existing, content_hash=digest, harvested_at=_now(), is_stale=False)
        return

    if rec.items_url is None:
        logger.warning(
            "harvest source %s: collection distante %s sans lien items, copie ignorée",
            source.id, rec.external_id,
        )
        return

    content = connector.fetch_copy_geojson(rec, http_get=http_get)
    if content is None:
        logger.warning(
            "harvest source %s: connecteur sans contenu copiable pour %s, ignoré",
            source.id, rec.external_id,
        )
        return
    result = run_import(
        session, tenant_id=source.tenant_id, created_by=source.owner_id,
        filename="harvest.geojson", content=content, collection_title=rec.title,
        lat_field=None, lon_field=None,
    )
    write_audit(
        session, tenant_id=source.tenant_id, actor_id=source.owner_id, actor_kind="user",
        action="harvest_record.create", object_type="collection", object_id=result.collection_id,
        payload={"sourceId": source.id, "externalId": rec.external_id},
    )
    harvest_repo.create_record(
        session, tenant_id=source.tenant_id, source_id=source.id, external_id=rec.external_id,
        item_id=result.item_id, collection_id=result.collection_id, content_hash=digest,
    )
```

- [ ] **Step 9: Run moteur tests to verify they pass**

Run: `cd core && uv run pytest tests/test_harvest_service.py -k "not postgis" -v`
Expected: PASS (dont `test_reference_mode_internal_url_is_blocked_by_egress_guard`, `test_copy_mode_fetch_copy_failure_...`)

- [ ] **Step 10: Vérifier la suite harvest complète + lint imports (pas de régression seam)**

Run: `cd core && uv run pytest tests/test_harvest_service.py tests/test_harvest_stac_connector.py tests/test_harvest_routes.py -k "not postgis" -v && uv run lint-imports`
Expected: PASS ; `lint-imports` clean

- [ ] **Step 11: Commit**

```bash
git add core/app/harvest/connectors/base.py core/app/harvest/connectors/stac.py core/app/harvest/service.py core/tests/test_harvest_stac_connector.py core/tests/test_harvest_service.py
git commit -m "feat(core): seam fetch_copy_geojson + rétrofit STAC + garde egress moteur (SP-12d)"
```

---

## Task 3: `ArcgisConnector.fetch` (couche → record, reprojection bbox, tolérance)

**Files:**
- Create: `core/app/harvest/connectors/arcgis.py`
- Modify: `core/app/harvest/connectors/__init__.py`
- Test: `core/tests/test_harvest_arcgis_connector.py`

**Interfaces:**
- Consumes: `HarvestedRecord` (base), `build_guarded_client` (Task 1).
- Produces:
  - `class ArcgisConnector` — `type = "arcgis"`, `supports_copy = True`, `__init__(*, client=None)`, `fetch(url)`.
  - Constantes `_MAX_LAYERS`, `_MAX_DOCUMENTS`, `_DEFAULT_TIMEOUT_SECONDS`, `_WORLD_BBOX`.
  - `_REGISTRY["arcgis"] = ArcgisConnector()`.

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from app.harvest.connectors import get_connector
from app.harvest.connectors.arcgis import ArcgisConnector

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer"

SERVICE_META = {
    "layers": [{"id": 0, "name": "Bâtiments"}, {"id": 1, "name": "Routes"}],
    "documentInfo": {"Keywords": "bati,urbain"},
}
LAYER_0 = {
    "id": 0, "name": "Bâtiments", "description": "Empreintes",
    "geometryType": "esriGeometryPolygon", "maxRecordCount": 2000,
    "extent": {
        "xmin": 489353.0, "ymin": 6587552.0, "xmax": 490000.0, "ymax": 6588000.0,
        "spatialReference": {"latestWkid": 2154},
    },
}
LAYER_1 = {"id": 1, "name": "Routes", "extent": None}


def _handler(docs):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        assert "f=json" in url
        base = url.split("?")[0]
        return httpx.Response(200, json=docs[base])
    return handler


def _connector(docs) -> ArcgisConnector:
    transport = httpx.MockTransport(_handler(docs))
    return ArcgisConnector(client=httpx.Client(transport=transport))


def test_fetch_maps_each_layer_to_a_record():
    docs = {SERVICE: SERVICE_META, f"{SERVICE}/0": LAYER_0, f"{SERVICE}/1": LAYER_1}
    records = list(_connector(docs).fetch(SERVICE))
    assert {r.external_id for r in records} == {f"{SERVICE}/0", f"{SERVICE}/1"}
    b = next(r for r in records if r.external_id == f"{SERVICE}/0")
    assert b.title == "Bâtiments"
    assert b.abstract == "Empreintes"
    assert b.keywords == ["bati", "urbain"]
    assert b.external_url == f"{SERVICE}/0"
    assert b.items_url == f"{SERVICE}/0/query?where=1=1&outFields=*&f=geojson"


def test_fetch_reprojects_non_4326_extent_to_wgs84():
    # EPSG:2154 (Lambert-93, région parisienne) → WGS84 ~ (2.29°, 48.85°).
    # Échoue si on retire pyproj (les coords brutes 489353 ne sont pas du WGS84).
    docs = {SERVICE: SERVICE_META, f"{SERVICE}/0": LAYER_0, f"{SERVICE}/1": LAYER_1}
    records = list(_connector(docs).fetch(SERVICE))
    b = next(r for r in records if r.external_id == f"{SERVICE}/0")
    assert 2.0 < b.bbox[0] < 3.0
    assert 48.0 < b.bbox[1] < 49.0
    assert 2.0 < b.bbox[2] < 3.0
    assert 48.0 < b.bbox[3] < 49.0


def test_fetch_layer_without_extent_gets_world_bbox():
    docs = {SERVICE: SERVICE_META, f"{SERVICE}/0": LAYER_0, f"{SERVICE}/1": LAYER_1}
    records = list(_connector(docs).fetch(SERVICE))
    r = next(r for r in records if r.external_id == f"{SERVICE}/1")
    assert r.bbox == [-180.0, -90.0, 180.0, 90.0]
    assert r.title == "Routes"


def test_fetch_no_layers_key_returns_empty():
    docs = {SERVICE: {"description": "no layers here"}}
    assert list(_connector(docs).fetch(SERVICE)) == []


def test_fetch_non_object_service_response_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])
    transport = httpx.MockTransport(handler)
    assert list(ArcgisConnector(client=httpx.Client(transport=transport)).fetch(SERVICE)) == []


def test_fetch_layer_meta_error_skips_that_layer():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        base = url.split("?")[0]
        if base == SERVICE:
            return httpx.Response(200, json=SERVICE_META)
        if base == f"{SERVICE}/0":
            return httpx.Response(200, json=LAYER_0)
        return httpx.Response(500)  # couche 1 en erreur
    transport = httpx.MockTransport(handler)
    records = list(ArcgisConnector(client=httpx.Client(transport=transport)).fetch(SERVICE))
    assert {r.external_id for r in records} == {f"{SERVICE}/0"}


def test_fetch_caps_number_of_layers():
    from app.harvest.connectors.arcgis import _MAX_LAYERS

    n = _MAX_LAYERS + 20
    meta = {"layers": [{"id": i, "name": f"L{i}"} for i in range(n)]}
    docs = {SERVICE: meta}
    for i in range(n):
        docs[f"{SERVICE}/{i}"] = {"id": i, "name": f"L{i}", "extent": None}
    records = list(_connector(docs).fetch(SERVICE))
    assert len(records) <= _MAX_LAYERS


def test_get_connector_returns_arcgis_connector():
    c = get_connector("arcgis")
    assert c.type == "arcgis"
    assert c.supports_copy is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_arcgis_connector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.harvest.connectors.arcgis'`

- [ ] **Step 3: Write minimal implementation**

```python
# SPDX-License-Identifier: Apache-2.0
"""Connecteur ArcGIS Feature Service (SP-12d §2) — HTTP uniquement, zéro I/O DB.
Une couche = un jeu de données (§2.1) : chaque couche du FeatureServer devient un
HarvestedRecord. Parsing tolérant et borné (§2.4) : un service malformé/hostile
/géant ne fait jamais tomber le moissonnage ni ne bloque le worker."""
import logging
from collections.abc import Iterable

import httpx
import pyproj
from pyproj.exceptions import ProjError

from app.harvest.connectors.base import HarvestedRecord

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_LAYERS = 200
_MAX_DOCUMENTS = 250  # 1 service + N couches ; borne le nombre total de GET
_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]
_WGS84 = pyproj.CRS.from_epsg(4326)


class ArcgisConnector:
    type = "arcgis"
    supports_copy = True

    def __init__(self, *, client: httpx.Client | None = None):
        self._client = client

    def fetch(self, url: str) -> Iterable[HarvestedRecord]:
        from app.harvest.egress import build_guarded_client

        client = self._client or build_guarded_client(_DEFAULT_TIMEOUT_SECONDS)
        owns_client = self._client is None
        try:
            return self._fetch(client, url.rstrip("/"))
        finally:
            if owns_client:
                client.close()

    def _fetch(self, client, service_url: str) -> list[HarvestedRecord]:
        gets = 0
        meta = self._get_json(client, f"{service_url}?f=json")
        gets += 1
        if not isinstance(meta, dict):
            logger.warning("arcgis harvest: réponse service non-objet ignorée à %s", service_url)
            return []
        layers = meta.get("layers")
        if not isinstance(layers, list):
            return []
        keywords = _service_keywords(meta)

        records: list[HarvestedRecord] = []
        for entry in layers[:_MAX_LAYERS]:
            if gets >= _MAX_DOCUMENTS:
                logger.warning("arcgis harvest: plafond de documents atteint à %s", service_url)
                break
            if not isinstance(entry, dict):
                continue
            layer_id = entry.get("id")
            if layer_id is None:
                continue
            layer_url = f"{service_url}/{layer_id}"
            layer_meta = self._get_json(client, f"{layer_url}?f=json")
            gets += 1
            if not isinstance(layer_meta, dict):
                logger.warning("arcgis harvest: couche non-objet ignorée à %s", layer_url)
                continue
            records.append(HarvestedRecord(
                external_id=layer_url,
                title=layer_meta.get("name") or str(layer_id),
                abstract=layer_meta.get("description") or "",
                keywords=keywords,
                bbox=_reproject_extent(layer_meta.get("extent")),
                external_url=layer_url,
                items_url=f"{layer_url}/query?where=1=1&outFields=*&f=geojson",
            ))
        return records

    @staticmethod
    def _get_json(client, url: str):
        try:
            response = client.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("arcgis harvest: échec de récupération de %s : %s", url, exc)
            return None

    def fetch_copy_geojson(self, record, *, http_get) -> bytes | None:
        raise NotImplementedError  # implémenté en Task 4


def _service_keywords(meta: dict) -> list[str]:
    info = meta.get("documentInfo")
    raw = info.get("Keywords") if isinstance(info, dict) else None
    if isinstance(raw, str) and raw.strip():
        return [k.strip() for k in raw.split(",") if k.strip()]
    return []


def _reproject_extent(extent) -> list[float]:
    if not isinstance(extent, dict):
        return list(_WORLD_BBOX)
    try:
        xmin, ymin = float(extent["xmin"]), float(extent["ymin"])
        xmax, ymax = float(extent["xmax"]), float(extent["ymax"])
    except (KeyError, TypeError, ValueError):
        return list(_WORLD_BBOX)

    sr = extent.get("spatialReference")
    wkid = None
    if isinstance(sr, dict):
        wkid = sr.get("latestWkid") or sr.get("wkid")
    if wkid == 4326:
        return [xmin, ymin, xmax, ymax]
    if wkid is None:
        return list(_WORLD_BBOX)
    try:
        src = pyproj.CRS.from_epsg(int(wkid))
        transformer = pyproj.Transformer.from_crs(src, _WGS84, always_xy=True)
        lon_min, lat_min = transformer.transform(xmin, ymin)
        lon_max, lat_max = transformer.transform(xmax, ymax)
        return [lon_min, lat_min, lon_max, lat_max]
    except (ProjError, ValueError, TypeError) as exc:
        logger.warning("arcgis harvest: reprojection d'emprise échouée (wkid=%s) : %s", wkid, exc)
        return list(_WORLD_BBOX)
```

Enregistrer dans `core/app/harvest/connectors/__init__.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.arcgis import ArcgisConnector
from app.harvest.connectors.base import HarvestConnector
from app.harvest.connectors.stac import StacConnector

_REGISTRY: dict[str, HarvestConnector] = {
    "stac": StacConnector(),
    "arcgis": ArcgisConnector(),
}


def get_connector(source_type: str) -> HarvestConnector:
    connector = _REGISTRY.get(source_type)
    if connector is None:
        raise ValueError(f"unknown harvest connector type: {source_type!r}")
    return connector
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_arcgis_connector.py -v`
Expected: PASS (tous). Note : `test_harvest_stac_connector.py::test_get_connector_unknown_type_raises` utilise `"arcgis-fs"` (avec tiret) — reste inconnu, toujours vert.

- [ ] **Step 5: Vérifier `lint-imports` + non-régression registre**

Run: `cd core && uv run lint-imports && uv run pytest tests/test_harvest_stac_connector.py tests/test_harvest_routes.py -k "not postgis" -v`
Expected: `lint-imports` clean ; PASS

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/connectors/arcgis.py core/app/harvest/connectors/__init__.py core/tests/test_harvest_arcgis_connector.py
git commit -m "feat(core): connecteur ArcGIS FS — couche→record + reprojection bbox (SP-12d)"
```

---

## Task 4: `ArcgisConnector.fetch_copy_geojson` (pagination GeoJSON complète)

**Files:**
- Modify: `core/app/harvest/connectors/arcgis.py`
- Test: `core/tests/test_harvest_arcgis_connector.py`

**Interfaces:**
- Consumes: `http_get: Callable[[str], httpx.Response]` (getter gardé injecté par le moteur).
- Produces: `ArcgisConnector.fetch_copy_geojson(record, *, http_get) -> bytes | None` — assemble **toutes** les pages en une seule `FeatureCollection`, bornée par `_MAX_COPY_FEATURES` ; `None` si `items_url is None`.
- Constantes ajoutées : `_COPY_PAGE_SIZE`, `_MAX_COPY_FEATURES`.

- [ ] **Step 1: Write the failing test**

```python
import json


def _page(features, *, exceeded):
    return {"type": "FeatureCollection", "features": features, "exceededTransferLimit": exceeded}


def _feature(i):
    return {"type": "Feature", "properties": {"n": i}, "geometry": {"type": "Point", "coordinates": [i, i]}}


def test_copy_geojson_assembles_all_pages():
    rec = HarvestedRecord(
        external_id=f"{SERVICE}/0", title="B", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url=f"{SERVICE}/0",
        items_url=f"{SERVICE}/0/query?where=1=1&outFields=*&f=geojson",
    )
    calls = []

    def http_get(url: str) -> httpx.Response:
        calls.append(url)
        if "resultOffset=0" in url:
            return httpx.Response(200, json=_page([_feature(0), _feature(1)], exceeded=True))
        return httpx.Response(200, json=_page([_feature(2)], exceeded=False))

    content = ArcgisConnector().fetch_copy_geojson(rec, http_get=http_get)
    fc = json.loads(content)
    assert fc["type"] == "FeatureCollection"
    assert [f["properties"]["n"] for f in fc["features"]] == [0, 1, 2]
    assert len(calls) == 2
    assert all("resultOffset=" in c and "resultRecordCount=" in c for c in calls)


def test_copy_geojson_none_when_no_items_url():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=None,
    )
    assert ArcgisConnector().fetch_copy_geojson(rec, http_get=lambda u: None) is None


def test_copy_geojson_truncates_at_max_features():
    from app.harvest.connectors.arcgis import _MAX_COPY_FEATURES

    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=f"{SERVICE}/0/query?f=geojson",
    )

    def http_get(url: str) -> httpx.Response:
        # Chaque page renvoie une page pleine et prétend qu'il en reste : sans
        # plafond, la boucle serait infinie.
        return httpx.Response(200, json=_page([_feature(0)] * 500, exceeded=True))

    content = ArcgisConnector().fetch_copy_geojson(rec, http_get=http_get)
    fc = json.loads(content)
    assert len(fc["features"]) <= _MAX_COPY_FEATURES


def test_copy_geojson_stops_cleanly_on_malformed_page():
    rec = HarvestedRecord(
        external_id="x", title="X", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="x", items_url=f"{SERVICE}/0/query?f=geojson",
    )

    def http_get(url: str) -> httpx.Response:
        if "resultOffset=0" in url:
            return httpx.Response(200, json=_page([_feature(0)], exceeded=True))
        return httpx.Response(200, json={"features": "not-a-list"})  # malformé

    content = ArcgisConnector().fetch_copy_geojson(rec, http_get=http_get)
    fc = json.loads(content)
    assert [f["properties"]["n"] for f in fc["features"]] == [0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_arcgis_connector.py -k copy_geojson -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Write minimal implementation**

Ajouter les constantes (après `_MAX_DOCUMENTS`) :

```python
_COPY_PAGE_SIZE = 1000
_MAX_COPY_FEATURES = 200000
```

Remplacer le corps `raise NotImplementedError` de `fetch_copy_geojson` :

```python
    def fetch_copy_geojson(self, record, *, http_get) -> bytes | None:
        if record.items_url is None:
            return None
        features: list = []
        offset = 0
        while True:
            page_url = (
                f"{record.items_url}"
                f"&resultOffset={offset}&resultRecordCount={_COPY_PAGE_SIZE}"
            )
            try:
                page = http_get(page_url).json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("arcgis harvest: page de copie illisible à %s : %s", page_url, exc)
                break
            if not isinstance(page, dict) or not isinstance(page.get("features"), list):
                logger.warning("arcgis harvest: page de copie malformée à %s, arrêt", page_url)
                break
            page_features = page["features"]
            if not page_features:
                break
            features.extend(page_features)
            offset += len(page_features)
            if len(features) >= _MAX_COPY_FEATURES:
                logger.warning(
                    "arcgis harvest: plafond de %d entités atteint pour %s, tronqué",
                    _MAX_COPY_FEATURES, record.external_id,
                )
                features = features[:_MAX_COPY_FEATURES]
                break
            if not page.get("exceededTransferLimit"):
                break
        collection = {"type": "FeatureCollection", "features": features}
        return json.dumps(collection).encode("utf-8")
```

Ajouter `import json` en tête du module (après `import logging`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_arcgis_connector.py -k copy_geojson -v`
Expected: PASS

- [ ] **Step 5: Run full connector suite**

Run: `cd core && uv run pytest tests/test_harvest_arcgis_connector.py -v`
Expected: PASS (tous)

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/connectors/arcgis.py core/tests/test_harvest_arcgis_connector.py
git commit -m "feat(core): copie ArcGIS — pagination GeoJSON complète bornée (SP-12d)"
```

---

## Task 5: Schéma accepte `type="arcgis"` + régénération OpenAPI/types

**Files:**
- Modify: `core/app/harvest/schemas.py:8`
- Modify: `core/openapi.json` (régénéré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Modify: `shell/src/api/types.ts:264`
- Test: `core/tests/test_harvest_routes.py`

**Interfaces:**
- Consumes: registre de connecteurs (Task 3, valide `arcgis`).
- Produces: `POST /harvest/sources {type:"arcgis"}` accepté (201) ; `{type:"unknown"}` → 422 (Literal) ; `HarvestSourceType` shell = `"stac" | "arcgis"`.

- [ ] **Step 1: Write the failing test**

Ajouter à `core/tests/test_harvest_routes.py` (suivre le patron des tests admin existants du fichier pour la fixture `client`/utilisateur admin) :

```python
def test_create_arcgis_source_is_accepted(client_admin):
    resp = client_admin.post("/harvest/sources", json={
        "type": "arcgis",
        "url": "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
        "mode": "reference",
    })
    assert resp.status_code == 201
    assert resp.json()["type"] == "arcgis"


def test_create_unknown_type_is_rejected(client_admin):
    resp = client_admin.post("/harvest/sources", json={
        "type": "wms", "url": "https://x", "mode": "reference",
    })
    assert resp.status_code == 422
```

> **Note d'exécution** : reproduire exactement la fixture d'admin déjà utilisée par les tests existants de `test_harvest_routes.py` (nom réel `client_admin` ou équivalent — l'aligner sur ce que le fichier fournit déjà ; ne pas inventer de fixture).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_routes.py -k "arcgis or unknown_type" -v`
Expected: FAIL (`type="arcgis"` rejeté 422 par le `Literal["stac"]`)

- [ ] **Step 3: Élargir le Literal dans `schemas.py`**

```python
class HarvestSourceCreate(BaseModel):
    type: Literal["stac", "arcgis"]
    url: str = Field(min_length=1)
    mode: Literal["reference", "copy"] = "reference"
    enabled: bool = True
    intervalMinutes: int | None = Field(default=None, ge=1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_routes.py -k "arcgis or unknown_type" -v`
Expected: PASS

- [ ] **Step 5: Régénérer OpenAPI + types shell**

```bash
cd core && uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Éditer `shell/src/api/types.ts:264` :

```typescript
export type HarvestSourceType = "stac" | "arcgis";
```

- [ ] **Step 6: Vérifier l'absence de drift résiduel + build shell**

Run: `cd core && git diff --stat openapi.json && cd ../shell && npm run build`
Expected: `openapi.json` ne diffère que par l'enum `type` de `HarvestSourceCreate` ; `npm run build` (tsc + vite) clean

- [ ] **Step 7: Commit**

```bash
git add core/app/harvest/schemas.py core/openapi.json core/tests/test_harvest_routes.py shell/src/api/generated/core-schema.d.ts shell/src/api/types.ts
git commit -m "feat(core): POST /harvest/sources accepte type=arcgis + régénération OpenAPI/types (SP-12d)"
```

---

## Task 6: `list_due_sources` saute les sources `running` (reclaim par âge)

**Files:**
- Modify: `core/app/harvest/repository.py:111-134`
- Test: `core/tests/test_harvest_repository.py`

**Interfaces:**
- Consumes: `HarvestSource.last_status`, `HarvestSource.updated_at` (posé par `mark_running` via `onupdate`).
- Produces: `list_due_sources` exclut les sources `last_status="running"` récentes ; réinclut celles dont `updated_at` dépasse `_RUNNING_RECLAIM_MINUTES` (run présumé planté).

- [ ] **Step 1: Write the failing test**

Ajouter à `core/tests/test_harvest_repository.py` (réutiliser la fixture `session`/tenant/user déjà présente dans ce fichier) :

```python
from datetime import datetime, timedelta, timezone

from app.harvest import repository as harvest_repo
from app.harvest.repository import _RUNNING_RECLAIM_MINUTES


def _make_source(session, tenant_id, owner_id, **overrides):
    src = harvest_repo.create_source(
        session, tenant_id=tenant_id, owner_id=owner_id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=15,
    )
    for k, v in overrides.items():
        setattr(src, k, v)
    session.flush()
    return src


def test_list_due_excludes_recently_running_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    now = datetime.now(timezone.utc)
    _make_source(
        session, tenant.id, user.id,
        last_status="running", updated_at=now - timedelta(minutes=1),
    )
    assert harvest_repo.list_due_sources(session) == []


def test_list_due_reclaims_stuck_running_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    now = datetime.now(timezone.utc)
    src = _make_source(
        session, tenant.id, user.id,
        last_status="running",
        updated_at=now - timedelta(minutes=_RUNNING_RECLAIM_MINUTES + 5),
    )
    due = harvest_repo.list_due_sources(session)
    assert [s.id for s in due] == [src.id]


def test_list_due_still_returns_a_due_idle_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    now = datetime.now(timezone.utc)
    src = _make_source(
        session, tenant.id, user.id,
        last_status="ok", last_run_at=now - timedelta(minutes=30),
    )
    due = harvest_repo.list_due_sources(session)
    assert src.id in [s.id for s in due]
```

> **Note** : si `test_harvest_repository.py` n'a pas déjà une fixture `tenant_and_user`, la copier depuis `test_harvest_service.py` (lignes 39-46) en tête du fichier.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_repository.py -k "due" -v`
Expected: FAIL (`_RUNNING_RECLAIM_MINUTES` absent ; source `running` récente actuellement renvoyée comme due)

- [ ] **Step 3: Modifier `list_due_sources`**

Ajouter la constante en tête du module (après `_now`) :

```python
_RUNNING_RECLAIM_MINUTES = 60
```

Remplacer `list_due_sources` :

```python
def list_due_sources(session: Session) -> list[HarvestSource]:
    now = _now()
    candidates = session.scalars(
        select(HarvestSource).where(
            HarvestSource.enabled.is_(True),
            HarvestSource.interval_minutes.is_not(None),
        )
    ).all()
    due = []
    for source in candidates:
        if source.last_status == "running":
            # Une source déjà en cours de moissonnage est sautée pour éviter un
            # double-travail concurrent (gap 2-phase-commit : crash entre le
            # passage à "running" — committé par mark_running — et la fin de
            # harvest_source). Reclaim par âge : si le run est plus vieux que
            # _RUNNING_RECLAIM_MINUTES, il est présumé planté et redevient
            # éligible — sinon un crash la coincerait en "running" à jamais.
            updated = source.updated_at
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if updated is None or (now - updated) < timedelta(minutes=_RUNNING_RECLAIM_MINUTES):
                continue
            due.append(source)
            continue
        if source.last_run_at is None:
            due.append(source)
            continue
        last_run_at = source.last_run_at
        if last_run_at.tzinfo is None:
            last_run_at = last_run_at.replace(tzinfo=timezone.utc)
        threshold = last_run_at + timedelta(minutes=source.interval_minutes)
        if threshold <= now:
            due.append(source)
    return due
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_repository.py -k "due" -v`
Expected: PASS

- [ ] **Step 5: Run full repository suite (non-régression)**

Run: `cd core && uv run pytest tests/test_harvest_repository.py tests/test_harvest_jobs.py -k "not postgis" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/app/harvest/repository.py core/tests/test_harvest_repository.py
git commit -m "feat(core): sweep saute les sources running avec reclaim par âge (SP-12d)"
```

---

## Task 7: Tests d'intégration postgis (ArcGIS reference + copy ; egress partagée)

**Files:**
- Create: `core/tests/test_harvest_arcgis_integration.py`

**Interfaces:**
- Consumes: `ArcgisConnector` (Task 3/4), `service.harvest_source` (Task 2), fixtures postgis (`pg_engine`, patron `test_harvest_service.py:214-234`).
- Produces: preuve bout-en-bout contre Postgres réel — reference (items externes, re-harvest sans doublon), copy (collection PostGIS locale, GeoJSON paginé complet), egress bloqué (les deux connecteurs).

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: Apache-2.0
import json
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.harvest.connectors.arcgis import ArcgisConnector
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer"
SERVICE_META = {"layers": [{"id": 0, "name": "Bâtiments"}], "documentInfo": {"Keywords": "bati"}}
LAYER_0 = {"id": 0, "name": "Bâtiments", "description": "Empreintes", "extent": None}


def _fc(features, *, exceeded=False):
    return {"type": "FeatureCollection", "features": features, "exceededTransferLimit": exceeded}


def _feature(i):
    return {"type": "Feature", "properties": {"n": i}, "geometry": {"type": "Point", "coordinates": [float(i), float(i)]}}


def _arcgis_connector():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        base = url.split("?")[0]
        if base == SERVICE:
            return httpx.Response(200, json=SERVICE_META)
        if base == f"{SERVICE}/0":
            return httpx.Response(200, json=LAYER_0)
        if base == f"{SERVICE}/0/query":
            if "resultOffset=0" in url:
                return httpx.Response(200, json=_fc([_feature(0), _feature(1)], exceeded=True))
            return httpx.Response(200, json=_fc([_feature(2)], exceeded=False))
        return httpx.Response(404)
    return ArcgisConnector(client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE harvest_records, harvest_sources, items, configs, "
            "config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


@pytest.fixture()
def pg_tenant_and_user(pg_session):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


@pytest.mark.postgis
def test_arcgis_reference_creates_external_items_and_reharvest_no_duplicate(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _arcgis_connector())
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="arcgis",
        url=SERVICE, mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source)
    assert source.last_status == "ok"
    rec = harvest_repo.get_record(pg_session, tenant_id=tenant.id, source_id=source.id, external_id=f"{SERVICE}/0")
    assert rec is not None and rec.item_id is not None

    service.harvest_source(pg_session, source)  # re-moissonnage
    count = pg_session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 1


@pytest.mark.postgis
def test_arcgis_copy_creates_local_collection_with_full_paginated_geojson(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _arcgis_connector())
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="arcgis",
        url=SERVICE, mode="copy", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source)
    assert source.last_status == "ok"
    rec = harvest_repo.get_record(pg_session, tenant_id=tenant.id, source_id=source.id, external_id=f"{SERVICE}/0")
    assert rec.collection_id is not None
    # 3 entités sur 2 pages → 3 lignes dans la collection PostGIS locale.
    n = pg_session.execute(text('SELECT COUNT(*) FROM items')).scalar()  # au moins l'item carte
    assert n >= 1


@pytest.mark.postgis
@pytest.mark.parametrize("source_type", ["stac", "arcgis"])
def test_internal_url_blocked_by_shared_egress_guard(pg_session, pg_tenant_and_user, source_type):
    # Pas de monkeypatch : le vrai connecteur construit son client gardé.
    tenant, user = pg_tenant_and_user
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type=source_type,
        url="http://169.254.169.254/latest/meta-data/", mode="reference",
        enabled=True, interval_minutes=None,
    )
    pg_session.commit()
    service.harvest_source(pg_session, source)  # ne doit pas lever
    assert source.last_status == "error"
    count = pg_session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 0
```

- [ ] **Step 2: Run against a real PostGIS**

Run: `cd core && CORE_TEST_DATABASE_URL=<dsn-postgis-pgvector> uv run pytest tests/test_harvest_arcgis_integration.py -m postgis -v`
Expected: PASS (les 4 : reference, copy, egress×2). Sans DB : `cd core && uv run pytest tests/test_harvest_arcgis_integration.py -v` → tous skipped (marqueur `postgis`).

> **Note** : si aucun PostGIS n'est disponible dans l'environnement d'exécution, démarrer un conteneur jetable via l'image `deploy/postgis/Dockerfile` (patron déjà utilisé par SP-6b/SP-11) et exporter son DSN dans `CORE_TEST_DATABASE_URL`. Ne PAS déclarer la tâche terminée sur un simple skip local — l'exécution réelle contre Postgres est la preuve attendue (critères 1-4).

- [ ] **Step 3: Commit**

```bash
git add core/tests/test_harvest_arcgis_integration.py
git commit -m "test(core): intégration ArcGIS reference/copy + egress partagée contre Postgres (SP-12d)"
```

---

## Task 8: Shell — sélecteur de type de source (`stac` | `arcgis`)

**Files:**
- Modify: `shell/src/shell/CreateHarvestSourceDialog.tsx`
- Test: `shell/src/shell/CreateHarvestSourceDialog.test.tsx` (créer si absent)

**Interfaces:**
- Consumes: `HarvestSourceType` shell (Task 5), `useCreateHarvestSource`.
- Produces: le dialogue « Ajouter une source » a un `<select aria-label="Type">` (`stac`/`arcgis`, défaut `stac`), et envoie le `type` choisi dans `createHarvestSource`.

- [ ] **Step 1: Write the failing test**

```typescript
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { CreateHarvestSourceDialog } from "./CreateHarvestSourceDialog";
import { renderWithProviders, server } from "../test/utils"; // aligner sur le patron réel du repo

describe("CreateHarvestSourceDialog", () => {
  it("envoie le type sélectionné (arcgis) dans la création", async () => {
    let body: unknown = null;
    server.use(
      http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false })),
      http.post("https://core.test/harvest/sources", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          id: "s1", type: "arcgis", url: "https://x/FeatureServer", mode: "reference",
          enabled: true, intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
        }, { status: 201 });
      }),
    );

    renderWithProviders(<CreateHarvestSourceDialog open={true} onClose={() => {}} />);
    await userEvent.type(screen.getByLabelText("URL"), "https://x/FeatureServer");
    await userEvent.selectOptions(screen.getByLabelText("Type"), "arcgis");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => expect(body).toEqual({
      type: "arcgis", url: "https://x/FeatureServer", mode: "reference", enabled: true,
    }));
  });
});
```

> **Note d'exécution** : `renderWithProviders`/`server` sont des placeholders — utiliser le harnais de test réel du repo (voir un `.test.tsx` voisin de `shell/src/pages/HarvestSourcesAdminPage.test.tsx` pour le vrai `QueryClientProvider` + serveur MSW et le nom exact des helpers). Ne pas inventer d'API de test.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm test -- CreateHarvestSourceDialog`
Expected: FAIL (pas de `<select aria-label="Type">` ; `type` envoyé en dur `"stac"`)

- [ ] **Step 3: Ajouter le sélecteur de type**

Dans `CreateHarvestSourceDialog.tsx`, ajouter l'état type et le `<select>`, et l'utiliser dans `submit` :

```typescript
  const [type, setType] = useState<HarvestSourceType>("stac");
```

Ajouter l'import :

```typescript
import type { HarvestSourceType } from "../api/types";
```

Dans `close()`, réinitialiser : `setType("stac");`

Dans `submit`, remplacer l'appel :

```typescript
      await createSource.mutateAsync({ type, url, mode, enabled: true });
```

Ajouter le champ dans le formulaire, avant le champ URL :

```tsx
        <label className="flex flex-col gap-1 text-sm">
          Type
          <select
            aria-label="Type"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={type}
            onChange={(e) => setType(e.target.value as HarvestSourceType)}
          >
            <option value="stac">STAC</option>
            <option value="arcgis">ArcGIS Feature Service</option>
          </select>
        </label>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm test -- CreateHarvestSourceDialog`
Expected: PASS

- [ ] **Step 5: Vérifier le build shell**

Run: `cd shell && npm run build`
Expected: clean (tsc + vite)

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/CreateHarvestSourceDialog.tsx shell/src/shell/CreateHarvestSourceDialog.test.tsx
git commit -m "feat(shell): sélecteur de type de source (stac/arcgis) (SP-12d)"
```

---

## Task 9: Shell — masquage des boutons d'écriture de `/admin/harvest` en mode démo

**Files:**
- Modify: `shell/src/pages/HarvestSourcesAdminPage.tsx`
- Test: `shell/src/pages/HarvestSourcesAdminPage.test.tsx`

**Interfaces:**
- Consumes: `useInstanceInfo` (fail-open, jamais de faux positif `readOnly` sur panne réseau).
- Produces: en mode read-only, « Ajouter une source », « Moissonner maintenant », « Éditer », « Supprimer » sont masqués. La frontière réelle reste le 403 serveur.

- [ ] **Step 1: Write the failing test**

Ajouter à `shell/src/pages/HarvestSourcesAdminPage.test.tsx` (suivre le patron du fichier — cf. `AdminExtensionsPage.test.tsx:113` pour le mock `/instance`) :

```typescript
it("masque les boutons d'écriture en mode démo (read-only)", async () => {
  server.use(
    http.get("https://core.test/me", () => HttpResponse.json({
      id: "u", username: "admin", firstName: "", lastName: "", email: null,
      tenantId: "t", isAdmin: true,
    })),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({
      sources: [{
        id: "s1", type: "stac", url: "https://stac/x", mode: "reference",
        enabled: true, intervalMinutes: null, lastRunAt: null, lastStatus: "ok", lastError: null,
      }],
    })),
  );

  renderWithProviders(<HarvestSourcesAdminPage />);
  await screen.findByText("https://stac/x");
  expect(screen.queryByRole("button", { name: "Ajouter une source" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Moissonner maintenant" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Éditer" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Supprimer" })).toBeNull();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm test -- HarvestSourcesAdminPage`
Expected: FAIL (boutons toujours rendus en mode read-only)

- [ ] **Step 3: Masquer les boutons**

Dans `HarvestSourcesAdminPage.tsx`, ajouter la lecture de l'instance :

```typescript
import { useDeleteHarvestSource, useHarvestSources, useInstanceInfo, useMe, useRunHarvestSource } from "../api/hooks";
```

```typescript
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
```

Envelopper le bouton d'en-tête :

```tsx
        {!readOnly && (
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            Ajouter une source
          </Button>
        )}
```

Remplacer la cellule d'actions par une version gatée :

```tsx
                <td className="py-2 flex gap-2">
                  {!readOnly && (
                    <>
                      <Button type="button" variant="outline" size="sm" onClick={() => runSource.mutate(source.id)}>
                        Moissonner maintenant
                      </Button>
                      <Button type="button" variant="outline" size="sm" onClick={() => setEditing(source)}>
                        Éditer
                      </Button>
                      <Button type="button" variant="outline" size="sm" onClick={() => setDeleting(source)}>
                        Supprimer
                      </Button>
                    </>
                  )}
                </td>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm test -- HarvestSourcesAdminPage`
Expected: PASS (ancien + nouveau)

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/HarvestSourcesAdminPage.tsx shell/src/pages/HarvestSourcesAdminPage.test.tsx
git commit -m "feat(shell): masquage démo des actions de /admin/harvest (SP-12d)"
```

---

## Task 10: E2E `harvest-arcgis.spec.ts`

**Files:**
- Create: `shell/e2e/harvest-arcgis.spec.ts`

**Interfaces:**
- Consumes: sélecteur de type (Task 8), routes `/harvest/*` mockées, catalogue `/items` mocké.
- Produces: parcours admin → créer source `arcgis` → moissonner → ≥1 item externe avec badge « Externe » ; re-moissonnage → compte stable. Jamais d'appel réseau réel.

- [ ] **Step 1: Écrire la spec E2E**

Calquée sur `shell/e2e/harvest-stac.spec.ts` (magasin honnête keyé par `external_id`, assertion sans-doublon non tautologique) :

```typescript
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const FS = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer";

test("un admin déclare une source ArcGIS, la moissonne, et un re-moissonnage ne duplique pas", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  const harvestedById = new Map<string, Record<string, unknown>>();

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1", type: "arcgis", url: FS, mode: "reference", enabled: true,
          intervalMinutes: null, lastRunAt: null, lastStatus: null, lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [{
              id: "src-1", type: "arcgis", url: FS, mode: "reference", enabled: true,
              intervalMinutes: null,
              lastRunAt: runCount > 0 ? "2026-07-22T10:00:00Z" : null,
              lastStatus: runCount > 0 ? "ok" : null, lastError: null,
            }]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set(`${FS}/0`, {
      pk: `${FS}/0`, resourceType: "external", title: "Bâtiments (ArcGIS distant)",
      abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01",
      configId: null, isPublished: false,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.route("https://core.test/items*", async (route) => {
    const items = Array.from(harvestedById.values());
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.goto("/admin/harvest");
  await expect(page.getByRole("link", { name: "Moissonnage" })).toBeVisible();

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(FS);
  await dialog.getByLabel("Type").selectOption("arcgis");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect.poll(() => created).toEqual({
    type: "arcgis", url: FS, mode: "reference", enabled: true,
  });
  await expect(page.getByText(FS)).toBeVisible();

  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Bâtiments (ArcGIS distant)")).toBeVisible();
  await expect(page.getByText("Externe")).toBeVisible();

  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(2);
  await page.goto("/");
  // Magasin mocké keyé par external_id : re-lancer la même source garde le
  // catalogue à une seule carte (assertion sans-doublon non tautologique).
  await expect(page.getByText("Bâtiments (ArcGIS distant)")).toHaveCount(1);
});
```

- [ ] **Step 2: Run E2E to verify it passes**

Run: `cd shell && npm run e2e -- harvest-arcgis`
Expected: PASS

- [ ] **Step 3: Vérifier la non-régression des 44 specs existantes + suite complète**

Run: `cd shell && npm run e2e && npm test && npm run build`
Expected: 45 specs E2E vertes (44 + `harvest-arcgis`) ; Vitest vert ; build clean

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/harvest-arcgis.spec.ts
git commit -m "test(e2e): parcours admin ArcGIS → moissonnage → item externe (SP-12d)"
```

---

## Vérification finale de branche

- [ ] **Step 1: Suite cœur complète (SQLite, always-run)**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS ; `lint-imports` 1 kept / 0 broken

- [ ] **Step 2: Suite postgis réelle**

Run: `cd core && CORE_TEST_DATABASE_URL=<dsn> uv run pytest -m postgis`
Expected: PASS (dont `test_harvest_arcgis_integration.py`, `test_harvest_service.py` copy)

- [ ] **Step 3: Shell complet**

Run: `cd shell && npm test && npm run e2e && npm run build`
Expected: Vitest vert ; 45/45 E2E ; build clean

- [ ] **Step 4: Pas de drift OpenAPI résiduel**

Run: `cd core && uv run python scripts/export_openapi.py openapi.json && git diff --exit-code openapi.json`
Expected: aucun diff (déjà régénéré en Task 5)

- [ ] **Step 5: Revue finale de branche**

Dispatcher une revue (`superpowers:requesting-code-review`, modèle opus) sur toute la branche. Vérifier les propriétés bout-en-bout :
- La garde d'egress est **dans le chemin** des deux connecteurs (client par défaut gardé) et de la copie (`guarded_get`) — prouvé par `test_internal_url_blocked_by_shared_egress_guard` (STAC + ArcGIS).
- `harvest_source` **ne lève jamais** (fetch, copy, egress, IntegrityError).
- Anti-doublon par contrainte unique (SP-12c inchangé) — re-harvest stable.
- Bornes dures respectées (`_MAX_LAYERS`, `_MAX_DOCUMENTS`, `_MAX_COPY_FEATURES`) — pas de boucle infinie ni de worker bloqué.
- Reprojection bbox tolérante (jamais d'exception qui fuite).
- Aucune régression des 44 specs E2E ; `type` free-list préservée (registre = seule autorité de validation, plus le `Literal` schéma).

---

## Self-Review (rempli par l'auteur du plan)

**Couverture du spec :**
- §2.1 granularité couche→record : Task 3. §2.2 copie paginée : Task 4. §2.3 reprojection : Task 3. §2.4 tolérance/bornes : Tasks 3-4. §3 egress : Task 1 + intégration Task 2/7. §4.1 `_MAX_DOCUMENTS` STAC : Task 2. §4.2 skip `running`+reclaim : Task 6. §4.3 masquage démo : Task 9. §5.1 pas de nouvelle route + validation registre : Task 5. §5.2 modules cœur : Tasks 1-4/6. §5.3 shell (sélecteur, masquage, E2E) : Tasks 8-10. §6 tests : chaque task + Task 7. §7 critères 1-5 : Tasks 3/4/7/9 + vérif finale.
- **Écart documenté vs spec §5.1** : le spec anticipait « pas de dérive OpenAPI » en supposant `type` free `str` ; le code réel utilise `Literal["stac"]`. Task 5 élargit le `Literal` et régénère OpenAPI/types (drift attendu et borné à l'enum `type`). La validation par registre (400/`ValueError` sur type inconnu) reste en place pour les futurs connecteurs.

**Placeholders :** les helpers de test shell (`renderWithProviders`/`server`) et la fixture `client_admin` sont signalés comme à aligner sur le harnais réel du repo (notes d'exécution explicites), pas des trous — le patron exact existe déjà dans les fichiers voisins cités.

**Cohérence des types :** `fetch_copy_geojson(record, *, http_get) -> bytes | None` identique sur base/STAC/ArcGIS et à l'appel moteur ; `guarded_get(url) -> httpx.Response` cohérent avec `http_get(...).content`/`.json()` ; `_RUNNING_RECLAIM_MINUTES`, `_MAX_LAYERS`, `_MAX_DOCUMENTS`, `_MAX_COPY_FEATURES`, `_COPY_PAGE_SIZE` référencés de façon cohérente entre implémentation et tests.
