// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { MapLayer } from "../api/types";
import { t } from "../i18n";
import { MapStyleTransfer } from "./MapStyleTransfer";
import { exportMapLibreStyle } from "./mapLibreStyle";

const existing: MapLayer = {
  id: "a",
  title: "A",
  visible: true,
  kind: "raster",
  tilesUrl: "https://t/{z}/{x}/{y}.png",
};

function pick(file: File) {
  fireEvent.change(screen.getByTestId("style-import-input"), { target: { files: [file] } });
}

it("importe un style MapLibre : couches ajoutées avec de nouveaux ids", async () => {
  const onChange = vi.fn();
  render(<MapStyleTransfer layers={[existing]} onChange={onChange} />);
  const doc = JSON.stringify(exportMapLibreStyle([existing], "x"));
  pick(new File([doc], "s.json", { type: "application/json" }));
  await waitFor(() => expect(onChange).toHaveBeenCalled());
  const next = onChange.mock.calls[0][0] as MapLayer[];
  expect(next).toHaveLength(2);
  expect(next[1].id).not.toBe("a");
  expect(await screen.findByRole("status")).toHaveTextContent(
    t("styleTransfer.importResult", { imported: 1, skipped: 0 }),
  );
});

it("refuse un fichier illisible sans rien modifier", async () => {
  const onChange = vi.fn();
  render(<MapStyleTransfer layers={[existing]} onChange={onChange} />);
  pick(new File(["pas du json"], "s.json"));
  expect(await screen.findByRole("status")).toHaveTextContent(t("styleTransfer.invalid"));
  expect(onChange).not.toHaveBeenCalled();
});
