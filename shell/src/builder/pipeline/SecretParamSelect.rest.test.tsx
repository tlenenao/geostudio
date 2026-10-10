// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { t } from "../../i18n";
import { SecretParamSelect } from "./SecretParamSelect";

function renderSelect(kindFilter: "bearer_token" | "smtp", createSecret: ReturnType<typeof vi.fn>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = { listSecrets: () => Promise.resolve([]), createSecret } as unknown as ItemClient;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <SecretParamSelect
          value=""
          onChange={vi.fn()}
          ariaLabel="secretName"
          kindFilter={kindFilter}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

// REV-294 : un secret REST est lié à une URL de base (le cœur l'exige à l'exécution).
test("un secret bearer_token porte son baseUrl (REV-294)", async () => {
  const createSecret = vi.fn().mockResolvedValue({ id: "s9", name: "api" });
  renderSelect("bearer_token", createSecret);
  await userEvent.click(screen.getByText("Créer un secret"));
  await userEvent.type(screen.getByLabelText("Nom"), "api");
  await userEvent.type(screen.getByLabelText(t("secretParamSelect.tokenLabel")), "tok");
  await userEvent.type(
    screen.getByLabelText(t("secretParamSelect.baseUrlLabel")),
    "https://api.example.test/v1",
  );
  await userEvent.click(screen.getByText("Créer"));
  await waitFor(() => expect(createSecret).toHaveBeenCalled());
  expect(createSecret.mock.calls[0][0].payload).toEqual({
    kind: "bearer_token",
    token: "tok",
    baseUrl: "https://api.example.test/v1",
  });
});

test("le contrôle TLS d'un secret SMTP peut être décoché (useTls=false)", async () => {
  const createSecret = vi.fn().mockResolvedValue({ id: "s8", name: "smtp" });
  renderSelect("smtp", createSecret);
  await userEvent.click(screen.getByText("Créer un secret"));
  await userEvent.type(screen.getByLabelText("Nom"), "smtp");
  await userEvent.type(screen.getByLabelText("Hôte"), "localhost");
  await userEvent.type(screen.getByLabelText("Port"), "25");
  const tls = screen.getByLabelText(t("secretParamSelect.useTlsLabel"));
  expect(tls).toBeChecked();
  await userEvent.click(tls);
  await userEvent.click(screen.getByText("Créer"));
  await waitFor(() => expect(createSecret).toHaveBeenCalled());
  expect(createSecret.mock.calls[0][0].payload.useTls).toBe(false);
});
