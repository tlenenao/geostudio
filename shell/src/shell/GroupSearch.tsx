// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useGroups } from "../api/hooks";
import type { Group } from "../api/types";
import { t } from "../i18n";
import { Input } from "../ui/kit/Input";
import "../i18n/domains/admin";

/** REV-277 : `GET /groups` ne renvoie que les groupes de l'appelant ; `?q=` (2 à 100
 *  caractères côté cœur) atteint les autres. Sous 2 caractères on garde la liste par défaut.
 *  Hors recherche on affiche la liste par défaut, pendant une recherche ses résultats. */
export function useGroupSearch(shared?: { groupId: string; name?: string | null }[]) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);
  const defaults = useGroups();
  const searching = debounced.length >= 2;
  const searched = useGroups({ q: debounced, enabled: searching });
  return {
    search,
    setSearch,
    defaults,
    searching,
    searched,
    groups: withSharedGroups((searching ? searched.data : defaults.data) ?? [], shared, searching),
  };
}

/** REV-277 : les groupes déjà ciblés par un partage restent lisibles (nom fourni par le cœur
 *  en lecture seule) même hors de l'annuaire borné ; ils ne s'ajoutent pas pendant une recherche. */
function withSharedGroups(
  groups: Group[],
  shared: { groupId: string; name?: string | null }[] | undefined,
  searching: boolean,
): Group[] {
  if (searching || !shared) return groups;
  const known = new Set(groups.map((g) => g.id));
  const extra = shared
    .filter((g) => !known.has(g.groupId))
    .map((g) => ({ id: g.groupId, title: g.name ?? g.groupId }));
  return extra.length ? [...groups, ...extra] : groups;
}

type GroupSearchState = Pick<
  ReturnType<typeof useGroupSearch>,
  "search" | "setSearch" | "searching" | "searched"
>;

/** Champ de recherche + états chargement/vide/erreur de la recherche. */
export function GroupSearchField({ state }: { state: GroupSearchState }) {
  const { search, setSearch, searching, searched } = state;
  return (
    <div className="flex flex-col gap-1">
      <Input
        type="search"
        aria-label={t("groupSearch.aria")}
        placeholder={t("groupSearch.placeholder")}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {searching && searched.isLoading && (
        <p className="text-xs text-ink-2">{t("groupSearch.loading")}</p>
      )}
      {searching && searched.isError && (
        <p role="alert" className="text-xs text-danger">
          {t("groupSearch.error")}
        </p>
      )}
      {searching && searched.isSuccess && searched.data.length === 0 && (
        <p className="text-xs text-ink-2">{t("groupSearch.empty")}</p>
      )}
    </div>
  );
}
