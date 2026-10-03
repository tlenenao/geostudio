// SPDX-License-Identifier: Apache-2.0
// j11-006 : le copilote existe mais n'est pas configuré — le dire plutôt
// que de laisser la fonction invisible.
import { t } from "../../i18n";

export function CopilotUnavailable() {
  return (
    <p role="status" className="text-xs text-ink-2">
      {t("copilot.unavailable")}
    </p>
  );
}
