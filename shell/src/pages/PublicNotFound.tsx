// SPDX-License-Identifier: Apache-2.0
import { t } from "../i18n";
import "../i18n/domains/misc";

/** Page introuvable des surfaces publiques : `<main>` + `<h1>` (repère de
 * navigation pour les lecteurs d'écran, REV-284) autour de l'alerte. */
export function PublicNotFound({ message = t("publicPage.notFound") }: { message?: string }) {
  return (
    <main className="p-8 text-center">
      <h1 className="sr-only">{t("publicPage.notFoundHeading")}</h1>
      <p role="alert" className="text-sm text-ink-2">
        {message}
      </p>
    </main>
  );
}
