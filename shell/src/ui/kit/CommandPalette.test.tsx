// SPDX-License-Identifier: Apache-2.0
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CommandPalette } from "./CommandPalette";
import type { Profile } from "../../auth/capabilities";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../../api/hooks", () => ({
  useMe: () => ({ data: { privileges: ["apps.manage", "admin.users.manage"] } }),
}));

const profile: Profile = {
  privileges: new Set(["apps.manage", "admin.users.manage"]),
  capabilities: {
    readOnly: false,
    etlEnabled: false,
    exportEnabled: false,
    appExportEnabled: false,
    tileset3dEnabled: false,
    terrain3dEnabled: false,
    copilotEnabled: false,
    quotasEnabled: false,
  },
};

describe("CommandPalette", () => {
  // Le mock module-level `navigateMock` n'est jamais recréé entre les `it()`
  // (vitest.config n'active ni clearMocks ni restoreMocks) — sans ce
  // `beforeEach`, un appel de navigate() dans un test antérieur restait visible
  // par `toHaveBeenCalledWith` dans un test suivant qui n'appelle pas navigate.
  beforeEach(() => {
    navigateMock.mockClear();
  });

  it("navigue vers le domaine sélectionné au clavier puis se ferme", async () => {
    const onOpenChange = vi.fn();
    render(
      <MemoryRouter>
        <CommandPalette open onOpenChange={onOpenChange} profile={profile} />
      </MemoryRouter>,
    );
    const input = screen.getByRole("combobox");
    await userEvent.type(input, "Apps");
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/?type=app"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("propose Nouvel élément et clique le vrai déclencheur du DOM", async () => {
    document.body.innerHTML = '<button id="new-item-trigger">Nouveau</button>';
    const realButton = document.getElementById("new-item-trigger")!;
    const clickSpy = vi.spyOn(realButton, "click");
    render(
      <MemoryRouter>
        <CommandPalette open onOpenChange={vi.fn()} profile={profile} />
      </MemoryRouter>,
    );
    const input = screen.getByRole("combobox");
    await userEvent.type(input, "Nouvel");
    await userEvent.keyboard("{Enter}");
    expect(clickSpy).toHaveBeenCalled();
  });

  it("ferme sur Échap sans naviguer", async () => {
    const onOpenChange = vi.fn();
    render(
      <MemoryRouter>
        <CommandPalette open onOpenChange={onOpenChange} profile={profile} />
      </MemoryRouter>,
    );
    await userEvent.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
