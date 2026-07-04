import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import type { Page } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const emptyLayout = { type: "grid" as const, breakpoints: {}, items: [] };
const pages: Page[] = [
  { id: "p1", name: "Accueil", layout: emptyLayout },
  { id: "p2", name: "Détails", layout: emptyLayout },
];

test("renders one button per page and calls ctx.navigate with its id on click", async () => {
  const Nav = getWidget("nav")!.Component;
  const navigate = vi.fn();
  render(<Nav props={{}} ctx={{ mode: "runtime", pages, navigate } as WidgetContext} />);
  await userEvent.click(screen.getByRole("button", { name: "Détails" }));
  expect(navigate).toHaveBeenCalledWith("p2");
});

test("shows a placeholder when there are no pages", () => {
  const Nav = getWidget("nav")!.Component;
  render(<Nav props={{}} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText(/aucune page/i)).toBeInTheDocument();
});

test("supports a vertical orientation prop", () => {
  const Nav = getWidget("nav")!.Component;
  const { container } = render(
    <Nav props={{ direction: "vertical" }} ctx={{ mode: "runtime", pages, navigate: vi.fn() } as WidgetContext} />,
  );
  expect(container.querySelector("nav")).toHaveClass("flex-col");
});
