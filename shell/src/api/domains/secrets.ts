// SPDX-License-Identifier: Apache-2.0
import type { ItemClient, SecretPayload, SecretSummary } from "../types";
import type { ItemClientBase } from "../base";

export type { SecretPayload, SecretSummary };

type SecretsMethods = Pick<
  ItemClient,
  "listSecrets" | "createSecret" | "updateSecret" | "deleteSecret"
>;

export function createSecretsMethods(base: ItemClientBase): SecretsMethods {
  const { request } = base;
  return {
    listSecrets: () => request<SecretSummary[]>("GET", "/secrets"),
    createSecret: (input: { name: string; payload: SecretPayload }) =>
      request<SecretSummary>("POST", "/secrets", input),
    updateSecret: (id: string, payload: SecretPayload) =>
      request<SecretSummary>("PUT", `/secrets/${id}`, { payload }),
    deleteSecret: (id: string) => request<void>("DELETE", `/secrets/${id}`),
  };
}
