// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useGroups } from "../api/hooks";
import { t } from "../i18n";
import { Input } from "../ui/kit/Input";
import "../i18n/domains/admin";

/** REV-277 : `GET /groups` ne renvoie que les groupes de l'appelant ; `?q=` (2 à 100
 *  caractères côté cœur) atteint les autres. Sous 2 caractères on garde la liste par défaut.
 *  Hors recherche on affiche la liste par défaut, pendant une recherche ses résultats. */
export function useGroupSearch() {
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
    groups: (searching ? searched.data : defaults.data) ?? [],
  };
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
