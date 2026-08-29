// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  hasPermission,
  OWNER_PERMISSIONS,
  READ_ONLY_PERMISSIONS,
  type ItemPermissions,
} from "./permissions";

const viewer: ItemPermissions = { read: true, write: false, delete: false, share: false };

describe("hasPermission", () => {
  it("lit le verdict rendu par le cœur", () => {
    expect(hasPermission({ permissions: viewer }, "read")).toBe(true);
    expect(hasPermission({ permissions: viewer }, "write")).toBe(false);
    expect(hasPermission({ permissions: OWNER_PERMISSIONS }, "share")).toBe(true);
  });

  it("refuse tout quand la charge utile ne porte pas de permissions", () => {
    // Repli sûr et volontairement visible : si un écran perd soudain ses
    // commandes, c'est que sa source n'a pas été mise à jour — on veut le voir,
    // pas le masquer derrière un « autorisé par défaut ».
    expect(hasPermission(null, "read")).toBe(false);
    expect(hasPermission(undefined, "write")).toBe(false);
  });

  it("expose deux jeux constants, propriétaire et lecture seule", () => {
    expect(OWNER_PERMISSIONS).toEqual({ read: true, write: true, delete: true, share: true });
    expect(READ_ONLY_PERMISSIONS).toEqual({
      read: true,
      write: false,
      delete: false,
      share: false,
    });
  });
});
