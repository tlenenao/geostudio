// SPDX-License-Identifier: Apache-2.0
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";

vi.mock("react-oidc-context", () => ({
  useAuth: () => ({
    signinSilent: vi.fn().mockResolvedValue({ access_token: "real-mcp-token" }),
  }),
}));

// Pas de vi.resetModules() ici : ce fichier ne contient qu'un seul test, et
// resetModules() casserait le partage d'instance de module entre l'import
// statique d'enableMockAuth() ci-dessus et l'import dynamique de
// useMcpToken.ts ci-dessous — enableMockAuth() positionnerait le drapeau
// mockMode sur une instance de ../../auth/useAuth, tandis que useMcpToken.ts
// en importerait une autre (fraîchement réinitialisée), et isMockMode()
// verrait faussement false. Vérifié empiriquement. L'isolation vis-à-vis de
// useMcpTokenOidc.test.tsx (qui ne mock mode jamais) est déjà garantie par
// le fait que Vitest exécute chaque fichier de test dans son propre
// contexte de module.
describe("useMcpToken", () => {
  it("returns a fixed mock token synchronously in mock mode", async () => {
    enableMockAuth();
    const { useMcpToken } = await import("./useMcpToken");
    const { result } = renderHook(() => useMcpToken());
    const token = await result.current();
    expect(token).toBe("mock-mcp-token");
  });
});
