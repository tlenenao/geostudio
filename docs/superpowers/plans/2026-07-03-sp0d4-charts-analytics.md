# GeoStudio SP-0d.4 — Graphiques (ECharts) & analytique — Implementation Plan

> **Statut : IMPLÉMENTÉ (2026-07-04, branche `dev`).** Ce document reflète ce qui a été livré.
> La conception initiale (graphiques SVG maison) a été **remplacée** à la demande de l'utilisateur
> par une intégration **Apache ECharts** de niveau « Grafana minimum » (tooltips, axes formatés,
> séries multiples, zoom, large couverture de panels + échappatoire JSON). Plan détaillé de la
> décision : `~/.claude-perso/plans/fancy-stargazing-tarjan.md`.

**Goal:** Donner au builder une analytique riche — une source **statistics** (agrégation façade, multi-séries), un widget **Graphique** ECharts config-driven (10 familles de panels + option brute JSON), une **Table** triable/paginée, et un **Texte** à liaisons dynamiques `{{champ}}`.

**Architecture:** `DataSource.type:"statistics"` agrège les features côté façade (`aggregateRecords` dans `itemClient.ts`) en un **dataset large** (une ligne par catégorie, une colonne par série) via group-by + count/sum/avg/min/max, **pivot par champ `split`** et/ou **plusieurs `measures`**. Le widget Graphique traduit sa config en option ECharts par une fonction **pure** `buildOption` (`chartOption.ts`, testée sans React ni ECharts), puis la rend via un wrapper `EChart` **lazy-loadé** (chunk séparé, canvas, `ResizeObserver`) — mocké en unitaire, rendu réel en E2E. Une échappatoire « option ECharts avancée (JSON) » est fusionnée en profondeur par-dessus l'option construite. Moteur unique `AppRenderer` → rendu identique edit/preview/runtime.

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library + MSW + Playwright ; TanStack Query v5 ; **`echarts` 6** (Apache-2.0, `echarts/core` tree-shakeable, `CanvasRenderer`).

## Global Constraints
- Front : tout accès réseau via `item-client` ; les clés de config statistiques (`STAT_KEYS = groupBy/split/agg/field/measures`) sont retirées de l'URL featureserv.
- ECharts confiné à `EChart.tsx`, lazy-load + `vi.mock` → aucune suite `registerBuiltinWidgets` ne tire ECharts/canvas.
- `Item`/`ItemClient`/`AppConfig`/`DataSource` étendus par ADDITION ; tests existants verts ; `npm run build` OK.
- Backend inchangé — `DataSource.type` est un `str` non contraint (`builder-service/app/schemas.py`).
- Commits terminés par `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`, branche `dev`.

## Tâches livrées (TDD, un commit chacune)
1. **Statistics multi-séries** — `types.ts` (`type += "statistics"`), `itemClient.ts` (`STAT_KEYS`, `aggregateRecords` split/mesures/min-max, branche statistics de `queryDataSource`), tests MSW.
   Fichiers : `shell/src/api/types.ts`, `shell/src/api/itemClient.ts(.test.ts)`.
2. **DataSourcePanel** — type « Statistiques » + `groupBy`/`split`/agg-champ + liste de mesures.
   Fichiers : `shell/src/builder/DataSourcePanel.tsx(.test.tsx)`.
3. **Dépendance + wrapper `EChart`** — `echarts` ; `EChart.tsx` (register large : bar/line/pie/scatter/radar/heatmap/gauge/boxplot/candlestick/funnel/sankey/treemap + tooltip/legend/grid/dataZoom/visualMap/… + canvas ; `data-chart-type`/`data-chart-series` pour l'E2E).
   Fichiers : `shell/package.json`, `shell/src/builder/EChart.tsx`.
4. **`buildOption` pur** — `chartOption.ts` : catKey/seriesKeys inférés, dataset+encode, familles bar/line/area/scatter/pie/doughnut/radar/heatmap/gauge/boxplot, axes (category/value/time/log) + formatage unité, tooltip/legend/dataZoom, **deep-merge de `advancedOption` JSON**. 12 tests purs.
   Fichiers : `shell/src/builder/widgets/chartOption.ts(.test.ts)`.
5. **Widget `chart`** — `chart.tsx` : lazy `EChart`, PropsPanel riche (type, champs, axes, unité, stack/legend/zoom, textarea JSON avancé), garde-fous loading/error/empty ; enregistré dans `index.tsx`. Test avec `EChart` mocké.
   Fichiers : `shell/src/builder/widgets/chart.tsx(.test.tsx)`, `shell/src/builder/widgets/index.tsx`.
6. **E2E** — `chart.spec.ts` : app → source statistics `villes` (groupBy region, split annee, sum pop) → Graphique lié → save → runtime : `[data-testid=echart] canvas` visible + `data-chart-series="2"`. Mock `villes` dans `mocks.ts`.
   Fichiers : `shell/e2e/chart.spec.ts`, `shell/e2e/mocks.ts`.
7. **Table avancée** — tri au clic d'en-tête (asc/desc) + pagination `pageSize` (Précédent/Suivant).
   Fichiers : `shell/src/builder/widgets/data.tsx(.test.tsx)`.
8. **Texte dynamique** — interpolation `{{champ}}` depuis le 1er record de la source liée + binding dans le PropsPanel.
   Fichiers : `shell/src/builder/widgets/index.tsx`, `shell/src/builder/widgets/text.test.tsx`.

## Vérification (exécutée)
- Unitaire : `cd shell && npx vitest run` → **194 tests verts** (dont `chartOption` 12, `chart`, `itemClient` pivot/mesures, `DataSourcePanel`). `npm run build` OK — ECharts en **chunk séparé** `EChart-*.js` (~815 Ko), hors bundle principal.
- E2E : `cd shell && npx playwright test` → **10 specs vertes** (catalog + map-editor + app-builder + data-widget + actions + chart).
- Manuel recommandé : lancer l'app, créer une source statistics, déposer un Graphique, basculer les types, survoler (tooltips), tester l'échappatoire JSON (ex. candlestick), Enregistrer → runtime.
