// SPDX-License-Identifier: Apache-2.0
import { t } from "../../i18n";

// P10.09 : un widget dont `dataSourceId` ne référence aucune source existante
// (source retirée) n'est pas « en chargement » — état explicite.
export function SourceMissing() {
  return (
    <p role="status" className="text-xs text-danger">
      {t("common.sourceMissing")}
    </p>
  );
}
