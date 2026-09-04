// SPDX-License-Identifier: Apache-2.0
import { useId, useState } from "react";
import type { PopupConfig, PopupField } from "../api/types";
import { validateExpression } from "../builder/expr";
import { closingBrace } from "./popupTemplate";
import { Button } from "../ui/kit/Button";
import { labelCls, inputCls } from "./formFieldStyles";

// Contrôle répété une fois par champ disponible dans une liste dense
// (`PopupEditor` ci-dessous) : reste en h-8 par exception, même hauteur que
// les contrôles denses équivalents de QueryFilterBuilder.tsx/
// CrossFilterLinkEditor.tsx (convention de hauteur tranchée le 2026-09-01,
// CLAUDE.md) — seule cette hauteur est partagée, pas leur recette complète
// (ces deux fichiers portent aussi `bg-surface text-ink`, absents ici).
const denseInputCls = "h-8 rounded-md border border-rule px-2 text-sm";

// Vérifie les placeholders d'un gabarit sans le rendre. Réutilise le scanner
// de popupTemplate.ts (closingBrace), conscient des littéraux de chaîne CEL —
// un scan naïf local du "{"/"}" mésinterpréterait un "}" à l'intérieur d'une
// chaîne CEL comme fermant le placeholder (classe de bug I2-T8, revue de la
// Task 8).
function templateError(template: string): string | null {
  let i = 0;
  while (i < template.length) {
    const open = template.indexOf("${", i);
    if (open === -1) return null;
    const close = closingBrace(template, open);
    if (close === -1) return "Expression non fermée";
    const err = validateExpression(template.slice(open + 2, close).trim());
    if (err) return `Expression invalide : ${err}`;
    i = close + 1;
  }
  return null;
}

// Éditeur partagé par les DEUX surfaces d'auteur (éditeur de cartes et
// PropsPanel du widget carte) : l'écart I2 de la revue finale SP-23 était un
// garde-fou écrit pour une surface et jamais reporté sur sa jumelle.
export function PopupEditor({
  value,
  availableFields,
  attachmentFields,
  onChange,
}: {
  value: PopupConfig | undefined;
  availableFields: string[];
  attachmentFields: string[];
  onChange: (next: PopupConfig | undefined) => void;
}) {
  const [advanced, setAdvanced] = useState(Boolean(value?.template));
  const [draftField, setDraftField] = useState("");
  const listId = useId();
  const selected = value?.fields;
  const error = value?.template ? templateError(value.template) : null;

  function toggleField(name: string) {
    const current: PopupField[] = selected ?? [];
    const next = current.some((f) => f.name === name)
      ? current.filter((f) => f.name !== name)
      : [...current, { name }];
    onChange({ ...value, fields: next });
  }

  function addDraftField() {
    const name = draftField.trim();
    if (!name || (selected ?? []).some((f) => f.name === name)) return;
    onChange({ ...value, fields: [...(selected ?? []), { name }] });
    setDraftField("");
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          aria-label="Afficher les attributs au clic"
          checked={value !== undefined}
          onChange={(e) => onChange(e.target.checked ? {} : undefined)}
        />
        Afficher les attributs au clic
      </label>
      {value !== undefined && !advanced && (
        <>
          <label className={labelCls}>
            Champ titre
            {/* Une saisie avec datalist plutôt qu'un <select> : le même
                contrôle marche quand availableFields est vide (surface du
                widget carte, où PropsPanel n'a ni schéma ni
                enregistrements) et quand il est renseigné (éditeur de
                cartes, où le schéma de la collection est chargé). */}
            <input
              aria-label="Champ titre"
              list={`${listId}-titre`}
              className={inputCls}
              value={value.titleField ?? ""}
              onChange={(e) => onChange({ ...value, titleField: e.target.value || undefined })}
            />
            <datalist id={`${listId}-titre`}>
              {availableFields.map((f) => (
                <option key={f} value={f} />
              ))}
            </datalist>
          </label>
          <p className="text-xs text-ink-3">Sans sélection, tous les champs sont affichés.</p>
          <ul className="flex flex-col gap-1">
            {availableFields.map((f) => {
              const entry = selected?.find((s) => s.name === f);
              return (
                <li key={f} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={f}
                    checked={Boolean(entry)}
                    onChange={() => toggleField(f)}
                  />
                  <span className="flex-1 truncate">{f}</span>
                  {entry && (
                    <input
                      aria-label={`Libellé de ${f}`}
                      className={`${denseInputCls} w-28`}
                      value={entry.label ?? ""}
                      onChange={(e) =>
                        onChange({
                          ...value,
                          fields: (selected ?? []).map((s) =>
                            s.name === f ? { ...s, label: e.target.value || undefined } : s,
                          ),
                        })
                      }
                    />
                  )}
                </li>
              );
            })}
            {(selected ?? [])
              .filter((f) => !availableFields.includes(f.name))
              .map((f) => (
                <li key={f.name} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={f.name}
                    checked
                    onChange={() => toggleField(f.name)}
                  />
                  <span className="flex-1 truncate">{f.name}</span>
                  <input
                    aria-label={`Libellé de ${f.name}`}
                    className={`${denseInputCls} w-28`}
                    value={f.label ?? ""}
                    onChange={(e) =>
                      onChange({
                        ...value,
                        fields: (selected ?? []).map((s) =>
                          s.name === f.name ? { ...s, label: e.target.value || undefined } : s,
                        ),
                      })
                    }
                  />
                </li>
              ))}
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            <input
              aria-label="Nom du champ à ajouter"
              list={`${listId}-titre`}
              className={`${inputCls} flex-1`}
              value={draftField}
              onChange={(e) => setDraftField(e.target.value)}
            />
            <Button type="button" size="sm" variant="outline" onClick={addDraftField}>
              Ajouter le champ
            </Button>
          </div>
        </>
      )}
      {value !== undefined && attachmentFields.length > 0 && (
        <label className={labelCls}>
          Pièces jointes
          <select
            aria-label="Pièces jointes"
            className={inputCls}
            value={value.attachmentField ?? ""}
            onChange={(e) => onChange({ ...value, attachmentField: e.target.value || undefined })}
          >
            <option value="">Aucune</option>
            {attachmentFields.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
      )}
      {value !== undefined && (
        <button
          type="button"
          className="self-start text-xs text-accent underline"
          onClick={() => setAdvanced((a) => !a)}
        >
          {advanced ? "Liste de champs" : "Avancé (gabarit)"}
        </button>
      )}
      {value !== undefined && advanced && (
        <label className={labelCls}>
          Gabarit
          <textarea
            aria-label="Gabarit"
            className="min-h-24 rounded-md border border-rule p-2 font-mono text-xs"
            value={value.template ?? ""}
            onChange={(e) => onChange({ ...value, template: e.target.value })}
          />
          <span className="text-xs text-ink-3">
            Markdown ; chaque {"${expression}"} est évaluée sur l&apos;entité cliquée, par exemple{" "}
            {"${record.nom}"}.
          </span>
        </label>
      )}
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
