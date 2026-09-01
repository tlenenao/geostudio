// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";

// Champ centile en état local, partagé par les deux surfaces qui laissent
// saisir `p` : l'assistant de requête visuelle (QuerySummaryBuilder) et le
// panneau de sources analytiques (DataSourcePanel). `p` porte l'invariant
// `0 < p < 100` et une case vide ou hors bornes ne doit jamais l'atteindre
// (Number("") === 0, pas null — et une requête `{agg: "percentile"}` sans `p`
// est refusée en 422 par le cœur, ce qui rend une config enregistrable mais
// cassée pour tous ses lecteurs). On tient donc un brouillon texte séparé de
// la valeur validée : chaque frappe met à jour l'affichage, mais seule une
// valeur qui respecte l'invariant remonte via onCommit. Une frappe invalide
// (vide, hors bornes, non numérique) reste visible dans le champ sans jamais
// atteindre l'état — et surtout sans jamais réinitialiser le champ à la volée,
// qui empêcherait l'auteur de vider puis retaper une valeur (piège déjà
// rencontré ailleurs dans ce dépôt sur des champs contrôlés). Au blur, le
// brouillon retombe sur la dernière valeur validée, pour donner un signal
// visuel qu'une saisie laissée invalide n'a pas été retenue.
export function PercentileInput({
  label,
  value,
  onCommit,
  className = "h-8 w-20 rounded border border-rule bg-surface px-2 text-xs text-ink",
  placeholder,
}: {
  label: string;
  value: number;
  onCommit: (p: number) => void;
  className?: string;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  function handleChange(text: string) {
    setDraft(text);
    const n = Number(text);
    if (text.trim() !== "" && Number.isFinite(n) && n > 0 && n < 100) {
      onCommit(n);
    }
  }

  return (
    <input
      aria-label={label}
      type="number"
      min={1}
      max={99}
      placeholder={placeholder}
      className={className}
      value={draft}
      onChange={(e) => handleChange(e.target.value)}
      onBlur={() => setDraft(String(value))}
    />
  );
}
