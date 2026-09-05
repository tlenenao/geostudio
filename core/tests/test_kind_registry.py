# SPDX-License-Identifier: Apache-2.0
"""Registre unique kind -> privilège requis — SP-43 Étape 1. Remplace le
dict privé _KIND_PRIVILEGE de app.configs.routes, consommé jusqu'ici par 4
sites avec 3 formes de couplage différentes (import de nom privé, import du
dict privé lui-même, recopie de valeur en dur) — cf. spec §1.1."""

import pytest

from app.roles.kind_registry import privilege_for_kind
from app.roles.privileges import Privilege

KNOWN_KINDS = {
    "app": Privilege.APPS_MANAGE.value,
    "dashboard": Privilege.APPS_MANAGE.value,
    "site": Privilege.APPS_MANAGE.value,
    "map": Privilege.MAPS_MANAGE.value,
    "dataset": Privilege.DATA_MANAGE.value,
    "pipeline": Privilege.AUTOMATION_MANAGE.value,
    "alert": Privilege.AUTOMATION_MANAGE.value,
    "report": Privilege.AUTOMATION_MANAGE.value,
    "bookmark": Privilege.ANALYTICS_VIEW.value,
    "tileset3d": Privilege.CATALOG_MANAGE.value,
    "terrain3d": Privilege.CATALOG_MANAGE.value,
}


@pytest.mark.parametrize("kind,expected", list(KNOWN_KINDS.items()))
def test_privilege_for_known_kind(kind: str, expected: str) -> None:
    assert privilege_for_kind(kind) == expected


def test_privilege_for_unknown_kind_falls_back_to_catalog_manage() -> None:
    assert privilege_for_kind("unknown-future-kind") == Privilege.CATALOG_MANAGE.value
