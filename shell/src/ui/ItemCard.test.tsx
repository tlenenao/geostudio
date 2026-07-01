import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { Item } from "../api/types";
import { ItemCard } from "./ItemCard";

const item: Item = {
  pk: "42",
  resourceType: "dashboard",
  title: "Suivi incidents",
  abstract: "Tableau de bord",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01T00:00:00Z",
  configId: null,
};

test("renders title and type", () => {
  render(<ItemCard item={item} onOpen={() => {}} />);
  expect(screen.getByRole("heading", { name: "Suivi incidents" })).toBeInTheDocument();
  expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
});

test("calls onOpen with the pk", async () => {
  const onOpen = vi.fn();
  render(<ItemCard item={item} onOpen={onOpen} />);
  await userEvent.click(screen.getByRole("button", { name: /ouvrir/i }));
  expect(onOpen).toHaveBeenCalledWith("42");
});

test("renders the actions slot when provided", () => {
  render(<ItemCard item={item} onOpen={() => {}} actions={<span>ACTIONS</span>} />);
  expect(screen.getByText("ACTIONS")).toBeInTheDocument();
});
