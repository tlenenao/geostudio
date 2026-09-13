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
