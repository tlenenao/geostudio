// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { registerServiceWorker } from "../offline/registerSw";
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";
import "../i18n/domains/misc";

// L8 : nouvelle version du shell prête (service worker en attente) : proposée, jamais imposée.
export function UpdateBanner() {
  const [apply, setApply] = useState<(() => void) | null>(null);
  useEffect(() => {
    registerServiceWorker((fn) => setApply(() => fn));
  }, []);
  if (!apply) return null;
  return (
    <div
      role="status"
      className="flex w-full flex-wrap items-center justify-center gap-3 bg-sunken px-4 py-2 text-sm text-ink"
    >
      <span>{t("sw.updateReady")}</span>
      <Button type="button" size="sm" variant="outline" onClick={apply}>
        {t("sw.updateAction")}
      </Button>
    </div>
  );
}
