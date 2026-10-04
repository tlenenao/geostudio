// SPDX-License-Identifier: Apache-2.0
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { MapPopup } from "./MapPopup";

test("renders the title and the rows", () => {
  render(
    <MapPopup
      content={{ title: "Tulle", rows: [{ label: "Habitants", value: "14000" }], html: null }}
      x={10}
      y={20}
      onClose={() => {}}
    />,
  );
  expect(screen.getByText("Tulle")).toBeInTheDocument();
  expect(screen.getByText("Habitants")).toBeInTheDocument();
  expect(screen.getByText("14000")).toBeInTheDocument();
});

test("renders the sanitized html of a template popup", () => {
  render(
    <MapPopup
      content={{ title: null, rows: [], html: "<strong>Tulle</strong>" }}
      x={0}
      y={0}
      onClose={() => {}}
    />,
  );
  expect(screen.getByText("Tulle").tagName).toBe("STRONG");
});

test("is positioned where the map projected the clicked point", () => {
  render(
    <MapPopup content={{ title: null, rows: [], html: null }} x={42} y={7} onClose={() => {}} />,
  );
  const popup = screen.getByRole("dialog");
  expect(popup.style.left).toBe("42px");
  expect(popup.style.top).toBe("7px");
});

test("closes on the close button", async () => {
  const onClose = vi.fn();
  render(
    <MapPopup content={{ title: null, rows: [], html: null }} x={0} y={0} onClose={onClose} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Fermer" }));
  expect(onClose).toHaveBeenCalledOnce();
});

test("a template that interpolates to an empty string is treated as no html, not an empty bubble", () => {
  const { container } = render(
    <MapPopup content={{ title: null, rows: [], html: "" }} x={0} y={0} onClose={() => {}} />,
  );
  expect(screen.getByText("Aucun attribut")).toBeInTheDocument();
  // La branche rendue est celle des lignes (une `<dl>`, ici vide), jamais
  // le `<div>` injecté par `dangerouslySetInnerHTML`.
  expect(container.querySelector("dl")).not.toBeNull();
});

test("shows an explicit message when the feature carries no attribute", () => {
  render(
    <MapPopup content={{ title: null, rows: [], html: null }} x={0} y={0} onClose={() => {}} />,
  );
  expect(screen.getByText("Aucun attribut")).toBeInTheDocument();
});

test("affiche la section Pièces jointes quand la liste est non vide", async () => {
  const onDownloadAttachment = vi.fn();
  render(
    <MapPopup
      content={{ title: "X", rows: [], html: null }}
      x={0}
      y={0}
      onClose={vi.fn()}
      attachments={[
        {
          id: "a1",
          fieldKey: "photos",
          filename: "a.jpg",
          contentType: "image/jpeg",
          byteSize: 1,
          createdAt: "",
        },
      ]}
      onDownloadAttachment={onDownloadAttachment}
    />,
  );
  expect(screen.getByText("Pièces jointes")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "a.jpg" }));
  expect(onDownloadAttachment).toHaveBeenCalledWith("a1", "a.jpg");
});

test("n'affiche pas la section Pièces jointes quand attachments est vide ou absent", () => {
  render(<MapPopup content={{ title: "X", rows: [], html: null }} x={0} y={0} onClose={vi.fn()} />);
  expect(screen.queryByText("Pièces jointes")).not.toBeInTheDocument();
});

test("D41 : Échap ferme la popup", async () => {
  const onClose = vi.fn();
  render(
    <MapPopup
      content={{ title: "Tulle", rows: [{ label: "Habitants", value: "14000" }], html: null }}
      x={0}
      y={0}
      onClose={onClose}
    />,
  );
  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledOnce();
});

test("D41 : le focus est posé sur le premier élément interactif (bouton Fermer) au montage", () => {
  render(
    <MapPopup
      content={{ title: "Tulle", rows: [{ label: "Habitants", value: "14000" }], html: null }}
      x={0}
      y={0}
      onClose={() => {}}
    />,
  );
  expect(screen.getByRole("button", { name: "Fermer" })).toHaveFocus();
});

// REV-286(d) : stub de ResizeObserver LOCAL au test (piège n°10, jamais
// dans setup.ts) ; mise en page simulée par des getters espionnés.
test("le clamp horizontal est recalculé quand le conteneur rétrécit", () => {
  const ro = { callback: () => {}, observe: vi.fn(), disconnect: vi.fn() };
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(cb: () => void) {
        ro.callback = cb;
      }
      observe = ro.observe;
      disconnect = ro.disconnect;
      unobserve() {}
    },
  );
  const parent = document.createElement("div");
  let parentWidth = 400;
  Object.defineProperty(parent, "clientWidth", { get: () => parentWidth });
  Object.defineProperty(parent, "clientHeight", { get: () => 300 });
  const spies = [
    vi.spyOn(HTMLElement.prototype, "offsetParent", "get").mockReturnValue(parent),
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(100),
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(50),
  ];
  try {
    const { unmount } = render(
      <MapPopup
        content={{ title: "T", rows: [], html: null }}
        x={350}
        y={200}
        onClose={() => {}}
      />,
    );
    const popup = screen.getByRole("dialog");
    expect(popup.style.left).toBe("300px"); // min(350 - 50, 400 - 100)
    expect(ro.observe).toHaveBeenCalledWith(parent);
    parentWidth = 200;
    act(() => ro.callback());
    expect(popup.style.left).toBe("100px"); // min(300, 200 - 100)
    unmount();
    expect(ro.disconnect).toHaveBeenCalled();
  } finally {
    spies.forEach((s) => s.mockRestore());
    vi.unstubAllGlobals();
  }
});
