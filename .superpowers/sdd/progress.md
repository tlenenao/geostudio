# SP-16b — Alertes (`AlertRule`) — Progress Ledger

Plan: docs/superpowers/plans/2026-08-07-sp16b-alertes.md
Spec: docs/superpowers/specs/2026-08-07-sp16b-alertes-design.md
Workspace: checkout principal, branche `dev` (convention établie, pas de worktree).
Base globale: dev@6ce9ae9 (HEAD au lancement, immédiatement après commit du plan).

## Pré-vol

Scan des 16 tâches + Global Constraints contre l'état réel du repo avant
dispatch :
- `core/pyproject.toml` : alembic head confirmé `0019` (Task 4 attend
  `0020`) ; deps `requests`, `croniter>=6.2`, `openpyxl` déjà présentes ;
  contrat import-linter `[tool.importlinter]` layers list confirmée
  (`app.harvest`, `app.pipelines`, `app.secrets`, …) — **écart trouvé**.
- `core/app/analytics/sql_sandbox.py` : `parse_ast`/`validate_select_only`/
  `collect_table_refs`/`SqlSandboxError` tous confirmés présents (Task 1).
- `core/app/configs/schemas.py` : `kind: Literal[...]` ligne 234 et
  `_require_kind_payload` confirmés identiques au texte "avant" du plan
  (Task 2).
- `core/app/analytics/aggregate.py` : `AggregateRequestBody` confirmé avec
  tous les champs attendus (`groupBy`, `split`, `bucket`, `bins`,
  `measures`) (Task 2).
- `core/app/secrets/schemas.py` : union à 5 variantes confirmée
  (`ApiKeyPayload`/`BearerTokenPayload`/`BasicAuthPayload`/
  `OAuth2ClientCredentialsPayload`/`PostgresDsnPayload`) (Task 7).
- `core/app/pipelines/jobs.py` + `repository.py` : patron sweep+task
  (`run_pipeline_sweep_task`, `list_due_pipelines`) confirmé comme modèle
  mirroré par Task 5/9.
- `core/app/jobs.py` (registre des modules de tâches) et `core/app/main.py`
  (`app.include_router(...)`) : points d'insertion confirmés pour Task 9/10.

**Écart trouvé et arbitré par l'utilisateur avant dispatch** : les Global
Constraints déclarent que `app.alerts` doit être positionné dans le
contrat de couches import-linter (`layers = [...]` de
`core/pyproject.toml`) directement sous `app.pipelines` et au-dessus de
`app.secrets` — mais aucune des 16 tâches ne modifie cette liste. Sans
cette entrée, le contrat "layers" d'import-linter ne connaît pas
`app.alerts` et n'imposerait rien (violation silencieuse possible). CI
exécute `lint-imports` (`.github/workflows/ci.yml`), donc l'écart est
réel et vérifiable. Décision utilisateur : je l'ajoute moi-même en petit
addendum à la Task 4 (première tâche qui crée `core/app/alerts/`) —
insertion de `"app.alerts"` dans la liste `layers`, plus un
`lint-imports` de vérification dans cette tâche.

Aucune autre contradiction trouvée entre tâches ni avec les Global
Constraints.

## Tasks (16 + final check)

1. `app.configs.alert_condition` — condition scalaire bornée — core
2. `AlertRule` payload schema (`BuilderConfig.kind="alert"`) — core
3. `app.configs.alert_validation` — validation datasetItemId — core
4. `AlertEvaluation` model + migration 0020 (+ addendum layers) — core
5. `app.alerts.repository` — core
6. `app.alerts.egress` — garde SSRF webhooks — core
7. `SmtpCredentialsPayload` (secret kind) — core
8. `app.alerts.notify` — webhook + email — core
9. `app.alerts.jobs` — sweep + evaluate tasks — core
10. `app.alerts.routes` — liste règles + historique — core
11. Régénération types OpenAPI/TS
12. MCP `explain_alert_rule`
13. Shell — `ItemClient` types + méthodes AlertRule
14. Shell — section "Alertes" sur `DatasetEditPage`
15. E2E `alert-rule.spec.ts`
16. Vérification finale + mise à jour CLAUDE.md

Base Task 1: 6ce9ae9
Task 1: complete (commits 6ce9ae9..c20c033, 2 rounds de fix, review
Approved en round 3). Implémentation initiale (10591b9) conforme au
texte du brief mais celui-ci était du code dicté verbatim par le plan et
contenait une faille de sécurité réelle : `collect_table_refs` ne détecte
que les nœuds AST `BASE_TABLE`, pas `TABLE_FUNCTION` — un `expr` du type
`(SELECT count(*) FROM read_csv_auto('/etc/hostname')) > -1` passait la
validation et `evaluate_condition` l'exécutait pour de vrai (lecture
fichier confirmée par moi-même indépendamment du reviewer). Écart
plan-mandaté soumis à l'utilisateur (arbitrage : corriger avant Task 2 —
approuvé). Fix round 1 (1df8c58) : verrouillage DuckDB
(`enable_external_access=false`+`lock_configuration=true`) avant
exécution, avec garde d'idempotence pour connexion réutilisée. Re-revue a
trouvé un second Critical NON couvert par ce fix : les fonctions de table
purement calculatoires (`range()`) contournent aussi bien le scan AST que
le verrou I/O — DoS reproduit (20s+ sans borne). Pas un conflit avec le
texte du plan (bug trouvé en revue, pas dicté) donc pas de nouvel
arbitrage utilisateur nécessaire — fix round 2 (c20c033) : timeout
statutaire + limites mémoire/threads en miroir de
`sql_sandbox._apply_limits`/`_execute_bounded`. Le rapport de
l'implémenteur du round 2 signalait lui-même une réserve ("query-shape-
sensitive, peut ne pas interrompre de façon fiable") — le reviewer l'a
vérifiée à fond (8 essais indépendants, 2 formes, 2 valeurs de timeout,
3 échelles) et a réfuté la réserve : le timeout borne fiablement la forme
exacte de la vulnérabilité. Approved. 10/10 tests (fichier), lint-imports
propre, aucune dérive de périmètre sur les 3 commits (seuls
`alert_condition.py`+`test_alert_condition.py` touchés hors rapport).

Base Task 2: c20c033
Task 2: complete (commits c20c033..98b6d81, 1 round de fix, review
Approved en round 2). Implémentation initiale (a46882c) conforme au
brief — délégation correcte à `alert_condition.validate_condition_expr`
(parse-only, pas besoin du hardening runtime de Task 1), noms de champs
alignés avec `AggregateRequestBody` réel, changement du `Literal`
`BuilderConfig.kind` purement additif (35/35 régression, 1231/1231
suite complète). Revue a trouvé 1 Important plan-mandaté :
`channels: list[AlertChannelWebhook | AlertChannelEmail]` sans
discriminateur — un payload sans `kind` mais avec des champs des deux
formes se résolvait silencieusement en une variante arbitraire (repro
vérifié : `{"url":..., "to":..., "smtpSecretName":...}` devenait
`AlertChannelEmail`, perdant `url` sans erreur), alors que le fichier a
déjà le bon patron ailleurs (`DatasetCrossFilterLink`,
`Field(discriminator="mode")`). Arbitrage utilisateur : corriger
(approuvé). Fix (98b6d81) : `Field(discriminator="kind")` en miroir du
patron existant. Re-revue a vérifié à fond que le discriminateur engage
réellement le mécanisme Pydantic (message d'erreur
`Unable to extract tag using discriminator 'kind'`, pas juste une
correspondance de forme) et ne casse aucun appelant légitime (le type
n'a encore aucun consommateur hors ce fichier). Approved. 45/45 tests
régression, 1232/1232 suite complète.

Base Task 3: 98b6d81
Task 3: complete (commit 395750c, review Approved au premier passage).
`app.configs.alert_validation.validate_alert_payload` miroir exact de
`bookmark_validation.py`, câblé sur les 3 sites (`create_config`/
`update_config`/`update_config_by_item`). 1 déviation du texte littéral
du brief identifiée par l'implémenteur ET vérifiée en profondeur par le
reviewer (pas du scope creep, pur test) : le fixture du brief supposait
que l'authentification mock résout l'utilisateur depuis le contenu du
bearer token ("Bearer mock:alice" → alice) — en réalité
`get_current_user` en mode mock résout toujours une identité fixe
(`oidc_sub="mock-sub"`/`username="mockuser"`, le contenu du token n'est
jamais lu). Sans la correction, un test passait pour la mauvaise raison
(masquage de la vérification resourceType) et un autre échouait
franchement (422 au lieu de 201 attendu) — les deux confirmés
indépendamment par le reviewer en rejouant le fixture originel. Aucun
code de production modifié pour compenser. 3/3 tests, 84 tests régression,
1235/131 suite complète.

Base Task 4: 395750c
Task 4: complete (commits 4f4729d, c1e3745, review Approved au premier
passage). `AlertEvaluation` model + migration 0020 conformes au brief.
Addendum utilisateur (écart plan trouvé en pré-vol) livré : `"app.alerts"`
inséré dans `pyproject.toml` entre `app.pipelines` et `app.secrets`,
`lint-imports` vérifié 0 broken. Gap supplémentaire trouvé ET corrigé par
l'implémenteur lui-même (pas dans le brief ni l'addendum) : `app/db.py`
n'important pas `app.alerts.models`, rendant `alert_evaluations` invisible
à `Base.metadata.create_all()` (SQLite) et à la liste noire de noms de
collections — corrigé en 1 ligne, motif identique aux 13 autres entrées
`app.db -> app.X.models` déjà présentes, vérifié par le reviewer contre le
motif existant (pas un contournement isolé). 1/1 test, suite complète
1236/6 skipped, lint-imports propre. `alembic upgrade head` réel non
exécuté (aucune stack Postgres locale up) — couvert par la case postgis
CI, même réserve acceptée que les migrations précédentes du repo.

Base Task 5: c1e3745
Task 5: complete (commit 0c283d8, review Approved au premier passage —
code correct, mais narration du self-review de l'implémenteur invalidée
par le reviewer). `app.alerts.repository` (CRUD évaluations,
`list_due_rules`) miroir de `app.pipelines.repository`/SP-15h. Divergence
intentionnelle vérifiée correcte : ancre de reclaim `created_at` seul
(pas de `started_at`, cycle de vie à 2 états seulement contrairement à
`PipelineRun`). Le garde de normalisation timezone est réellement
nécessaire — mais l'implémenteur avait affirmé l'avoir vérifié
"dormant en session unique / seulement cross-session en prod" et le
reviewer a reproduit l'expérience exacte (suppression du garde) et
obtenu l'inverse : le garde est déclenché tout de suite dans la même
session via `session.refresh()` (stockage SQLite sans offset). Code
livré non défectueux, juste la justification du rapport était fausse —
noté comme leçon (« ne pas affirmer un résultat d'expérience sans
vraiment la lancer », déjà la leçon de SP-15h) sans bloquer le merge.
6/6 tests, suite complète 1242/131 skipped.

Base Task 6: 0c283d8
Task 6: complete (commit d744f0e, review Approved au premier passage).
`app.alerts.egress` duplication fidèle de `app.pipelines.egress`
(confirmé par `diff` octet pour octet à partir de `_ALLOWLIST_ENV`), sa
propre `CORE_ALERTS_EGRESS_ALLOWLIST`. 1 déviation du texte littéral du
brief (DONE_WITH_CONCERNS, pur test) vérifiée réelle par le reviewer :
les hostnames `.test` du brief ne résolvent jamais (RFC 2606, `gaierror`
reproduit en direct) — corrigé en mockant `socket.getaddrinfo`, technique
identique et déjà éprouvée dans les 2 suites sœurs
(`test_pipeline_egress.py`/`test_harvest_egress.py`, même IP factice).
1 Minor plan-mandaté noté (docstring anglais au lieu du français
habituel du repo — texte dicté verbatim par le brief, cosmétique,
n'affecte pas la correction) — reporté à la revue finale, pas bloquant.
Résiduel TOCTOU DNS-rebinding déjà accepté (CLAUDE.md, pinning IP
différé) explicitement hors périmètre, non re-soulevé. 5/5 tests,
32/32 avec les 2 suites sœurs.

Base Task 7: d744f0e
Task 7: complete (commit 5f15a75, review Approved au premier passage).
`SmtpCredentialsPayload` 6e variante additive de `SecretPayload` (union
discriminée déjà établie dans ce fichier — contrairement à Task 2, pas
de piège de discriminateur ici, le patron existant l'a déjà). Aucune
garde d'egress ajoutée (bon choix, même modèle de confiance que
`postgres_dsn`, vérifié par le reviewer). Test round-trip réel via
`SECRET_PAYLOAD_ADAPTER` (pas juste construction du modèle). 2 Minor
(docstring anglais au lieu du français habituel ; import local redondant
dans le test, copié du brief) — non bloquants. 10/10 tests fichier,
38/38 suite secrets complète.

Base Task 8: 5f15a75
Task 8: complete (commit 9efab00, review Approved au premier passage —
mais correction appliquée AVANT dispatch, pas en boucle de revue).
Écart trouvé en lisant le brief avant de dispatcher l'implémenteur (pas
par une revue après coup) : le code dicté par le plan pour `send_webhook`
ne fait la vérification `assert_egress_allowed` qu'une fois, puis livre
via `requests.post` brut — qui suit les redirections HTTP par défaut,
sans re-vérifier chaque saut. Task 6 avait déjà construit
`build_guarded_session()` (adaptateur qui re-vérifie l'egress à chaque
saut de redirection, confirmé via le code réel de `requests` 2.34.2 —
`resolve_redirects` réinvoque `adapter.send()` par saut) précisément pour
cet usage, mais Task 8 ne l'utilisait pas. Arbitrage utilisateur :
corriger avant dispatch (approuvé) — implémenteur briefé pour utiliser
`build_guarded_session()` au lieu de `requests.post`. Reviewer a vérifié
à fond que le nouveau test de régression exerce réellement le mécanisme
de redirection de `requests` (mock au niveau `HTTPAdapter.send`, pas
au-dessus) et reproduit lui-même indépendamment la preuve
naïf→`TooManyRedirects` vs corrigé→`EgressBlockedError`. `send_email`
conforme au brief, chiffrement réel testé (pas de raccourci). 2 Minor
non bloquants (narration légèrement imprécise dans le rapport ; en-têtes
EmailMessage hors du bloc try, hérité verbatim du brief, pas introduit
par l'implémenteur). 7/7 tests, suite complète 1255/131 skipped,
lint-imports propre.

Base Task 9: 9efab00
Task 9: complete (commits 9c7a6ba, 7a9f417, 2 rounds de fix, review
Approved en round 3). Tâche la plus grosse et la plus intégrative du plan
(8 tâches consommées). 1 bug confirmé AVANT dispatch (pas en boucle de
revue) : `_measure_value` codait en dur `base_uri=f"s3://{bucket}/cdc"`
sans jamais lire `S3_CDC_BUCKET_BASE_URI`, alors que `app.pipelines.jobs`
a déjà un helper `_analytics_base_uri()` avec ce test seam et le propre
test postgis dicté par Task 9 s'appuyait dessus. Arbitrage utilisateur :
corriger avant dispatch (approuvé) — implémenteur briefé pour dupliquer
le helper. L'implémenteur a lui-même trouvé ET corrigé un second bug
réel non prévu : `get_latest_evaluation` renvoyant toujours l'évaluation
courante (déjà committée par le sweep avant de déférer), cassant la
détection de transition (chaque tick se faisait passer pour un "premier
run" et re-notifiait à chaque tick stable). Revue round 1 a confirmé ce
fix mais trouvé un Important résiduel réel (pas plan-mandaté, gap dans
le fix lui-même) : le fix ne sautait que la ligne courante, pas les
autres lignes "pending" bloquées du chemin de reclaim
(`_PENDING_RECLAIM_MINUTES`) — un rétablissement après worker
planté/redémarré aurait renotifié à tort. Fix round 2 : nouvelle
fonction pure `_previous_terminal_state` sautant TOUTE série de lignes
non-terminales en tête (pas juste une), testée isolément + les 5
scénarios tracés à la main par le reviewer + suite postgis réelle
(container `postgis-test` reconstruit indépendamment par le reviewer,
3/3, puis 50/50 sur `-k alert`). Reste des éléments round 1
(commit-avant-defer, gestion d'erreur, 2 connexions DuckDB par
évaluation — dicté tel quel, pas "corrigé" unilatéralement) reconfirmés
intacts. 1 Minor (pas de test dédié à 2+ lignes bloquées, généralité
prouvée par lecture de code plutôt que par test) — non bloquant.

Base Task 10: 7a9f417
Task 10: complete (commit f6edf49, review Approved au premier passage).
Écart confirmé AVANT dispatch (pas en boucle de revue) : le code dicté
par le plan pour `GET /datasets/{id}/alerts` appelait
`list_configs_by_kind` directement depuis une route — sa propre
docstring interdit explicitement cet usage ("jamais exposé via une
route : ... le tuple retourné porte tenant_id en clair", réservé aux
tâches système cross-tenant). Arbitrage utilisateur : corriger avant
dispatch (approuvé) — nouvelle fonction `list_configs_by_kind_and_tenant`
avec filtre `Config.tenant_id` au niveau SQL, vérifiée par le reviewer
comme un vrai filtre serveur (pas juste un re-filtrage Python après coup)
et par un test d'isolation réel (2 tenants réels, chacun ne voit que sa
propre règle). Implémenteur a aussi trouvé et corrigé le même piège
d'authentification mock que Task 3 (identité mock fixe ignorée par le
brief). 1 Important noté (pas un défaut du code, un problème
d'attribution) : l'implémenteur a regénéré `openapi.json`/
`core-schema.d.ts` de sa propre initiative (pas demandé par le brief) et
a absorbé TOUT le drift accumulé depuis Task 1 (SmtpCredentialsPayload,
AlertRulePayload, etc. — jamais régénérés avant), pas seulement les 2
routes de Task 10 ; rapport de l'implémenteur décrivait ça à tort comme
"additif, scope de cette tâche seulement". Sans risque (mécaniquement
correct, CI verte) mais rend Task 11 vide de contenu quand elle
viendra — attendu et noté, pas de re-travail nécessaire. 21/21 tests
nouveaux, lint-imports propre.

Task 11 : no-op confirmé directement (pas de dispatch implémenteur/
reviewer — rien à faire). Task 10 avait déjà régénéré `openapi.json` et
`core-schema.d.ts` en absorbant tout le drift depuis Task 1. Vérifié moi-
même : régénération des deux fichiers dans `/tmp`, diff vide contre les
fichiers trackés dans les deux cas. Aucun changement à committer.

Base Task 12: f6edf49
Task 12: complete (commit 1517260, review Approved au premier passage).
2 bugs confirmés AVANT dispatch (pas en boucle de revue) : le code dicté
utilisait `@mcp.tool()` (n'existe pas dans ce fichier — l'instance
FastMCP s'appelle `server`, `mcp` n'est que le module importé,
`NameError` garanti) et copiait l'indentation de `explain_pipeline`, qui
est imbriqué dans `if is_etl_enabled():` — alors que Task 12 exige un
enregistrement inconditionnel. Arbitrage utilisateur : corriger avant
dispatch (approuvé) — implémenteur briefé pour `@server.tool()` +
placement hors du bloc conditionnel. Reviewer a vérifié en lisant le
fichier réel (pas juste le diff) ET en exécutant le test avec
`CORE_ETL_ENABLED` non défini puis `=true` — les deux passent, l'outil
est réellement indépendant du flag, pas juste indenté pour le paraître.
Implémenteur a aussi trouvé et corrigé un bug non signalé dans le
fixture du brief (`TestClient` sans `base_url`, cause un rejet 421 —
motif déjà présent dans toutes les suites MCP sœurs). 2/2 tests, 13/13
régression, 48/48 suite mcp_tools plus large.

Base Task 13: 1517260
Task 13: complete (commit 3953ae6, review Approved au premier passage).
Première tâche shell/TypeScript. 1 clarification résolue AVANT dispatch
(pas un bug, une hypothèse fausse du brief) : le brief supposait
l'existence d'un type TS structuré `AggregateRequestBody`-like à
réutiliser pour `AlertRulePayload.query`, en suggérant lui-même de le
vérifier par grep — le grep ne trouve rien, aucun tel type n'existe.
Convention réelle du repo pour ce genre de donnée : `DataSource.query:
Record<string, unknown>` (non typé, toutes les widgets le traitent en
sac de champs dynamique). Implémenteur briefé pour typer en
conséquence, vérifié par le reviewer (grep indépendant confirmant
l'absence du type supposé). Implémenteur a aussi ajouté `"alert"` à
l'union `ResourceType` (nécessaire pour que le code dicté par le brief
compile, même patron que `"pipeline"`/`"bookmark"` précédemment — vérifié
réel par le reviewer, pas une invention). 2 Minor non bloquants (en-tête
du brief mentionne des interfaces `AlertChannelWebhook`/
`AlertChannelEmail` séparées alors que le code dicté utilise une union
discriminée `AlertChannel` — incohérence du brief lui-même, pas de
l'implémenteur ; `useCreateAlertRule` n'invalide que la clé de requête
scoped dataset, pas `["items"]` comme son frère pipeline — dicté
verbatim par le brief, flagué par l'implémenteur lui-même). 5/5 tests
nouveaux, 143 tests fichiers concernés, 995/995 suite shell complète,
build tsc+vite propre.

Base Task 14: 3953ae6
Task 14: complete (commits 3004e37, 0243cc5, 1 round de fix, review
Approved en round 2). `AlertRuleEditor` (liste + création inline) monté
sur `DatasetEditPage`, patron de markup identique à la section Export
vérifié octet pour octet. 1 Important plan-mandaté trouvé en revue :
`(rulesQuery.data ?? []).map(...)` sans vérifier `rulesQuery.isError` —
un échec réel de fetch (permission, 500, réseau) rendait une liste vide
silencieuse, indiscernable de "aucune règle configurée", alors que les 3
autres sections de la même page (schema/export/save) affichent toutes
un bandeau `role="alert"`. Arbitrage utilisateur : corriger (approuvé).
Fix : bandeau d'erreur ajouté au même patron exact, + mise à jour
nécessaire du fixture `DatasetEditPage.test.tsx` (le nouveau bandeau
créait une ambiguïté dans un test existant utilisant `findByRole("alert")`
sans scope — corrigé en mockant `listAlertRulesForDataset` par défaut
dans `renderPage()`, vérifié par le reviewer comme un vrai besoin, pas un
masquage). `DatasetEditPage.tsx` (le composant) non touché par le fix.
1 Minor résiduel non bloquant (incohérence `text-sm` sur le bandeau
`createError` préexistant, hors périmètre du fix). 12/12 tests fichiers
concernés, 999/999 suite shell complète, build propre.

Base Task 15: 0243cc5
Task 15: complete (commits e2a0a55, 5ace423, 1 round de fix, review
Approved en round 2). Spec E2E passée du premier coup sans itération
(implémenteur avait vérifié les vrais sélecteurs/routes avant de lancer).
1 Important plan-mandaté trouvé en revue (auto-signalé honnêtement par
l'implémenteur) : les 2 premières assertions ("Trop d'incidents" visible,
"firing" visible) étaient satisfaites par des mocks GET inconditionnels
qui se déclenchent au montage, AVANT le clic sur "Créer la règle" — seule
la dernière assertion (`createdAlertConfig` non-null) dépendait du vrai
clic+POST, mais ne vérifiait qu'un POST avait eu lieu, pas que son corps
reflétait les valeurs saisies (un mauvais câblage champ→état aurait quand
même fait passer le test). `bookmarks.spec.ts` avait déjà établi une
barre plus haute (deep-check du corps POST contre les vraies valeurs
saisies). Arbitrage utilisateur : corriger (approuvé). Fix : assertion
`toMatchObject` sur `condition.expr`/`channels[0].url`/`title`, prouvée
réellement porteuse par le reviewer lui-même (édition locale non
committée de la valeur attendue → échec réel observé → restauration →
succès), pas seulement fait confiance au rapport. 92/92 E2E, aucune
régression.

Base Task 16: 5ace423
Task 16: complete (commit ae8840a, fait directement — pas de dispatch
implémenteur/reviewer, tâche de vérification + docs). Suites complètes
relancées moi-même : core 1269 passed/134 skipped, shell 999/999, build
tsc+vite propre, E2E 92/92. CLAUDE.md mis à jour : nuance trouvée en
lisant le design spec (pas dans le texte du plan lui-même) — le spec
SP-16b renumérote explicitement "SP-16b = AlertRule seul, clôt SP-16, pas
de 16c" et déplace ReportSchedule/rapports planifiés entièrement vers
SP-17, avec le critère de sortie M12 explicitement reformulé pour ce
périmètre resserré (donc M12 réellement atteint, pas juste déclaré tel
quel sans vérifier). Bullet Fait détaillé avec les 9 défauts réels
trouvés/corrigés sur les 16 tâches (bien au-dessus de la moyenne des SP
précédents). SP-16 marqué clos dans À venir, SP-17 mis à jour pour
porter ReportSchedule.

## TOUTES LES 16 TÂCHES COMPLÈTES. Passage à la revue finale de branche.

Revue finale de branche (6ce9ae9..ae8840a, 22 commits, sur opus) : 3
Important trouvés, tous des coutures inter-tâches invisibles à une revue
scopée par tâche, tous dans `app/alerts/jobs.py` — (1) `_measure_value`
dérivait le label de mesure différemment de
`aggregate._measure_label` : une règle avec `measures:[{agg,field}]`
sans label explicite ne pouvait jamais s'évaluer (erreur permanente) ;
(2) `_notify` appelé dans le même bloc try que `mark_evaluated(new_state)`
déjà exécuté — toute exception hors `NotifyError` (ex. `messageTemplate`
mal formé, jamais validé) écrasait l'état réel mesuré par "error", qui
repassait "firing" au tick suivant et re-notifiait indéfiniment chaque
canal déjà réussi, violant "notification seulement sur transition" ; (3)
le handler générique `except Exception` n'écrivait jamais d'`audit_log`,
contrairement à son frère `AlertEvaluationError`, pour les pannes les
plus réalistes en prod (timeout DuckDB de Task 1, partition CDC absente,
env var manquante). Vérifié indépendamment (finding #1) avant de
présenter à l'utilisateur. Arbitrage utilisateur : corriger les 3
maintenant (approuvé) — un seul fixeur pour les 3 (pas un par finding,
per process). Fix (6a32598) : réutilise `_measure_label`/`_measures_for`
réels de `app.analytics.aggregate` (structurel, pas une réimplémentation
qui pourrait diverger à nouveau) ; restructuration garantissant que
`mark_evaluated` n'a que 3 sites d'appel, tous confinés à l'étape de
mesure — toute exception de notification ne peut plus les atteindre ;
validateur `messageTemplate` à la sauvegarde (defense in depth) ; entrée
`audit_log` ajoutée au handler générique, même forme que le frère.

Re-revue (opus) a vérifié à fond chaque fix (pas seulement fait
confiance au rapport) : reconstruit l'arbre pré-fix dans le scratchpad
pour rejouer RED sur les 4 nouveaux tests, confirmé les 3 signatures
d'échec prédites exactement. A aussi vérifié deux affirmations
"échecs pré-existants non liés" de l'implémenteur — moi-même vérifié la
RLS (identique sur 6ce9ae9 avant tout ce travail), le reviewer a vérifié
indépendamment le second (DSN CDC — artefact de configuration
d'environnement de l'implémenteur, pas un vrai échec, les 2 tests CDC
passent réellement à HEAD). 4 Minor de suivi non bloquants (catch
per-canal encore NotifyError-seul ; get_item hors des deux try ;
commentaire légèrement inexact ; couverture de test partielle sur les 3
formes de label). **Ready to merge: Yes.** Suite complète (avec postgis
réel) : 1403 passed/1 failed (RLS pré-existant)/5 skipped, lint-imports
propre, aucune dérive OpenAPI.

## REVUE FINALE APPROUVÉE. Passage à superpowers:finishing-a-development-branch.
