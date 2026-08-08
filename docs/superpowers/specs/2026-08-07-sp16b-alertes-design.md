# SP-16b — Alertes (`AlertRule`) (design)

> **Date : 2026-08-07 · Statut : validé (brainstorm)**
> Deuxième et **dernière** sous-partie de **SP-16 — Alertes & reporting**
> (feuille de route, jalon **M12**, brainstorm Analytics Platform 2026-07-09
> §4.6/§7 vague 2, arbitrage **A30**).
>
> **Correction de la découpe annoncée par le spec SP-16a**
> (`2026-08-07-sp16a-export-serveur-design.md`, en-tête) : ce document
> proposait à l'origine « 16b — `ReportSchedule` », « 16c — `AlertRule` ».
> Renumérotée en session avec Tanguy : **`ReportSchedule` (rapports
> planifiés, PDF de dashboards paginés) part entièrement dans SP-17**, où
> elle pourra s'appuyer directement sur le worker Playwright/`PrintLayout`
> plutôt que d'être construite deux fois (une fois en CSV/XLSX-only ici,
> une fois étendue au PDF là-bas). **SP-16b = `AlertRule` seul, et clôt
> SP-16** — il n'y a pas de 16c. Le socle export de SP-16a (routes
> `/export`/`/export/items`, sérialisation CSV/XLSX/GeoJSON/GPKG) reste la
> brique que `ReportSchedule` réutilisera en SP-17 ; rien n'est perdu dans
> ce renommage, seul l'endroit où le travail restant est planifié change.
>
> Références : feuille de route (§SP-16, A30) · brainstorm Analytics
> Platform (`2026-07-09-brainstorm-geostudio-analytics-platform.md` §2.1
> Grafana/l'alerte, §4.6 Reporting & diffusion, §4.7 transverses, §7 roadmap
> vague 2) · `CLAUDE.md` (règles d'architecture #1-4, arbitrages figés) ·
> SP-16a (`app.analytics.export`, patron des deux modes agrégé/entités
> brutes — non réutilisé ici, l'alerte ne produit pas de fichier) · SP-15a/h
> (`app.pipelines.jobs` : sweep périodique procrastinate, `RefreshPolicy`,
> patron commit-avant-defer) · SP-15a (`app.pipelines.expr_validation`,
> `app.analytics.sql_sandbox` : expression scalaire SQL bornée — **corrige
> une prémisse erronée de ce document avant écriture** : il n'existe **pas**
> de moteur CEL côté cœur, seulement côté shell (`cel-js`, `visibleWhen`) ;
> l'expression de condition suit le même mécanisme que
> `transform.filter`/`derive`, pas CEL) · SP-15e (`app.secrets` : union
> discriminée `SecretPayload`, additive) · SP-15f (`app.pipelines.egress` :
> garde SSRF dupliquée par couche, patron à reproduire côté sortant) ·
> SP-11b/SP-14a (`app.analytics.aggregate.run_collection_aggregate`,
> `AggregateRequestBody` — fonction pure réutilisable hors contexte HTTP) ·
> SP-12d/harvest (`live_query.translate_aggregate_query`,
> `_resolve_arcgis_dataset` — chemin agrégé arcgis, hors DuckDB).

## 1. Objectif & non-buts

**Objectif.** Un objet de plateforme `AlertRule` (dataset + condition de
seuil + fréquence) évalué périodiquement en tâche de fond, qui notifie par
webhook et/ou email au passage `ok→firing`/`firing→ok`, journalisé dans
`audit_log`. Critère de sortie (M12, reformulé pour ce périmètre resserré) :
une alerte de seuil sur un dataset se déclenche dans le cycle de sweep qui
suit le franchissement, notifie, et est journalisée.

**Non-buts explicites** :

- `ReportSchedule`, rapports planifiés, PDF de dashboards paginés — SP-17
  (cf. correction de découpe en en-tête).
- Prédicat spatial (« entité entre/sort d'une zone », géofencing léger,
  §2.1 du brainstorm) — décision produit : seuils attributaires/agrégés
  d'abord ; le géofencing a un chemin d'évaluation différent (par entité,
  pas par agrégat) et suivra en increment séparé si un besoin réel
  apparaît.
- Alerte multi-séries / par groupe (une alerte qui suit chaque valeur
  distincte d'un `groupBy`, façon alerting par série Grafana) — v1 évalue
  **un scalaire unique** par règle ; qui veut suivre plusieurs communes
  crée plusieurs règles (chacune filtrée) plutôt que la plateforme ne gère
  un état ok/firing par groupe.
- Ré-notification pendant que l'état reste stable — seule la transition
  notifie (§5).
- Nouvel outil MCP de création (`create_alert_rule`) — seul un outil de
  lecture (`explain_alert_rule`) est construit ici ; la création reste
  discipline "ferme le scope minimal", additif si un besoin agent concret
  apparaît.
- Nouveau flag de capacité instance-wide (type `CORE_ETL_ENABLED`) — les
  alertes sont une fonctionnalité de base comme l'export SP-16a, pas une
  capacité expérimentale togglable ; seule la garde `is_read_only_mode()`
  déjà systématique sur tout sweep périodique s'applique.

Le modèle reste additif : rien ici ne doit devoir être défait pour
construire `ReportSchedule` en SP-17.

## 2. Modèle de données

**`AlertRule` : 8ᵉ `kind` de `BuilderConfig`** (`app.configs.schemas`),
aux côtés de `app`/`dashboard`/`map`/`site`/`dataset`/`bookmark`/`pipeline`
— règle d'architecture #2 (tout objet de plateforme est un document
déclaratif schématisé), même patron que `PipelinePayload`/`BookmarkPayload`
(un payload optionnel typé sur `BuilderConfig`, jamais un nouveau document
racine) :

```python
class AlertCondition(BaseModel):
    # Expression scalaire SQL bornée, même mécanisme que
    # app.pipelines.expr_validation.validate_bounded_expr (SP-15a) :
    # UNE expression enveloppée dans SELECT (expr) sans FROM, jamais une
    # référence de table. Binding disponible : `value` (le scalaire produit
    # par la requête agrégée ci-dessous). Ex. "value > 100".
    expr: str

class AlertChannelWebhook(BaseModel):
    kind: Literal["webhook"] = "webhook"
    url: str

class AlertChannelEmail(BaseModel):
    kind: Literal["email"] = "email"
    to: str
    smtpSecretName: str   # résolu par nom à l'envoi seulement (§5)

class AlertRulePayload(BaseModel):
    datasetItemId: str                        # référence un item kind="dataset" existant
    query: AggregateRequestBody                # même contrat que /aggregate — réutilisé tel quel
    condition: AlertCondition
    refreshPolicy: PipelineRefreshPolicy       # réutilisé verbatim (enabled + cron + validation croniter)
    channels: list[AlertChannelWebhook | AlertChannelEmail]
    messageTemplate: str = "Alert {ruleName}: value={value} ({state})"

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "AlertRulePayload":
        if not self.channels:
            raise ValueError("alert rule requires at least one channel")
        return self
```

`query` réutilise **exactement** `AggregateRequestBody`
(`app.analytics.aggregate`) — même contrat que celui déjà envoyé par les
widgets à `/aggregate`. Contrainte propre à l'usage alerte : le résultat
doit se réduire à **une seule ligne** (pas de `groupBy` à plusieurs valeurs
distinctes) — validée à la sauvegarde par une requête à blanc contre le
schéma introspecté du dataset (même mécanisme que la validation de
`filters`/`groupBy` déjà faite par `_validate_fields`), pas seulement à
l'évaluation.

**`alert_evaluations`** — nouvelle table, même patron que `pipeline_runs`
(SP-15a) : `id`, `tenant_id`, `alert_rule_item_id`, `created_at`, `value`
(float nullable — nul si erreur), `state` (`"ok"|"firing"`), `transitioned`
(bool), `error` (text nullable). Aucune colonne dupliquée sur la config ;
« état courant » et « dernière notification » se dérivent **toujours** de
la dernière ligne (`get_latest_evaluation`, miroir de
`pipelines_repo.get_latest_run`) — jamais un champ `lastState` écrit à deux
endroits qui pourrait diverger.

## 3. Boucle d'évaluation

Reprise verbatim du patron SP-15h (`app.pipelines.jobs`), dans un nouveau
module `app.alerts.jobs` :

```python
@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl")
def sweep_alert_rules_task(timestamp: int) -> None:
    if is_read_only_mode():
        return
    with request_scoped_session(session_factory) as session:
        due = alerts_repo.list_due_rules(session)   # miroir list_due_pipelines
        for item_id, tenant_id in due:
            evaluation = alerts_repo.create_evaluation(session, ...)
            session.commit()   # commit AVANT defer — bug SP-15h Important #2 déjà corrigé, ne pas le réintroduire
            evaluate_alert_task.defer(evaluation_id=evaluation.id, tenant_id=tenant_id)
```

`list_due_rules` reprend `list_due_pipelines` presque à l'identique : scan
cross-tenant `list_configs_by_kind(kind="alert")`, `refreshPolicy.enabled`,
comparaison à `get_latest_evaluation`, même garde de réclamation par âge
(`_RUNNING_RECLAIM_MINUTES`) pour une évaluation restée bloquée. Queue
`etl` réutilisée telle quelle (pas de nouvelle file) — le volume attendu
(un scalaire par règle, pas un pipeline complet) est largement dans son
budget actuel.

`evaluate_alert_task(evaluation_id, tenant_id)` :

1. Recharge la règle (`AlertRulePayload`) et réévalue les droits du
   **propriétaire de la règle** (même garde double-vérification que
   `_acting_user` en SP-15a — si le propriétaire a perdu l'accès au dataset
   depuis la sauvegarde, l'évaluation échoue proprement, journalisée
   `error`, jamais un contournement admin implicite).
2. Exécute `query` :
   - Dataset `source="collection"` → `run_collection_aggregate` en process
     (DuckDB, `app.analytics.aggregate`), exactement le chemin déjà emprunté
     par `POST /collections/{id}/aggregate` — pas d'appel HTTP interne.
   - Dataset `source="arcgis"` → `live_query.translate_aggregate_query` +
     client httpx construit manuellement (miroir de
     `get_dataset_arcgis_aggregate`, sans les `Depends` FastAPI — même
     reconstruction manuelle que `run_pipeline_task` fait déjà pour
     `_acting_user`/le client S3).
   - Le résultat doit être une seule ligne (contrainte §2) → une seule
     valeur `value`.
3. Évalue `condition.expr` contre `value` via le même AST DuckDB borné que
   `app.pipelines.expr_validation.validate_bounded_expr` (§4 — la fonction
   elle-même n'est pas forcément importable telle quelle selon où
   `app.alerts` se place dans le contrat de couches import-linter ; à
   trancher en planification, cf. §4).
4. Compare au dernier état connu (`get_latest_evaluation`) → détermine
   `transitioned`.
5. Écrit la ligne `alert_evaluations`.
6. Si `transitioned` → déclenche la notification (§5), elle-même journalisée
   (succès/échec) dans `audit_log`.

Toute exception inattendue marque l'évaluation `error`, jamais une ligne
manquante ni un run "zombie" — même discipline que
`run_pipeline_task`/SP-6a.

## 4. Condition — expression scalaire bornée, pas CEL

Prémisse corrigée avant d'écrire ce document (cf. en-tête) : il n'existe
**aucun moteur CEL côté cœur**. Le seul CEL du projet tourne dans le shell
(`cel-js`, `visibleWhen`/colonnes calculées du builder). `condition.expr`
suit donc **le même principe** que celui déjà construit pour
`transform.filter`/`transform.derive`/`transform.aggregate.metrics`
(SP-15a, `app.pipelines.expr_validation.validate_bounded_expr`) : une
expression scalaire SQL DuckDB, dont la validation n'est en réalité qu'un
usage restreint des primitives **layer-free**
`app.analytics.sql_sandbox.parse_ast`/`validate_select_only`/
`collect_table_refs` (aucune référence de table autorisée) — `app.analytics`
n'est pas dans le contrat de couches import-linter (§ pyproject.toml, comme
`app.db`), donc directement importable par `app.alerts` sans ambiguïté de
couche. Point à trancher en planification, pas ici : soit `app.alerts`
importe `app.pipelines.expr_validation.validate_bounded_expr` tel quel (si
la position choisie pour `app.alerts` dans le contrat de couches
l'autorise), soit il en duplique le wrapper de 4 lignes par-dessus les
mêmes primitives `sql_sandbox` — même arbitrage, et même idiome assumé
(« dupliquer plutôt que forcer une couche »), que la duplication de
`app.harvest.egress` vers `app.pipelines.egress` en SP-15f. Le binding
`value` est fourni en substituant le scalaire mesuré dans l'expression
avant validation/exécution (`SELECT ({expr})` avec `value` remplacé par le
littéral SQL du float, même style que `_sql_lit` dans
`app.analytics.aggregate`) — pas de moteur d'expression à variables, juste
une requête DuckDB à une ligne.

`messageTemplate` : simple substitution de chaîne (`str.format`-like sur un
dictionnaire fermé `{ruleName, value, state, datasetName}`), pas
d'interprétation d'expression — cohérent avec l'absence de CEL serveur.

## 5. Notification — transition seule, deux canaux

**Règle de re-notification.** Une notification part uniquement quand
`transitioned=True` (`ok→firing` ou `firing→ok`) — jamais à chaque tick de
sweep tant que l'état reste stable. Calculé en comparant `state` de la
nouvelle évaluation à `state` de `get_latest_evaluation` (avant écriture de
la nouvelle ligne).

**Webhook** — nouveau module `app.alerts.egress`, duplication délibérée de
`app.pipelines.egress` (même raison que SP-15f : `app.alerts` a sa propre
position dans le contrat de couches import-linter, dupliquer la garde SSRF
coûte moins cher que de la faire traverser une frontière). Variable dédiée
`CORE_ALERTS_EGRESS_ALLOWLIST` (distincte de
`CORE_PIPELINES_EGRESS_ALLOWLIST`/`CORE_HARVEST_EGRESS_ALLOWLIST`, même
motif de duplication assumée que les deux précédentes). POST JSON
`{ruleName, state, value, message}` vers `channel.url` après
`assert_egress_allowed`.

**Email** — nouvelle variante additive sur l'union discriminée
`SecretPayload` (`app.secrets.schemas`, SP-15e) :

```python
class SmtpCredentialsPayload(BaseModel):
    kind: Literal["smtp"] = "smtp"
    host: str
    port: int
    username: str
    password: str
    useTls: bool = True
    fromAddress: str
```

Aucune migration (union Pydantic, pas un nouveau type de colonne — même
mécanisme que les 5 variantes existantes). Résolu **par nom** au moment de
l'envoi seulement (`smtpSecretName`, jamais à la sauvegarde de la règle) —
même discipline que SP-15f pour l'auth des connecteurs. Envoi via
`smtplib` (stdlib, **aucune nouvelle dépendance** `pyproject.toml`) —
`SMTP`/`SMTP_SSL` selon `useTls`, un message texte simple
(`email.message.EmailMessage`), pas de HTML/pièce jointe (cohérent avec
« pas de PDF/fichier joint en SP-16b », §1).

Chaque tentative de notification (webhook ou email, succès ou échec) écrit
une entrée `audit_log` (`action="alert.notify"`, payload
`{channel: "webhook"|"email", state, success}`) — exigence transverse du
brainstorm §4.7.

## 6. REST + MCP

`AlertRule` obtient gratuitement les 3 routes CRUD génériques que tout
`kind` de `BuilderConfig` a déjà via `app.configs` — rien de spécifique à
écrire là. Une seule route nouvelle :

- `GET /alerts/{itemId}/evaluations` — historique paginé
  (`alert_evaluations` DESC), consommé par le badge d'état + le journal
  côté shell (§7).

MCP : `explain_alert_rule` (lecture seule, même forme que
`explain_pipeline`/`explain_dataset` — dataset, condition, fréquence,
dernier état). Pas de `create_alert_rule` (non-but §1).

## 7. Shell — section « Alertes » sur `DatasetEditPage`

Même placement que la section Export de SP-16a (pas de nouvelle page, pas
de nouvelle entrée de nav, pas de changement canvas) :

- Liste des règles du dataset courant : nom, résumé de condition
  (`{field} {comparator} {threshold}`, dérivé de `condition.expr` pour
  l'affichage — pas un second champ structuré séparé, juste un parseur
  d'affichage best-effort côté shell), badge d'état (ok/firing, couleur),
  horodatage du dernier déclenchement.
- Formulaire de création/édition, inline (pas de modal dédiée) :
  champ/comparateur/seuil (réutilise les mêmes contrôles que le
  configurateur de requête agrégée des widgets chart/kpi — même
  `AggregateRequestBody` bindé), fréquence via `PipelineScheduleEditor`
  (SP-15h, 3 préréglages + mode cron avancé, réutilisé tel quel), champs
  canal (URL webhook et/ou secret SMTP + destinataire).
- Erreurs de sauvegarde affichées près du bouton Enregistrer, même patron
  que l'Export (SP-16a Task 12) et le scheduling (SP-15h).

## 8. Tests

- **Cœur (pytest, TDD)** : sweep/`list_due_rules` (garde de reclaim par
  âge, commit-avant-defer — reproduire explicitly le test de régression
  offset/concurrence de SP-15h, ne pas juste faire confiance au copier-
  coller du patron) ; évaluation de condition (`validate_bounded_expr`
  réutilisé, cas rejeté : référence de table) ; machine à états (ok→firing,
  firing→ok, stable→pas de notification) ; garde SSRF webhook (mêmes cas
  que SP-15f : IP privée, DNS résolvant en interne) ; envoi SMTP (transport
  mocké, jamais un vrai serveur SMTP en test) ; `audit_log` écrit pour
  chaque évaluation ET chaque tentative de notification.
- **Shell (Vitest)** : section Alertes de `DatasetEditPage` — liste, badge
  d'état, formulaire de création, erreurs de sauvegarde.
- **E2E (Playwright, obligatoire — feature visible, CLAUDE.md)** : nouvelle
  spec `alert-rule.spec.ts` — créer une règle, déclencher via fixture
  (mock du sweep ou évaluation directe), vérifier le badge firing dans
  `DatasetEditPage`. Specs E2E existantes restent vertes (aucun changement
  de schéma de config existant, `AlertRule` est un nouveau `kind` additif).

## 9. Risques

| Risque | Garde-fou |
|---|---|
| Webhook = POST sortant vers une URL fournie par l'utilisateur → SSRF | `app.alerts.egress`, garde dupliquée identique à SP-12/SP-15f, `CORE_ALERTS_EGRESS_ALLOWLIST` dédiée |
| Nouvelle dépendance implicite (bibliothèque email tierce) | `smtplib` stdlib — aucune dépendance `pyproject.toml` ajoutée |
| Confusion entre condition scalaire et CEL (le reste de la plateforme utilise CEL côté shell) | §4 documente explicitement l'absence de CEL serveur ; le champ s'appelle `expr` (SQL), jamais nommé `cel`/`condition.cel` dans le schéma pour éviter l'ambiguïté |
| Chemin arcgis de l'évaluation reconstruit manuellement un client httpx hors FastAPI `Depends` | Même reconstruction déjà faite par `run_pipeline_task` pour `_acting_user`/S3 — patron éprouvé, pas un nouveau risque |
| Re-notification bruyante si le calcul de transition a un bug | Testé explicitement en RED (condition reste vraie 3 sweeps de suite → une seule notification) avant tout GREEN |
| Duplication future avec `ReportSchedule` (SP-17) si mal isolé | Le sweep/scheduling (§3) et l'egress (§5) sont conçus comme des modules indépendants de l'objet `AlertRule` lui-même, pour que SP-17 les référence en patron plutôt qu'en copiant `app.alerts` tel quel |
