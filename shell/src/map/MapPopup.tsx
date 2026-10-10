// SPDX-License-Identifier: Apache-2.0
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { AttachmentSummary } from "../api/types";
import type { PopupContent } from "./popupContent";
import { t } from "../i18n";
import "../i18n/domains/map";

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

  const containerRef = useRef<HTMLDivElement>(null);

  // P31.11 : le popup est ancré au-dessus du point (translate -50%/-100%) ;
  // près d'un bord de la carte il sortait du cadre visible. Après mesure
  // (avant peinture), on le ramène dans le conteneur positionné : clamp en X,
  // et bascule sous le point si le haut manque de place.
  const [placed, setPlaced] = useState<{ left: number; top: number } | null>(null);
  useLayoutEffect(() => {
    const el = containerRef.current;
    const parent = el?.offsetParent as HTMLElement | null;
    if (!el || !parent) return;
    const popup: HTMLElement = el;
    const box: HTMLElement = parent;
    function place() {
      const w = popup.offsetWidth;
      const h = popup.offsetHeight;
      const pw = box.clientWidth;
      const ph = box.clientHeight;
      if (pw === 0 || ph === 0) return; // pas de mise en page mesurable (jsdom, conteneur masqué)
      const left = Math.max(0, Math.min(x - w / 2, pw - w));
      const above = y - h;
      const top = above >= 0 ? above : Math.max(0, Math.min(y, ph - h));
      setPlaced((p) => (p && p.left === left && p.top === top ? p : { left, top }));
    }
    place();
    // REV-286(d) : volet replié, rotation d'écran — le conteneur change de
    // taille sans que x/y bougent ; on recalcule le clamp.
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(place);
    observer.observe(box);
    return () => observer.disconnect();
  }, [x, y, content, attachments]);

  // D41 : composant présentationnel sans Radix (positionné en x/y absolus
  // sur une feature carte, coexiste avec l'interaction carte derrière) —
  // pas de FocusScope automatique. Gère lui-même Échap et le focus initial
  // au montage : premier élément focusable réel (bouton Fermer en
  // pratique, toujours en tête du DOM). Pas de restauration de focus à la
  // fermeture : le déclencheur est un clic sur une feature carte, une
  // cible de restauration ambiguë (hors périmètre D41, cf. spec SP-C1).
  useEffect(() => {
    containerRef.current?.querySelector<HTMLElement>("button, a, [tabindex]")?.focus();
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- volontairement au montage seul (cf. commentaire ci-dessus)
  }, []);

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-label={t("mapPopup.attributesAria")}
      className={`absolute z-20 max-h-64 max-w-xs overflow-auto rounded-md bg-surface p-2 text-xs text-ink shadow-lg pointer-coarse:pr-11 ${placed ? "" : "-translate-x-1/2 -translate-y-full"}`}
      style={
        placed
          ? { left: `${placed.left}px`, top: `${placed.top}px` }
          : { left: `${x}px`, top: `${y}px` }
      }
    >
      <button
        type="button"
        aria-label={t("mapPopup.closeAria")}
        className="absolute right-0 top-0 inline-flex min-h-6 min-w-6 items-center justify-center px-1 text-ink-3 pointer-coarse:min-h-11 pointer-coarse:min-w-11"
        onClick={onClose}
      >
        ✕
      </button>
      {content.title && <p className="mb-1 pr-6 font-medium">{content.title}</p>}
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
