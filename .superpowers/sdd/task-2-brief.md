## Task 2: SSRF egress guard for `app.pipelines` — `app/pipelines/egress.py`

**Files:**
- Create: `core/app/pipelines/egress.py`
- Modify: `core/pyproject.toml` (add `requests` dependency)
- Test: `core/tests/test_pipeline_egress.py`

**Interfaces:**
- Produces: `app.pipelines.egress.EgressBlockedError`,
  `assert_egress_allowed(url: str) -> None`,
  `build_guarded_session() -> requests.Session`. Consumed by Task 3
  (`connector_runtime.materialize_rest_connector` passes the guarded
  session to dlt's `RESTClient`).

- [ ] **Step 1: Add the `requests` dependency**

Modify `core/pyproject.toml` — in `dependencies = [...]`, add after
`"httpx>=0.27",`:

```toml
    "requests>=2.31",  # SP-15f : garde SSRF pour reader.connector.rest — dlt's
                       # RESTClient utilise `requests`, pas httpx (que le reste
                       # du dépôt utilise déjà) ; déclaré ici en dépendance
                       # directe plutôt que de compter sur la transitive de dlt.
```

Run: `cd core && uv sync`
Expected: resolves; `requests` becomes a direct dependency (it was almost
certainly already present transitively via other packages, but wasn't
importable as a guaranteed direct dependency before this).

- [ ] **Step 2: Write the failing tests**

Create `core/tests/test_pipeline_egress.py` (mirrors
`core/tests/test_harvest_egress.py` exactly, adapted from `httpx` to
`requests`):

```python
# SPDX-License-Identifier: Apache-2.0
import socket

import pytest
import requests

from app.pipelines.egress import (
    EgressBlockedError,
    assert_egress_allowed,
    build_guarded_session,
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
    monkeypatch.setenv("CORE_PIPELINES_EGRESS_ALLOWLIST", "other.example.com")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://public.example.com/x")
    monkeypatch.setenv("CORE_PIPELINES_EGRESS_ALLOWLIST", "public.example.com,other.example.com")
    assert_egress_allowed("https://public.example.com/x") is None


def test_guarded_session_blocks_before_connection():
    # 127.0.0.1:9 (discard) : la garde doit lever AVANT toute tentative de
    # connexion réseau — donc EgressBlockedError, jamais un ConnectionError.
    session = build_guarded_session()
    with pytest.raises(EgressBlockedError):
        session.get("http://127.0.0.1:9/x", timeout=1.0)


def test_guarded_session_is_a_real_requests_session():
    session = build_guarded_session()
    assert isinstance(session, requests.Session)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_egress.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.egress'`.

- [ ] **Step 4: Implement `egress.py`**

Create `core/app/pipelines/egress.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF pour reader.connector.rest (design SP-15f §5.1) —
duplication délibérée de app.harvest.egress : app.pipelines est positionné
SOUS app.harvest dans le contrat de couches import-linter
(core/pyproject.toml [[tool.importlinter.contracts]]), donc ne peut pas
l'importer. Point d'application différent de l'original : dlt.sources.rest_api
utilise `requests`, pas `httpx` — copier le transport httpx de
app.harvest.egress ne garderait rien en pratique."""
import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Variable dédiée, distincte de CORE_HARVEST_EGRESS_ALLOWLIST (app.harvest) :
# même logique de duplication que la garde elle-même, plutôt que de partager
# un état de configuration à travers la frontière de couches.
_ALLOWLIST_ENV = "CORE_PIPELINES_EGRESS_ALLOWLIST"


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


class _GuardedHTTPAdapter(requests.adapters.HTTPAdapter):
    def send(self, request, **kwargs):
        assert_egress_allowed(request.url)
        return super().send(request, **kwargs)


def build_guarded_session() -> requests.Session:
    session = requests.Session()
    adapter = _GuardedHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_egress.py -v`
Expected: 8 passed.

- [ ] **Step 6: Verify the layering contract still holds**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` — `egress.py` imports nothing from
any other `app.*` module, so this only confirms nothing else broke.

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/egress.py core/pyproject.toml core/uv.lock core/tests/test_pipeline_egress.py
git commit -m "feat(core): pipelines — SSRF egress guard for reader.connector.rest"
```

---

