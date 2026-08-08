# Rapport de correction — revue finale de branche SP-16b (AlertRule)

Corrige les 3 Important remontés par la revue finale de branche SP-16b
(alertes à seuil, webhook+email), tous dans `core/app/alerts/jobs.py` —
des défauts d'intégration entre tâches, invisibles à la revue scopée de
chaque tâche prise isolément.

Fichiers modifiés :
- `core/app/alerts/jobs.py`
- `core/app/configs/schemas.py`
- `core/tests/test_alert_jobs.py`
- `core/tests/test_alert_config_schema.py`

## Finding 1 — décalage de label de mesure rend les règles `measures[]` inévaluables à vie

**Constat** : `_measure_value` calculait
`label = payload.query.measures[0].label if payload.query.measures else "value"`,
alors que le row-keying réel côté `app/analytics/aggregate.py` est
`_measure_label(m) = m.label or (f"{m.agg}_{m.field}" if m.field else m.agg)`,
appliqué via `_measures_for(request)`. Une règle sauvegardée avec
`query: {"measures": [{"agg": "sum", "field": "amount"}]}` (schéma valide,
sans label explicite) calculait `label=None`, alors que la ligne agrégée
réelle est clé `"sum_amount"` — `None not in row` est toujours vrai, donc
`AlertEvaluationError` à chaque évaluation, pour toujours. La règle se
sauvegarde sans erreur mais ne peut jamais s'évaluer.

**Correction** : import direct de `_measure_label` et `_measures_for` depuis
`app.analytics.aggregate` dans `app/alerts/jobs.py` (précédent déjà établi
dans ce dépôt : `app/analytics/sql_sandbox.py` et `app/pipelines/runtime.py`
importent déjà des fonctions privées de ce même module). `_measure_value`
calcule désormais `label = _measure_label(_measures_for(payload.query)[0])`,
garantissant l'accord avec le row-keying réel quelle que soit la forme de
requête légale au schéma (agg/field top-level, ou une liste `measures` à un
élément, labellée ou non). Le contrat import-linter autorise cet import
(`app.analytics` n'est même pas dans la liste des layers contraints,
confirmé par `uv run lint-imports` → `layered architecture KEPT`).

## Finding 2 — un échec de notification imprévu écrase l'état d'évaluation réel, provoquant des notifications dupliquées indéfinies

**Constat** : dans `evaluate_alert_task`, tout (calcul de valeur → condition
→ transition → `mark_evaluated` → `write_audit("alert.evaluate")` →
`_notify`) était dans un seul grand `try`. `_notify` ne catchait que
`NotifyError` par canal ; toute autre exception (un `.format()` levant
`KeyError`/`IndexError`/`ValueError` sur un `messageTemplate` malformé —
non validé à la sauvegarde —, ou une exception non-`SMTPException`/`OSError`
lors du déchiffrement de secret dans `send_email`) remontait au `except
Exception` générique externe, qui appelait `mark_evaluated(...,
state="error")` une SECONDE fois sur la même ligne d'évaluation — écrasant
l'état réel `ok`/`firing` pourtant déjà correctement enregistré et audité
quelques lignes plus haut. Conséquence : le tick suivant voyait "error"
comme état précédent, dérivait `transitioned=True` sur le nouvel état
(disons "firing" à nouveau), et renotifiait chaque canal — y compris ceux
ayant déjà réussi — indéfiniment.

**Correction** : restructuration de `evaluate_alert_task` en deux étapes
séquentielles, toujours dans la même transaction/session (donc pas de perte
d'atomicité — un `return` à l'intérieur du bloc `with
request_scoped_session(...)` termine le bloc normalement et committe, il ne
lève pas) :
1. Calcul + `mark_evaluated` + `write_audit("alert.evaluate")` de l'état
   mesuré, dans le `try`/`except AlertEvaluationError`/`except Exception`
   existant — chaque branche d'erreur fait maintenant un `return` explicite
   immédiatement après avoir enregistré l'état "error", pour ne jamais
   atteindre l'étape de notification avec un état déjà en erreur.
2. Si `transitioned`, tentative de `_notify(...)` dans son propre
   `try/except Exception` large, séparé — un échec y écrit sa propre entrée
   d'audit (`action="alert.notify"`, `channel=None`, `success=False`,
   `error=...`) et se contente de logger, **sans jamais rappeler
   `alerts_repo.mark_evaluated`** pour cette évaluation. L'état mesuré réel
   reste donc intact quoi qu'il arrive pendant la notification.

Également : ajout d'un `model_validator` `_require_valid_message_template`
sur `AlertRulePayload` (`app/configs/schemas.py`) qui rejoue le même appel
`.format(ruleName="x", value=1.0, state="firing", datasetName="y")` que
`_render_message` (même forme d'appel, commentée des deux côtés pour rester
synchronisée — `app.configs` est SOUS `app.alerts` dans le contrat de
couches, donc ne peut pas importer `_render_message` pour garantir l'accord
mécaniquement) et catche `KeyError`/`IndexError`/`ValueError` pour rejeter
(422) un template inconnu ou mal formé dès la sauvegarde, plutôt que de
laisser une règle se sauvegarder puis échouer toute notification pour
toujours.

## Finding 3 — le handler d'exception générique n'écrivait jamais d'entrée audit_log

**Constat** : la branche `except AlertEvaluationError` écrivait une entrée
`alert.evaluate` documentant l'erreur ; sa sœur `except Exception` (pour les
erreurs vraiment inattendues — notamment le chemin de timeout de
`SqlSandboxError` de la Task 1, une `IOException` DuckDB sur une collection
sans données CDC, ou un `KeyError` sur une variable d'env `S3_*` manquante)
ne le faisait pas, malgré un changement d'état identique (`state="error"`).

**Correction** : ajout du même appel `write_audit(..., action="alert.evaluate",
object_type="item", object_id=item_id, payload={"error": error_detail})`
dans la branche `except Exception`, avec la même forme que la branche
`AlertEvaluationError`.

## Tests ajoutés

`core/tests/test_alert_jobs.py` (marqués `postgis`, Postgres réel via
`postgis-test` sur `127.0.0.1:5433`) :
- `test_evaluate_alert_task_evaluates_a_measures_declared_rule_without_explicit_label`
  — rule sauvegardée avec `query: {"measures": [{"agg": "count"}]}` (sans
  label) évalue correctement (`state="firing"`, `value=3.0`, `error is None`).
  Preuve directe du fix Finding 1 : ce scénario levait
  `AlertEvaluationError("expected measure 'None' not present...")` à chaque
  évaluation avant la correction.
- `test_notify_failure_does_not_overwrite_measured_state_or_cause_renotify` —
  mock de `send_webhook` levant un `ValueError` (pas un `NotifyError`).
  Vérifie que l'état mesuré (`"firing"`, `value=3.0`, `transitioned=True`)
  survit à l'échec de notification, qu'une seule entrée audit
  `alert.notify` (`success=False`) est écrite, puis qu'un second tick avec
  le même état `"firing"` ne redéclenche PAS de notification
  (`transitioned=False`, toujours une seule entrée `alert.notify` au total).
- `test_evaluate_alert_task_writes_audit_log_on_unexpected_error` — mock de
  `_measure_value` levant un `RuntimeError` générique. Vérifie
  `evaluation.state=="error"` ET la présence d'une entrée `audit_log`
  (`action="alert.evaluate"`) contenant le message d'erreur.

`core/tests/test_alert_config_schema.py` :
- `test_alert_message_template_rejects_an_unknown_placeholder`
- `test_alert_message_template_rejects_a_malformed_brace`
- `test_alert_message_template_accepts_the_known_placeholders`

## Résultats de tests

Ciblés (postgis inclus, container `postgis-test` déjà en place) :
```
tests/test_alert_jobs.py tests/test_alert_config_schema.py \
tests/test_alert_sweep.py tests/test_alert_repository.py \
tests/test_alert_condition.py
→ 40 passed
```
(6/6 dans `test_alert_jobs.py`, incluant les 3 nouveaux tests postgis-marqués.)

`uv run lint-imports` → `layered architecture KEPT` (1 kept, 0 broken) —
le nouvel import de fonctions privées `app.analytics.aggregate` depuis
`app.alerts.jobs` respecte le contrat de couches.

Suite complète (`uv run pytest -q`, avec `CORE_TEST_DATABASE_URL` pointant
vers `postgis-test`) : **1401 passed, 5 skipped, 3 failed, 2 errors** en
130s. Les 3 échecs + 2 erreurs sont confirmés **préexistants et sans
rapport** avec cette correction :
- `tests/test_cdc_consumer_postgis.py::test_stream_changes_decodes_and_stops_on_should_stop`
  et `::test_stream_changes_ack_advances_confirmed_flush_lsn` (+ 2 erreurs
  de teardown associées) — `psycopg2.connect()` reçoit un DSN au format
  SQLAlchemy (`postgresql+psycopg2://...`) au lieu d'un DSN libpq brut ;
  problème d'environnement de test sur `app/cdc/consumer.py`, fichier non
  touché par cette session (confirmé par `git diff HEAD` vide sur ce
  fichier et son test).
- `tests/test_features_rls.py::test_scope_preserves_original_sql_error` —
  le message d'erreur Postgres attendu ("row-level security") ne matche
  plus le message réellement renvoyé par cette version de Postgres/psycopg2
  ("current transaction is aborted..."), sur `app/features/rls.py`,
  également non touché par cette session.
Vérifié en isolant les 4 fichiers de cette correction via `git stash` (ces
3 échecs/2 erreurs apparaissent identiquement stash appliqué ou non) avant
de restaurer les changements (`git stash pop`).

Note sur les chiffres attendus de la consigne ("1269+ passed, 134 ou moins
skipped") : avec `postgis-test` réellement disponible cette session-ci, la
plupart des tests marqués `postgis` s'exécutent au lieu d'être skippés,
d'où 1401 passed / 5 skipped au lieu du plancher indiqué (qui correspond au
cas sans Postgres réel) — cohérent, pas une régression.

## Auto-revue

- Vérifié que `_measures_for`/`_measure_label` restent cohérents pour
  toutes les formes de requête légales au schéma (top-level agg/field,
  measures=[] explicite, measures=[un élément] avec/sans label) — les
  quatre passent par le même chemin de code que `aggregate.py` lui-même.
- Vérifié que le `return` ajouté dans les branches d'erreur du `try`
  s'exécute toujours à l'intérieur du bloc `with request_scoped_session(...)`
  — sort du bloc normalement (donc commit), ne le fait pas lever
  d'exception (qui aurait déclenché un rollback et perdu le
  `mark_evaluated`/`write_audit` déjà flush dans la même transaction).
- Vérifié qu'un template avec échappement `{{...}}` (littéral voulu) reste
  accepté par le nouveau validateur (`.format()` le résout sans lever), et
  qu'un placeholder positionnel (`{0}`) est bien rejeté (`IndexError`, car
  aucun argument positionnel n'est fourni à la sonde).
- Vérifié qu'aucun autre appelant de `_measure_value`/`_render_message`
  n'existe hors de `app/alerts/jobs.py` (grep) — changement contenu.

## Préoccupations

Aucune préoccupation bloquante. Point mineur noté dans le code (commentaire
sur le fallback de `_notify`) : la validation `messageTemplate` à la
sauvegarde rend le chemin de fallback de la Finding 2 inatteignable pour
les *nouvelles* règles, mais des règles préexistantes sauvegardées avant ce
validateur restent possibles — le fallback reste donc utile et n'est pas
mort code.
