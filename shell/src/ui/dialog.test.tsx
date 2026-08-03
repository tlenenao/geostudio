// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { Dialog } from "./dialog";

test("renders nothing when closed", () => {
  render(
    <Dialog open={false} onClose={() => {}} title="T">
      <p>body</p>
    </Dialog>,
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("renders content when open and closes on Escape", async () => {
  const onClose = vi.fn();
  render(
    <Dialog open onClose={onClose} title="Titre">
      <p>body</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog", { name: "Titre" })).toBeInTheDocument();
  expect(screen.getByText("body")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("uses a wider max-width when wide is set", () => {
  render(
    <Dialog open onClose={() => {}} title="T" wide>
      <p>body</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-2xl");
});

test("defaults to the standard max-width when wide is omitted", () => {
  render(
    <Dialog open onClose={() => {}} title="T">
      <p>body</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-md");
});
