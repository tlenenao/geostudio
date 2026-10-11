# SPDX-License-Identifier: Apache-2.0
"""GAP-22 Tâche 1 : privilège data.view_sensitive (masquage de colonne par rôle).

Décision (spec GAP-22) : ce privilège rejoint automatiquement le rôle
Administrateur (déjà porteur de tout `ALL_PRIVILEGE_VALUES` sauf
`compliance.manage`, exclusion nommée) mais aucun des 3 autres rôles
prédéfinis (Créateur/Analyste/Lecteur), qui restent des listes explicites."""

from app.roles.privileges import ALL_PRIVILEGE_VALUES, BUILT_IN_ROLE_PRIVILEGES, Privilege


def test_data_view_sensitive_exists_and_joins_admin_only():
    assert Privilege.DATA_VIEW_SENSITIVE == "data.view_sensitive"
    assert Privilege.DATA_VIEW_SENSITIVE.value in ALL_PRIVILEGE_VALUES
    assert Privilege.DATA_VIEW_SENSITIVE.value in BUILT_IN_ROLE_PRIVILEGES["admin"]
    for role in ("creator", "analyst", "reader"):
        assert Privilege.DATA_VIEW_SENSITIVE.value not in BUILT_IN_ROLE_PRIVILEGES[role]


def test_every_privilege_is_enforced_server_side_or_declared_navigation_only_c01_010():
    """Un privilège catalogué doit garder au moins une route/décision du cœur,
    ou figurer explicitement dans NAVIGATION_ONLY_PRIVILEGES."""
    import pathlib
    import re

    from app.roles.privileges import NAVIGATION_ONLY_PRIVILEGES

    app_dir = pathlib.Path(__file__).parent.parent / "app"
    source = "\n".join(
        p.read_text()
        for p in app_dir.rglob("*.py")
        if p.name != "privileges.py" or p.parent.name != "roles"
    )
    unguarded = {
        p
        for p in Privilege
        if not re.search(rf"Privilege\.{p.name}\b", source) and f'"{p.value}"' not in source
    }
    assert unguarded == NAVIGATION_ONLY_PRIVILEGES


def test_reader_can_create_bookmarks_rev270_p12_10():
    """Décision produit REV-270/P12.10 (inverse j02-015) : le Lecteur crée des
    bookmarks via analytics.view, et rien d'autre."""
    from app.roles.kind_registry import privilege_for_kind

    assert BUILT_IN_ROLE_PRIVILEGES["reader"] == [Privilege.ANALYTICS_VIEW.value]
    assert privilege_for_kind("bookmark") == Privilege.ANALYTICS_VIEW.value
