# Spec — REV-119 / GAP-25 : métriques nommées sur le dataset

Date : 2026-10-16. Décision de Tanguy : « spécifier et implémenter » (lot 8 du
plan `2026-10-15-cloture-toutes-rev-v0.2.0.md`). Constat de départ :
`docs/revue/2026-10-11-rev119-constat.md` (Cas 2 : aucune métrique nommée sur
le dataset, A28 non livré). Cette spec retient l'**option A** du constat.

## 1. Périmètre

Une **métrique nommée** est une définition déclarative attachée à la config du
dataset : `{field, agg, p?, label?, format?, unit?, description?}`, identifiée
par une clé (`^[a-z][A-Za-z0-9_]{0,63}$`). Elle est référencée par nom dans une
mesure d'agrégat (`{"metric": "recettes_total"}`) et résolue en
`AggregateMeasure` **avant** exécution : un seul moteur d'évaluation
(`_agg_expr`), pas de second dialecte.

Consommateurs fermés par ce lot : widgets/sources `statistics` (via
`DataSourcePanel`), MCP `run_analytics_query`, règles d'alerte
(`AlertRulePayload.query.measures`), routes REST ArcGIS
`/datasets/{id}/arcgis/aggregate` (+ export). Éditeur : onglet « Métriques »
de `DatasetEditPage`.

## 2. Modèle de données (`core/app/configs/schemas.py`)

```python
class DatasetMetric(BaseModel):
    field: str | None = None      # requis sauf agg == "count"
    agg: Literal["count","countDistinct","sum","avg","min","max","median","percentile","stddev"]
    p: float | None = None        # 0<p<100, uniquement agg == "percentile"
    label: str | None = None      # libellé d'affichage (défaut : la clé)
    format: str | None = None     # libre, comme DatasetColumnMeta.format
    unit: str | None = None
    description: str | None = None

DatasetPayload.metrics: dict[str, DatasetMetric] = {}   # max 50, clés validées
```

`AggregateMeasure` gagne `metric: str | None`. Une mesure `{metric}` seule est
résolue par `resolve_metrics(request, metrics)` (`app/analytics/aggregate.py`,
fonction pure, duck-typée pour ne pas inverser le contrat de couches) en
`AggregateMeasure(field, agg, p, label=m.label_clé)`. Le **libellé de ligne** de
la mesure résolue est la **clé** de la métrique (stable, indépendante du
libellé d'affichage), sauf si l'appelant donne un `label` explicite.

Versionnement : gratuit, `metrics` fait partie de la config du dataset
(`configs.current_version`, rollback, `If-Match`). Aucune migration Alembic
(la config est du JSON) ; pas de numéro ≥0090 consommé.

## 3. Validation

- À l'écriture (`DatasetPayload`, model_validator) : clé valide, `agg` ∈ liste
  fermée (test de dérive contre `_agg_expr`), `field` requis hors `count`,
  `p` borné et réservé à `percentile` (mêmes règles que `_validate_p`),
  ≤ 50 métriques.
- À l'exécution : `_validate_fields` refuse une mesure `metric` non résolue
  (`UnknownAggregateField`, 422/400 selon la surface) — jamais un `count`
  silencieux ; une métrique inconnue du dataset est refusée de même. Le
  `field` de la métrique est validé par `_validate_fields` comme n'importe quel
  champ (donc **champ masqué GAP-22 → rejeté**).

## 4. Sécurité

Aucun nouvel accès aux données : la résolution produit une requête
d'agrégat ordinaire, exécutée par `run_collection_aggregate` sous `can()`,
masquage de champs GAP-22, limites géographiques (`refuse_geo_limited`) et
bornes DuckDB existants. Les métriques sont lisibles par quiconque lit le
dataset (même statut que `columns`). L'écriture suit `PUT /configs` (droit
d'écriture sur l'item, `If-Match`). Aucune route nouvelle.

## 5. API et surfaces

- REST : aucune route ajoutée ; `metrics` apparaît dans `PUT/GET
  /configs/by-item/{id}` (OpenAPI/types TS régénérés). Les routes ArcGIS
  `aggregate`/`export` résolvent côté serveur (elles chargent déjà le
  dataset). La route `POST /collections/{id}/aggregate` (sans contexte dataset)
  refuse `metric` (400).
- MCP : `run_analytics_query` résout `measures[].metric` sur le dataset
  (branche collection **et** arcgis). Pas de nouvel outil : `explain_dataset`
  renvoie déjà la config ; `metrics` y figure.
- Alertes : `_measure_value` résout avec le dataset de la règle (mêmes
  garanties que ci-dessus), y compris le second site de libellé.
- Shell : `ResolvedDataset.metrics` (chemin de lecture, piège n°5) ;
  `queryPage` résout les mesures `metric` avant `buildAggregateBody` ;
  `DataSourcePanel` propose un sélecteur « Métrique » par mesure quand la
  source pointe un dataset ayant des métriques ; `DatasetEditPage` édite la
  liste (clé, libellé, agrégat, champ, centile, format, unité).

## 6. Choix et alternatives écartées

| Choix | Écarté | Pourquoi |
|---|---|---|
| Option A (sur `DatasetPayload`) | B (`Collection.metrics`) | A28 dit dataset ; pas de migration ; versionnement gratuit ; couvre ArcGIS |
| `field+agg` seulement | expression CEL libre | un seul moteur (`_agg_expr`) ; CEL-vers-SQL = second dialecte à garder équivalent (risque du constat) |
| Résolution côté appelant (shell) + côté serveur pour MCP/alertes/ArcGIS | nouvelle route `POST /datasets/{id}/aggregate` | zéro route (compte REST inchangé), pas de second chemin d'exécution |
| Libellé de ligne = clé | libellé d'affichage | stabilité des liaisons de widget lors d'un renommage de libellé |
| Requête visuelle (Filtrer→Joindre→Résumer) hors périmètre | y brancher les métriques | elle compile en nœuds pipeline ayant leurs propres `metrics` locales ; la brancher change le contrat du pipeline. Résiduel : REV-325 (partage entre datasets) |
| Pas de DAG/dépendance entre métriques, pas de partage inter-datasets | — | spéculatif ; reste hors périmètre (REV-325 si besoin) |

Limite assumée : un changement de métrique modifie tous les widgets qui la
référencent (c'est l'objectif d'une couche sémantique) ; l'historique de
version du dataset (`ConfigHistoryPanel`) sert de garde-fou. Le mode
Autoporté (mini-serveur) n'embarque pas les datasets : une `metric` y est
refusée (400), le shell exporté résout côté client comme en mode connecté.

## 7. Tests

Core : schéma (clés, agg, p, plafond, dérive vs `_agg_expr`), `resolve_metrics`,
refus non résolu, MCP (collection+arcgis), alerte, routes ArcGIS. Shell :
`resolveDataset` round-trip `metrics`, `queryPage` résolution, éditeur,
sélecteur. E2E : `e2e/dataset-metrics.spec.ts` (créer une métrique, la
choisir dans une source de widget, vérifier le corps `aggregate`).
