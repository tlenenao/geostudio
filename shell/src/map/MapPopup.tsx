// SPDX-License-Identifier: Apache-2.0
import type { PopupContent } from "./popupContent";

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
}: {
  content: PopupContent;
  x: number;
  y: number;
  onClose: () => void;
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
      aria-label="Attributs de l'entité"
      className="absolute z-20 max-h-64 max-w-xs -translate-x-1/2 -translate-y-full overflow-auto rounded-md bg-surface p-2 text-xs text-ink shadow-lg"
      style={{ left: `${x}px`, top: `${y}px` }}
    >
      <button
        type="button"
        aria-label="Fermer"
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
      {empty && <p className="text-ink-3">Aucun attribut</p>}
    </div>
  );
}
