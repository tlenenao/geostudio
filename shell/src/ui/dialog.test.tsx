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
