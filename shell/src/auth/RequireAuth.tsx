// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { t } from "../i18n";
import { useAuth } from "./useAuth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, error, signIn } = useAuth();
  const [searchParams] = useSearchParams();
  // P07.01 : un signinSilent() (jeton MCP, renouvellement) repasse
  // isLoading à true (et peut poser `error`) alors que la session est
  // vivante ; démonter les enfants perdrait le brouillon et la pile d'undo.
  const wasAuthenticated = useRef(false);
  if (isAuthenticated) wasAuthenticated.current = true;
  // The Playwright export worker (Task 6, core/app/export/jobs.py) navigates
  // straight to a protected route carrying ?exportToken=... instead of a
  // real Keycloak session — redirecting it to signIn() would break every
  // export. The actual security boundary lives entirely on the core side
  // (Task 4's decode_export_token / tenant / user checks); this is purely
  // "don't redirect away" and grants no elevated trust here.
  const hasExportToken = searchParams.get("exportToken") !== null;

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !error && !hasExportToken) {
      signIn();
    }
  }, [isLoading, isAuthenticated, error, hasExportToken, signIn]);

  if (hasExportToken) {
    return <>{children}</>;
  }

  if (wasAuthenticated.current && isAuthenticated) {
    return <>{children}</>;
  }

  if (isLoading) {
    return (
      <div role="status" className="p-8 text-sm text-muted-foreground">
        Connexion…
      </div>
    );
  }
  if (error) {
    return (
      <div role="alert" className="p-8 text-sm text-danger">
        Échec de la connexion : {error}{" "}
        <button className="underline" onClick={signIn}>
          {t("common.retry")}
        </button>
      </div>
    );
  }
  if (!isAuthenticated) {
    return null;
  }
  return <>{children}</>;
}
