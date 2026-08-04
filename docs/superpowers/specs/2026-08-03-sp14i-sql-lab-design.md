# SP-14i — SQL Lab (design)

> **Date : 2026-08-03 · Statut : validé (brainstorm)**
> Neuvième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur**,
> **SP-14d — Menu explorer & voir les entités**, **SP-14e — KPI riche &
> séries temporelles comparées**, **SP-14f — Nouveaux types de graphiques**,
> **SP-14g — Tableau croisé / pivot** et **SP-14h — Carte analytique**.
> Traite un des éléments encore listés « hors périmètre » par 14h
> (« Conteneurs [...], requête visuelle, SQL Lab, source `arcgis`, MCP
> analytique — sous-parties SP-14 ultérieures (14i…) ») : **SQL Lab**,
> « l'UI de l'endpoint SQL read-only du rôle analyste — éditeur, historique,
> "enregistrer comme dataset" » (feuille de route §SP-14). Conteneurs
> (onglets/modale/tiroir), requête visuelle, source `arcgis`, MCP analytique
> restent hors périmètre — sous-parties SP-14 ultérieures (14j…).

## 1. Objectif & non-buts

**Objectif.** L'endpoint `POST /analytics/sql` (livré en **SP-11c**, réservé
au rôle `is_analyst`, isolation imposée par DuckDB, quotas timeout/lignes/
mémoire, `audit_log` et compteur OTel déjà en place) gagne son UI : un
analyste écrit du SQL read-only sur ses collections lisibles, l'exécute,
consulte le résultat tabulaire et rappelle une requête précédente depuis un
historique local. **Zéro changement cœur** — SP-11c a explicitement livré le
backend en prévoyant cette UI pour SP-14 ; ce plan ne fait que la construire.

**Non-buts explicites** (reportés) :

- **« Enregistrer comme dataset »** (dernier morceau du bullet SQL Lab de la
  feuille de route). Faire qu'un dataset issu de SQL Lab reste consommable
  par un **non-analyste** demanderait un modèle « definer » (le SQL s'exécute
  avec l'autorité de l'analyste auteur, pas du lecteur, ré-autorisé
  uniquement via `can()` sur le dataset) — une frontière de sécurité nouvelle
  et non triviale, symétrique à celle déjà verrouillée par le spike SP-11c
  mais distincte (elle attache une autorité *stockée* à une requête, pas une
  vérification *à la volée*). Reporté à quand le moteur de pipeline **SP-15**
  existera (A39 : « Pipeline de SP-15 EST ce pipeline, avec un
  `writer.dataset` ») — cohérent avec le report déjà acté en 14a du pipeline
  de transformations et des sources autres que `collection`. Décision prise
  avec l'utilisateur (2026-08-03) : différer explicitement plutôt que
  construire le modèle definer maintenant.
- **Historique persisté côté serveur.** v1 = `localStorage` du navigateur
  uniquement. `audit_log` trace déjà chaque exécution (SP-11c : acteur,
  tenant, texte tronqué) mais aucun endpoint de lecture n'existe ; en
  construire un (pagination, filtrage par acteur) serait un chantier à part
  entière hors périmètre YAGNI pour un premier éditeur. Décision prise avec
  l'utilisateur (2026-08-03).
- **Éditeur enrichi** (coloration syntaxique, autocomplétion, raccourcis
  clavier d'exécution). Suit le patron déjà établi par le champ `visibleWhen`
  (CEL) dans `PropsPanel.tsx` : un `<textarea>` `font-mono`, sans dépendance
  nouvelle (CodeMirror/Monaco) — disproportionné pour un v1.
- **Explorateur de schéma** (liste des collections/colonnes disponibles dans
  la sidebar de l'éditeur) — non demandé par la feuille de route pour SQL
  Lab ; l'analyste connaît déjà ses collections via le catalogue. Pourra
  s'ajouter sans rupture si le besoin émerge.
- Conteneurs (onglets/modale/tiroir), requête visuelle, source `arcgis`, MCP
  analytique (`create_dataset`/`run_analytics_query`/`explain_dataset`) —
  reste de la liste SP-14, sous-parties ultérieures.
- Bookmarks/situations nommées, cross-filter inter-datasets — toujours hors
  périmètre (inchangé depuis 14b).

Le modèle reste additif et à faible surface partagée : une nouvelle méthode
`itemClient.runAnalyticsSql`, une nouvelle page autonome, un lien nav
conditionnel. Aucun changement à `core/`, aux widgets existants, à
`DataSourcePanel.tsx`, ni au modèle `DatasetPayload`.

## 2. Rappel du contrat backend (SP-11c, inchangé)

- `POST /analytics/sql`, corps `{ "sql": "<texte>" }`.
- 403 si `!user.is_analyst`, avant tout travail DuckDB.
- Succès (200) : `{ "columns": string[], "rows": unknown[][], "truncated": boolean }`
  — `columns` = noms de colonnes dans l'ordre du `SELECT`, `rows` = valeurs
  positionnelles (pas d'objets `{col: valeur}`), `truncated` = vrai si le
  plafond de lignes (`ROW_CAP`) a coupé le résultat.
- Erreur (400) : `{ "detail": { "errors": [{ "field": "sql", "code": "sql_error", "message": "<texte>" }] } }`
  — même forme que `_validation_error` ailleurs dans `core/app/features/routes.py`
  (déjà consommée côté shell par `FeatureValidationError`), le message est
  directement lisible par l'analyste (ex. « collection 'x' has no data yet »,
  message DuckDB brut sur SQL invalide, « query exceeded the time limit »).
- `GET /me` expose déjà `isAnalyst` (`shell/src/api/types.ts:32`,
  `itemClient.ts:275/282`) — sans consommateur UI avant ce plan.

## 3. Shell — `itemClient`

Nouvelle méthode sur l'interface `ItemClient` (`api/types.ts`) et son
implémentation (`api/itemClient.ts`), au même niveau que `queryDataSource` :

```ts
runAnalyticsSql(sql: string): Promise<{ columns: string[]; rows: unknown[][]; truncated: boolean }>;
```

Implémentation : `fetch` direct (comme `requestFeatureWrite`), **pas** le
`request<T>` générique — celui-ci ne parse pas `detail.errors` et jetterait un
message générique (`Request failed: 400 POST /analytics/sql`) au lieu du
message SQL réel, qui est justement ce que l'analyste doit voir pour corriger
sa requête. Nouvelle classe d'erreur minimale :

```ts
export class SqlQueryError extends Error {
  constructor(message: string) { super(message); this.name = "SqlQueryError"; }
}
```

Sur 400 : parser `detail.errors[0]?.message`, fallback sur un message
générique si absent/malformé (patron identique à `FeatureValidationError`,
mais un seul message textuel suffit ici — pas de correspondance par champ à
afficher, il n'y a qu'un seul champ `sql`).

Aucun nouveau hook React Query générique (`useXxxQuery`) : l'exécution est une
action ponctuelle déclenchée par un clic, pas une donnée à cacher/refetch —
un simple état local (`useState` + `useMutation` de TanStack Query, comme
`useSaveDataset`) suffit, exécuté dans la page elle-même.

## 4. Shell — page `SqlLabPage`

Nouvelle page `pages/SqlLabPage.tsx`, route `/analytics/sql` (au même niveau
que `/admin/extensions` dans `shell/routes.tsx`, sous `ProtectedLayout`).

**Garde d'accès** — mirror exact d'`AdminExtensionsPage.tsx` :

```tsx
if (meQuery.isLoading) return <p role="status">Chargement…</p>;
if (meQuery.data?.isAnalyst !== true)
  return <p role="alert" className="text-sm text-red-600">Accès réservé aux analystes.</p>;
```

**Lien nav** dans `shell/AppLayout.tsx`, à côté des liens admin, conditionné
par `meQuery.data?.isAnalyst === true` (indépendant du bloc `isAdmin` existant
— les deux rôles sont orthogonaux, cf. SP-11c « `is_admin` n'implique PAS
`is_analyst` »).

**Contenu de la page :**

- `<textarea>` `font-mono text-xs` (patron `visibleWhen`), `aria-label="Requête SQL"`,
  valeur contrôlée par un état local.
- Bouton « Exécuter » (`disabled` si texte vide ou requête en cours),
  déclenche la mutation `runAnalyticsSql`.
- Résultat :
  - succès → table générique : `<thead>` depuis `columns`, `<tbody>` depuis
    `rows` (rendu positionnel, `String(cell)` pour toute valeur, cellule vide
    si `null`/`undefined`) ; si `truncated`, bandeau
    « Résultat tronqué aux N premières lignes » sous la table (N = longueur
    de `rows`, pas une constante dupliquée du cœur).
  - erreur → `<p role="alert">{error.message}</p>`, le texte SQL reste dans
    l'éditeur pour correction (pas de reset).
- **Historique** (panneau sous l'éditeur) : liste des ~20 dernières requêtes
  exécutées avec succès ou en erreur (texte SQL tronqué à l'affichage,
  horodatage, statut ok/erreur), la plus récente en tête. Clic sur une entrée
  → recopie son texte SQL dans l'éditeur (ne ré-exécute **pas**
  automatiquement — l'analyste garde le contrôle, cohérent avec le fait que
  la requête peut porter sur des données qui ont changé).

## 5. Historique — `localStorage`

Module pur `lib/sqlLabHistory.ts` (même esprit que `lib/datasetSchema.ts` :
zéro dépendance React) :

```ts
export type SqlHistoryEntry = { sql: string; executedAt: string; status: "ok" | "error"; rowCount?: number };
export function readSqlHistory(): SqlHistoryEntry[];
export function appendSqlHistory(entry: SqlHistoryEntry): SqlHistoryEntry[]; // cap 20, plus récent en tête
```

Clé `localStorage` fixe (`"geostudio.sqlLab.history"`), pas de scoping par
utilisateur/tenant (poste personnel supposé, comme le reste du shell
mono-session — aucune autre fonctionnalité du shell ne fait de scoping
`localStorage` par utilisateur). `JSON.parse` défensif (liste vide si contenu
corrompu/absent — jamais de throw qui casserait le chargement de la page).

## 6. Compatibilité & tests

- Additif pur : nouvelle route, nouvelle page, nouveau champ optionnel sur
  l'interface `ItemClient`. Les 76 specs E2E existantes restent vertes sans
  modification (le lien nav n'apparaît que si `isAnalyst === true`, absent du
  mock `/me` par défaut dans `e2e/mocks.ts`).
- **Unitaires** (`SqlLabPage.test.tsx`) : garde d'accès (non-analyste → message,
  analyste → éditeur) ; exécution réussie → table rendue avec les bonnes
  colonnes/lignes ; bandeau de troncature affiché seulement si
  `truncated === true` ; exécution en erreur → message affiché, éditeur
  conserve le texte ; historique — une entrée ajoutée après exécution
  (succès et erreur), clic sur une entrée recopie le texte dans l'éditeur,
  plafond de 20 respecté. `sqlLabHistory.test.ts` : lecture/écriture/cap/
  JSON corrompu, en isolation de tout composant React.
- **E2E** (`e2e/sql-lab.spec.ts`, patron `admin-collections.spec.ts`) : mock
  `/me` avec `isAnalyst: true` et mock `POST **/analytics/sql` ; scénarios —
  lien nav absent pour un utilisateur non-analyste (mock par défaut
  `e2e/mocks.ts`, inchangé) ; lien nav présent et page accessible pour un
  analyste ; exécution réussie affiche la table de résultats ; réponse 400
  affiche le message d'erreur SQL ; historique — exécuter deux requêtes puis
  cliquer la plus ancienne recharge son texte dans l'éditeur.

## 7. Risques

- **Aucun risque de sécurité nouveau** : la frontière (403 avant tout travail
  DuckDB, isolation DuckDB `enable_external_access = false`) est entièrement
  côté cœur, déjà validée par le spike go/no-go de SP-11c. Ce plan ne touche
  à aucun code d'autorisation.
- **Rendu d'un tableau à colonnes dynamiques** — cas déjà traité ailleurs
  (résultats `aggregate` dans les widgets `chart`/`table`/pivot), pas un
  nouveau patron.
- **`localStorage` plein/désactivé** (navigation privée) — `appendSqlHistory`
  échoue silencieusement (try/catch), dégrade en « pas d'historique » plutôt
  que de casser l'exécution de la requête elle-même.
