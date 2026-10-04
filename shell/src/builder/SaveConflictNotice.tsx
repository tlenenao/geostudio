// SPDX-License-Identifier: Apache-2.0
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";

// UX de conflit 412 commune à tous les éditeurs de config (extraite du
// builder d'app, commit 5ed004d1) : message accessible + « Recharger ».
export function SaveConflictNotice({
  onReload,
  message,
  reloadLabel,
}: {
  onReload: () => void;
  message?: string;
  reloadLabel?: string;
}) {
  return (
    <div role="alert" className="flex flex-col gap-1 text-sm text-danger">
      <span>{message ?? t("common.saveConflict")}</span>
      <Button size="sm" variant="outline" className="w-fit" onClick={onReload}>
        {reloadLabel ?? t("common.saveConflictReload")}
      </Button>
    </div>
  );
}
