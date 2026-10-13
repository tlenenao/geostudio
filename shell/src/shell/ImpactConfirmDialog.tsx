// SPDX-License-Identifier: Apache-2.0
import { useImpact } from "../api/hooks";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import type { ImpactTarget, ResourceType } from "../api/types";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { plural, t } from "../i18n";
import "../i18n/domains/misc";

/**
 * Dialogue de suppression avec vue d'impact (ARC4-F15) : liste les dépendants que
 * l'utilisateur peut voir et compte, sans les nommer, ceux qu'il ne peut pas lire.
 * La confirmation reste possible si la vue d'impact est indisponible (avertissement).
 */
export function ImpactConfirmDialog({
  target,
  title,
  message,
  confirmLabel,
  pending,
  onConfirm,
  onCancel,
  returnFocusRef,
}: {
  /** null = dialogue fermé. */
  target: ImpactTarget | null;
  title: string;
  message: string;
  confirmLabel: string;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}) {
  const impact = useImpact(target);
  const data = impact.data;

  return (
    <ConfirmDialog
      open={target !== null}
      title={title}
      message={message}
      confirmLabel={confirmLabel}
      pending={pending || impact.isLoading}
      onConfirm={onConfirm}
      onCancel={onCancel}
      returnFocusRef={returnFocusRef}
    >
      <div className="mb-4 text-sm" data-testid="impact-summary">
        {impact.isLoading && <p className="text-ink-muted">{t("impact.loading")}</p>}
        {impact.isError && (
          <p role="alert" className="text-danger">
            {t("impact.failed")}
          </p>
        )}
        {data && data.dependents.length === 0 && data.hiddenCount === 0 && (
          <p className="text-ink-muted">{t("impact.none")}</p>
        )}
        {data && data.dependents.length > 0 && (
          <>
            <p className="font-medium">
              {t(plural(data.dependents.length, "impact.headingOne", "impact.headingMany"), {
                n: data.dependents.length,
              })}
            </p>
            <ul className="mt-1 list-disc pl-5">
              {data.dependents.map((d) => (
                <li key={`${d.type}:${d.id}`}>
                  {d.title}{" "}
                  <span className="text-ink-muted">
                    ({RESOURCE_TYPE_LABELS[d.resourceType as ResourceType] ?? d.resourceType}
                    {d.direct ? "" : `, ${t("impact.indirect")}`})
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
        {data && data.hiddenCount > 0 && (
          <p className="mt-1 text-ink-muted">
            {t(plural(data.hiddenCount, "impact.hiddenOne", "impact.hiddenMany"), {
              n: data.hiddenCount,
            })}
          </p>
        )}
      </div>
    </ConfirmDialog>
  );
}
