// SPDX-License-Identifier: Apache-2.0
import { useMe } from "../../api/hooks";

export function StatusBar() {
  const meQuery = useMe();
  if (!meQuery.data) return <div className="h-[21px] border-t border-rule" />;
  return (
    <div className="flex h-[21px] items-center gap-3 border-t border-rule px-2 font-mono text-[9px] text-ink-3">
      <span>
        v{meQuery.data.version} · {meQuery.data.tenantSlug}
      </span>
    </div>
  );
}
