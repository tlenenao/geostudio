// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useRolesCatalog, useUpdateRole } from "../api/hooks";
import type { Role } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Checkbox } from "../ui/kit/Checkbox";
import { resolveMessageKey, t } from "../i18n";
import type { MessageKey } from "../i18n";

export function EditRolePanel({ role, onClose }: { role: Role; onClose: () => void }) {
  const updateRole = useUpdateRole(role.id);
  const catalogQuery = useRolesCatalog();
  const [name, setName] = useState(role.name);
  const [privileges, setPrivileges] = useState<Set<string>>(new Set(role.privileges));

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
    try {
      await updateRole.mutateAsync({ name, privileges: [...privileges] });
      onClose();
    } catch {
      // surfaced via updateRole.isError
    }
  }

  const byDomain = new Map<string, { privilege: string; labelKey: MessageKey }[]>();
  for (const entry of catalogQuery.data ?? []) {
    const list = byDomain.get(entry.domain) ?? [];
    list.push({
      privilege: entry.privilege,
      labelKey: resolveMessageKey(entry.labelKey, "roles.privilege.unknown"),
    });
    byDomain.set(entry.domain, list);
  }

  return (
    <section
      aria-label={t("roles.editHeading", { name: role.name })}
      className="flex flex-col gap-3"
    >
      <h2 className="text-sm font-semibold text-ink">
        {t("roles.editHeading", { name: role.name })}
      </h2>
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
        {updateRole.isError && (
          <p role="alert" className="text-sm text-danger">
            {t("roles.updateFailed")}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            {t("confirmDialog.cancel")}
          </Button>
          <Button type="submit" size="sm" disabled={!name || updateRole.isPending}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </section>
  );
}
