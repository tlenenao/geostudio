"""fec0::/10 (site-local IPv6 déprécié) : `is_global` le laisse passer (j06-003)."""

import ipaddress
from importlib import import_module

import pytest

MODULES = [
    "app.search.egress",
    "app.copilot.egress",
    "app.geocoding.egress",
    "app.alerts.egress",
    "app.pipelines.egress",
    "app.harvest.egress",
]


@pytest.mark.parametrize("module", MODULES)
def test_site_local_ipv6_is_internal(module):
    assert import_module(module)._is_internal(ipaddress.ip_address("fec0::1"))


@pytest.mark.parametrize("module", MODULES)
def test_public_addresses_stay_allowed(module):
    is_internal = import_module(module)._is_internal
    assert not is_internal(ipaddress.ip_address("8.8.8.8"))
    assert not is_internal(ipaddress.ip_address("2606:4700:4700::1111"))
