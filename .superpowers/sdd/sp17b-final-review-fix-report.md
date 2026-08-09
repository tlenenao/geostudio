# SP-17b — corrections de la revue finale de branche

Branche `dev`, base `e75f955`. Neuf commits, un par finding (les Minor groupés).

---

## C1 — OpenAPI + types TS jamais régénérés

**Changé** : régénération avec les commandes exactes de `.github/workflows/ci.yml`
(job `api-types-drift`) :

```
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAEC…Hh8=" uv run python scripts/export_openapi.py openapi.json
cd shell && npm run gen:api-types
```

`core/openapi.json` : +162 lignes (`ReportSchedulePayload`, `ReportRunStatus`,
`"report"` dans l'enum `kind`, `GET /reports/{item_id}/runs`).
`shell/src/api/generated/core-schema.d.ts` : +75 lignes.

**Vérifié** : le diff régénéré ne contient AUCUNE route export — la CI ne pose
jamais `CORE_EXPORT_ENABLED`, donc `app.main` ne monte pas `export_routes` ;
c'est le précédent déjà établi pour `CORE_ETL_ENABLED`/pipelines (et le piège
exact qui avait cassé la CI au round 2 de SP-17a). Régénéré une seconde fois
après TOUS les commits suivants : toujours aucun drift.

**Avant / après** : `grep -c report shell/src/api/generated/core-schema.d.ts` :
0 → 5. `grep -c "ReportSchedulePayload\|ReportRunStatus" core/openapi.json` :
0 → 6.

**Test** : pas de test unitaire — la preuve est `git diff --exit-code` sur les
deux fichiers, exactement ce que fait la CI.

---

## C2 — `_notify_pending_reports` sans filet large

**Changé** (`core/app/reports/jobs.py`) : le corps par run — depuis le calcul
de `result_url` jusqu'à la fin de la boucle de canaux — est encadré par un
`try/except Exception` ; `mark_notified` + `commit` passent en `finally`.
L'audit d'échec (`action="report.notify"`, `payload={"channel": None,
"success": False, "error": "erreur interne : …"}`) est lui-même protégé par un
`try/except` interne pour qu'une session déjà cassée ne puisse pas empêcher le
`mark_notified`.

**Avant** : `_presigned_url_for_job` (KeyError sur `S3_ENDPOINT_URL`, erreurs
botocore) ou `send_email` (KeyError/RuntimeError du chargement de la clé
maître, `InvalidTag` AES-GCM sur un secret corrompu) faisaient sortir
l'exception de `_notify_pending_reports` AVANT `mark_notified`.
`list_unnotified_runs` étant cross-tenant et non ordonnée, un seul run cassé
bloquait définitivement la notification de tous les rapports de tous les
tenants (le sweep repêchait le même run toutes les 5 min).

**Après** : le run est marqué notifié quoi qu'il arrive — la contrainte
« une notification est tentée une fois par run, jamais rejouée, même en
échec » tient aussi sur le chemin d'erreur inattendue.

**Tests** (`core/tests/test_report_jobs.py`) :
- `test_notify_marks_notified_when_channel_raises_a_non_notify_error` —
  `send_webhook` lève un `RuntimeError` nu ; `notified_at is not None` après un
  seul appel, et une ligne d'audit `report.notify` avec `channel=None`,
  `success=False` a été écrite.
- `test_notify_marks_notified_when_presigned_url_raises` — l'échec survient
  AVANT la boucle de canaux (`KeyError("S3_ENDPOINT_URL")`) : aucun webhook
  envoyé, run tout de même marqué notifié.

Les deux échouent sur le code d'avant (vérifié par `git stash` du seul
`jobs.py` : `2 failed, 6 passed`).

---

## I1 — `_trigger_due_reports` : seule `ReportTriggerError` était rattrapée

**Changé** :
- ajout d'un `except Exception` frère du `except ReportTriggerError`, avec
  `logger.exception(...)` et le même audit (`_audit_trigger_failure`) ;
- extraction de `_record_trigger_failure(session, …)` : `session.rollback()`
  (annule les écritures partielles de l'itération) puis audit puis commit ;
- **`render_export_task.defer` isolé dans son propre `try`** : à ce point le
  run et son `export_jobs` sont déjà committés (patron commit-avant-defer), un
  échec de mise en file laissait un job « pending » que personne ne dépilerait
  jamais (`reclaim_stuck_jobs` ne récupère que les « running »). Il est
  désormais clos en `error`, la notification le verra au tick suivant.

**Avant** : une panne transitoire sur le rapport n°1 (blip DB pendant
`.defer()`, `write_audit`, un `commit()`) abandonnait les rapports n°2..N de
tous les tenants pour ce tick et sautait le `export_repo.reclaim_stuck_jobs`
final.

**Tests** :
- `test_trigger_continues_to_next_report_when_one_raises_an_unexpected_error` —
  deux rapports dus, `defer` lève au premier appel : `attempts == 2` (le second
  rapport est bien traité), une seule ligne d'audit d'échec, et le job du
  rapport en échec est en `error`.
- `test_trigger_audits_unexpected_error_raised_inside_the_loop_body` — l'erreur
  survient avant le commit (`encode_analytics_context` monkeypatché) : audit
  `"erreur interne : bookmark illisible"`, rien de déféré.

---

## I2 — un rapport en échec permanent se redéclenchait toutes les 5 minutes

**Décision** : option (a) du brief — colonne nullable + nouvelle migration.
Option (b) n'était effectivement pas applicable (un déclenchement en échec ne
crée jamais de ligne `export_jobs`).

**Changé** :
- `core/app/reports/models.py` : `export_job_id` devient
  `Mapped[str | None]` / `nullable=True` ;
- `core/alembic/versions/0024_report_runs_nullable_export_job.py` : nouvelle
  migration, `alter_column(… nullable=True)` — relâchement de contrainte
  uniquement, aucune donnée touchée, conforme à la contrainte globale du plan ;
- `reports_repo.create_run(…, export_job_id: str | None)` ;
- `_record_trigger_failure` crée la ligne `report_runs` (sans job) **et** la
  marque notifiée d'emblée : rien à notifier, l'audit `report.run` porte
  l'échec (comportement explicitement non requis par le plan, donc pas de
  notification d'échec de déclenchement) ;
- `_notify_pending_reports` : branche explicite `export_job_id is None`
  (filet, normalement inatteignable puisque déjà marqué notifié) ;
- `GET /reports/{item_id}/runs` : un run sans job remonte
  `status="error"`, `error="déclenchement échoué (voir le journal d'audit)"`,
  au lieu d'aller chercher un job sur un id nul.

**Avant** : `list_due_reports` dérive « dû ? » de `get_latest_run` ; sans
ligne, un rapport dont le propriétaire a définitivement perdu l'accès était
réessayé à chaque tick de 5 min — des centaines de lignes d'audit par jour au
lieu d'une par cycle cron.

**Tests** :
- `test_failed_trigger_still_records_a_run_so_cron_cadence_is_respected` —
  cron hebdomadaire `0 8 * * 1`, bookmark illisible : après un
  `_trigger_due_reports`, le run existe avec `export_job_id is None` et
  `notified_at is not None`, et **`list_due_reports` ne liste plus le rapport
  au même tick** (c'est l'acceptance bar du brief, sur le modèle de
  `test_list_due_reports_respects_cron_cadence_against_last_run`).
- `test_get_report_runs_reports_failed_trigger_run_as_error`
  (`tests/test_report_routes.py`).
- Les deux tests existants qui affirmaient `get_latest_run(...) is None` après
  un échec ont été mis à jour (le changement de comportement est intentionnel) :
  ils vérifient maintenant `run is not None and run.export_job_id is None`.

---

## I3 — conditionner ReportSchedule à la capacité export

**1. Garde à la création** (`core/app/configs/routes.py`) :
`_require_export_enabled_for_report(config)`, calqué sur
`_require_etl_enabled_for_pipeline` (`config.kind == "report" and not
is_export_enabled()` → `HTTPException(403, "Export capability disabled on this
instance")`), câblé aux 3 mêmes points d'appel (`create_config`,
`update_config`, `update_config_by_item`), juste après l'appel ETL.
`is_export_enabled` importé depuis `app.auth.dependency` — `app.configs`
importait déjà `is_etl_enabled` de là, contrat de couches inchangé (vérifié :
`lint-imports` KEPT).

**2. Fail-fast dans le balayage** (`core/app/reports/jobs.py`) : dans la boucle
(pas en tête de fonction, pour que CHAQUE rapport dû obtienne sa ligne d'échec
et donc sa cadence), après chargement du payload :
`if not is_export_enabled(): raise ReportTriggerError("export capability
disabled on this instance")` — réutilise le chemin d'échec d'I1/I2 (audit +
run en échec, aucun `defer`).

**3. Complément shell** (non demandé explicitement, mais c'est le précédent
établi et l'alternative était un 403 seulement après remplissage du
formulaire) : `ItemActions` masque « Programmer un rapport » quand
`exportEnabled` est faux — exactement comme `NewItemButton` masque l'option
« Pipeline » quand `etlEnabled` est faux. La spec E2E surcharge donc
`GET /instance` (le défaut de `mockCore` ne porte que `readOnly`).

**Tests** :
- `tests/test_report_validation.py` : `…_rejected_when_export_capability_is_disabled`
  (403 + message exact sur `POST /configs`),
  `…_accepted_when_export_capability_is_enabled` (201),
  `test_update_report_is_rejected_when_export_capability_is_disabled`
  (création avec la capacité active, puis `PUT` après coupure → 403).
- `tests/test_report_jobs.py::test_trigger_fails_report_without_deferring_when_export_capability_is_disabled`
  — rien de déféré, run en échec créé, audit
  `"export capability disabled on this instance"`. Pur SQLite, aucun Postgres
  ni S3 réel.
- `src/shell/ItemActions.test.tsx` : deux tests (entrée visible / masquée).
- Fixture autouse `_export_enabled` ajoutée à `test_report_jobs.py` et
  `test_report_sweep.py` (`CORE_EXPORT_ENABLED=true`) : ces tests décrivent une
  instance où la capacité est active ; le cas coupé a son test dédié.

---

## I4 — TTL du lien présigné de notification

**Changé** : `_NOTIFICATION_URL_TTL_SECONDS = 604_800` (7 jours) passé en
`expires_in` dans `_presigned_url_for_job` uniquement, avec un commentaire
français expliquant pourquoi ce chemin diffère du défaut. `generate_presigned_get_url`
(défaut 3600) et `GET /reports/{item_id}/runs` (re-signe à chaque sondage)
sont inchangés, conformément au brief.

**Tests** : aucun test n'existait sur cette fonction ; deux ajoutés —
`test_presigned_url_for_notification_uses_a_seven_day_ttl` (monkeypatch de
`generate_presigned_get_url`, assert `expires_in == 604_800`) et
`test_presigned_url_is_none_for_a_job_that_is_not_done`.

---

## I5 — `ReportRunPanel` : sondage non borné + erreurs avalées

Lecture faite de `PipelineRunPanel.tsx` : il s'arrête net quand le run quitte
`queued`/`running`. Choix retenu ici : **back-off** plutôt qu'arrêt net —
option explicitement autorisée par le brief, et la bonne ici, car un run peut
apparaître à tout moment sans action utilisateur (le balayage tourne toutes les
5 minutes) ; un arrêt net ferait qu'un rapport fraîchement créé n'afficherait
jamais son premier run.

**Changé** (`shell/src/builder/report/ReportRunPanel.tsx`) :
- `ACTIVE_POLL_MS = 1500` tant que le run le plus récent est
  `pending`/`running`, `IDLE_POLL_MS = 30000` sinon (`done`/`error`/`unknown`,
  et liste vide) ;
- état `hasError` posé sur échec de fetch, remis à zéro au succès suivant,
  rendu en `role="alert"` (« Impossible de charger l'historique des
  exécutions. ») et distinct du message « Aucune exécution pour l'instant. » ;
- forme du composant inchangée : toujours aucun bouton de déclenchement manuel.

**Tests** : `ReportRunPanel.test.tsx` créé (sibling `PipelineRunPanel.test.tsx`
existe, donc la convention est bien « test unitaire »), 4 tests — affichage de
l'historique, message d'erreur distinct, passage en rythme lent (`done` : 1 seul
appel après 4,5 s simulées, 2ᵉ appel à 30 s), maintien du rythme rapide
(`running` : 2ᵉ appel à 1,5 s). Faux timers + `act`.

**E2E** : `report-schedule.spec.ts` relancé et vert (le run mocké est `done`,
donc affiché dès le premier fetch — « Terminé » et « Télécharger » intacts).

---

## Minor

1. **`reclaim_stuck_jobs` sans appelant périodique — faux depuis SP-17b** :
   `TODO(SP-17a fix round, I7)` supprimé de `core/app/export/jobs.py` et
   remplacé par un commentaire pointant l'appelant réel ; docstring de
   `core/app/export/repository.py` corrigée ; puce correspondante retirée de la
   section « Suivis non bloquants ouverts » de `CLAUDE.md` (seule cette puce a
   été touchée).
2. **`core/app/reports/ctx.py`** : « Reproduit octet pour octet » → « Produit la
   même valeur décodée (via JSON.parse côté shell) […] et non le même octet à
   octet : json.dumps et JSON.stringify diffèrent sur les séparateurs et
   l'échappement ASCII ».
3. **`core/app/reports/routes.py`** : vérifié dans `core/app/main.py` (l. 138) —
   seul `export_routes.get_exports_bucket` est overridé, jamais celui de ce
   module. Commentaire corrigé pour décrire la situation réelle (deux clés
   distinctes, sans conséquence car la valeur est lue dans l'environnement à
   chaque appel, exactement ce que fait l'override). Aucun override ajouté.
4. **Commentaires anglais** : `# still rendering — revisit next tick` (déjà
   traduit dans le commit C2), `# transient poll failure` (remplacé dans I5),
   `report_validation.py` l. 20 et 29 (`# guaranteed by …`, `# get_access_facts
   just confirmed …`) traduits.
5. **`from urllib.parse import quote`** remonté au bloc d'imports de
   `core/app/export/jobs.py`.

---

## Vérification

| # | Commande | Résultat |
|---|---|---|
| 1 | `cd core && uv run pytest -q` | `1373 passed, 137 skipped in 91.63s` (base 1361/137 → +12 tests, 0 régression) |
| 2 | `cd core && uv run lint-imports` | `layered architecture KEPT` — `Contracts: 1 kept, 0 broken.` |
| 3 | `cd shell && npm run build` | `✓ built in 11.97s` (tsc + vite, propre) |
| 4 | `cd shell && npm run test` | `Test Files 130 passed`, `Tests 1045 passed` (base 1039 → +6, 0 régression) |
| 5 | drift OpenAPI/TS | régénéré après tous les commits : `git diff --exit-code` propre. `"report"` ×2 dans `openapi.json`, `ReportSchedulePayload`/`ReportRunStatus` ×6, `report` ×5 dans `core-schema.d.ts` (0 avant) |
| 6 | `VITE_AUTH_MODE=mock npx playwright test report-schedule.spec.ts` | `1 passed (24.3s)` — lancée car I5 et le complément shell d'I3 la touchent |

Suite E2E complète non lancée (hors périmètre du brief).

---

## Non traité / à arbitrer

- **Rien n'est resté non corrigé** parmi C1–I5 et les Minor.
- Deux écarts assumés par rapport à la lettre du brief, tous deux justifiés
  ci-dessus et testés :
  - **I5** : back-off (30 s) plutôt qu'arrêt net du sondage — option
    explicitement autorisée, et nécessaire car les runs arrivent sans action
    utilisateur.
  - **I3** : un troisième volet côté shell (masquage de l'entrée de menu) en
    plus des deux volets serveur demandés — c'est le précédent
    `NewItemButton`/`etlEnabled` déjà établi dans le dépôt.
- Choix de conception fait dans I1 et non demandé explicitement : un échec de
  `render_export_task.defer` clôt le job en `error`. Sans ça, I2 laissait un
  job « pending » éternel (ni dépilé, ni récupérable par `reclaim_stuck_jobs`
  qui ne traite que les « running »).
- `CLAUDE.md` n'a été modifié que sur la puce périmée de `reclaim_stuck_jobs`
  (Minor 1). Le résumé SP-17b de la section « Fait » n'a pas été rédigé : hors
  périmètre de ce brief, à faire à la clôture de branche.

---

## Commits

| SHA | Sujet |
|---|---|
| `8ec303f` | `chore(core,shell)` régénère openapi.json et les types TS pour kind="report" |
| `b7be8fe` | `fix(core)` filet large sur `_notify_pending_reports` — un run cassé ne bloque plus tous les tenants |
| `de67de7` | `fix(core)` `_trigger_due_reports` — filet large par rapport, un échec ne tue plus le tick |
| `49e7b7e` | `fix(core)` un déclenchement de rapport en échec crée quand même un `report_runs` |
| `c0a4bd8` | `fix(core)` conditionne ReportSchedule à la capacité export (création + balayage) |
| `dee3677` | `fix(core)` lien présigné des notifications de rapport valable 7 jours |
| `f1e2d01` | `fix(shell)` ReportRunPanel — sondage borné et échec de chargement visible |
| `a3040c5` | `docs(core)` corrige les commentaires périmés ou inexacts de SP-17a/SP-17b |
| `1594192` | `fix(shell)` masque « Programmer un rapport » quand la capacité export est coupée |

Tous suffixés `(SP-17b final review fix)`.
