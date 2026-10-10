// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/ApiError";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";

const is401 = (e: unknown) => e instanceof ApiError && e.status === 401;

// t02-008 : un 401 qui survit au renouvellement silencieux (base.ts : un seul
// rejeu) arrive ici comme erreur de requête. On invite à se reconnecter par un
// clic (signIn conserve `returnTo`) — jamais de redirection automatique, donc
// pas de boucle si le 401 persiste après reconnexion. Levée au premier succès.
export function SessionExpiredBanner() {
  const queryClient = useQueryClient();
  const { signIn } = useAuth();
  const [expired, setExpired] = useState(false);
  const failed401 = useRef(new Set<string>());

  useEffect(() => {
    const unsubQ = queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated") return;
      const hash = event.query.queryHash;
      if (event.query.state.status === "error" && is401(event.query.state.error)) {
        failed401.current.add(hash);
        setExpired(true);
      } else if (event.action.type === "success" && !event.action.manual) {
        // Seul le succès d'une requête déjà tombée en 401 (donc authentifiée) lève
        // la bannière : une route publique qui réussit ne prouve rien sur la session.
        if (failed401.current.delete(hash)) setExpired(false);
      }
    });
    const unsubM = queryClient.getMutationCache().subscribe((event) => {
      if (event.type !== "updated") return;
      if (event.mutation.state.status === "error" && is401(event.mutation.state.error))
        setExpired(true);
      else if (event.mutation.state.status === "success") setExpired(false); // mutation = authentifiée
    });
    return () => {
      unsubQ();
      unsubM();
    };
  }, [queryClient]);

  if (!expired) return null;
  return (
    <div
      role="alert"
      className="flex w-full items-center justify-center gap-3 bg-danger-soft px-4 py-2 text-sm text-danger"
    >
      <span>{t("session.expired")}</span>
      <Button size="sm" variant="outline" onClick={signIn}>
        {t("session.signIn")}
      </Button>
    </div>
  );
}
