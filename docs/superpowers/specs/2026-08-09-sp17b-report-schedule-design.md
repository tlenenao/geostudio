# SP-17b — `ReportSchedule` (rapports planifiés)

> Brainstorm du 2026-08-09. Deuxième tranche de SP-17 (« 3D & impression »),
> consomme le socle SP-17a (worker Playwright, `export_jobs`, `printLayout`)
> et le patron de planification/notification de SP-16b (`AlertRule` :
> `refreshPolicy`/`PipelineRefreshPolicy`, sweep procrastinate périodique,
> canaux `AlertChannel` webhook/email). Ferme le dernier morceau listé sous
> SP-17 dans `CLAUDE.md` (§« À venir »).

## Objectif

Un `ReportSchedule` cible un `Bookmark` existant (état analytique figé :
app + page + contexte temps/emprise/cross-filter, SP-14m) et le rend en PDF
sur un cron, en réutilisant tel quel le worker d'export Playwright de
SP-17a — puis notifie un ou plusieurs destinataires (email/webhook, canaux
réutilisés verbatim de SP-16b) avec un lien de téléchargement présigné.

C'est la dernière brique de la chaîne SP-16/SP-17 « Alertes & reporting » :
`AlertRule` (SP-16b, seuils) + exports secs (SP-16a) + `ReportSchedule`
(ce document, rapports PDF planifiés) couvrent l'intégralité du périmètre
décrit dans la feuille de route pour SP-16.

## Hors périmètre (assumé, non traité ici)

- **PDF multi-pages fusionné** (rendre chaque page d'une app `PageManager`
  séparément puis les assembler en un seul document). Décision arbitrée
  pendant le brainstorm : un `ReportSchedule` cible **un seul bookmark**
  (une app + une page + un contexte), pas une app entière toutes pages
  confondues. La pagination physique du PDF vient gratuitement de Chromium
  quand le contenu de cette unique page dépasse une page imprimée — aucune
  fusion, aucune nouvelle dépendance (`pypdf` notamment). Si un besoin réel
  de rapport multi-sections apparaît, c'est une extension future qui
  construira sur ce document sans le défaire.
- **Pièce jointe PDF dans l'email.** Le mail/webhook porte un lien de
  téléchargement présigné (même patron que le job d'export SP-17a), jamais
  le fichier lui-même — `app.alerts.notify.send_email` ne sait pas attacher
  de fichier aujourd'hui et rien ne justifie de l'étendre sans demande
  réelle (limites de taille SMTP notamment).
- **Format autre que PDF.** Un `ReportSchedule` produit toujours un PDF (pas
  de choix PNG comme le bouton d'export manuel) — le concept « rapport
  planifié » n'a de sens qu'en document.
- **Composant « canaux » généralisé.** Les champs email/webhook sont
  saisis en ligne dans `ReportScheduleEditor`, comme le fait déjà
  `AlertRuleEditor` — pas de nouvelle abstraction partagée tant qu'un
  troisième consommateur ne le justifie pas.
- **Gabarits/branding de rapport au-delà du `printLayout` déjà existant**
  sur l'app cible (titre, légende, échelle, cartouche) — cf. le risque déjà
  documenté dans la feuille de route (« scope creep du reporting »,
  différé explicite).
- **Retry indéfini d'une notification en échec** — une notification est
  tentée une fois par run, jamais rejouée en boucle (cf. §5).

## Décisions arbitrées pendant le brainstorm

| Question | Décision | Pourquoi |
|---|---|---|
| Pagination du PDF | Un seul bookmark (app+page+contexte) par `ReportSchedule`, pagination physique gratuite via Chromium | Zéro nouvelle dépendance, zéro boucle de rendu multi-URL ; le texte de la feuille de route (« sauts de page par section ») n'est pas un besoin prouvé — à réexaminer sur demande réelle |
| Livraison | Lien S3 présigné dans le mail/webhook, jamais de pièce jointe | Même patron que SP-17a et que les liens déjà utilisés ailleurs ; évite d'étendre `send_email` et les limites SMTP |
| Cible du rapport | Référence à un `Bookmark` existant (`bookmarkItemId`), pas de contexte dupliqué | Réutilise l'objet SP-14m tel quel, cohérent avec le nom `ReportSchedule` de la feuille de route (« état analytique figé (bookmark) ») ; le flux « Enregistrer la vue » → « Programmer un rapport » est un entonnoir naturel à deux étapes |

## Modèle de données

Nouveau kind `BuilderConfig` (le 9e, après `alert`) :

```
kind: "app" | "dashboard" | "map" | "site" | "dataset" | "bookmark"
     | "pipeline" | "alert" | "report"
```

```python
class ReportSchedulePayload(BaseModel):
    bookmarkItemId: str
    refreshPolicy: PipelineRefreshPolicy   # réutilisé verbatim (SP-15h/16b)
    channels: list[AlertChannel]           # réutilisé verbatim (SP-16b, webhook | email)

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "ReportSchedulePayload":
        if not self.channels:
            raise ValueError("report schedule requires at least one channel")
        return self
```

Aucun champ `appId`/`pageId`/`timeRange`/`crossFilter`/`printLayout` propre :
tout est résolu à l'exécution depuis le `Bookmark` référencé et l'`AppConfig`
qu'il cible (§4). Le format est toujours `pdf`, non configurable.

## 1. Extension du socle export (SP-17a)

`render_export_task` construit aujourd'hui l'URL de rendu comme
`{SHELL_BASE_URL}/apps/{item_id}?exportToken=...&exportRender=1` — pas de
sélection de page, pas de contexte bookmark. Côté shell, `AppRuntimePage`
accepte déjà un segment de route `:pageId?` optionnel (route
`/apps/:pk/:pageId?`, défaut = première page) et décode déjà `?ctx=` au
montage indépendamment de `exportRender` — les deux mécanismes (contexte
bookmark, rendu d'export) composent déjà **sans aucun changement shell**.

Changements `app.export`, additifs et rétrocompatibles :
- `ExportJob` gagne deux colonnes nullables : `page_id: str | None`,
  `ctx: str | None`. Nouvelle migration Alembic (colonnes nullables, aucun
  backfill) — **à exécuter et vérifier contre un vrai Postgres**, pas
  seulement SQLite en mémoire (leçon SP-17a round 1 : la migration
  `export_jobs` elle-même avait été oubliée).
- `render_export_task` ajoute `/{page_id}` et `&ctx={ctx}` à l'URL cible
  quand ces champs sont renseignés (`None` → comportement actuel inchangé,
  couvre le bouton d'export manuel existant).
- `render_export` (`app/export/rendering.py`) : `page.pdf(...)` ajoute
  `display_header_footer=True` avec un gabarit de pied de page minimal
  (date de génération) — le seul morceau d'« en-tête/pied » retenu dans ce
  périmètre resserré (pas de numérotation de section, puisqu'il n'y a
  qu'une seule page source).
- `export_repo.create_job`/`CreateExportRequest` (route REST) restent
  inchangés — `app.reports` appelle `export_repo.create_job(...)`
  directement avec `page_id`/`ctx` renseignés, puis commit, puis défère
  `render_export_task`, dupliquant la séquence commit-puis-defer déjà
  dupliquée telle quelle dans `app.pipelines`/`app.alerts` (pas de nouvelle
  fonction partagée — cohérent avec le style existant).
- **Bonus à coût quasi nul** : `export_repo.reclaim_stuck_jobs` (SP-17a,
  testé mais jamais appelé — TODO documenté dans `app/export/jobs.py`) est
  branché dans le nouveau sweep périodique de `app.reports` (§2), puisque
  SP-17b introduit la première tâche périodique qui touche `export_jobs`.
  Ferme ce suivi non bloquant sans travail dédié.

## 2. Planification & notification

Nouveau module `core/app/reports/` :

- **Table `report_runs`** (nouvelle migration Alembic) :
  `id, tenant_id, report_item_id, export_job_id, notified_at, created_at`.
  Pas de colonnes dupliquées (status/erreur/lien) — lues en joignant la
  ligne `export_jobs` référencée, même discipline que `pipeline_runs`/
  `get_latest_run` (SP-15h).
- **Une tâche périodique** (`@app.periodic(cron="*/5 * * * *")`, queue
  `etl`, no-op si `is_read_only_mode()`), deux étapes par tick :

  1. **Déclenchement** — `list_due_reports` (mirroir exact de
     `list_due_rules` : `croniter` contre le `created_at` du dernier
     `report_runs`, ignore les `refreshPolicy.enabled=false`). Pour chaque
     rapport dû :
     - résout le propriétaire de l'item `report` (mirroir de `_owner_user`)
       et **re-vérifie `can(owner, read, bookmark)` et
       `can(owner, read, app_cible)`** — un rapport dont le propriétaire a
       perdu l'accès entre-temps échoue proprement (évaluation en erreur,
       jamais un rendu silencieusement hors droits) ;
     - résout `appId`/`pageId`/`ctx` depuis le `BookmarkPayload` référencé ;
     - crée la ligne `export_jobs` (avec `page_id`/`ctx`) + une ligne
       `report_runs`, **commit**, puis **defer** `render_export_task` —
       même règle commit-avant-defer que partout ailleurs (SP-15h) ;
     - appelle `export_repo.reclaim_stuck_jobs()` (bonus §1).
  2. **Notification** — pour chaque `report_runs` où `notified_at IS NULL`
     et dont l'`export_jobs` joint est `done` ou `error` : envoie chaque
     canal (`app.alerts.notify.send_email`/`send_webhook`, réutilisés
     verbatim — succès → lien présigné dans le corps/payload, échec →
     message d'erreur), audite chaque tentative par canal (même forme que
     `AlertRule` : `{channel, success, error}`), puis pose `notified_at`
     **après la tentative, quel que soit le résultat par canal**. Pas de
     nouvelle tentative au tick suivant — une notification n'est jamais
     rejouée indéfiniment (évite qu'un webhook cassé de façon permanente
     ne devienne un déni de service applicatif sur le sweep).

Positionnement dans le contrat de couches import-linter
(`core/pyproject.toml`) : `app.reports` inséré **au-dessus de `app.alerts`**
(donc aussi au-dessus de `app.export`, déjà sous `app.alerts`) — seul
positionnement qui lui permet d'importer `app.alerts.notify` et
`app.export.{repository,jobs}`.

## 3. API cœur, MCP

- **CRUD** : entièrement les routes génériques `/configs` (kind="report")
  — comme `AlertRule`/`Pipeline`, aucune route de création/édition/
  suppression bespoke.
- **`GET /reports/{item_id}/runs`** (mirroir de
  `GET /alerts/{item_id}/evaluations`) : historique des runs, statut/lien
  présigné/erreur lus par jointure sur `export_jobs`.
- **MCP `explain_report_schedule`** (lecture seule, mirroir
  `explain_alert_rule`/`explain_pipeline`) : bookmark cible, planification,
  canaux, dernier run.

## 4. Shell

- **`ReportScheduleEditor.tsx`** (mirroir du style inline de
  `AlertRuleEditor` — pas de nouveau composant « canaux » généralisé) :
  sélecteur des bookmarks de l'utilisateur (même source que
  `BookmarksPage`), champs email/webhook en ligne, `PipelineScheduleEditor`
  réutilisé tel quel pour le cron.
- **Point d'entrée** : action « Programmer un rapport » sur chaque ligne de
  `BookmarksPage` (« Mes vues »), pré-remplissant `bookmarkItemId` — même
  logique d'entonnoir contextuel que `AlertRuleEditor` depuis
  `DatasetEditPage`.
- **Route `/reports`** : `CatalogPage` avec `fixedType="report"` (« Mes
  rapports »), même patron que `/bookmarks`.
- **Panneau d'historique des runs** (mirroir `PipelineRunPanel`) sur la
  page d'édition du rapport, poll `GET /reports/{id}/runs`.
- Aucun changement à `AppRuntimePage`/`MapEditorPage`/au bouton d'export
  manuel — la composition `ctx`+`pageId`+`exportToken` fonctionne déjà.

## 5. Sécurité, permissions, audit

- Permission re-vérifiée **au moment du déclenchement** (pas seulement à la
  création du `ReportSchedule`), sur les droits du **propriétaire** de
  l'item `report` — mirroir exact du patron `AlertRule` (§2).
- Chaque déclenchement et chaque tentative de notification écrit une
  entrée `audit_log` (`action="report.run"` / `"report.notify"`).
- Le rendu lui-même hérite de toutes les garanties déjà en place côté
  `app.export` (jeton scopé item+utilisateur, TTL court, aucune credential
  à droits larges pour le worker Playwright).
- `CORE_EXPORT_ENABLED=false` : le sweep continue de créer des
  `export_jobs`, qui échouent immédiatement en `error` (`render_export_task`
  vérifie déjà `is_export_enabled()`) — un `ReportSchedule` planifié alors
  que la capacité export est désactivée échoue proprement à chaque tick,
  jamais un job silencieusement ignoré.

## Tests

TDD cœur :
- `ReportSchedulePayload` : validation (au moins un canal), round-trip
  Pydantic.
- `list_due_reports` : due au premier tick, respecte `refreshPolicy.enabled`,
  cadence cron correcte contre le dernier `report_runs.created_at`.
- Sweep déclenchement : permission propriétaire révoquée → pas de job créé,
  entrée d'erreur ; permission ok → `export_jobs`+`report_runs` créés,
  commit avant defer (vérifié par mock du deferrer, même patron que les
  tests `app.pipelines`/`app.alerts`) ; `page_id`/`ctx` correctement résolus
  depuis le bookmark.
- Sweep notification : `done` → email/webhook appelés avec le lien
  présigné, `notified_at` posé ; `error` → canaux appelés avec le message
  d'erreur ; échec de tous les canaux → `notified_at` quand même posé, pas
  de re-tentative au tick suivant ; audit_log écrit par tentative de canal.
- `render_export_task`/`render_export` : URL avec `page_id`/`ctx` présents
  vs absents (rétrocompatibilité de l'export manuel) ; `display_header_footer`
  et gabarit de pied de page passés à `page.pdf(...)`.
- Migration Alembic (`export_jobs.page_id`/`ctx`, `report_runs`) exécutée
  contre un vrai Postgres (pas seulement SQLite en mémoire).

E2E Playwright (nouvelle spec, ou extension de `dataset-export.spec.ts`) :
- Créer un bookmark, programmer un rapport dessus (canal webhook simple à
  observer en E2E), déclencher le sweep (ou avancer artificiellement le
  cron), vérifier qu'un run apparaît `done` avec un lien de téléchargement,
  et que la notification a été envoyée.

## Critères d'acceptation

- Un rapport hebdomadaire PDF planifié sur un bookmark arrive par email
  (lien de téléchargement) à l'heure prévue par le cron, avec l'état
  analytique figé attendu (mêmes filtres/emprise/temps que le bookmark).
- Un `ReportSchedule` dont le propriétaire a perdu l'accès à l'app cible
  échoue proprement (aucun rendu, erreur journalisée) plutôt que de
  continuer à produire des rapports.
- Un canal de notification cassé (webhook injoignable) ne bloque ni ne
  boucle le sweep — l'échec est audité et le run passe à notifié sans
  retenter indéfiniment.
- `CORE_EXPORT_ENABLED=false` : les rapports planifiés échouent proprement
  à chaque tick plutôt que d'être exécutés hors capacité.

## Risques

| Risque | Garde-fou |
|---|---|
| Chevauchement de runs si un rendu précédent reste bloqué (le TODO reclaim de SP-17a n'était pas encore branché) | `reclaim_stuck_jobs` désormais appelé à chaque tick du sweep (§1 bonus) — un job `running` trop vieux est nettoyé avant le tick suivant |
| Notification jamais retentée après un échec transitoire (SMTP temporairement indisponible) | Accepté explicitement (§5, non-but) — cohérent avec la cadence hebdo/quotidienne typique d'un rapport ; un besoin réel de retry sera une extension future |
| Un bookmark supprimé après qu'un `ReportSchedule` le référence | Le déclenchement échoue proprement (item introuvable → erreur journalisée), même discipline que les autres références d'item du projet (`datasetItemId` sur `AlertRule` notamment) |
| Duplication du footer PDF minimal si un futur besoin de mise en page plus riche apparaît | Fonction de rendu (`render_export`) reste pure et testable indépendamment — étendre le gabarit ne touche pas au flux de planification |
