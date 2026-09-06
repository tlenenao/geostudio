# Spec — GAP-25 : couche sémantique minimale (métriques nommées par collection)

Date : 2026-09-06. Ferme `GAP-25` (`docs/revue/2026-09-04-analyse-gaps.md`) :
« aucune couche sémantique/synchronisation de métriques centralisée (façon
dbt/Superset SIP-182) — GeoStudio a des colonnes calculées CEL au niveau
config, pas de couche de métriques versionnée partagée entre datasets ».

**Statut du gap** : le plus spéculatif des 6 traités cette session — anticipation
générique confirmée par Tanguy en brainstorming, aucun cas d'usage précis
remonté. v0 délibérément minimale : un catalogue de mesures nommées, scopé à
une collection, réutilisable partout où `AggregateMeasure` circule déjà. Pas
de moteur de transformation, pas de DAG de dépendances entre métriques, pas de
synchronisation externe.

## 1. Contexte : ce qui existe déjà

### 1.1 `AggregateMeasure`/`run_collection_aggregate` (`core/app/analytics/aggregate.py`)

`POST /collections/{id}/aggregate` (`core/app/features/routes.py:251`) résout
une requête `AggregateRequestBody` en SQL DuckDB contre le GeoParquet CDC
d'une collection (SP-11b). Une mesure ad hoc a la forme :

```python
class AggregateMeasure(BaseModel):
    field: str | None = None
    agg: str = "count"
    label: str | None = None
    p: float | None = None  # centile, 0 < p < 100, uniquement pour agg="percentile"
```

`_measures_for(request)` (ligne 210) synthétise la liste de mesures à
exécuter : `request.measures` si fourni, sinon un unique
`AggregateMeasure(field=request.field, agg=request.agg, label="value",
p=request.p)` dérivé des champs sommets historiques. Chaque mesure de la
liste est ensuite compilée en SQL par `_agg_expr(agg, field, p)` (ligne 152) —
**seul générateur de SQL d'agrégat de ce dépôt**, jamais dupliqué. Deux
fonctions d'appel : `_pivot_measures`/`_pivot_multi_measures` (lignes
278-299), qui indexent chaque colonne de sortie par `_measure_label(m)`
(ligne 192, dérive `{agg}_{field}` ou `{agg}{p:g}_{field}` pour un centile, si
`m.label` est absent).

`run_collection_aggregate` (ligne 437) appelle `_measures_for` à exactement
deux endroits internes (groupBy multi-champs, ligne 492 ; branche par défaut,
ligne 542) — ce sont les deux seuls points où une liste de mesures nommées
devra être résolue. **Le chemin `split` (ligne 533) et les chemins
`bins`/`sample` n'utilisent jamais `_measures_for`** : ils exécutent
directement `_agg_expr(request.agg, request.field, request.p)` (une mesure
ad hoc unique, `request.measures` déjà silencieusement ignoré par ce chemin
aujourd'hui, pré-existant). Une métrique nommée héritera de la même
limitation — pas une régression introduite par ce plan.

### 1.2 Cinq consommateurs réels de `run_collection_aggregate`/`AggregateMeasure`

Recherche exhaustive (`grep -rn "AggregateMeasure\|run_collection_aggregate"`),
au-delà des deux mentionnés par le brainstorming :

| Site | Backing | A un `Collection` chargé ? |
|---|---|---|
| `features/routes.py::aggregate_features` (251) | REST `POST /collections/{id}/aggregate` | oui (`col`, ligne 261) |
| `features/routes.py::export_collection_aggregate` (286) | REST `POST /collections/{id}/export` | oui (`col`, ligne 307) |
| `mcp/tools/analytics.py::run_analytics_query`, branche `collection` (94-120) | outil MCP, « mirrors POST /collections/{id}/aggregate » (docstring ligne 85) | oui (`col`, ligne 96) |
| `alerts/jobs.py::_measure_value` (110) | évaluation planifiée d'une `AlertRule` | oui (`col`, ligne 130) — **mais** un 2e site indépendant du même fichier (ligne 166, `_measure_label(_measures_for(payload.query)[0])`, calcule le libellé affiché du résultat) devrait recevoir le **même** catalogue pour rester cohérent avec l'exécution — sinon une règle utilisant `metricName` casse silencieusement sur ce second appel |
| `appexport/miniserver/main.py::aggregate` (156) | mode Autoporté, mini-serveur sans session DB | **non** — lit un `manifest.json` figé au moment de l'export (`CollectionSnapshotEntry.collection_json`, sérialisé par `appexport/snapshot.py::_collection_json`, **une fonction dupliquée indépendante** de `collections/routes.py::_collection_json`, pas les mêmes champs) |
| `harvest/routes.py`, 2 routes ArcGIS live-query (376, 447) | `/datasets/{item_id}/arcgis/aggregate` | non — source `arcgis`, aucune `Collection` ne les adosse ; construisent `AggregateMeasure` puis appellent `live_query.translate_aggregate_query` (moteur de traduction REST ArcGIS, **jamais** `_agg_expr`/DuckDB) |

Une métrique nommée est par décision **scopée à sa collection** (§4) : les
deux routes ArcGIS et le tool `explain_dataset`/`run_analytics_query` branche
`arcgis` en sont donc structurellement exclus, pas par choix de périmètre.

### 1.3 `Collection.metrics` — précédent direct : `attachment_fields`

`core/app/collections/models.py:51` porte déjà un champ JSON/liste sur ce
même modèle avec exactement le patron à reproduire :

```python
attachment_fields: Mapped[list] = mapped_column(
    JSON, default=list, nullable=False, server_default="[]"
)
```

`server_default="[]"` en chaîne nue (pas un `sa.text("'[]'::json")` casté) —
un cast `::json` casse le DDL SQLite des tests unitaires (commentaire ligne
40-50 du modèle). Le comparateur `test_model_alembic_parity.py` a un
traitement spécial pour ce genre de `server_default` JSON (cf. commentaire).
Édition depuis `PATCH /collections/{id}` (`collections/routes.py:512`) :
`body.attachmentFields` validé (dédoublonnage sans DB dans
`CollectionPatch._reject_duplicate_attachment_field_keys`, schemas.py:98 ;
collision avec une colonne réelle avec DB dans
`_reject_attachment_field_collisions`, routes.py:475) puis assigné tel quel
(`col.attachment_fields = [f.model_dump() for f in body.attachmentFields]`,
routes.py:570). Exposé en lecture par `_collection_json()` (routes.py:153,
clé `"attachmentFields"`).

Édité côté shell dans `shell/src/shell/EditCollectionPanel.tsx` (314 lignes) :
état React `attachmentFields` (ligne 29), formulaire d'ajout à deux champs
(`draftKey`/`draftLabel`, lignes 30-31, fonction `addAttachmentField` ligne
80), liste avec bouton de suppression par ligne (`removeAttachmentField`,
ligne 89). **C'est le patron à reproduire pour le catalogue de métriques.**

### 1.4 Correction d'une prémisse du brainstorming : le versioning n'est PAS gratuit tel qu'annoncé

Le brainstorming affirmait : « `Collection.version` existe déjà et est bumpé
à chaque édition de collection — AUCUN nouveau mécanisme de version à
construire ». **Lecture directe du modèle (`models.py:68`) et de la route
(`routes.py:554`) : c'est faux.**

```python
version: Mapped[str] = mapped_column(String, default="", server_default="", nullable=False)
```

`version` est un champ **texte libre de métadonnées DCAT** (SP-41, ex. `"1.2.0"`
saisi par un humain sur la fiche de la collection — même famille que
`license`/`producer`/`lineage`), directement réassignable par
`PATCH /collections/{id}` (`("version", body.version)`, routes.py:554). Ce
n'est **pas** un compteur auto-incrémenté à chaque écriture (pas de
`version_id_col` SQLAlchemy, aucun mécanisme de ce type trouvé sur
`Collection` — contrairement aux `ConfigRevision` des items, qui ont un vrai
historique versionné, `ConfigHistoryPanel`). Aucune trace d'un bump
automatique nulle part dans `app/collections/`.

**Conséquence retenue pour ce plan** (cf. piège CLAUDE.md n°12 — le récit
prime trop souvent sur le code) : ce chantier ne construit **aucun nouveau
mécanisme de version** — l'intention du brainstorming (pas de nouvelle
infrastructure de versioning pour ce v0 spéculatif) est préservée, mais sa
justification littérale était fausse. La seule trace de changement du
catalogue de métriques restera l'entrée `audit_log` déjà émise par
`patch_collection` (action `"collection.update"`, payload
`body.model_dump(exclude_none=True, mode="json")`, routes.py:574-583) — un
changement de `body.metrics` y apparaîtra automatiquement dès lors que
`metrics` devient un champ de `CollectionPatch`, sans aucun code
supplémentaire. Ce n'est **pas** un historique versionné consultable
(pas de diff, pas de rollback) — juste un fait déjà vrai pour tout le reste
des métadonnées de collection, étendu ici par construction. Documenté comme
tel, pas présenté comme plus qu'il n'est.

### 1.5 Le wizard de requête visuelle ne passe PAS par `AggregateMeasure`

Découverte critique en explorant `QuerySummaryBuilder.tsx`/`inferSchema.ts`/
`compilePipeline.ts` : le générateur de résumé du wizard de requête visuelle
(SP-14o) **ne produit pas** un `AggregateRequestBody` consommé par
`POST /collections/{id}/aggregate`. Il compile `SummaryConfig`/`MetricConfig`
en un **pipeline** (`kind="pipeline"`, SP-15) via
`compileVisualQueryToPipeline()` (`compilePipeline.ts:60`), dont le nœud
`transform.aggregate` a pour params :

```python
class TransformAggregateParams(BaseModel):
    groupBy: list[str] = Field(default_factory=list)
    metrics: dict[str, str] = Field(default_factory=dict)  # alias -> expr SQL DuckDB brute
```

(`core/app/pipelines/ops/schemas.py:37`). `metricExpr()`
(`compilePipeline.ts:37`) compile chaque `MetricConfig` en une **chaîne SQL
DuckDB littérale** (`"sum(champ)"`, `"count(*)"`, `"quantile_cont(champ,
0.5)"`…) — un moteur d'exécution **entièrement distinct**
d'`app.analytics.aggregate`/`_agg_expr` (le pipeline runtime compile et
exécute ces chaînes lui-même, `core/app/pipelines/runtime.py` +
`compiler.py`, ~57 monkeypatchs de test existants, zone fragile documentée
par SP-43).

**Conséquence architecturale** (§4.4) : le sélecteur de métrique nommée dans
`QuerySummaryBuilder.tsx` ne peut pas — sans réécrire le compilateur de
pipeline et son runtime, hors budget de ce v0 spéculatif — envoyer un
`metricName` qui traverserait jusqu'au nœud `transform.aggregate`. Il agit
donc comme un **autofill côté client uniquement** : sélectionner une
métrique nommée copie sa définition stockée (`function`/`sourceColumn`/`p`)
dans les champs `MetricConfig` déjà existants ; le payload de pipeline
compilé est ensuite **strictement identique** à celui qu'aurait produit la
même métrique construite à la main. Aucun changement de schéma de pipeline,
aucun changement de runtime. Cela respecte la décision « un seul chemin
d'exécution » par construction : il n'existe pas de second chemin, puisque
le wizard n'envoie jamais `metricName` nulle part.

## 2. Décisions (reformulées, brainstorming + corrections ci-dessus)

1. **`Collection.metrics: list[NamedMetric]`**, colonne JSON/liste sur
   `Collection` (`core/app/collections/models.py`), patron exact
   `attachment_fields` (§1.3). `NamedMetric` a la forme d'`AggregateMeasure`
   plus un identifiant stable :

   ```python
   class NamedMetric(AggregateMeasure):
       name: str = Field(min_length=1, max_length=64)
   ```

   (hérite `field`/`agg`/`label`/`p` tels quels — jamais redéfinis en
   parallèle). Migration Alembic simple (nouvelle colonne, pas de nouvelle
   table), pas de RLS supplémentaire (les métriques voyagent avec la ligne
   `Collection`, déjà scopée `tenant_id`).

2. **`AggregateMeasure` gagne un champ optionnel `metricName: str | None =
   None`.** Une mesure de requête porte soit une définition ad hoc
   (`field`/`agg`/`p`, comme aujourd'hui), soit `metricName` — jamais les
   deux à la fois (exclusivité validée, §4.2). Résolution **strictement à
   l'intérieur de `_measures_for()`** (le point de passage unique déjà
   emprunté par les deux branches de `run_collection_aggregate` qui
   consomment des mesures, §1.1) : `_measures_for` reçoit désormais un
   paramètre optionnel `metrics_catalog: dict[str, AggregateMeasure] |
   None`, construit une fois par mesure `metricName` non nulle. Le
   `AggregateMeasure` résolu est produit **avant** tout appel à `_agg_expr` —
   aucun second générateur de SQL, aucun code dupliqué : c'est la garantie
   littérale demandée par le brainstorming, obtenue en résolvant à
   l'intérieur du seul endroit qui appelle déjà `_agg_expr`.

   `run_collection_aggregate(..., metrics_catalog: list[NamedMetric] | None
   = None)` — paramètre optionnel à mots-clé, tous les appelants existants
   restent valides sans modification. Seuls les appelants qui disposent
   d'un `Collection` réel (§1.2) passent `metrics_catalog=col.metrics` pour
   activer la résolution ; les autres continuent de fonctionner
   à l'identique (une mesure `metricName` y échouerait proprement avec
   `UnknownAggregateField`, jamais un flou silencieux).

3. **Portée retenue pour ce v0** (au-delà des deux endpoints cités
   littéralement par le brainstorming, après audit exhaustif §1.2) :
   - `POST /collections/{id}/aggregate` et `POST /collections/{id}/export`
     (`features/routes.py`) — cités par le brainstorming.
   - `run_analytics_query` (MCP, branche `collection`) — retenu : son propre
     docstring s'engage à « mirror POST /collections/{id}/aggregate, same
     query contract » ; le laisser diverger créerait exactement la classe de
     défaut que le piège CLAUDE.md n°4 documente (une garde/capacité posée
     sur une surface, jamais reportée sur sa jumelle).
   - `explain_dataset` (MCP) gagne une clé `"metrics"` (liste des
     `NamedMetric` de la collection) dans sa réponse — lecture seule,
     cohérent avec l'esprit du gap (rendre une couche sémantique
     découvrable par un agent avant qu'il construise une requête).
   - **Exclus explicitement de ce v0** (§5) : `alerts/jobs.py` (double site
     d'appel à synchroniser, risque réel sur un chemin de production
     silencieux) et `appexport/miniserver` (sérialiseur dupliqué
     indépendant, mode d'export marginal).

4. **Édition du catalogue** : `CollectionPatch.metrics: list[NamedMetric] |
   None = None` (`app/collections/schemas.py`), même mécanique que
   `attachmentFields` — dédoublonnage des `name` sans DB (model_validator),
   assignation directe dans `patch_collection`
   (`col.metrics = [m.model_dump() for m in body.metrics]`),
   **aucune validation de `field` contre les colonnes réelles au moment du
   PATCH** (décision explicite, §4.3 — cohérent avec le fait qu'une mesure
   ad hoc n'est elle-même jamais validée avant d'être exécutée : la
   validation de `field` reste au moment de la résolution/exécution,
   `_validate_fields`, comme pour toute mesure). `_collection_json()` gagne
   une clé `"metrics"`. Édition shell dans `EditCollectionPanel.tsx`, panneau
   additionnel au même patron que « Champs pièce jointe » (§1.3).

5. **Versioning** : aucun nouveau mécanisme (§1.4, corrige la prémisse du
   brainstorming). L'entrée `audit_log` `"collection.update"` déjà émise
   par `patch_collection` couvre gratuitement tout changement du
   catalogue — ni plus, ni moins que pour les autres champs de métadonnées
   de collection.

## 3. Hors périmètre explicite

- **Métriques cross-collection/jointures** : une métrique reste scopée à SA
  collection (`NamedMetric` n'a pas de `collectionId` propre — elle vit
  dans `Collection.metrics`, jamais référencée depuis une autre collection).
- **Gouvernance/workflow d'approbation** d'une métrique.
- **Lignage/documentation de métrique** (à qui elle sert, historique de
  changement au-delà de l'entrée `audit_log` déjà gratuite, §2.5).
- **Synchronisation avec un outil externe façon dbt.**
- **`alerts/jobs.py`** (§2.3) : `_measure_value` (exécution) et le calcul de
  libellé à la ligne 166 (`_measure_label(_measures_for(payload.query)[0])`)
  sont deux appels indépendants du même fichier qui devraient recevoir
  *exactement* le même `metrics_catalog` pour rester cohérents — sans quoi
  une `AlertRule` utilisant `metricName` verrait son évaluation réussir mais
  son libellé lever `UnknownAggregateField` (ou l'inverse selon lequel des
  deux reçoit le catalogue), silencieusement, sur un chemin déjà identifié
  comme fragile (procrastinate, notification best-effort séparée du commit
  de statut, SP-39). Risque jugé disproportionné pour la fonctionnalité la
  plus spéculative de cette session — reporté à une itération future si un
  besoin réel émerge.
- **`appexport/miniserver`** (§2.3) : nécessiterait de dupliquer l'ajout de
  la clé `metrics` dans le sérialiseur **indépendant**
  `appexport/snapshot.py::_collection_json` (39 lignes, déjà une copie
  distincte de `collections/routes.py::_collection_json`, aucune parenté de
  code) en plus du parsing côté `miniserver/main.py::aggregate`. Mode
  d'export marginal (Autoporté), aucun besoin remonté — exclu.
- **Routes ArcGIS live-query** (`harvest/routes.py`) : aucune `Collection`
  ne les adosse structurellement (§1.2) — `metricName` n'y a pas de sens.
- **`request.split`/`bins`/`sample`** : n'utilisent jamais `_measures_for`
  aujourd'hui (limitation pré-existante, §1.1) — `metricName` en hérite,
  ce n'est pas une régression de ce plan.
- **Widgets shell autres que le wizard** (`indicator.tsx`, `mapWidget.tsx`,
  `AlertRuleEditor.tsx`, `DataSourcePanel.tsx`) : ne gagnent aucun sélecteur
  de métrique nommée dédié dans ce v0, alors qu'ils bénéficieraient déjà
  silencieusement de `metricName` côté serveur (ils postent tous
  directement vers `POST /collections/{id}/aggregate`). Seul le décision
  brainstorming n°3 (wizard) est câblé côté UI ; l'extension aux autres
  écrans est un chantier UI ultérieur, non arbitré ici.
- **`name` de `NamedMetric`** : validé uniquement `min_length=1`/dédoublonné
  par collection — pas de regex d'identifiant (aucun précédent de ce type
  dans le dépôt pour un champ de cette famille, cf. `AttachmentFieldSpec.key`
  qui n'en a pas non plus ; ne pas inventer une convention non vérifiée,
  piège CLAUDE.md n°3).

## 4. Architecture détaillée

### 4.1 Migration Alembic `0041_collection_metrics.py`

Tête actuelle : `0040_share_links.py`. Nouvelle colonne, patron identique à
la migration d'`attachment_fields` (chercher son numéro exact pour copier le
style `upgrade()`/`downgrade()` — colonne `sa.Column("metrics",
sa.JSON(), nullable=False, server_default="[]")` sur `collections`,
`downgrade()` = `drop_column`). Testée upgrade/downgrade/upgrade sur base
non vide (piège CLAUDE.md n°8) : au moins une ligne `collections` existante
doit survivre avec `metrics == []` après l'upgrade.

`core/app/collections/models.py` :

```python
# Catalogue de métriques nommées (GAP-25, chantier sémantique minimal) — même
# forme qu'AggregateMeasure (app.analytics.aggregate) plus un identifiant
# stable ; résolu par metricName dans une requête d'agrégat. Patron JSON
# identique à attachment_fields ci-dessus (server_default="[]" en chaîne nue,
# jamais un cast "::json" — casse le DDL SQLite des tests, cf. commentaire
# attachment_fields).
metrics: Mapped[list] = mapped_column(
    JSON, default=list, nullable=False, server_default="[]"
)
```

### 4.2 `app/analytics/aggregate.py`

```python
class AggregateMeasure(BaseModel):
    field: str | None = None
    agg: str = "count"
    label: str | None = None
    p: float | None = None
    # GAP-25 : référence une NamedMetric de Collection.metrics par son name.
    # Exclusif avec field/agg/p (validé par _validate_fields) — une mesure
    # porte soit une définition ad hoc, soit une référence nommée, jamais les
    # deux à la fois.
    metricName: str | None = None


class NamedMetric(AggregateMeasure):
    name: str = Field(min_length=1, max_length=64)
```

`_validate_fields` (ligne 97) — ajouter, dans la boucle existante sur
`request.measures` (lignes 122-124), la garde d'exclusivité :

```python
for i, m in enumerate(request.measures or []):
    if m.metricName is not None and (m.field is not None or m.agg != "count" or m.p is not None):
        raise UnknownAggregateField(
            f"measures[{i}]", "metricName cannot be combined with field/agg/p"
        )
    check(m.field, f"measures[{i}].field")
    _validate_p(m.agg, m.p, f"measures[{i}].p")
```

(placée avant les deux lignes existantes — une mesure `metricName` valide a
`field=None`/`agg="count"`/`p=None`, donc `check`/`_validate_p` restent
inertes dessus comme aujourd'hui, sans changement de comportement pour les
mesures ad hoc.)

`_measures_for` (ligne 210) — nouvelle signature :

```python
def _measures_for(
    request: AggregateRequestBody,
    metrics_catalog: dict[str, AggregateMeasure] | None = None,
) -> list[AggregateMeasure]:
    raw = request.measures or [
        AggregateMeasure(field=request.field, agg=request.agg, label="value", p=request.p)
    ]
    catalog = metrics_catalog or {}
    resolved: list[AggregateMeasure] = []
    for i, m in enumerate(raw):
        if m.metricName is None:
            resolved.append(m)
            continue
        stored = catalog.get(m.metricName)
        if stored is None:
            raise UnknownAggregateField(
                f"measures[{i}].metricName", f"unknown metric '{m.metricName}'"
            )
        resolved.append(
            AggregateMeasure(
                field=stored.field,
                agg=stored.agg,
                p=stored.p,
                # Le libellé de sortie d'une métrique nommée retombe sur son
                # NOM (identifiant stable) plutôt que sur la dérivation
                # générique {agg}_{field} : la métrique garde une clé de
                # résultat stable même si sa définition (field/agg) change
                # plus tard dans le catalogue — c'est tout l'intérêt d'un
                # nom par rapport à une mesure ad hoc.
                label=m.label or stored.label or m.metricName,
            )
        )
    return resolved
```

Les deux call sites internes à `run_collection_aggregate` (lignes 492, 542)
passent désormais `metrics_catalog` — lui-même reçu en paramètre par la
fonction :

```python
def run_collection_aggregate(
    conn: duckdb.DuckDBPyConnection,
    *,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
    table_info: TableInfo,
    request: AggregateRequestBody,
    metrics_catalog: list[NamedMetric] | None = None,
) -> tuple[str | list[str], list[dict[str, Any]]]:
    ...
    catalog_by_name = {m.name: m for m in (metrics_catalog or [])}
    ...
    measures = _measures_for(request, catalog_by_name)
```

(remplace les deux appels `_measures_for(request)` existants). Paramètre
optionnel à mots-clé — **tous les appelants non listés en §2.3 restent
valides sans modification du tout** (appexport miniserver, alerts/jobs.py
inchangés dans ce plan).

### 4.3 `app/collections/schemas.py` + `routes.py`

`schemas.py` — importer `NamedMetric` depuis `app.analytics.aggregate`.
**Direction vérifiée contre le contrat de couches réel**
(`core/pyproject.toml`, section `[tool.importlinter]` du bloc `layers`) :
`app.collections` est listé **au-dessus** d'`app.analytics` (lui-même « placé
au plus bas du contrat », commentaire ligne ~275) — un import
`app.collections.schemas -> app.analytics.aggregate` va donc du haut vers le
bas, direction déjà autorisée par la contrainte de couches existante, sans
exemption nommée à ajouter. `app.analytics` a déjà deux exemptions nommées
dans l'autre sens (`app.analytics.aggregate -> app.collections.introspection`,
`app.analytics.sql_sandbox -> app.collections.introspection`) pour un cycle
de paquet différent (lecture de schéma de colonnes) — sans rapport avec cet
import-ci, qui n'a besoin d'aucune exemption. `CollectionPatch` gagne :

```python
metrics: list[NamedMetric] | None = None
```

```python
@model_validator(mode="after")
def _reject_duplicate_metric_names(self) -> "CollectionPatch":
    if self.metrics is None:
        return self
    names = [m.name for m in self.metrics]
    if len(names) != len(set(names)):
        duplicates = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"duplicate metric name(s): {', '.join(duplicates)}")
    return self
```

`routes.py::patch_collection` — ajouter `metrics` à l'assignation directe
(pas de validation contre les colonnes réelles, décision §2.4) :

```python
if body.metrics is not None:
    col.metrics = [m.model_dump() for m in body.metrics]
```

`_collection_json()` gagne `"metrics": col.metrics`.
`get_collection_schema`/`table_info_to_schema` **ne changent pas** — le
catalogue de métriques n'est pas un champ de schéma de colonnes, il est
exposé par `GET /collections/{id}` (déjà appelé par l'écran d'admin et par
tout consommateur qui charge la collection avant de construire une
requête).

### 4.4 `app/mcp/tools/analytics.py`

`run_analytics_query`, branche `collection` (lignes 94-120) : passer
`metrics_catalog=col.metrics` à `run_collection_aggregate` (ligne 108).

`explain_dataset`, branche `collection` (lignes 181-194) : ajouter
`"metrics": [m for m in col.metrics]` (ou la forme sérialisée équivalente)
au dict retourné — lecture seule, ne change aucune garde d'autorisation
existante (même `require_collection_read` déjà appelé).

### 4.5 Shell

`shell/src/api/types.ts` :

```ts
export type NamedMetric = {
  name: string;
  field: string | null;
  agg: string;
  label: string | null;
  p: number | null;
};
```

`CollectionAdmin.metrics: NamedMetric[]` (après `attachmentFields`, même
patron) ; `CollectionPatchInput.metrics?: NamedMetric[]`.

`shell/src/shell/EditCollectionPanel.tsx` : nouveau panneau « Métriques »,
même structure que « Champs pièce jointe » (§1.3) — état
`metrics = useState(collection.metrics ?? [])`, formulaire d'ajout
(name/agg/field conditionnel selon agg/p conditionnel si
`agg==="percentile"`, réutilisant `PercentileInput` déjà importé par
`QuerySummaryBuilder.tsx`), liste avec suppression par ligne, inclus dans le
payload `PATCH` déjà construit par ce composant. Toutes les nouvelles
chaînes visibles passent par `t()` (le détecteur i18n de `npm run lint`
couvre `shell/src/shell/`).

`shell/src/builder/visualQuery/QuerySummaryBuilder.tsx` : nouveau
sélecteur au-dessus de (ou à côté de) la ligne de métrique ad hoc existante
— liste des `NamedMetric` de la collection courante (prop supplémentaire
`namedMetrics: NamedMetric[]`, source : la `Collection` déjà résolue par la
page appelante). Choisir une entrée appelle `updateMetric(i, {...})` en
copiant `function`/`sourceColumn`/`p` depuis la métrique nommée dans les
champs `MetricConfig` existants (autofill, §1.5) — **aucun champ
`metricName` n'est ajouté à `MetricConfig`/`SummaryConfig`/`compilePipeline.ts`**,
le payload de pipeline compilé reste inchangé pour une sélection donnée.

Régénération obligatoire (piège CLAUDE.md n°1) :
```
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY=... uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Diff attendu non vide (nouvelle colonne `metrics` sur `CollectionAdmin`/
`CollectionPatchInput`, nouveau champ `metricName` sur `AggregateMeasure`
dans le schéma OpenAPI, nouvelle clé `metrics` dans la réponse
`explain_dataset` — celle-ci n'apparaît PAS dans l'OpenAPI REST, MCP
seulement, donc pas dans ce diff).

## 5. Critères d'acceptation

1. Migration 0041 : upgrade/downgrade/upgrade sur base non vide (au moins une
   ligne `collections` préexistante), `metrics == []` après upgrade initial.
2. `POST /collections/{id}/aggregate` avec une mesure `{"metricName":
   "total_ventes"}` référençant une entrée existante de `col.metrics` produit
   des lignes de résultat identiques (mêmes valeurs, même clé de colonne par
   défaut = le nom de la métrique) à la mesure ad hoc équivalente construite
   à la main — test d'équivalence explicite, pas seulement « ne lève pas ».
3. `POST /collections/{id}/aggregate` avec `{"metricName": "inconnu"}`
   échoue avec une erreur de validation propre (400, `unknown_field` —
   même mécanisme `_validation_error`/`UnknownAggregateField` que toute
   autre erreur de champ de cette route, `features/routes.py:118`, pas le
   422 générique de FastAPI/Pydantic, réservé aux erreurs de forme captées
   avant d'atteindre la route), jamais un 500 ni un résultat silencieusement
   vide.
4. `{"metricName": "x", "field": "y"}` (exclusivité) échoue avec une erreur
   de validation propre.
5. `POST /collections/{id}/export`, `run_analytics_query` (MCP) réussissent
   la même résolution `metricName` — testés indépendamment, pas supposés
   hérités par ressemblance de code.
6. `explain_dataset` (MCP) expose `col.metrics` dans sa réponse pour une
   dataset source `collection`.
7. `PATCH /collections/{id}` avec `metrics: [...]` contenant deux entrées de
   même `name` échoue (422, message explicite) sans toucher la DB.
8. `PATCH /collections/{id}` avec `metrics` valide persiste, `GET
   /collections/{id}` renvoie le catalogue à l'identique, et l'entrée
   `audit_log` `"collection.update"` correspondante porte `metrics` dans son
   payload.
9. `EditCollectionPanel.tsx` permet d'ajouter/lister/supprimer une métrique
   nommée, envoie le payload PATCH attendu.
10. `QuerySummaryBuilder.tsx` : sélectionner une métrique nommée renseigne
    les champs `function`/`sourceColumn`/`p` de la ligne courante ; le
    payload de pipeline compilé (`compileVisualQueryToPipeline`) pour cette
    sélection est **byte-for-byte identique** à celui produit par la même
    métrique construite à la main (test de non-régression explicite).
11. Aucun appelant non listé en §2.3 (`alerts/jobs.py`,
    `appexport/miniserver`, routes ArcGIS) n'est modifié par ce plan — un
    `grep` de contrôle en confirme l'absence de diff sur ces fichiers.
12. `uv run lint-imports` reste vert, sans nouvelle exception nommée
    (`app.collections -> app.analytics.aggregate` est déjà une direction
    autorisée par le contrat de couches actuel, §4.3).
13. Diff `openapi.json`/`core-schema.d.ts` non vide et cohérent avec les
    champs ajoutés (§4.5).
14. Suites complètes core + shell vertes, seuils de couverture non
    régressifs.

## 6. Auto-revue

- Pas de TBD : chaque décision du brainstorming a été reformulée avec un nom
  de fichier/ligne réel à l'appui, ou explicitement corrigée (§1.4, §1.5)
  avec la justification de la correction.
- Pas de contradiction : la portée §2.3/§3 est cohérente avec l'architecture
  détaillée §4 (aucun appelant hors liste n'est touché en §4).
- Portée bornée : 5 fichiers cœur (models.py, aggregate.py, schemas.py,
  routes.py de collections, tools/analytics.py) + 3 fichiers shell
  (types.ts, EditCollectionPanel.tsx, QuerySummaryBuilder.tsx) + 1 migration
  + régénération OpenAPI/TS. Aucune nouvelle table, aucun nouveau privilège,
  aucune nouvelle route.
- Pas d'ambiguïté restante : l'emplacement de `NamedMetric` (`app.analytics.
  aggregate`, importé depuis `app.collections.schemas`) a été vérifié contre
  le contrat de couches réel (`core/pyproject.toml`) plutôt que supposé —
  direction déjà autorisée, aucune exception nommée à ajouter (§4.3).
