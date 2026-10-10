// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
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

  useEffect(() => {
    const unsubQ = queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated") return;
      if (event.query.state.status === "error" && is401(event.query.state.error)) setExpired(true);
      else if (event.action.type === "success" && !event.action.manual) setExpired(false);
    });
    const unsubM = queryClient.getMutationCache().subscribe((event) => {
      if (event.type !== "updated") return;
      if (event.mutation.state.status === "error" && is401(event.mutation.state.error))
        setExpired(true);
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
