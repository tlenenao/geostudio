// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { CameraControls } from "./CameraControls";

test("renders the current pitch and bearing", () => {
  render(<CameraControls pitch={30} bearing={120} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Inclinaison de la caméra")).toHaveValue("30");
  expect(screen.getByLabelText("Orientation de la caméra")).toHaveValue("120");
});

test("moving the pitch slider reports the new pitch and keeps bearing", () => {
  const onChange = vi.fn();
  render(<CameraControls pitch={30} bearing={120} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Inclinaison de la caméra"), { target: { value: "45" } });
  expect(onChange).toHaveBeenCalledWith({ pitch: 45, bearing: 120 });
});

test("moving the bearing slider reports the new bearing and keeps pitch", () => {
  const onChange = vi.fn();
  render(<CameraControls pitch={30} bearing={120} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Orientation de la caméra"), { target: { value: "200" } });
  expect(onChange).toHaveBeenCalledWith({ pitch: 30, bearing: 200 });
});

test("normalizes a negative bearing from MapLibre into [0, 360) for display", () => {
  // map.getBearing() returns (-180, 180]: rotating past north yields -170,
  // which the [0, 360] slider would clamp to 0 while the label printed -170.
  render(<CameraControls pitch={0} bearing={-170} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Orientation de la caméra")).toHaveValue("190");
  expect(screen.getByText(/Orientation \(bearing\)/)).toHaveTextContent("190°");
});

test("normalizes a bearing beyond a full turn for display", () => {
  render(<CameraControls pitch={0} bearing={400} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Orientation de la caméra")).toHaveValue("40");
});

test("the reset button reports pitch 0 and bearing 0", async () => {
  const onChange = vi.fn();
  render(<CameraControls pitch={30} bearing={120} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Réinitialiser en 2D" }));
  expect(onChange).toHaveBeenCalledWith({ pitch: 0, bearing: 0 });
});
