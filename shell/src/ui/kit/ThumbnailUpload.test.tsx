// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ThumbnailUpload } from "./ThumbnailUpload";

test("calls onUpload for a valid image", async () => {
  const onUpload = vi.fn();
  render(<ThumbnailUpload onUpload={onUpload} />);
  const file = new File(["x"], "t.png", { type: "image/png" });
  await userEvent.upload(screen.getByLabelText("Miniature"), file);
  expect(onUpload).toHaveBeenCalledWith(file);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("rejects a non-image file", async () => {
  const onUpload = vi.fn();
  render(<ThumbnailUpload onUpload={onUpload} />);
  const file = new File(["x"], "t.txt", { type: "text/plain" });
  // `accept="image/*"` is only advisory; bypass userEvent's accept filter to
  // exercise the component's own type guard (a user can still pick any file).
  await userEvent.upload(screen.getByLabelText("Miniature"), file, { applyAccept: false });
  expect(onUpload).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toBeInTheDocument();
});

test("rejects an image larger than 2 MB", async () => {
  const onUpload = vi.fn();
  render(<ThumbnailUpload onUpload={onUpload} />);
  const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], "big.png", { type: "image/png" });
  await userEvent.upload(screen.getByLabelText("Miniature"), big);
  expect(onUpload).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toBeInTheDocument();
});
