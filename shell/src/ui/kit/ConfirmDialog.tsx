// SPDX-License-Identifier: Apache-2.0
import { Button } from "./Button";
import { Dialog } from "./Dialog";
import { t } from "../../i18n";
import "../../i18n/domains/misc";

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  pending,
  returnFocusRef,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  pending?: boolean;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && onCancel()}
      title={title}
      description={message}
      alert
      returnFocusRef={returnFocusRef}
    >
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          {t("confirmDialog.cancel")}
        </Button>
        <Button type="button" variant="danger" size="sm" disabled={pending} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
