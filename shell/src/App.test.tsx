import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders the GeoStudio heading", () => {
  render(<App />);
  expect(
    screen.getByRole("heading", { name: /geostudio/i }),
  ).toBeInTheDocument();
});
