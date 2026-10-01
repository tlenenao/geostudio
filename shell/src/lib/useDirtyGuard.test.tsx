// SPDX-License-Identifier: Apache-2.0
// useDirtyGuard (SP-B6b) : garde de navigation in-app sur brouillon non
// enregistré, via useBlocker (react-router-dom, data router — Tâche 25).
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Link, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { t } from "../i18n";
import { useDirtyGuard } from "./useDirtyGuard";

describe("useDirtyGuard", () => {
  it("bloque la navigation quand isDirty est vrai, débloque après confirmation", async () => {
    function Harness() {
      const [dirty, setDirty] = useState(true);
      const { ConfirmLeaveDialog } = useDirtyGuard(dirty);
      return (
        <>
          <button onClick={() => setDirty(false)}>marquer propre</button>
          <Link to="/autre">partir</Link>
          <ConfirmLeaveDialog />
        </>
      );
    }
    const router = createMemoryRouter(
      [
        { path: "/", element: <Harness /> },
        { path: "/autre", element: <p>Autre page</p> },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);

    await userEvent.click(screen.getByRole("link", { name: "partir" }));

    expect(await screen.findByRole("dialog")).toHaveTextContent(
      t("navigation.unsavedChangesMessage"),
    );

    await userEvent.click(screen.getByRole("button", { name: t("navigation.leaveAnyway") }));

    expect(await screen.findByText("Autre page")).toBeInTheDocument();
  });

  it("ne bloque pas la navigation quand isDirty est faux", async () => {
    function Harness() {
      const { ConfirmLeaveDialog } = useDirtyGuard(false);
      return (
        <>
          <Link to="/autre">partir</Link>
          <ConfirmLeaveDialog />
        </>
      );
    }
    const router = createMemoryRouter(
      [
        { path: "/", element: <Harness /> },
        { path: "/autre", element: <p>Autre page</p> },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);

    await userEvent.click(screen.getByRole("link", { name: "partir" }));

    expect(await screen.findByText("Autre page")).toBeInTheDocument();
  });

  it("ne démonte pas la boîte de dialogue de confirmation quand le composant appelant se re-rend pour une raison sans rapport (identité de ConfirmLeaveDialog stable)", async () => {
    // Régression : une version naïve de useDirtyGuard qui déclare la fonction
    // de rendu de la boîte de dialogue à l'intérieur du corps du hook (sans
    // useCallback) recrée un nouveau type de composant à chaque rendu du
    // composant appelant — React démonte alors tout le sous-arbre à chaque
    // fois qu'un état sans rapport change pendant que la boîte est affichée
    // (ex. un refetch de fond). Falsifié contre la version naïve avant le
    // correctif (cf. rapport de tâche) : ce test échouait bien sur le nœud
    // racine devenu un objet DOM différent.
    function Harness() {
      const [dirty] = useState(true);
      const [tick, setTick] = useState(0);
      const { ConfirmLeaveDialog } = useDirtyGuard(dirty);
      return (
        <>
          <button onClick={() => setTick((n) => n + 1)}>re-render sans rapport ({tick})</button>
          <Link to="/autre">partir</Link>
          <ConfirmLeaveDialog />
        </>
      );
    }
    const router = createMemoryRouter(
      [
        { path: "/", element: <Harness /> },
        { path: "/autre", element: <p>Autre page</p> },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);

    // Radix masque (aria-hidden) tout le reste de la page pendant que le
    // Dialog est ouvert — le bouton de déclenchement doit donc être capturé
    // AVANT l'ouverture (encore accessible), puis actionné via fireEvent
    // (qui ne filtre pas par aria-hidden, contrairement aux requêtes
    // getByRole) une fois la boîte affichée.
    const tickButton = screen.getByRole("button", { name: /re-render sans rapport/ });

    await userEvent.click(screen.getByRole("link", { name: "partir" }));
    const dialogBeforeRerender = await screen.findByRole("dialog");

    fireEvent.click(tickButton);

    const dialogAfterRerender = screen.getByRole("dialog");
    expect(dialogAfterRerender).toBe(dialogBeforeRerender);
  });

  it("pose un beforeunload tant que le brouillon est sale, et le retire sinon (P09.06)", () => {
    function Harness({ dirty }: { dirty: boolean }) {
      useDirtyGuard(dirty);
      return null;
    }
    const mount = (dirty: boolean) => {
      const router = createMemoryRouter([{ path: "/", element: <Harness dirty={dirty} /> }]);
      return render(<RouterProvider router={router} />);
    };
    const fire = () => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };

    const dirty = mount(true);
    expect(fire()).toBe(true);
    dirty.unmount();
    expect(fire()).toBe(false);

    const clean = mount(false);
    expect(fire()).toBe(false);
    clean.unmount();
  });
});
