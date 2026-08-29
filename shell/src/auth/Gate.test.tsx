// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Gate } from "./Gate";
import { OWNER_PERMISSIONS, type ItemPermissions } from "./permissions";

const viewer: ItemPermissions = { read: true, write: false, delete: false, share: false };

describe("Gate", () => {
  it("rend ses enfants quand le droit est accordé", () => {
    render(
      <Gate on={{ permissions: OWNER_PERMISSIONS }} can="write">
        <button>Modifier</button>
      </Gate>,
    );
    expect(screen.getByRole("button", { name: "Modifier" })).toBeInTheDocument();
  });

  it("ne rend rien quand le droit est refusé et qu'aucun repli n'est fourni", () => {
    render(
      <Gate on={{ permissions: viewer }} can="write">
        <button>Modifier</button>
      </Gate>,
    );
    expect(screen.queryByRole("button", { name: "Modifier" })).not.toBeInTheDocument();
  });

  it("rend le repli quand il est fourni", () => {
    render(
      <Gate on={{ permissions: viewer }} can="delete" fallback={<span>Réservé aux éditeurs</span>}>
        <button>Supprimer</button>
      </Gate>,
    );
    expect(screen.queryByRole("button", { name: "Supprimer" })).not.toBeInTheDocument();
    expect(screen.getByText("Réservé aux éditeurs")).toBeInTheDocument();
  });

  it("couvre les quatre actions", () => {
    const perms: ItemPermissions = { read: true, write: true, delete: false, share: false };
    for (const [action, expected] of [
      ["read", true],
      ["write", true],
      ["delete", false],
      ["share", false],
    ] as const) {
      const { unmount } = render(
        <Gate on={{ permissions: perms }} can={action}>
          <span>{action}</span>
        </Gate>,
      );
      expect(screen.queryByText(action) !== null).toBe(expected);
      unmount();
    }
  });
});
