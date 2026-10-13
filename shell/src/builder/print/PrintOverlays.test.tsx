// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PrintOverlays } from "./PrintOverlays";

describe("PrintOverlays (ARC-16)", () => {
  it("ne rend rien sans mise en page", () => {
    const { container } = render(<PrintOverlays layout={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("rend titre, cartouche, texte libre, logo et flèche du nord", () => {
    render(
      <PrintOverlays
        layout={{
          title: "Atlas",
          cartouche: "Service SIG",
          freeText: "Source : INSEE",
          logo: "data:image/png;base64,AAAA",
          northArrow: true,
        }}
      />,
    );
    expect(screen.getByTestId("print-title")).toHaveTextContent("Atlas");
    expect(screen.getByTestId("print-cartouche")).toHaveTextContent("Service SIG");
    expect(screen.getByTestId("print-free-text")).toHaveTextContent("Source : INSEE");
    expect(screen.getByTestId("print-logo")).toHaveAttribute("src", "data:image/png;base64,AAAA");
    expect(screen.getByRole("img", { name: "Nord" })).toBeInTheDocument();
  });

  it("n'affiche la légende que si showLegend est vrai", () => {
    const { rerender } = render(
      <PrintOverlays layout={{ showLegend: false }} legend={<p>entrée</p>} />,
    );
    expect(screen.queryByText("entrée")).toBeNull();
    rerender(<PrintOverlays layout={{ showLegend: true }} legend={<p>entrée</p>} />);
    expect(screen.getByTestId("print-legend")).toHaveTextContent("entrée");
  });

  it("n'affiche ni logo ni flèche quand ils sont désactivés", () => {
    render(<PrintOverlays layout={{ title: "x", northArrow: false, logo: null }} />);
    expect(screen.queryByTestId("print-logo")).toBeNull();
    expect(screen.queryByTestId("print-north-arrow")).toBeNull();
  });
});
