// SPDX-License-Identifier: Apache-2.0
import { ApiError } from "../../api/ApiError";
import { t } from "../../i18n";
import { Banner } from "./Banner";

type FailableQuery = { isError: boolean; error: unknown; refetch: () => unknown };

// P22.10 : état d'erreur de lecture unique (Banner danger). P22.09 : distingue
// 404/403 (« introuvable » / « accès refusé », sans Réessayer) d'une vraie
// panne de chargement (message + « Réessayer » qui relance les requêtes en
// échec). Sans requête en erreur (donnée absente), c'est un « introuvable ».
export function QueryErrorState({
  queries,
  notFoundMessage,
  loadErrorMessage,
}: {
  queries: FailableQuery[];
  notFoundMessage: string;
  loadErrorMessage?: string;
}) {
  const failed = queries.filter((q) => q.isError);
  const status = failed
    .map((q) => (q.error instanceof ApiError ? q.error.status : undefined))
    .find((s) => s === 404 || s === 403);
  if (failed.length === 0 || status === 404)
    return <Banner variant="danger">{notFoundMessage}</Banner>;
  if (status === 403) return <Banner variant="danger">{t("common.accessDenied")}</Banner>;
  return (
    <Banner variant="danger" onRetry={() => failed.forEach((q) => void q.refetch())}>
      {loadErrorMessage ?? t("common.loadError")}
    </Banner>
  );
}
