// SPDX-License-Identifier: Apache-2.0
import type { RawClientOp } from "./applyClientOp";

/**
 * Insère un brouillon SQL dans l'éditeur. Retourne `true` si quelque chose a
 * réellement été inséré (M1 : CopilotChat n'annonce « Brouillon SQL
 * inséré. » que dans ce cas — un SQL vide ou blanc est un no-op silencieux
 * depuis l'origine, comportement correct, conservé tel quel).
 *
 * Limitation assumée (I4, revue finale de branche GAP-17) : `setSql` écrase
 * le texte en cours sans passer par une pile d'annulation — SqlLabPage tient
 * son SQL en `useState` nu, sans équivalent du `setDraft`/`useUndoableDraft`
 * (SP-19) du builder d'App. Y brancher un undo est une fonctionnalité à part
 * entière (il faudrait aussi une commande Annuler dans l'écran), hors du
 * périmètre de cette passe. Atténuation existante : le SQL remplacé reste
 * récupérable via l'historique de SQL Lab dès qu'il a été exécuté une fois.
 */
export function applySqlLabClientOp(raw: RawClientOp, setSql: (sql: string) => void): boolean {
  if (raw.op !== "applySqlDraft") return false;
  const sql = String(raw.args.sql ?? "").trim();
  if (!sql) return false;
  setSql(sql);
  return true;
}
