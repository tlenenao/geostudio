// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { Item } from "../api/types";
import { ItemCard } from "./ItemCard";
import { OWNER_PERMISSIONS } from "../auth/permissions";

const item: Item = {
  pk: "42",
  resourceType: "dashboard",
  title: "Suivi incidents",
  abstract: "Tableau de bord",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01T00:00:00Z",
  configId: null,
  isPublished: false,
  permissions: OWNER_PERMISSIONS,
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
  expect(onOpen).toHaveBeenCalledWith("42", "dashboard");
});

test("renders the actions slot when provided", () => {
  render(<ItemCard item={item} onOpen={() => {}} actions={<span>ACTIONS</span>} />);
  expect(screen.getByText("ACTIONS")).toBeInTheDocument();
});

test("shows a thumbnail image when thumbnailUrl is set", () => {
  render(
    <ItemCard
      item={{ ...item, thumbnailUrl: "https://geonode.test/thumbs/42.png" }}
      onOpen={() => {}}
    />,
  );
  expect(screen.getByRole("img", { name: item.title })).toHaveAttribute(
    "src",
    "https://geonode.test/thumbs/42.png",
  );
});

test("shows no image when thumbnailUrl is null", () => {
  render(<ItemCard item={item} onOpen={() => {}} />);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

test("renders a French 'Externe' badge for resourceType external", () => {
  render(<ItemCard item={{ ...item, resourceType: "external" }} onOpen={() => {}} />);
  expect(screen.getByText("Externe")).toBeInTheDocument();
});

test("renders the French label for other types", () => {
  render(<ItemCard item={{ ...item, resourceType: "map" }} onOpen={() => {}} />);
  expect(screen.getByText("Carte")).toBeInTheDocument();
});
