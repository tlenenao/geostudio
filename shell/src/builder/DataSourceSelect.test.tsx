import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { DataSource } from "../api/types";
import { DataSourceSelect } from "./DataSourceSelect";

const sources: DataSource[] = [
  { id: "ds1", type: "features", service: "fs", layer: "parcs", query: {} },
  { id: "ds2", type: "static", service: "", layer: "", query: {} },
];

test("selects a data source and emits its id", async () => {
  const onChange = vi.fn();
  render(<DataSourceSelect value="" dataSources={sources} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Source de données"), "ds2");
  expect(onChange).toHaveBeenCalledWith("ds2");
});
