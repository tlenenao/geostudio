// SPDX-License-Identifier: Apache-2.0
// ARC-10 : file de modération des soumissions publiques + gestion des jetons d'une collection.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { LoadingState } from "../ui/kit/LoadingState";
import { t } from "../i18n";
import "../i18n/domains/admin";

export function SubmissionsPanel({
  collectionId,
  onClose,
}: {
  collectionId: string;
  onClose: () => void;
}) {
  const client = useItemClient();
  const qc = useQueryClient();
  const subKey = ["submissions", collectionId];
  const tokKey = ["submission-tokens", collectionId];
  const [name, setName] = useState("");
  const [days, setDays] = useState(30);
  const [max, setMax] = useState(100);
  const [fresh, setFresh] = useState<string | null>(null);

  const submissions = useQuery({
    queryKey: subKey,
    queryFn: () => client.listSubmissions!(collectionId),
    enabled: client.listSubmissions !== undefined,
  });
  const tokens = useQuery({
    queryKey: tokKey,
    queryFn: () => client.listSubmissionTokens!(collectionId),
    enabled: client.listSubmissionTokens !== undefined,
  });
  const approve = useMutation({
    mutationFn: (id: string) => client.approveSubmission!(collectionId, id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: subKey }),
  });
  const reject = useMutation({
    mutationFn: (id: string) => client.rejectSubmission!(collectionId, id, ""),
    onSuccess: () => void qc.invalidateQueries({ queryKey: subKey }),
  });
  const create = useMutation({
    mutationFn: () =>
      client.createSubmissionToken!(collectionId, {
        name,
        expiresInDays: days,
        maxSubmissions: max,
      }),
    onSuccess: (r) => {
      setFresh(r.token);
      setName("");
      void qc.invalidateQueries({ queryKey: tokKey });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => client.revokeSubmissionToken!(collectionId, id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: tokKey }),
  });

  return (
    <section aria-label={t("submissions.title")} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">{t("submissions.title")}</h2>
      <h3 className="text-xs font-semibold text-ink">{t("submissions.queue")}</h3>
      {submissions.isLoading && <LoadingState />}
      {submissions.isError && <p className="text-danger">{t("submissions.error")}</p>}
      {submissions.data?.length === 0 && <p className="text-ink-3">{t("submissions.empty")}</p>}
      <ul className="flex flex-col gap-2">
        {submissions.data?.map((s) => (
          <li key={s.id} className="flex flex-col gap-1 rounded border border-rule p-2 text-xs">
            <span>
              {Object.entries(s.properties)
                .map(([k, v]) => `${k} : ${String(v)}`)
                .join(" · ")}
            </span>
            {s.attachment && (
              <span className="text-ink-3">
                {t("submissions.attachment", { name: s.attachment.filename })}
              </span>
            )}
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                disabled={approve.isPending}
                aria-label={t("submissions.approveFor", { id: s.id })}
                onClick={() => approve.mutate(s.id)}
              >
                {t("submissions.approve")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={reject.isPending}
                aria-label={t("submissions.rejectFor", { id: s.id })}
                onClick={() => reject.mutate(s.id)}
              >
                {t("submissions.reject")}
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {(approve.isError || reject.isError) && (
        <p role="alert" className="text-danger">
          {t("submissions.moderationError")}
        </p>
      )}

      <h3 className="text-xs font-semibold text-ink">{t("submissions.tokens")}</h3>
      <ul className="flex flex-col gap-1 text-xs">
        {tokens.data?.map((k) => (
          <li key={k.id} className="flex items-center gap-2">
            <span>
              {k.name} · {k.prefix}… · {k.submissionCount}/{k.maxSubmissions}
              {k.revokedAt ? ` · ${t("submissions.revoked")}` : ""}
            </span>
            {!k.revokedAt && (
              <Button type="button" size="sm" variant="outline" onClick={() => revoke.mutate(k.id)}>
                {t("submissions.revoke")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      <form
        className="flex flex-wrap items-end gap-2 text-xs"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <label className="flex flex-col">
          {t("submissions.tokenName")}
          <input
            required
            className="h-9 rounded border border-control bg-surface px-2 text-ink"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="flex flex-col">
          {t("submissions.tokenDays")}
          <input
            type="number"
            min={1}
            max={365}
            className="h-9 w-24 rounded border border-control bg-surface px-2 text-ink"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          />
        </label>
        <label className="flex flex-col">
          {t("submissions.tokenMax")}
          <input
            type="number"
            min={1}
            className="h-9 w-24 rounded border border-control bg-surface px-2 text-ink"
            value={max}
            onChange={(e) => setMax(Number(e.target.value))}
          />
        </label>
        <Button type="submit" size="sm" disabled={create.isPending}>
          {t("submissions.createToken")}
        </Button>
      </form>
      {fresh && (
        <p role="status" className="break-all rounded bg-surface p-2 text-xs">
          {t("submissions.tokenOnce")} <code>{fresh}</code>
          <br />
          {t("submissions.publicLink")} <code>{`${window.location.origin}/collect/${fresh}`}</code>
        </p>
      )}
      <Button type="button" variant="outline" size="sm" className="self-start" onClick={onClose}>
        {t("submissions.close")}
      </Button>
    </section>
  );
}
