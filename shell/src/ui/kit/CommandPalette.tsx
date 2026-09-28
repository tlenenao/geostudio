// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog } from "./Dialog";
import { Input } from "./Input";
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { DOMAIN_PATHS } from "../../shell/chrome/domainRoutes";
import { SETTINGS_LINKS } from "../../shell/chrome/SettingsNav";
import { useMe } from "../../api/hooks";
import { t } from "../../i18n";

type CommandItem = { id: string; label: string; run: () => void };

// Duplique volontairement la garde grossière de NewItemButton.tsx (privilège
// de création, pas la capacité etlEnabled du pipeline — le clic réel sur le
// bouton du DOM refait la vérification complète et n'ouvre le tiroir que si
// elle passe) : éviter un couplage direct à l'état interne de ce composant,
// hors périmètre de cette tâche.
const CREATE_PRIVILEGES = [
  "apps.manage",
  "maps.manage",
  "data.manage",
  "automation.manage",
] as const;

export function CommandPalette({
  open,
  onOpenChange,
  profile,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profile: Profile;
}) {
  const navigate = useNavigate();
  const meQuery = useMe();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      // jsx-a11y/no-autofocus interdit l'attribut autoFocus (piège pour un
      // utilisateur clavier arrivant sur une page qui en abuse) — ici la
      // palette est un Dialog modal ouvert explicitement par l'utilisateur
      // (Ctrl/Cmd+K ou clic), le focus programmatique est le comportement
      // attendu d'une command palette, pas une surprise.
      inputRef.current?.focus();
    }
  }, [open]);

  const items = useMemo<CommandItem[]>(() => {
    const out: CommandItem[] = [];
    for (const { domain } of navigableDomains(profile)) {
      out.push({
        id: `domain:${domain.id}`,
        label: t(domain.labelKey),
        run: () => navigate(DOMAIN_PATHS[domain.id]),
      });
    }
    const privileges = meQuery.data?.privileges ?? [];
    if (CREATE_PRIVILEGES.some((p) => privileges.includes(p))) {
      out.push({
        id: "action:new-item",
        label: t("commandPalette.newItemAction"),
        run: () => document.getElementById("new-item-trigger")?.click(),
      });
    }
    for (const link of SETTINGS_LINKS) {
      if (link.privilege !== undefined && !privileges.includes(link.privilege)) continue;
      out.push({
        id: `settings:${link.to}`,
        label: t(link.labelKey),
        run: () => navigate(link.to),
      });
    }
    return out;
  }, [profile, meQuery.data, navigate]);

  const filtered = useMemo(
    () => items.filter((i) => i.label.toLowerCase().includes(query.toLowerCase())),
    [items, query],
  );

  function commit(item: CommandItem) {
    item.run();
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t("commandPalette.title")}>
      <Input
        ref={inputRef}
        role="combobox"
        aria-label={t("commandPalette.searchAria")}
        aria-expanded={open}
        autoComplete="off"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActiveIndex(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActiveIndex((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            if (filtered[activeIndex]) commit(filtered[activeIndex]);
          } else if (e.key === "Escape") {
            onOpenChange(false);
          }
        }}
      />
      <ul role="listbox" className="mt-2 flex max-h-80 flex-col gap-0.5 overflow-y-auto">
        {filtered.map((item, index) => (
          <li key={item.id}>
            <button
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              onClick={() => commit(item)}
              className={
                index === activeIndex
                  ? "w-full rounded-md bg-sunken px-2 py-1.5 text-left text-sm text-ink"
                  : "w-full rounded-md px-2 py-1.5 text-left text-sm text-ink hover:bg-sunken"
              }
            >
              {item.label}
            </button>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}
