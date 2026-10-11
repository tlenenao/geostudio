// SPDX-License-Identifier: Apache-2.0
// Miroir de PRIVILEGE_METADATA (core/app/roles/privileges.py) : les labelKey sont
// fournies par `GET /roles/catalog` et résolues dynamiquement (resolveMessageKey).
// Citées ici en littéral pour que le détecteur de clés inutilisées les voie ;
// la parité avec le cœur est testée par core/tests/test_privilege_label_keys.py
// (REV-306) : toute dérive cœur/shell échoue en CI.
export const CORE_PRIVILEGE_LABEL_KEYS = [
  "roles.privilege.catalogManage",
  "roles.privilege.mapsManage",
  "roles.privilege.dataView",
  "roles.privilege.dataManage",
  "roles.privilege.appsManage",
  "roles.privilege.automationManage",
  "roles.privilege.automationSecretsManage",
  "roles.privilege.analyticsView",
  "roles.privilege.analyticsSqlLabAccess",
  "roles.privilege.tasksView",
  "roles.privilege.tasksViewAll",
  "roles.privilege.adminUsersManage",
  "roles.privilege.adminRolesManage",
  "roles.privilege.adminHarvestManage",
  "roles.privilege.adminCollectionsManage",
  "roles.privilege.adminExtensionsManage",
  "roles.privilege.adminSecretsManage",
  "roles.privilege.settingsInstanceManage",
  "roles.privilege.complianceManage",
  "roles.privilege.dataViewSensitive",
] as const;
