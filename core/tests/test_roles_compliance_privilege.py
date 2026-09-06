# SPDX-License-Identifier: Apache-2.0
"""SP-58 Tâche 8 : privilège dédié compliance.manage (purge de tenant).

Décision explicite (spec §3.3) : aucun rôle prédéfini — pas même
Administrateur, qui porte pourtant la totalité des privilèges "admin.*" —
ne porte ce privilège par défaut. Un rôle sur mesure doit être créé
explicitement par un admin de tenant pour l'attribuer à qui de droit."""

from app.roles.privileges import (
    ALL_PRIVILEGE_VALUES,
    BUILT_IN_ROLE_PRIVILEGES,
    PRIVILEGE_METADATA,
    Privilege,
)


def test_compliance_manage_is_a_catalogued_privilege():
    assert Privilege.COMPLIANCE_MANAGE.value == "compliance.manage"
    assert Privilege.COMPLIANCE_MANAGE in PRIVILEGE_METADATA
    assert Privilege.COMPLIANCE_MANAGE.value in ALL_PRIVILEGE_VALUES


def test_no_built_in_role_carries_compliance_manage_by_default():
    for role_slug, privileges in BUILT_IN_ROLE_PRIVILEGES.items():
        assert Privilege.COMPLIANCE_MANAGE.value not in privileges, (
            f"le rôle prédéfini '{role_slug}' porte compliance.manage — "
            "décision explicite de la spec SP-58 §3.3 : aucun rôle prédéfini "
            "ne doit le porter automatiquement, y compris admin."
        )
