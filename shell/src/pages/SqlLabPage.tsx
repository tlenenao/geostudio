// SPDX-License-Identifier: Apache-2.0
import { HelpCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import CodeMirror, { Prec, keymap } from "@uiw/react-codemirror";
import { acceptCompletion, autocompletion, completionKeymap } from "@codemirror/autocomplete";
// Alias `sqlLang` : le fichier a déjà une variable d'état locale `sql` (le
// texte de la requête) — l'import du snippet du brief, nommé `sql` sans
// alias, entre en collision de nom avec elle.
import { sql as sqlLang, SQLite, type SQLNamespace } from "@codemirror/lang-sql";
import { EditorView } from "@codemirror/view";
import { useCollectionsAdmin, useInstanceInfo } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import {
  appendSqlHistory,
  findSqlHistoryEntry,
  readSqlHistory,
  type SqlHistoryEntry,
} from "../lib/sqlLabHistory";
import { useUrlSyncedState } from "../lib/useUrlSyncedState";
import { useUrlTab } from "../lib/useUrlTab";
import { SqlLabCopilotPanel } from "../builder/copilot/SqlLabCopilotPanel";
import { CopilotUnavailable } from "../builder/copilot/CopilotUnavailable";
import { parseDuckDbError } from "../lib/parseDuckDbError";
import { Banner } from "../ui/kit/Banner";
import { Button } from "../ui/kit/Button";
import { IconButton } from "../ui/kit/IconButton";
import { Popover } from "../ui/kit/Popover";
import { Panel } from "../ui/kit/Panel";
import { EmptyState } from "../ui/kit/EmptyState";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";
import { jobStatusLabel } from "../lib/jobStatusLabel";
import { PageTitle } from "../ui/kit/PageTitle";
import "../i18n/domains/automation";
import "../i18n/domains/misc";
import "../i18n/domains/widgets";

// P25.14 : toutes les collections interrogeables sont proposées à la saisie
// (titre en détail), colonnes ajoutées dès que leur schéma est connu.
export function buildSqlSchema(
  collections: { id: string; title: string }[],
  columnsById: Record<string, string[]>,
): Record<string, SQLNamespace> {
  const schema: Record<string, SQLNamespace> = {};
  for (const [id, columns] of Object.entries(columnsById)) schema[id] = columns;
  for (const c of collections) {
    schema[c.id] = {
      self: { label: c.id, type: "table", detail: c.title },
      children: columnsById[c.id] ?? [],
    };
  }
  return schema;
}

// P25.16 : Entrée insère une nouvelle ligne même quand la liste de complétion
// est ouverte (elle validait le mot-clé « catalog ») ; Tab accepte la complétion.
// REV-280c : `basicSetup` installe la keymap de complétion avec sa propre
// priorité, qui gagnait sur Prec.highest — on la désactive et on la remet ici
// sans sa liaison Entrée.
const sqlEditorKeys = [
  autocompletion({ defaultKeymap: false }),
  Prec.highest(
    keymap.of([
      ...completionKeymap.filter((binding) => binding.key !== "Enter"),
      {
        key: "Enter",
        run: (view) => {
          view.dispatch(view.state.replaceSelection("\n"), { scrollIntoView: true });
          return true;
        },
      },
      { key: "Tab", run: acceptCompletion },
    ]),
  ),
];

type SqlResult = { columns: string[]; rows: unknown[][]; truncated: boolean };

export function SqlLabPage() {
  const client = useItemClient();
  const tabProps = useUrlTab("query");
  const [sql, setSql] = useState("");
  const [result, setResult] = useState<SqlResult | null>(null);
  // D54b (Vague C, Tâche 26) : autocomplétion de colonnes lazy — dès qu'un
  // id de collection connu apparaît dans le texte SQL, on récupère son
  // schéma en arrière-plan et on l'accumule pour nourrir l'extension
  // `sql({schema})` de CodeMirror.
  const [schemaByCollection, setSchemaByCollection] = useState<Record<string, string[]>>({});
  const [history, setHistory] = useState<SqlHistoryEntry[]>(() => readSqlHistory());
  const [historyId, setHistoryId] = useUrlSyncedState<string>("historyId", null);
  const instanceQuery = useInstanceInfo();
  const copilotEnabled = instanceQuery.data?.copilotEnabled === true;
  // D54 (Vague C) : la liste des collections alimente désormais aussi
  // l'autocomplétion SQL (Tâche 26, D54b), plus seulement le panneau
  // copilote — appel inconditionnel.
  // REV-184(5) : GET /v1/collections sans `limit` ne renvoie que sa première
  // page (DEFAULT_LIMIT = 100, core/app/collections/routes.py) — au-delà, ni
  // l'autocomplétion ni le copilote ne voient les collections suivantes. Et
  // un tour de copilote envoyé avant la résolution de cette requête part avec
  // `collections: []` (course de chargement assumée, rare en pratique).
  const collectionsQuery = useCollectionsAdmin();

  // SP-B9d : restaure la requête sélectionnée dans l'historique depuis
  // l'URL (?historyId=…) — au montage et à chaque changement externe de
  // l'URL (navigation, partage de lien). Un `historyId` inconnu ou périmé
  // (localStorage vidé entre-temps) ne fait rien : le `sql` déjà présent
  // dans l'éditeur reste inchangé.
  useEffect(() => {
    if (!historyId) return;
    const entry = findSqlHistoryEntry(historyId);
    if (entry) {
      setSql(entry.sql);
    }
  }, [historyId]);

  // D54b : détection lazy des collections référencées dans le texte SQL,
  // fetch de leur schéma une seule fois chacune (accumulation dans
  // schemaByCollection, jamais re-fetché une fois connu).
  const knownCollectionIds = (collectionsQuery.data ?? []).map((c) => c.id);
  useEffect(() => {
    const referenced = knownCollectionIds.filter(
      (id) => sql.includes(id) && !(id in schemaByCollection),
    );
    if (referenced.length === 0) return;
    let cancelled = false;
    // `void` : patron déjà suivi par LayersPanel.tsx pour un effet
    // fire-and-forget (contrainte @typescript-eslint/no-floating-promises).
    //
    // Revue finale Vague C (point 7) : `Promise.all` faisait perdre TOUT le
    // lot dès qu'une seule collection référencée échouait à résoudre son
    // schéma (id périmé, droit de lecture retiré entre-temps…) — aucune
    // `.catch()`, la promesse rejetait, `setSchemaByCollection` n'était
    // jamais appelé, pas même pour les collections qui avaient réussi. Pire :
    // comme l'id en échec n'entrait jamais dans `schemaByCollection`, la
    // condition `!(id in schemaByCollection)` ci-dessus le considérait
    // encore "jamais tenté" à l'effet suivant — chaque frappe relançait un
    // nouveau fetch voué au même échec, en boucle. `Promise.allSettled`
    // laisse les succès entrer dans l'état ; un échec est mémorisé avec un
    // schéma vide (`[]`, jamais pire qu'aucune autocomplétion) pour sortir
    // définitivement de la liste des ids "à essayer" et casser la boucle,
    // et journalisé individuellement (mêmes conventions que labelSource.ts/
    // MapView.tsx pour un échec de fond non bloquant).
    void Promise.allSettled(
      referenced.map((id) =>
        client.getCollectionSchema(id).then((schema) => [id, schema] as const),
      ),
    ).then((results) => {
      if (cancelled) return;
      setSchemaByCollection((prev) => {
        const next = { ...prev };
        results.forEach((outcome, i) => {
          const id = referenced[i];
          if (outcome.status === "fulfilled") {
            const [, schema] = outcome.value;
            next[id] = schema.fields.map((f) => f.name);
          } else {
            // i18n-ok: journal développeur, jamais affiché
            console.warn(
              // i18n-ok
              `SqlLabPage: échec de récupération du schéma de la collection "${id}" (autocomplétion désactivée pour elle)`,
              outcome.reason,
            );
            next[id] = [];
          }
        });
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
    // REV-265 : `collectionsQuery.data` (référence stable entre rendus) relance
    // l'effet quand la liste arrive après un SQL restauré depuis l'historique.
    // knownCollectionIds (tableau neuf à chaque rendu) et schemaByCollection
    // (garde anti-refetch lue dans l'effet) restent hors dépendances.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cf. ci-dessus
  }, [sql, collectionsQuery.data]);

  const run = useMutation({
    mutationFn: (query: string) => client.runAnalyticsSql(query),
    onSuccess: (data, query) => {
      setResult(data);
      setHistory(
        appendSqlHistory({
          sql: query,
          executedAt: new Date().toISOString(),
          status: "ok",
          rowCount: data.rows.length,
        }),
      );
    },
    onError: (_error, query) => {
      setResult(null);
      setHistory(
        appendSqlHistory({ sql: query, executedAt: new Date().toISOString(), status: "error" }),
      );
    },
  });

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        {...tabProps}
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                {t("nav.backToCatalog")}
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "query",
          label: t("sqlLab.queryLabel"),
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center gap-1.5">
                <PageTitle>{t("sqlLab.heading")}</PageTitle>
                <Popover
                  aria-label={t("sqlLab.helpAria")}
                  trigger={
                    <IconButton
                      icon={<HelpCircle size={14} />}
                      aria-label={t("sqlLab.helpAria")}
                      size="sm"
                    />
                  }
                >
                  {t("sqlLab.helpBody")}
                </Popover>
              </div>
              <div className="flex flex-col gap-1 text-sm text-ink">
                <span>{t("sqlLab.sqlQueryLabel")}</span>
                <CodeMirror
                  value={sql}
                  height="8rem"
                  extensions={[
                    sqlLang({
                      dialect: SQLite,
                      schema: buildSqlSchema(collectionsQuery.data ?? [], schemaByCollection),
                    }),
                    sqlEditorKeys,
                    // `aria-label` passé directement à <CodeMirror> atterrit
                    // sur le conteneur englobant, pas sur le
                    // `role="textbox"` (div `.cm-content` contenteditable)
                    // que les tests (et les lecteurs d'écran) interrogent —
                    // vérifié empiriquement (piège n°3 CLAUDE.md). Seul
                    // `EditorView.contentAttributes` pose l'attribut sur le
                    // bon élément.
                    EditorView.contentAttributes.of({
                      "aria-label": t("sqlLab.sqlQueryLabel"),
                      "aria-describedby": "sql-editor-keyboard-hint",
                    }),
                  ]}
                  onChange={(value) => setSql(value)}
                  className="rounded-md border border-rule text-xs"
                />
                {/* P33.13 (WCAG 2.1.2) : Tab indente dans l'éditeur ; la sortie au
                    clavier est dite, pas devinée. */}
                <span id="sql-editor-keyboard-hint" className="text-xs text-ink-3">
                  {t("sqlLab.keyboardHint")}
                </span>
              </div>
              <Button
                size="sm"
                className="w-fit"
                disabled={!sql.trim() || run.isPending}
                onClick={() => run.mutate(sql)}
              >
                {t("sqlLab.runButton")}
              </Button>
              {run.isError &&
                (() => {
                  const parsed = parseDuckDbError((run.error as Error).message);
                  return (
                    <Banner variant="danger">
                      {parsed.category && <p className="font-semibold">{parsed.category}</p>}
                      <p>{parsed.message}</p>
                      {parsed.line !== null && (
                        <p className="mt-1 font-mono text-xs">
                          {t("sqlLab.errorLineLabel", { line: parsed.line })}
                          {parsed.sqlSnippet}
                        </p>
                      )}
                    </Banner>
                  );
                })()}
              {result && (
                <div>
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr>
                        {result.columns.map((col) => (
                          <th key={col} className="border-b border-rule p-1 text-ink">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, i) => (
                        <tr key={i}>
                          {row.map((cell, j) => (
                            <td key={j} className="border-b border-rule-2 p-1 text-ink">
                              {cell === null || cell === undefined ? (
                                <span className="italic text-ink-2">{t("sqlLab.nullCell")}</span>
                              ) : (
                                String(cell)
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {result.truncated && (
                    <p className="mt-1 text-xs text-ink-2">
                      {t("sqlLab.truncatedMessage", { n: result.rows.length })}
                    </p>
                  )}
                </div>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "history",
          label: t("sqlLab.historyLabel"),
          content: (
            <div className="flex flex-col gap-2 p-3">
              {history.length === 0 ? (
                <EmptyState title={t("sqlLab.emptyHistory")} />
              ) : (
                <ul className="flex flex-col gap-1">
                  {history.map((entry) => (
                    <li key={entry.id} className="flex items-center gap-2 text-xs">
                      <span aria-hidden="true">{entry.status === "error" ? "✕" : "✓"}</span>
                      <span className="sr-only">
                        {t("sqlLab.historyStatusAria", {
                          status: jobStatusLabel(entry.status === "error" ? "error" : "done"),
                        })}
                      </span>
                      <button
                        type="button"
                        aria-label={t("sqlLab.reloadQueryAria", { sql: entry.sql })}
                        className="text-left font-mono text-ink-2 hover:underline"
                        onClick={() => {
                          setSql(entry.sql);
                          setHistoryId(entry.id);
                        }}
                      >
                        {entry.sql}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {(copilotEnabled || instanceQuery.isSuccess) && (
                <div className="border-t border-rule pt-3">
                  <p className="mb-1 text-xs font-medium text-ink-2">
                    {t("appBuilder.copilotLabel")}
                  </p>
                  {!copilotEnabled && <CopilotUnavailable />}
                  {copilotEnabled && (
                    <SqlLabCopilotPanel
                      sql={sql}
                      setSql={setSql}
                      collections={(collectionsQuery.data ?? []).map((c) => ({
                        id: c.id,
                        title: c.title,
                      }))}
                    />
                  )}
                </div>
              )}
            </div>
          ),
        }}
      />
    </div>
  );
}
