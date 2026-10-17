# SPDX-License-Identifier: Apache-2.0
"""AUD-124 : une seule garde, paramétrée sur les 6 domaines (parité)."""

import importlib
import ipaddress

import pytest

from app.egress_guard import embedded_ipv4, is_internal

MODULES = [
    "app.alerts.egress",
    "app.copilot.egress",
    "app.geocoding.egress",
    "app.harvest.egress",
    "app.pipelines.egress",
    "app.search.egress",
]

INTERNAL = [
    "127.0.0.1",
    "10.0.0.1",
    "169.254.169.254",
    "100.64.0.1",
    "::1",
    "fec0::1",
    "::ffff:169.254.169.254",
    "64:ff9b::a9fe:a9fe",
    "64:ff9b::7f00:1",
    "64:ff9b::a00:1",
    "64:ff9b:1::a00:1",
    "::a9fe:a9fe",
    "2002:a9fe:a9fe::1",
    "224.0.0.1",
]
PUBLIC = [
    "8.8.8.8",
    "2001:4860:4860::8888",
    "2606:4700:4700::1111",
    "64:ff9b::808:808",
    "::ffff:8.8.8.8",
]


@pytest.mark.parametrize("addr", INTERNAL)
def test_internal_addresses_are_internal(addr):
    assert is_internal(ipaddress.ip_address(addr))


@pytest.mark.parametrize("addr", PUBLIC)
def test_public_addresses_are_not_internal(addr):
    assert not is_internal(ipaddress.ip_address(addr))


def test_embedded_ipv4_unwraps_nat64_mapped_and_compat():
    assert str(embedded_ipv4(ipaddress.ip_address("64:ff9b::a9fe:a9fe"))) == "169.254.169.254"
    assert str(embedded_ipv4(ipaddress.ip_address("::ffff:10.0.0.1"))) == "10.0.0.1"
    assert str(embedded_ipv4(ipaddress.ip_address("::a9fe:a9fe"))) == "169.254.169.254"
    assert embedded_ipv4(ipaddress.ip_address("8.8.8.8")) is None


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("addr", ["64:ff9b::a9fe:a9fe", "::a9fe:a9fe", "127.0.0.1"])
def test_every_domain_guard_blocks_internal_literals(monkeypatch, module_name, addr):
    mod = importlib.import_module(module_name)
    monkeypatch.delenv("CORE_GEOCODING_EGRESS_ALLOWLIST", raising=False)
    host = f"[{addr}]" if ":" in addr else addr
    with pytest.raises(mod.EgressBlockedError):
        mod.assert_egress_allowed(f"http://{host}/x")


@pytest.mark.parametrize("module_name", MODULES)
def test_every_domain_guard_refuses_non_http(module_name):
    mod = importlib.import_module(module_name)
    with pytest.raises(mod.EgressBlockedError):
        mod.assert_egress_allowed("file:///etc/passwd")


def test_geocoding_keeps_its_default_allowlist(monkeypatch):
    mod = importlib.import_module("app.geocoding.egress")
    monkeypatch.delenv("CORE_GEOCODING_EGRESS_ALLOWLIST", raising=False)
    with pytest.raises(mod.EgressBlockedError, match="allowlist"):
        mod.assert_egress_allowed("http://8.8.8.8/")
