// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import {
  useCreatePipelineWebhookToken,
  usePipelineWebhookTokens,
  useRevokePipelineWebhookToken,
} from "../../api/domains/pipelines.hooks";
import { t } from "../../i18n";
import { Button } from "../../ui/kit/Button";

// GAP-24, SP-53 : génération/liste/révocation des jetons de déclenchement.
// Le jeton en clair n'existe qu'une fois, dans la réponse de création — ni
// GET /pipelines/{id}/webhook-tokens (liste) ni le cœur en général ne le
// rendent plus jamais ensuite (même discipline que le coffre de secrets).
export function PipelineWebhookTrigger({ pipelineId }: { pipelineId: string }) {
  const tokensQuery = usePipelineWebhookTokens(pipelineId);
  const createToken = useCreatePipelineWebhookToken(pipelineId);
  const revokeToken = useRevokePipelineWebhookToken(pipelineId);
  const [justCreated, setJustCreated] = useState<{ id: string; token: string } | null>(null);

  async function generateToken() {
    const result = await createToken.mutateAsync();
    setJustCreated(result);
  }

  return (
    <div className="flex flex-col gap-2 border-t border-rule pt-2 text-xs">
      <p className="font-medium text-ink-2">{t("pipelineWebhook.heading")}</p>
      {(tokensQuery.data ?? []).map((token) => (
        <div key={token.id} className="flex items-center justify-between">
          <span>
            {token.id.slice(0, 8)}
            {t("pipelineWebhook.createdOnTemplate", { createdAt: token.createdAt })}
          </span>
          <button
            type="button"
            className="text-ink-2 hover:underline"
            aria-label={t("pipelineWebhook.revokeAria", { id: token.id.slice(0, 8) })}
            onClick={() => void revokeToken.mutateAsync(token.id)}
          >
            {t("pipelineWebhook.revokeButton")}
          </button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-fit"
        onClick={() => void generateToken()}
      >
        {t("pipelineWebhook.generateButton")}
      </Button>
      {justCreated && (
        <div
          role="status"
          className="flex flex-col gap-1 rounded border border-rule bg-surface p-2 text-ink"
        >
          <p className="font-mono">{justCreated.token}</p>
          <p className="text-danger">{t("pipelineWebhook.tokenWarning")}</p>
          <p className="font-mono text-ink-2">
            {t("pipelineWebhook.triggerCommandTemplate", {
              id: pipelineId,
              token: justCreated.token,
            })}
          </p>
        </div>
      )}
    </div>
  );
}
