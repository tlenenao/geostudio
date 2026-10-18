// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import {
  useCreateGroupClaimMapping,
  useDeleteGroupClaimMapping,
  useGroupClaimMappings,
  useGroups,
} from "../api/hooks";
import { Banner } from "../ui/kit/Banner";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { t } from "../i18n";
import "../i18n/domains/admin";
import { NativeSelect } from "../ui/kit/NativeSelect";

/** ARC-24 (ADR 0022) : mapping administré claim IdP -> groupe du cœur. */
export function GroupClaimMappingsSection() {
  const mappings = useGroupClaimMappings();
  const groups = useGroups();
  const create = useCreateGroupClaimMapping();
  const remove = useDeleteGroupClaimMapping();
  const [claimValue, setClaimValue] = useState("");
  const [groupId, setGroupId] = useState("");
  const [error, setError] = useState(false);

  const groupName = (id: string) => groups.data?.find((g) => g.id === id)?.title ?? id;

  async function add() {
    setError(false);
    try {
      await create.mutateAsync({ groupId, claimValue: claimValue.trim() });
      setClaimValue("");
    } catch {
      setError(true);
    }
  }

  return (
    <section aria-labelledby="claim-map-title" className="flex flex-col gap-2">
      <h2 id="claim-map-title" className="text-base font-semibold text-ink">
        {t("claimMap.title")}
      </h2>
      <p className="text-sm text-ink-2">{t("claimMap.help")}</p>
      {mappings.isError && (
        <Banner variant="danger" onRetry={() => void mappings.refetch()}>
          {t("claimMap.loadError")}
        </Banner>
      )}
      {mappings.data?.length === 0 && <p className="text-sm text-ink-2">{t("claimMap.empty")}</p>}
      <ul className="flex flex-col gap-1">
        {mappings.data?.map((m) => (
          <li key={m.id} className="flex items-center gap-2 text-sm text-ink">
            <code>{m.claimValue}</code>
            <span aria-hidden="true">→</span>
            <span>{groupName(m.groupId)}</span>
            <Button
              size="sm"
              variant="outline"
              aria-label={t("claimMap.remove", {
                claim: m.claimValue,
                group: groupName(m.groupId),
              })}
              onClick={() => remove.mutate(m.id)}
            >
              ×
            </Button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("claimMap.claimLabel")}
          <Input value={claimValue} onChange={(e) => setClaimValue(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("claimMap.groupLabel")}
          <NativeSelect
            className="h-9 rounded-md border border-control bg-surface px-2 text-sm text-ink w-auto"
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
          >
            <option value="">{t("claimMap.pickGroup")}</option>
            {groups.data?.map((g) => (
              <option key={g.id} value={g.id}>
                {g.title}
              </option>
            ))}
          </NativeSelect>
        </label>
        <Button
          size="sm"
          disabled={!claimValue.trim() || !groupId || create.isPending}
          onClick={() => void add()}
        >
          {t("claimMap.add")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {t("claimMap.saveError")}
        </p>
      )}
    </section>
  );
}
