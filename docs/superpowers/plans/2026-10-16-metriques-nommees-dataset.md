# Plan — métriques nommées sur le dataset (REV-119)

Spec : `docs/superpowers/specs/2026-10-16-metriques-nommees-dataset-design.md`.
TDD, un commit par tâche.

1. **Core schéma** : `DatasetMetric` + `DatasetPayload.metrics` + validateur ;
   test `test_dataset_metrics_schema.py` (clé, agg, p, plafond, dérive vs `_agg_expr`).
2. **Core résolution** : `AggregateMeasure.metric`, `resolve_metrics`, refus dans
   `_validate_fields` ; tests dans `test_analytics_aggregate.py`.
3. **Core surfaces** : MCP `run_analytics_query`, `_measure_value` (alertes),
   routes ArcGIS aggregate+export ; tests dédiés.
4. **OpenAPI + types TS** régénérés ; inventaire fonctionnalités + bilan.
5. **Shell lecture/résolution** : `ResolvedDataset.metrics`, types, `queryPage`
   (`resolveMetricMeasures`), tests vitest.
6. **Shell UI** : éditeur de métriques (`DatasetMetricsEditor`) dans
   `DatasetEditPage`, sélecteur dans `DataSourcePanel`, i18n par domaine.
7. **E2E** `dataset-metrics.spec.ts`.
8. **Clôture** : backlog, gaps, historique, CLAUDE.md, suites complètes, revue du diff.
