# SPDX-License-Identifier: Apache-2.0
"""SSRF egress guard for AlertRule webhook delivery (design SP-16b §5): the
webhook URL is user-supplied per rule (unlike the SMTP secret, which is
admin-configured, cf. Global Constraints). The check itself is shared
(`app.egress_guard`, AUD-124); only the allowlist is per domain:
CORE_ALERTS_EGRESS_ALLOWLIST, distinct from CORE_PIPELINES_EGRESS_ALLOWLIST/
CORE_HARVEST_EGRESS_ALLOWLIST (different trust perimeters)."""

import logging

import requests

from app.egress_guard import check_url
from app.net_pin import ValidatedIp, pinned_adapter

logger = logging.getLogger(__name__)

_ALLOWLIST_ENV = "CORE_ALERTS_EGRESS_ALLOWLIST"


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


def assert_egress_allowed(url: str) -> ValidatedIp:
    # AUD-124 : logique commune dans app.egress_guard ; seule l'allowlist est propre au domaine.
    return check_url(url, allowlist_env=_ALLOWLIST_ENV, error=EgressBlockedError)


def _pin_ip(host: str) -> str:
    # REV-273d : la connexion vise l'IP que la garde vient de valider (anti
    # DNS-rebinding entre contrôle et connexion). Lookup du nom global à
    # l'appel : reste neutralisable par les fixtures de tests
    # (`assert_egress_allowed` remplacé par un lambda → None → pas d'épinglage).
    return assert_egress_allowed(f"http://[{host}]" if ":" in host else f"http://{host}")


class _GuardedHTTPAdapter(pinned_adapter(requests.adapters.HTTPAdapter, _pin_ip)):  # type: ignore[misc]
    def send(self, request, **kwargs):
        assert_egress_allowed(request.url)
        return super().send(request, **kwargs)


def build_guarded_session() -> requests.Session:
    session = requests.Session()
    adapter = _GuardedHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
