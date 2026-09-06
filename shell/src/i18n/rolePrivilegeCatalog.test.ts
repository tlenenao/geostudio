// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { fr } from "./catalog.fr";

// Miroir de PRIVILEGE_METADATA (core/app/roles/privileges.py) — même patron
// de duplication assumée que BUILT_IN_ROLE_PRIVILEGES/CREATOR_ME (cf. SP-47
// Task 2, shell/src/pages/UsagePage.tsx). Garde-fou de dérive cœur/shell
// (REV-064) : avant `resolveMessageKey()` (shell/src/i18n/index.ts),
// une labelKey renvoyée par `GET /roles/catalog` mais absente d'ici rendait
// silencieusement, dans CreateRolePanel/EditRolePanel, une case à cocher
// sans libellé ni aria-label — un cast non sûr (`as MessageKey`) ne le
// détectait jamais.
const CORE_PRIVILEGE_LABEL_KEYS = [
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
];

describe("catalogue de privilèges (miroir core/app/roles/privileges.py)", () => {
  it("chaque labelKey déclarée côté cœur est une clé réelle du catalogue fr", () => {
    const knownKeys = Object.keys(fr);
    for (const labelKey of CORE_PRIVILEGE_LABEL_KEYS) {
      expect(knownKeys, `labelKey absente du catalogue fr : ${labelKey}`).toContain(labelKey);
    }
  });
});
