// SPDX-License-Identifier: Apache-2.0
import { useCollectionsAdmin } from "../../api/hooks";

// Filtre d'affichage seulement (variant="writable" ne montre que les
// collections avec canWrite) — jamais une frontière de sécurité : la vraie
// vérification lisible/éditable a lieu côté serveur à la sauvegarde
// (app/pipelines/config_validation.py, SP-15a) et à nouveau à l'exécution.
// Réutilise useCollectionsAdmin() tel quel : GET /collections est déjà
// scopé à ce que l'utilisateur courant peut voir (design SP-15b §4.4).
export function CollectionParamSelect({
  value,
  onChange,
  variant,
  ariaLabel,
}: {
  value: string;
  onChange: (collectionId: string) => void;
  variant: "readable" | "writable";
  ariaLabel: string;
}) {
  const collectionsQuery = useCollectionsAdmin();
  const options = (collectionsQuery.data ?? []).filter((c) => variant === "readable" || c.canWrite);

  return (
    <select
      aria-label={ariaLabel}
      className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">Choisir…</option>
      {options.map((c) => (
        <option key={c.id} value={c.id}>
          {c.title}
        </option>
      ))}
    </select>
  );
}
