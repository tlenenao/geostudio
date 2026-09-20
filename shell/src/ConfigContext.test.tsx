// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { ConfigProvider, useConfig } from "./ConfigContext";
import type { AppConfig } from "./config";

const CONFIG: AppConfig = {
  coreUrl: "https://core.test",
  oidcAuthority: "https://kc.test/realms/geostudio",
  oidcClientId: "shell",
  oidcRedirectUri: "https://app.test/callback",
  authMode: "oidc",
};

function Consumer() {
  const config = useConfig();
  return <span>{config.oidcAuthority}</span>;
}

test("useConfig retourne la config fournie par ConfigProvider", () => {
  render(
    <ConfigProvider config={CONFIG}>
      <Consumer />
    </ConfigProvider>,
  );
  expect(screen.getByText("https://kc.test/realms/geostudio")).toBeInTheDocument();
});

test("useConfig lève une erreur sans ConfigProvider", () => {
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  expect(() => render(<Consumer />)).toThrow("useConfig must be used within a ConfigProvider");
  consoleError.mockRestore();
});
