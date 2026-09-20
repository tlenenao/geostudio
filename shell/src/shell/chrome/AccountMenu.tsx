// SPDX-License-Identifier: Apache-2.0
import { useAuth } from "../../auth/useAuth";
import { useMe } from "../../api/hooks";
import { roleLabel } from "../../auth/roleLabel";
import { Avatar } from "../../ui/kit/Avatar";
import { Popover } from "../../ui/kit/Popover";
import { Badge } from "../../ui/kit/Badge";
import { t } from "../../i18n";

function initials(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

export function AccountMenu() {
  const { username, signOut } = useAuth();
  const meQuery = useMe();
  const label = username ?? "";

  return (
    <Popover
      aria-label={t("account.menu")}
      trigger={
        <button aria-label={t("account.menu")} className="rounded-full">
          <Avatar alt={label} fallback={initials(label)} />
        </button>
      }
    >
      <div className="flex min-w-40 flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium text-ink">{label}</span>
          <Badge>{roleLabel(meQuery.data)}</Badge>
        </div>
        <button className="text-left text-sm text-ink-2 hover:text-ink" onClick={signOut}>
          {t("account.signOut")}
        </button>
      </div>
    </Popover>
  );
}
