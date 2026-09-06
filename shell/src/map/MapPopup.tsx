// SPDX-License-Identifier: Apache-2.0
import type { AttachmentSummary } from "../api/types";
import type { PopupContent } from "./popupContent";
import { t } from "../i18n";

// Composant purement présentationnel : il ne connaît ni MapLibre ni la
// configuration, seulement un contenu déjà résolu et une position déjà
// projetée. C'est ce qui le rend testable sans carte.
//
// dangerouslySetInnerHTML est ici le second usage légitime du dépôt : `html`
// sort TOUJOURS de renderPopupTemplate, donc de sanitizeMarkdown() (DOMPurify).
// Ce fichier est pour cette raison dans le bloc d'exception d'eslint.config.js.
export function MapPopup({
  content,
  x,
  y,
  onClose,
  attachments,
  onDownloadAttachment,
}: {
  content: PopupContent;
  x: number;
  y: number;
  onClose: () => void;
  // Pièces jointes de l'entité cliquée (chantier 4.12) : `MapView` les
  // résout lui-même (fetch nu, cf. son commentaire dédié) et les passe déjà
  // prêtes — ce composant reste purement présentationnel, sans connaître ni
  // ItemClient ni la notion de collection/fid.
  attachments?: AttachmentSummary[];
  onDownloadAttachment?: (attachmentId: string, filename: string) => void;
}) {
  // Un gabarit qui s'interpole en chaîne vide (`marked.parse("")` → `""`)
  // est traité comme « pas de html » : la chaîne vide n'a rien à afficher,
  // donc le même message « Aucun attribut » qu'une entité sans propriété
  // plutôt qu'une bulle avec un `<div>` vide. Un seul prédicat de vérité
  // pilote à la fois le choix de branche de rendu et le calcul de `empty`,
  // pour qu'ils ne puissent plus diverger sur ce cas.
  const hasHtml = Boolean(content.html);
  const empty = !hasHtml && content.rows.length === 0 && !content.title;
  return (
    <div
      role="dialog"
      aria-label={t("mapPopup.attributesAria")}
      className="absolute z-20 max-h-64 max-w-xs -translate-x-1/2 -translate-y-full overflow-auto rounded-md bg-surface p-2 text-xs text-ink shadow-lg"
      style={{ left: `${x}px`, top: `${y}px` }}
    >
      <button
        type="button"
        aria-label={t("mapPopup.closeAria")}
        className="absolute right-1 top-1 px-1 text-ink-3"
        onClick={onClose}
      >
        ✕
      </button>
      {content.title && <p className="mb-1 pr-4 font-medium">{content.title}</p>}
      {content.html ? (
        <div dangerouslySetInnerHTML={{ __html: content.html }} />
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-2">
          {content.rows.map((r) => (
            <div key={r.label} className="col-span-2 grid grid-cols-subgrid">
              <dt className="text-ink-3">{r.label}</dt>
              <dd className="break-words">{r.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {empty && <p className="text-ink-3">{t("mapPopup.emptyText")}</p>}
      {attachments && attachments.length > 0 && onDownloadAttachment && (
        <div className="mt-1 border-t border-rule pt-1">
          <p className="mb-1 text-ink-3">{t("mapPopup.attachmentsLabel")}</p>
          <ul className="flex flex-col gap-0.5">
            {attachments.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => onDownloadAttachment(a.id, a.filename)}
                  className="bg-transparent p-0 underline"
                >
                  {a.filename}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
