# SPDX-License-Identifier: Apache-2.0
from enum import StrEnum


class Privilege(StrEnum):
    CATALOG_MANAGE = "catalog.manage"
    MAPS_MANAGE = "maps.manage"
    DATA_VIEW = "data.view"
    DATA_MANAGE = "data.manage"
    APPS_MANAGE = "apps.manage"
    AUTOMATION_MANAGE = "automation.manage"
    AUTOMATION_SECRETS_MANAGE = "automation.secrets.manage"
    ANALYTICS_VIEW = "analytics.view"
    ANALYTICS_SQL_LAB_ACCESS = "analytics.sql_lab.access"
    TASKS_VIEW = "tasks.view"
    TASKS_VIEW_ALL = "tasks.view_all"
    ADMIN_USERS_MANAGE = "admin.users.manage"
    ADMIN_ROLES_MANAGE = "admin.roles.manage"
    ADMIN_HARVEST_MANAGE = "admin.harvest.manage"
    ADMIN_COLLECTIONS_MANAGE = "admin.collections.manage"
    ADMIN_EXTENSIONS_MANAGE = "admin.extensions.manage"
    ADMIN_SECRETS_MANAGE = "admin.secrets.manage"
    SETTINGS_INSTANCE_MANAGE = "settings.instance.manage"
    COMPLIANCE_MANAGE = "compliance.manage"


# (domaine shell/src/auth/capabilities.ts::DomainId, clé i18n shell/src/i18n/catalog.fr.ts)
# — le cœur ne porte aucun libellé français (A12), seulement l'identifiant du
# domaine et une clé que le shell résout via t().
PRIVILEGE_METADATA: dict[Privilege, tuple[str, str]] = {
    Privilege.CATALOG_MANAGE: ("catalog", "roles.privilege.catalogManage"),
    Privilege.MAPS_MANAGE: ("maps", "roles.privilege.mapsManage"),
    Privilege.DATA_VIEW: ("data", "roles.privilege.dataView"),
    Privilege.DATA_MANAGE: ("data", "roles.privilege.dataManage"),
    Privilege.APPS_MANAGE: ("apps", "roles.privilege.appsManage"),
    Privilege.AUTOMATION_MANAGE: ("automation", "roles.privilege.automationManage"),
    Privilege.AUTOMATION_SECRETS_MANAGE: (
        "automation",
        "roles.privilege.automationSecretsManage",
    ),
    Privilege.ANALYTICS_VIEW: ("analytics", "roles.privilege.analyticsView"),
    Privilege.ANALYTICS_SQL_LAB_ACCESS: ("analytics", "roles.privilege.analyticsSqlLabAccess"),
    Privilege.TASKS_VIEW: ("tasks", "roles.privilege.tasksView"),
    Privilege.TASKS_VIEW_ALL: ("tasks", "roles.privilege.tasksViewAll"),
    Privilege.ADMIN_USERS_MANAGE: ("admin", "roles.privilege.adminUsersManage"),
    Privilege.ADMIN_ROLES_MANAGE: ("admin", "roles.privilege.adminRolesManage"),
    Privilege.ADMIN_HARVEST_MANAGE: ("admin", "roles.privilege.adminHarvestManage"),
    Privilege.ADMIN_COLLECTIONS_MANAGE: ("admin", "roles.privilege.adminCollectionsManage"),
    Privilege.ADMIN_EXTENSIONS_MANAGE: ("admin", "roles.privilege.adminExtensionsManage"),
    Privilege.ADMIN_SECRETS_MANAGE: ("admin", "roles.privilege.adminSecretsManage"),
    Privilege.SETTINGS_INSTANCE_MANAGE: ("settings", "roles.privilege.settingsInstanceManage"),
    # Domaine "settings" par analogie avec SETTINGS_INSTANCE_MANAGE (même
    # famille shell) — décision de la Tâche 8 (spec SP-58 §3.3/§6, laissée
    # ouverte par la spec) : un domaine "compliance" dédié aurait demandé
    # d'étendre DomainId (shell/src/auth/capabilities.ts) pour un seul
    # privilège consommé par une unique action admin, jugé disproportionné.
    Privilege.COMPLIANCE_MANAGE: ("settings", "roles.privilege.complianceManage"),
}

ALL_PRIVILEGE_VALUES: list[str] = [p.value for p in Privilege]

BUILT_IN_ROLE_NAMES: dict[str, str] = {
    "admin": "Administrateur",
    "creator": "Créateur",
    "analyst": "Analyste",
    "reader": "Lecteur",
}

# Reprend la matrice §6.7 de docs/superpowers/specs/2026-08-29-refonte-ui-triptyque-design.md,
# traduite en privilèges concrets (design §3.3).
BUILT_IN_ROLE_PRIVILEGES: dict[str, list[str]] = {
    # SP-58 Tâche 8 (spec §3.3, décision explicite) : compliance.manage est
    # volontairement EXCLU, même de l'Administrateur — la purge de tenant
    # est irréversible, un rôle sur mesure doit l'attribuer consciemment.
    # Sans cette exclusion, `list(ALL_PRIVILEGE_VALUES)` l'aurait glissé
    # silencieusement dans "admin" dès son ajout à l'enum ci-dessus.
    "admin": [p for p in ALL_PRIVILEGE_VALUES if p != Privilege.COMPLIANCE_MANAGE.value],
    "creator": [
        Privilege.CATALOG_MANAGE.value,
        Privilege.MAPS_MANAGE.value,
        Privilege.DATA_VIEW.value,
        Privilege.DATA_MANAGE.value,
        Privilege.APPS_MANAGE.value,
        Privilege.AUTOMATION_MANAGE.value,
        Privilege.AUTOMATION_SECRETS_MANAGE.value,
        Privilege.ANALYTICS_VIEW.value,
        Privilege.TASKS_VIEW.value,
    ],
    "analyst": [
        Privilege.DATA_VIEW.value,
        Privilege.ANALYTICS_VIEW.value,
        Privilege.ANALYTICS_SQL_LAB_ACCESS.value,
        Privilege.TASKS_VIEW.value,
    ],
    "reader": [],
}
