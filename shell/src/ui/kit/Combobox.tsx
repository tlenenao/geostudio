// SPDX-License-Identifier: Apache-2.0
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { useEffect, useId, useMemo, useState } from "react";
import { cn } from "../../lib/utils";
import { t } from "../../i18n";
import { Input } from "./Input";

export function Combobox({
  value,
  onValueChange,
  options,
  "aria-label": ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  "aria-label": string;
}) {
  // id stable et unique par instance : deux Combobox sur le même écran ne
  // doivent pas partager un même id de listbox (aria-controls cassé, DOM
  // invalide) — le brief avait un id littéral "combobox-listbox".
  const listboxId = useId();
  const selectedLabel = options.find((o) => o.value === value)?.label ?? "";
  const [query, setQuery] = useState(selectedLabel);
  const [open, setOpen] = useState(false);
  // -1 = aucune option surlignée : la première flèche bas doit atterrir sur
  // l'option 0, pas la sauter (cf. Combobox.test.tsx — le brief initialisait
  // à 0, ce qui fait sélectionner "Beta" au lieu de "Alpha" au premier
  // ArrowDown, contredisant son propre test).
  const [activeIndex, setActiveIndex] = useState(-1);

  // Composant contrôlé : si le parent change `value` après le montage (reset
  // de formulaire, action externe), le champ affiché doit suivre — sinon le
  // texte visible ment sur la valeur réelle. `useState(selectedLabel)` seul
  // ne capture que la valeur au montage.
  useEffect(() => {
    setQuery(selectedLabel);
  }, [selectedLabel]);

  const filtered = useMemo(
    () => options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase())),
    [options, query],
  );

  const commit = (option: { value: string; label: string }) => {
    onValueChange(option.value);
    setQuery(option.label);
    setOpen(false);
  };

  // Id stable par option (préfixé par le même `listboxId` unique par
  // instance, cf. commentaire ci-dessus) — référencé par
  // `aria-activedescendant` sur l'input ci-dessous : le focus DOM réel reste
  // sur l'input (roving focus virtuel), les options ne rejoignent jamais
  // l'ordre de tabulation (`tabIndex={-1}` plus bas), mais un lecteur
  // d'écran doit pouvoir annoncer laquelle est actuellement surlignée par
  // les flèches — jusqu'ici seul `aria-selected`/le surlignage visuel le
  // portait, invisible en dehors d'un rendu visuel.
  const optionId = (index: number) => `${listboxId}-option-${index}`;

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Anchor asChild>
        <Input
          role="combobox"
          aria-label={ariaLabel}
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={
            open && activeIndex >= 0 && filtered[activeIndex] ? optionId(activeIndex) : undefined
          }
          autoComplete="off"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIndex(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActiveIndex((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              if (open && filtered[activeIndex]) commit(filtered[activeIndex]);
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
        />
      </PopoverPrimitive.Anchor>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          id={listboxId}
          role="listbox"
          onOpenAutoFocus={(e) => e.preventDefault()}
          // avoidCollisions=false : cf. Combobox.test.tsx pour la mesure — le
          // recalcul de collision de @floating-ui/react-dom (shift+flip)
          // entre dans une boucle de reset qui consomme ~13s de CPU par
          // test sous jsdom (rects 0×0, jamais convergent), un artefact
          // d'environnement de test qui ne se produit pas dans un vrai
          // navigateur (rects réels). Le compromis assumé en production :
          // ce menu déroulant simple reste ancré sous le champ sans se
          // replier au bord de la fenêtre — acceptable pour un premier jet.
          avoidCollisions={false}
          className="w-[var(--radix-popover-trigger-width)] rounded-md border border-rule bg-raised p-1 shadow-md"
        >
          {filtered.length === 0 ? (
            <p className="px-2 py-1.5 text-sm text-ink-3">{t("combobox.noResults")}</p>
          ) : (
            filtered.map((option, index) => (
              <div
                key={option.value}
                id={optionId(index)}
                role="option"
                aria-selected={index === activeIndex}
                // Hors de l'ordre de tabulation (roving focus virtuel porté
                // par l'input via aria-activedescendant ci-dessus) mais
                // explicitement focusable par programme — c'est ce que
                // jsx-a11y/interactive-supports-focus attend d'un rôle
                // "option" qui ne reçoit jamais le focus DOM réel.
                tabIndex={-1}
                onMouseDown={(e) => {
                  e.preventDefault();
                  commit(option);
                }}
                className={cn(
                  "cursor-pointer rounded-sm px-2 py-1.5 text-sm text-ink",
                  index === activeIndex && "bg-sunken",
                )}
              >
                {option.label}
              </div>
            ))
          )}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
