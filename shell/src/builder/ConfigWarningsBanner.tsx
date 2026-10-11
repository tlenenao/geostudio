// SPDX-License-Identifier: Apache-2.0
// REV-305 : le cœur relit en 200 une config devenue invalide, avec la liste
// des problèmes dans `warnings` (texte libre : pas d'id de widget structuré,
// donc pas de lien vers le widget fautif).
import { Banner } from "../ui/kit/Banner";
import { t } from "../i18n";
import "../i18n/domains/widgets";

export function ConfigWarningsBanner({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div role="status" className="p-2">
      <Banner variant="warn">
        <p className="font-medium">{t("configWarnings.title")}</p>
        <ul className="list-disc pl-5">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      </Banner>
    </div>
  );
}
