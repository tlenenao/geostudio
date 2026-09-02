// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateRole, useRolesCatalog } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Checkbox } from "../ui/kit/Checkbox";
import { t } from "../i18n";
import type { MessageKey } from "../i18n";

export function CreateRolePanel({ onClose }: { onClose: () => void }) {
  const createRole = useCreateRole();
  const catalogQuery = useRolesCatalog();
  const [name, setName] = useState("");
  const [privileges, setPrivileges] = useState<Set<string>>(new Set());

  function toggle(privilege: string) {
    setPrivileges((prev) => {
      const next = new Set(prev);
      if (next.has(privilege)) next.delete(privilege);
      else next.add(privilege);
      return next;
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name) return;
    try {
      await createRole.mutateAsync({ name, privileges: [...privileges] });
      onClose();
    } catch {
      // surfaced via createRole.isError
    }
  }

  const byDomain = new Map<string, { privilege: string; labelKey: MessageKey }[]>();
  for (const entry of catalogQuery.data ?? []) {
    const list = byDomain.get(entry.domain) ?? [];
    list.push({ privilege: entry.privilege, labelKey: entry.labelKey as MessageKey });
    byDomain.set(entry.domain, list);
  }

  return (
    <section aria-label={t("roles.addRole")} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">{t("roles.addRole")}</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          {t("roles.nameLabel")}
          <Input
            aria-label={t("roles.nameLabel")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm text-ink">{t("roles.privilegesLabel")}</legend>
          {[...byDomain.entries()].map(([domain, entries]) => (
            <div key={domain} className="flex flex-col gap-1">
              {entries.map(({ privilege, labelKey }) => (
                <label key={privilege} className="flex items-center gap-2 text-sm text-ink-2">
                  <Checkbox
                    checked={privileges.has(privilege)}
                    onCheckedChange={() => toggle(privilege)}
                    aria-label={t(labelKey)}
                  />
                  {t(labelKey)}
                </label>
              ))}
            </div>
          ))}
        </fieldset>
        {createRole.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la création.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={!name || createRole.isPending}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
