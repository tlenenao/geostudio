// SPDX-License-Identifier: Apache-2.0
import { useId, type ReactNode } from "react";

/**
 * Le traitement « verrouillé et expliqué » de la doctrine (spec §6.2) : le
 * contrôle reste visible, il est inopérant, et **la raison est écrite**. Jamais
 * un cadenas muet — l'utilisateur doit savoir quoi faire pour l'obtenir.
 *
 * Le `fieldset` désactivé rend inopérant tout ce qu'il contient, sans que
 * l'appelant ait à cloner ses enfants pour leur injecter `disabled`.
 */
export function Locked({ reason, children }: { reason: string; children: ReactNode }): ReactNode {
  const reasonId = useId();
  return (
    <fieldset disabled role="group" aria-describedby={reasonId} className="contents">
      {children}
      <span id={reasonId} className="block px-3 py-1 text-xs text-slate-500">
        {reason}
      </span>
    </fieldset>
  );
}
