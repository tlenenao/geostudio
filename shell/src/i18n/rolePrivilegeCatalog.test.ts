// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { fr } from "./catalog.fr";
import { CORE_PRIVILEGE_LABEL_KEYS } from "./corePrivilegeLabelKeys";

// Garde-fou de dérive cœur/shell (REV-064) : une labelKey renvoyée par
// `GET /roles/catalog` mais absente du catalogue rendait silencieusement une
// case à cocher sans libellé. La parité avec le cœur lui-même est testée côté
// Python (core/tests/test_privilege_label_keys.py, REV-306).
describe("catalogue de privilèges (miroir core/app/roles/privileges.py)", () => {
  it("chaque labelKey déclarée côté cœur est une clé réelle du catalogue fr", () => {
    const knownKeys = Object.keys(fr);
    for (const labelKey of CORE_PRIVILEGE_LABEL_KEYS) {
      expect(knownKeys, `labelKey absente du catalogue fr : ${labelKey}`).toContain(labelKey);
    }
  });
});
