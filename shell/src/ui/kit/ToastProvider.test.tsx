// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { ToastProvider, useToast } from "./ToastProvider";

function Trigger() {
  const { showToast } = useToast();
  return <button onClick={() => showToast("Enregistré")}>déclencher</button>;
}

function renderWithProvider() {
  return render(
    <ToastPrimitive.Provider>
      <ToastProvider>
        <Trigger />
      </ToastProvider>
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>,
  );
}

describe("ToastProvider", () => {
  it("affiche un toast poussé par un descendant", async () => {
    renderWithProvider();
    await userEvent.click(screen.getByRole("button", { name: "déclencher" }));
    expect(await screen.findByText("Enregistré")).toBeInTheDocument();
  });

  it("affiche un toast d'erreur avec le rôle alert", async () => {
    function ErrorTrigger() {
      const { showToast } = useToast();
      return <button onClick={() => showToast("Échec", { variant: "error" })}>err</button>;
    }
    render(
      <ToastPrimitive.Provider>
        <ToastProvider>
          <ErrorTrigger />
        </ToastProvider>
        <ToastPrimitive.Viewport />
      </ToastPrimitive.Provider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "err" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Échec");
  });
});
