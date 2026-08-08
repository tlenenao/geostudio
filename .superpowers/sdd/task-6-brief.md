### Task 6: `app/alerts/egress.py` — SSRF guard for webhooks

**Files:**
- Create: `core/app/alerts/egress.py`
- Modify: `.env.example`
- Test: `core/tests/test_alert_egress.py`

**Interfaces:**
- Produces: `assert_egress_allowed(url: str) -> None` (raises `EgressBlockedError`), consumed by Task 8 (`app.alerts.notify`).

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_alert_egress.py
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.alerts.egress import EgressBlockedError, assert_egress_allowed


def test_blocks_a_loopback_url():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("http://127.0.0.1:8080/hook")


def test_blocks_a_private_range_url():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("http://10.0.0.5/hook")


def test_blocks_a_non_http_scheme():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("file:///etc/passwd")


def test_allows_a_public_https_url():
    assert_egress_allowed("https://example.test/hook") is None


def test_allowlist_restricts_to_named_hosts(monkeypatch):
    monkeypatch.setenv("CORE_ALERTS_EGRESS_ALLOWLIST", "allowed.example.test")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://not-allowed.example.test/hook")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_egress.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.alerts.egress'`

- [ ] **Step 3: Write the implementation**

```python
# core/app/alerts/egress.py
# SPDX-License-Identifier: Apache-2.0
"""SSRF egress guard for AlertRule webhook delivery (design SP-16b §5) —
deliberate duplication of app.pipelines.egress/app.harvest.egress: the
webhook URL is user-supplied per rule (unlike the SMTP secret, which is
admin-configured, cf. Global Constraints), same threat model as the two
existing guards. Own CORE_ALERTS_EGRESS_ALLOWLIST env var, distinct from
CORE_PIPELINES_EGRESS_ALLOWLIST/CORE_HARVEST_EGRESS_ALLOWLIST — same
duplication rationale as the guard itself."""
import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_ALLOWLIST_ENV = "CORE_ALERTS_EGRESS_ALLOWLIST"


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

Add to `.env.example`, next to the existing egress allowlist entries:

```bash
# Allowlist d'hôtes pour la garde d'egress SSRF des webhooks d'alerte
# (AlertRule, SP-16b) — liste séparée par des virgules ; vide (défaut) =
# seules les plages réseau internes/privées sont bloquées, aucune
# restriction d'hôte supplémentaire.
CORE_ALERTS_EGRESS_ALLOWLIST=
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_egress.py`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add core/app/alerts/egress.py .env.example core/tests/test_alert_egress.py
git commit -m "feat(core): SP-16b — app.alerts.egress SSRF guard for webhook delivery"
```

---

