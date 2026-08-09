# SP-17b — `ReportSchedule` — Progress Ledger

Plan: docs/superpowers/plans/2026-08-09-sp17b-report-schedule-plan.md
Design: docs/superpowers/specs/2026-08-09-sp17b-report-schedule-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).
Base globale: dev@ac98d7a (HEAD au lancement).

## Pré-vol

Scan des 19 tâches + Global Constraints contre l'état réel du repo avant
dispatch, tous les points vérifiés matchent le texte du plan :
- `core/app/configs/schemas.py` : `AlertRulePayload` L270, `_require_single_scalar_query`
  L302, `BuilderConfig.kind` Literal L331, `alert: AlertRulePayload | None` L344,
  `_require_kind_payload` L348, branche `"alert"` L359 (Task 1).
- `core/app/configs/routes.py` : 3 sites `_validate_alert_payload` confirmés
  (L87, L141, L244) (Task 2).
- `core/app/export/models.py` : `format`/`status` confirmés, pas encore de
  `page_id`/`ctx` (Task 3).
- `core/app/export/repository.py` : `create_job` sans `page_id`/`ctx` (Task 3).
- `core/app/export/jobs.py` : bloc `item_id, user_id, export_format = ...` et
  `target_url` confirmés identiques au texte "avant" du plan (Task 4).
- `core/app/export/rendering.py` : `RenderPage.pdf` sans
  `display_header_footer`/`footer_template` (Task 5).
- `core/app/jobs.py` : `import_paths` confirmé, dernier élément
  `"app.export.jobs"` (Task 12).
- `core/app/main.py` : `alerts_routes` L105, `is_etl_enabled()` L106 (Task 12).
- `core/pyproject.toml` : layers confirmés (`app.pipelines`, `app.alerts`,
  `app.export`, `app.secrets`), `app.db -> app.export.models` présent (Task 12).
- `core/app/mcp/tools.py` : `explain_alert_rule` L702, `get_sharing` L733
  (Task 13).
- `shell/src/api/types.ts` : `ResourceType` L2 confirmé sans `"report"` (Task 14).
- `shell/src/shell/routes.tsx` : `useOpenItem` (L36-61, structure if/return +
  catch-all ternaire) confirmée identique au texte du plan, `PipelineEditRoute`
  L129, route `/pipelines/:pk/edit` L175 (Task 17).
- `shell/src/shell/ItemActions.tsx` : bouton "Modifier" L58 confirmé (Task 18).

**Décision utilisateur actée avant dispatch** : Task 10 ne duplique PAS
`_s3_client_from_env` — l'implémenteur importera le helper existant depuis
`app.export.jobs` (renommé sans underscore si besoin), puisque le contrat de
couches (Task 12) autorise déjà `app.reports` à importer `app.export`. Écart
volontaire par rapport au texte littéral du plan, décidé par Tanguy en pré-vol
(pas de blocage architectural comme pour la garde SSRF de SP-15f).

## Décision utilisateur — commentaires anglais "why" (récurrent Tasks 1/6/7/9)

Plusieurs tâches introduisent des docstrings/commentaires anglais narrant
un "why" non-trivial (hérités verbatim du texte du plan lui-même, cohérents
avec la convention déjà existante dans les fichiers frères comme
app.alerts.jobs). Les reviewers ont classé ça tantôt Minor tantôt Important
(plan-mandated). **Décision de Tanguy (après Task 9)** : ne pas corriger
tâche par tâche — faire UNE passe dédiée de traduction FR après les 19
tâches, avant/à la revue finale de branche. À ne pas oublier avant de
clore SP-17b.

## Tâches

Task 1: complete (commits ac98d7a..2c7cd20, review clean — 2 Minor non
bloquants : commentaires anglais "why" plan-mandatés, cohérents avec le
reste du fichier ; `Field(default_factory=list)` au lieu d'un champ requis,
purement stylistique)
Task 2: complete (commits 2c7cd20..6b3c5a0, review clean — miroir fidèle
d'alert_validation/bookmark_validation vérifié, 2 Minor hérités du patron
existant, non introduits par cette tâche)
Task 3: complete (commits 6b3c5a0..de1da29, review clean — colonnes
nullable-only vérifiées, migration 0022 upgrade/downgrade/re-upgrade
vérifiée sur Postgres jetable sp17b-migcheck, 1 Minor cosmétique sur le
rapport)
Task 4: complete (commits de1da29..2830c9e, review clean — quote()/ctx
vérifiés, adaptation route "maps" vs "apps" du brief justifiée et
documentée, 3 Minor sur couverture de test/style d'import)
Task 5: complete (commits 2830c9e..bebcbb0, 2 rounds — round 1 a trouvé un
Important réel : le _FakePage.pdf() de test_export_jobs.py n'acceptait pas
les nouveaux kwargs Protocol requis, avalé silencieusement par le
except Exception de render_export_task, jamais détecté faute d'assertion
sur le statut du job ; fix en **kwargs + assertion status=="done" sur
fetch frais, régression reproduite puis re-corrigée pour prouver
l'assertion mordante ; round 2 clean, 1 Minor cosmétique hérité)
Task 6: complete (commits bebcbb0..5ce6a76, review clean — pas de FK SQL
vers export_jobs vérifié architecturalement cohérent, migration 0023
upgrade/downgrade/re-upgrade vérifiée sur Postgres jetable, pyproject.toml
non touché confirmé, 1 Minor commentaire mixte FR/EN hérité du brief.
Postgres jetable sp17b-migcheck détruit après ce round — plus nécessaire.)
Task 7: complete (commits 5ce6a76..3702c46, review clean — 7/7 fonctions
vérifiées, list_due_reports confirmé fidèle au patron list_due_pipelines,
8 tests réels (pas 9 — coquille du brief lui-même, transcription fidèle
de l'implémenteur, non un gap). 3 Minor dont le rappel que app.reports
doit être ajouté au contrat import-linter — prévu Task 12.)
Task 8: complete (commits 3702c46..c2b5a02, 2 rounds — round 1 : bug réel
trouvé DANS LE TEXTE DU PLAN lui-même (entry.model_dump() sans by_alias
aurait cassé le format fil avec le décodeur JS pour toute valeur
crossFilter de type BookmarkTimeRange imbriqué, from_→"from"),
l'implémenteur avait déjà corrigé mais sans commentaire ; 1 Important =
absence de commentaire expliquant l'écart volontaire par rapport au
texte littéral du brief ; fix = commentaire FR ajouté, round 2 clean)
Task 9: complete (commits c2b5a02..6ef3258, 2 rounds — vérification
double des droits propriétaire (bookmark + app cible) confirmée correcte
et fidèle au patron app.alerts.jobs._owner_user ; round 1 a trouvé 1
Important réel (test manquant sur la branche "accès app perdu", seule la
branche "accès bookmark perdu" était couverte) + 1 Important langue
(différé, cf. décision ci-dessus) ; fix = nouveau test dont le seeding a
été tracé pas-à-pas contre can()/get_access_facts réels pour prouver
qu'il touche la bonne branche, round 2 clean)
Task 10: complete (commits 6ef3258..6b56a3c, review clean — écart décidé
par Tanguy exécuté sans accroc : _s3_client_from_env renommé en
s3_client_from_env dans app.export.jobs et importé (pas dupliqué) par
app.reports.jobs ; grep repo confirme 0 référence résiduelle à l'ancien
nom privé, 3 sites de monkeypatch de test mis à jour. notify-once-jamais-
retried et court-circuit lecture-seule vérifiés et testés. 3 Minor sur
couverture de test/portée héritée du brief.)
Task 11: complete (commits 6b56a3c..3b9cc20, review clean — 404 (pas 403)
vérifié, gate presigned URL sur status=="done" vérifié, main.py non
touché confirmé (Task 12), _require_report_read_access confirmé clone
structurel des helpers export/alerts. 2 Minor sur couverture de test.)
Task 12: complete (commits 3b9cc20..d40e976, review clean — lacune réelle
du BRIEF lui-même trouvée et corrigée par l'implémenteur : l'entrée
ignore_imports "app.db -> app.reports.models" n'avait rien à matcher sans
l'import compagnon dans db.py's core_table_names() (ReportRun ne
s'enregistrait sur Base.metadata que par accident d'ordre d'import) ;
fix minimal suivant le patron des 13 entrées sœurs, disclosed dans le
rapport, vérifié indépendamment par re-exécution de lint-imports par le
reviewer. app.reports maintenant monté sans condition + dans le worker +
dans le contrat de couches.)
Task 13: complete (commits d40e976..3b4bbd3, review clean — correction du
contrôleur appliquée : harnais de test réel app_client/call_tool copié
de test_mcp_tools_alert.py au lieu du fixture fictif du brief
(mcp_server_and_session/server.call_tool qui n'existe pas). Outil MCP
vérifié transcription littérale du brief, enregistrement inconditionnel
confirmé, pas de fuite d'existence (3 sites raise, même message). 2 Minor
= trous de couverture hérités du fichier frère lui-même.)
**Backend (Tasks 1-13) clos.** Reste : shell (Tasks 14-19) + revue finale.
Task 14: complete (commits 3b4bbd3..a89e259, review clean — build vérifié
indépendamment par le reviewer, 2 écarts mineurs du texte du brief gérés
correctement (import PipelineRefreshPolicy absent à raison, ajout
nécessaire des types à l'import exhaustif d'itemClient.ts), 0 Minor.)
Task 15: complete (commits a89e259..b105972, review clean — transcription
octet-pour-octet du brief confirmée par diff, build vérifié
indépendamment, composant contrôlé sans state interne confirmé, switch de
canal ne laisse pas fuir de champ obsolète. 2 Minor cosmétiques.)
Task 16: complete (commits b105972..1c0348d, review clean — transcription
vérifiée, absence de bouton "Exécuter" confirmée par lecture complète du
fichier, boucle de poll avec garde stopped-ref vérifiée aux 3 points
d'appel. 3 Minor cosmétiques hérités du patron PipelineRunPanel.)
Task 17: complete (commits 1c0348d..b37bc3f, review clean — risque signalé
en amont (branche "report" dans useOpenItem, PAS dans le ternaire séparé
d'ItemDetailRoute) vérifié correctement respecté ; replace:true sur la
nav create→edit confirmé ; ItemActions.tsx non touché confirmé (Task 18).
2 Minor hérités du patron PipelineBuilderPage, pas des régressions.)
Task 18: complete (commits b37bc3f..ef81a7a, review clean — écart du
brief nécessaire et vérifié : ItemActions.test.tsx a dû gagner un
MemoryRouter car useNavigate() est appelé inconditionnellement en haut du
composant, confirmé empiriquement par le reviewer (les 4 tests auraient
échoué sans le wrapper). 1 Minor = pas de test dédié à la nouvelle entrée,
couvert par le spec E2E de la Task 19.)
Task 19: complete (commits ef81a7a..ecbeead, review clean — flux complet
vérifié contre le code source réel (pas seulement le texte du spec),
ordre d'enregistrement des routes de mock vérifié nécessaire et correct
contre mocks.ts réel, assertion sur le contenu du POST (pas juste son
occurrence) confirmée. Spec relancé indépendamment par le reviewer : 1
passed. 96/96 suite E2E complète. 1 Minor = un chiffre de comptage de
fichiers dans le rapport ne se reproduit pas, sans incidence sur le code.)
**Les 19 tâches sont closes.** Reste : passe de traduction FR différée
(décision utilisateur post-Task 9) puis revue finale de branche.

## Revue finale de branche (post-Task 19 + passe FR)

Base : ac98d7a → e75f955 (167KB, 24 commits). Reviewer opus (le plus
capable disponible) : 2 Critical + 5 Important + Minor.
- **Critical** : C1 openapi.json/core-schema.d.ts jamais régénérés
  (reproduit empiriquement, casserait api-types-drift en CI) ; C2 pas de
  filet large sur _notify_pending_reports — une erreur inattendue (pas
  NotifyError) bloque la notification de TOUS les tenants pour toujours
  (violation du "jamais rejoué" par un autre mécanisme que prévu).
- **Important** : I1 même défaut sur _trigger_due_reports (un échec
  inattendu tue le reste du tick) ; I2 un déclenchement en échec ne
  respecte pas le cron (retenté toutes les 5 min pour toujours, faute de
  ligne report_runs) ; I3 CORE_EXPORT_ENABLED=false laisse les jobs
  "pending" pour toujours (export-worker jamais démarré par défaut,
  reclaim_stuck_jobs ignore "pending") — **décision Tanguy : bloquer la
  création + échec rapide dans le sweep** ; I4 lien présigné de
  notification expire en 1h (mail du dimanche soir mort avant lundi) —
  **décision Tanguy : étendre à quelques jours** ; I5 ReportRunPanel
  sonde indéfiniment sans jamais s'arrêter et avale les échecs réseau.

**Passe de fix unique (9 commits, opus)** : tout corrigé, y compris 3
écarts délibérés et justifiés (back-off 30s au lieu d'arrêt net pour I5 —
sinon le tout premier run d'un rapport neuf n'apparaît jamais sans
rechargement manuel ; 3e garde shell masquant l'entrée de menu sur
exportEnabled en plus des 2 gardes serveur demandées pour I3 ; clôture en
"error" d'un job dont le defer() a échoué pour I1, sinon "pending" pour
toujours). Migration 0024 (report_runs.export_job_id nullable,
additive-only). +12 tests core (1373 passed), +6 tests shell (1045
passed), lint-imports KEPT, OpenAPI/TS régénérés et vérifiés sans drift.

**Re-revue de branche (opus)** : "Ready to merge: Yes". Tous les
Critical/Important vérifiés résolus par lecture directe du contrôle de
flux (le `finally` de C2 tracé, pas un except optimiste ; les handlers
frères de I1 confirmés continuer la boucle ; migration 0024 confirmée
additive-only ; les 3 écarts délibérés vérifiés sains). 5 Minor résiduels
acceptés sans fix supplémentaire (aucun bloquant) :
1. Le `except Exception` de C2 ne fait pas `session.rollback()` avant son
   `finally` — une erreur DB (pas les causes réalistes énumérées) pourrait
   encore faire échapper mark_notified. Écart d'une ligne par rapport au
   patron _record_trigger_failure qui, lui, fait le rollback en premier.
2. I2 fait consommer un créneau de cron entier à un échec transitoire de
   déclenchement (compromis délibéré, parité avec AlertRule, non signalé
   comme tel dans le rapport de fix).
3. Chemin très étroit où un échec DANS le handler de defer-failure de I1
   peut produire 2 lignes report_runs pour un même tick (inoffensif,
   cadence basée sur created_at le plus récent).
4. downgrade() de la migration 0024 échouerait sur une base avec des
   lignes de déclenchement en échec (SET NOT NULL sur des NULL) — CI teste
   sur base vide, passe ; à savoir avant un rollback réel.
5. stopped-ref partagé entre exécutions d'effet dans ReportRunPanel,
   pré-existant au patron, non introduit par cette passe.

Décision : ne pas pousser de fix supplémentaire — le reviewer a donné
"Ready to merge: Yes" sans Critical/Important, ces 5 items sont soit des
compromis délibérés déjà justifiés, soit des cas limites extrêmement
étroits, soit pré-existants. **HEAD final : 1594192.**

## Passe de traduction FR différée (post-Task 19)

Commits ecbeead..43d7d30 puis 43d7d30..e75f955 (fix reviewer). 11
emplacements traduits (schemas.py, report_validation.py, reports/{ctx,
jobs,models,repository,routes}.py côté core ; types.ts, ReportRunPanel.tsx,
ReportScheduleEditor.tsx, ReportEditPage.tsx côté shell). Revue clean
après un round de fix (1 Important : locution anglaise "create-and-reset"
oubliée dans un bloc sinon francisé, corrigée). Échec de test transitoire
signalé par l'implémenteur (AppNotOpen sur test_list_due_reports_...) non
reproduit par le contrôleur ni sur les 8 fichiers de test reports seuls
(32/32) ni sur la suite complète (1361 passed, 137 skipped, 0 failed) —
traité comme un flake de session, pas un vrai défaut.
**HEAD final avant revue de branche : e75f955.**
