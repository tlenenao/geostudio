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
  children,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  pending?: boolean;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  /** Contenu complémentaire entre le message et les boutons (ex. vue d'impact). */
  children?: React.ReactNode;
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
      {children}
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
