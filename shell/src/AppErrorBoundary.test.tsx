// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppErrorBoundary } from "./AppErrorBoundary";
import { expectTokenizedClasses } from "./ui/kit/testUtils";

function Boom(): never {
  throw new Error("kaboom");
}

describe("AppErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(
      <AppErrorBoundary>
        <div>hello</div>
      </AppErrorBoundary>,
    );
    expect(screen.getByText("hello")).toBeInTheDocument();
  });

  it("renders a fallback instead of crashing when a child throws", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>,
    );
    expect(screen.queryByText("hello")).not.toBeInTheDocument();
    expect(screen.getByText(/une erreur est survenue/i)).toBeInTheDocument();
    // SP-B12c : pas de couleur Tailwind de palette codée en dur — un token
    // --gs-* à la place.
    expectTokenizedClasses(container);
    consoleError.mockRestore();
  });
});
