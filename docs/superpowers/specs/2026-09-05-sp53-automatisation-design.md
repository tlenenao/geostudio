# SP-53 — Automatisation : compléter les éditeurs + déclenchement par webhook

**Date** : 2026-09-05
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (via SP-42, gaps GAP-43/44/48/49/50/24)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (source des 6 gaps),
`docs/revue/2026-09-04-backlog.md` (`F-shell-builder-04`, cité par GAP-50),
`CLAUDE.md` (§ Reste SP-15 : « événements/déclencheurs durables au-delà du
cron, non planifié »).

**Portée** : fermer 6 manques déjà catalogués par la revue SP-42, tous dans le
domaine Automatisation (pipelines/alertes/rapports/moissonnage/extensions),
aucun ne dépendant de SP-43. Ce document vérifie chaque affirmation du GAP
contre le code réel du dépôt à la date ci-dessus (`dev`, après les commits
SP-43 déjà mergés — cf. §0) — pas contre le texte de l'analyse de gaps
elle-même (piège CLAUDE.md n°3/n°12).

---

## 0. État réel constaté (SP-43 déjà exécutée sur `dev`)

Au moment d'écrire cette spec, `dev` porte déjà les 10 tâches de SP-43
(`git log --oneline` montre les commits jusqu'à `f64a29c9`, dernier commit
« fix(shell): aria-expanded... »). Conséquences vérifiées pour ce document :

- `core/app/mcp/tools.py` (1134 lignes, cité par la spec SP-43) **n'existe
  plus** : c'est désormais un package `core/app/mcp/tools/` avec un module par
  domaine (`alerts.py`, `pipelines.py`, `configs.py`, etc.). Les tâches
  ci-dessous (§5, Tâche 5 en particulier) citent les fichiers réels de ce
  package, pas l'ancien monolithe.
- `core/app/pipelines/service.py` existe (extrait par SP-43 Étape 8) et porte
  déjà `run_pipeline_service()`, `require_pipeline_access()`,
  `require_pipeline_config()` — **c'est le point de passage unique** que
  GAP-24 (Tâche 6) doit réutiliser, pas dupliquer une 3e fois (la 2e étant déjà
  le balayage cron, qui n'appelle pas ce service — cf. §4.3).
- `core/app/jobs/common.py` existe (extrait par SP-43 Tâche 6) et porte
  `resolve_owner_user()`, réutilisée telle quelle par la Tâche 6 de ce
  document pour résoudre l'identité d'exécution d'un déclenchement webhook.
- `core/tests/test_model_alembic_parity.py` existe (SP-43 Tâche 1/5) : tout
  nouveau modèle SQLAlchemy introduit par ce document (Tâche 6) doit porter
  son `server_default=` dès l'écriture, pas en dette différée (leçon SP-43
  §1.6, déjà payée deux fois).

Aucune tâche de ce document ne dépend d'une tâche SP-43 spécifique : les
fichiers cités existent déjà et se comportent normalement, ce constat ne fait
que documenter les chemins réels à citer.

---

## 1. GAP-43 — Secret de connecteur pipeline : aucun sélecteur

**Vérifié** : `shell/src/builder/pipeline/PipelineNodeInspector.tsx::renderControl`
(lignes 126-209) ne connaît qu'un seul `format` spécial,
`"collection-id"` (ligne 127, délègue à `CollectionParamSelect`). Un champ
`secretName` (porté par `ReaderConnectorRestParams`/`ReaderConnectorPostgresParams`,
`core/app/pipelines/ops/schemas.py:158-184`) n'a **aucun** `format` déclaré
dans son schéma Pydantic — il retombe donc dans la branche générique
(ligne 190-208), un `<input type="text">` libre. L'opérateur doit connaître
par cœur le nom exact d'un secret déjà créé par ailleurs (`POST /secrets`,
`core/app/secrets/routes.py`, admin-only) : aucune UI shell n'existe pour
créer/lister/supprimer un secret — confirmé, zéro fichier `secrets` sous
`shell/src/api/domains/` ou `shell/src/builder/`.

Le coffre existe déjà et n'a besoin d'aucun changement de forme : 3 routes
(`POST/GET/DELETE /secrets`, admin-only via `Privilege.ADMIN_SECRETS_MANAGE`
= `"admin.secrets.manage"`, jamais `Privilege.AUTOMATION_SECRETS_MANAGE` =
`"automation.secrets.manage"` — cette 2e valeur existe dans le catalogue des
18 privilèges mais ne garde aucune route, cf. `CLAUDE.md` `REV-097`) et un
payload à discriminant `kind` (`api_key`/`bearer_token`/`basic_auth`/
`oauth2_client_credentials`/`postgres_dsn`/`smtp`, `core/app/secrets/schemas.py`).
Ne jamais retourner le payload déchiffré : les 3 routes ne renvoient que
`{id, name, kind, createdAt, updatedAt}` — le shell ne doit donc afficher
qu'un **sélecteur par nom**, jamais un formulaire d'édition de secret
existant (le cœur ne le permettrait de toute façon pas).

### Décision de conception

1. **Ajouter le marqueur de format côté cœur**, même patron que
   `collection-id` : `secretName: str | None = Field(default=None,
   json_schema_extra={"format": "secret-name"})` sur
   `ReaderConnectorRestParams`, et `secretName: str = Field(...,
   json_schema_extra={"format": "secret-name"})` sur
   `ReaderConnectorPostgresParams` (`core/app/pipelines/ops/schemas.py`).
   Exposé automatiquement par `GET /pipelines/ops` (`ops_catalog()`,
   `model_json_schema()`) — aucun changement de route nécessaire.
2. **Côté shell**, un nouveau domaine `shell/src/api/domains/secrets.ts` +
   `secrets.hooks.ts` (patron identique aux 11 domaines déjà découpés par
   SP-43) : `listSecrets()`, `createSecret()`, `deleteSecret()`, dérivés
   directement des 3 routes REST.
3. **Un composant `SecretParamSelect`** (`shell/src/builder/pipeline/`), calqué
   sur `CollectionParamSelect.tsx` (même fichier, même patron `<select>` +
   options) : liste les secrets existants (nom seul, jamais le payload), plus
   une action « Créer un secret » qui ouvre un formulaire minimal dont les
   champs dépendent du `kind` choisi (les 6 variantes de `SecretPayload`).
   Câblé dans `PipelineNodeInspector.renderControl` sur
   `prop.format === "secret-name"`, à côté de la branche `collection-id`
   existante.
4. **Réutilisation immédiate** : `ReportScheduleEditor.tsx` (ligne 76-81) et,
   après la Tâche 4 de ce document, `AlertRuleEditor` portent aussi un champ
   `smtpSecretName` en texte libre (`AlertChannelEmail.smtpSecretName`,
   `core/app/configs/schemas.py:300-303`) — même défaut, même correctif :
   `SecretParamSelect` filtré sur `kind === "smtp"`.

### Hors périmètre de ce point

- Aucune UI de **modification** d'un secret existant (le cœur ne l'expose
  pas — cohérent, un secret se recrée, ne se met jamais à jour partiellement).
- Ne pas router la création de secret par les routes `/pipelines/*` : elle
  reste un sous-domaine autonome (`/secrets`), consommé par plusieurs
  éditeurs (pipeline, alerte, rapport) — un seul point d'écriture, plusieurs
  points de lecture/sélection, cohérent avec la règle n°1 de CLAUDE.md.

---

## 2. GAP-44 — Planification du moissonnage : champ non exposé

**Vérifié** : `HarvestSourceCreateInput`/`HarvestSourcePatchInput`
(`shell/src/api/types.ts:764-775`) portent déjà `intervalMinutes?: number`,
côté cœur `core/app/harvest/schemas.py:12,19` déclare
`intervalMinutes: int | None = Field(default=None, ge=1)` sur les deux
schémas de création/patch, et `core/app/harvest/repository.py:204-229`
(`list_due_sources`) l'utilise déjà pour décider si une source est due. Un
`grep -n "intervalMinutes" shell/src/shell/CreateHarvestSourcePanel.tsx
shell/src/shell/EditHarvestSourcePanel.tsx` ne retourne **aucun résultat** :
confirmé, le champ n'est simplement jamais rendu dans les deux formulaires
(`shell/src/shell/CreateHarvestSourcePanel.tsx`,
`shell/src/shell/EditHarvestSourcePanel.tsx`), qui n'ont eux-mêmes aucun test
unitaire dédié (seule une poignée d'E2E `shell/e2e/harvest-*.spec.ts`,
aucune ne couvre la planification).

Contrairement à `PipelineRefreshPolicy` (un cron), `intervalMinutes` est un
entier brut en minutes, sans notion cron — `PipelineScheduleEditor` (le
composant cron déjà utilisé par pipelines/alertes/rapports) est **hors sujet
ici**, ne pas le réutiliser à tort.

### Décision de conception

Ajouter un simple champ numérique optionnel (« Intervalle de rafraîchissement
(minutes) », `type="number" min={1}`) dans les deux panneaux, lié à
`intervalMinutes` — même patron que les autres champs déjà présents
(`url`/`mode`/`enabled`). `CreateHarvestSourcePanel` l'envoie dans
`createSource.mutateAsync({..., intervalMinutes})` (`undefined` si vide,
cohérent avec `int | None` côté cœur) ; `EditHarvestSourcePanel` l'initialise
depuis `source.intervalMinutes` (`HarvestSource.intervalMinutes: number |
null`, ligne 758) et l'envoie dans le PATCH.

---

## 3. GAP-50 — `AlertRuleEditor` très en retrait vs `ReportScheduleEditor`

**Vérifié** : `shell/src/builder/AlertRuleEditor.tsx` (37 lignes utiles) :

- Ligne 45 : `query: { agg: "count" }` codé en dur dans `handleCreate()` —
  aucun contrôle UI pour choisir `agg`/`field`/`p`, alors que
  `AlertRulePayload.query` est un `AggregateRequestBody` complet côté cœur
  (`core/app/analytics/aggregate.py:35-47` : `groupBy`, `agg`, `field`, `p`,
  `measures`, etc. — l'alerte n'utilise en pratique qu'un sous-ensemble
  scalaire, cf. `_measure_value` dans `core/app/alerts/jobs.py:110-160`, qui
  exige que la requête réduise à exactement une ligne/une mesure).
- Ligne 48 : `channels: [{ kind: "webhook", url: webhookUrl }]` — aucune
  option email, alors que `AlertChannelEmail` existe déjà côté schéma
  (`core/app/configs/schemas.py:300-303`) et que le job d'évaluation sait déjà
  envoyer par ce canal (`core/app/alerts/jobs.py::_notify`, branche
  `AlertChannelEmail` → `send_email`).
- Aucune UI d'édition d'une règle existante — mais **le point de sortie
  existe déjà côté client** : `getAlertRuleConfig`/`saveAlertRuleConfig`
  (`shell/src/api/domains/alerts.ts:53-68`, `shell/src/api/types.ts:442-443`)
  sont déjà implémentées et testées (`itemClient.test.ts:2963-3013`), juste
  jamais appelées par un composant d'édition. `shell/src/shell/routes.tsx:82-94`
  documente explicitement (commentaire) qu'« une règle d'alerte n'a pas
  d'écran propre : elle s'édite dans la section Alertes de la page de son
  dataset » — décision de conception déjà actée, pas un oubli. **Ce document
  ne la rouvre pas** (cf. Hors périmètre ci-dessous) : le gap tel que
  formulé par GAP-50 porte sur la richesse du formulaire de **création**
  (canaux, requête), pas sur l'ajout d'un second écran d'édition.

`shell/src/builder/report/ReportScheduleEditor.tsx` est le patron cible pour
les canaux (lignes 32-45 : `<select>` webhook/email, lignes 47-85 : champs
propres à chaque canal) — mais **n'a lui-même aucune requête configurable**
(il référence un `Bookmark` existant, pas un agrégat ad hoc) : la
« requête configurable » du GAP-50 ne peut donc pas être copiée depuis ce
jumeau — elle doit être construite depuis un patron différent, déjà présent
ailleurs dans le dépôt : `shell/src/builder/DataSourcePanel.tsx` (lignes
161-193) construit déjà un sélecteur agrégat/champ/centile réutilisant
`ANALYTICS_AGGREGATES`/`aggregateNeedsP`/`DEFAULT_PERCENTILE`
(`shell/src/builder/aggregates.ts`) — c'est ce triplet qu'il faut réutiliser
pour la requête à mesure unique de l'alerte, pas réinventer une liste
d'agrégats.

### Décision de conception

1. **Canal** : ajouter le même `<select>` webhook/email que
   `ReportScheduleEditor` (lignes 32-45), avec les mêmes champs par canal —
   pour `email`, le champ `smtpSecretName` utilise `SecretParamSelect`
   (Tâche du §1) plutôt qu'un texte libre, un pas de plus que
   `ReportScheduleEditor` lui-même (qui garde un texte libre pour ce même
   champ — non repris ici, hors périmètre, cf. ci-dessous).
2. **Requête** : remplacer `query: { agg: "count" }` par un contrôle
   agg/champ/centile réutilisant `ANALYTICS_AGGREGATES`/`aggregateNeedsP`/
   `DEFAULT_PERCENTILE` de `builder/aggregates.ts` — un seul triplet
   (agg, field, p), pas de `groupBy`/`measures` (l'alerte exige un scalaire
   unique, cf. `_measure_value`).
3. **Rester un composant de création autonome** (ne pas migrer vers le patron
   valeur/onChange contrôlé de `ReportScheduleEditor` — la note de tête de ce
   dernier explique explicitement pourquoi les deux patrons divergent : le
   parent de `ReportScheduleEditor` a besoin d'un cycle création+édition+
   historique, celui d'`AlertRuleEditor` non, décision déjà actée par
   SP-16b/SP-17b, ne pas la rouvrir sans décision produit explicite).

### Hors périmètre de ce point

- **Écran d'édition d'une règle existante** — décision déjà actée (cf.
  ci-dessus), question ouverte pour une future session si Tanguy le
  souhaite, pas dans ce document.
- **Corriger `smtpSecretName` en texte libre sur `ReportScheduleEditor`** —
  gap voisin non catalogué par GAP-50 lui-même ; laissé en l'état pour ne
  pas élargir le périmètre au-delà du gap cité, mais noté comme incohérence
  résiduelle une fois `SecretParamSelect` disponible (question ouverte, §7).

---

## 4. GAP-48 — MCP : pas de création/exécution pour AlertRule

**Vérifié** : `core/app/mcp/tools/alerts.py` (52 lignes, extrait par SP-43
Étape 8) ne porte qu'un seul tool, `explain_alert_rule` — introspection pure,
aucune écriture. `core/app/mcp/tools/pipelines.py` (144 lignes, même
extraction) porte le triplet complet `create_pipeline`/`run_pipeline`/
`explain_pipeline`, chacun réutilisant la couche de service partagée avec la
route REST (`app.configs.service.create_config_service`,
`app.pipelines.service.run_pipeline_service`) — c'est le patron à reproduire.

Côté cœur, la création d'une règle d'alerte est **déjà** un cas générique de
`/configs` (`core/app/alerts/routes.py`, docstring : « Create/update/delete of
the rule itself are handled entirely by the generic /configs routes ») — donc
`create_alert_rule` peut être un décalque quasi exact de `create_pipeline`
(même appel à `create_config_service`, `kind="alert"` au lieu de
`"pipeline"`). En revanche, une alerte n'a **pas** d'équivalent exact de
`POST /pipelines/{id}/run` : son exécution est un job périodique
(`evaluate_alert_task`, déféré par `sweep_alert_rules_task`,
`core/app/alerts/jobs.py:257-271`), jamais une route REST « exécuter
maintenant ». `run_alert_rule` doit donc reproduire, côté MCP, exactement ce
que fait `sweep_alert_rules_task` pour **une seule règle** : créer une
`AlertEvaluation` (`alerts_repo.create_evaluation`), committer, déférer
`evaluate_alert_task` — sans passer par le balayage cross-tenant.

### Décision de conception

1. `create_alert_rule(ctx, title, datasetItemId, query, condition,
   refreshPolicy, channels, messageTemplate) -> ItemRead` — même forme que
   `create_pipeline`, construit un `AlertRulePayload` puis
   `BuilderConfig(kind="alert", alert=payload)`, appelle
   `create_config_service`. Monté **sans garde `CORE_ETL_ENABLED`**
   (contrairement à `pipelines.py` — les alertes ne sont pas gardées par ce
   flag, cf. `core/app/alerts/routes.py`, monté inconditionnellement).
2. `run_alert_rule(ctx, alertRuleId) -> dict` — vérifie l'accès en lecture
   (même garde que `explain_alert_rule`), crée une évaluation
   (`alerts_repo.create_evaluation`), commit, défère
   `evaluate_alert_task.defer(evaluation_id=..., tenant_id=...)`, retourne
   `{"evaluationId": evaluation.id}` (miroir de `{"runId": ...}` côté
   pipeline).
3. Test de parité : étendre `core/tests/test_mcp_rest_parity.py` (créé par
   SP-43 Étape 8) avec le cas alerte, même si `run_alert_rule` n'a pas de
   route REST jumelle exacte — comparer plutôt son effet observable (une
   ligne `AlertEvaluation` `pending` créée, un déféré sur la queue `etl`) à
   celui de `sweep_alert_rules_task` pour une règle unique.

### Hors périmètre de ce point

- Pas de `update_alert_rule`/`delete_alert_rule` MCP dédiés — génériques via
  les tools `update_config`/`delete_item` déjà existants (si présents ; à
  vérifier au moment de l'implémentation, ne pas supposer).

---

## 5. GAP-49 — Extension : pas de retour proactif sur les collections restreintes

**Vérifié, et partiellement contredit par le code réel (piège CLAUDE.md
n°12)** : le GAP affirme « aucun retour visible dans l'éditeur avant l'échec
de sauvegarde ». C'est faux pour le cas principal —
`shell/src/builder/wc/generatedPropsPanel.tsx::permittedDataSources()`
(lignes 8-14, livré par SP-8b le 2026-07-13, donc **avant** la revue SP-42
elle-même) filtre déjà le `<select>` de `DataSourceSelect` aux seules
sources dont `.layer` figure dans `manifest.permissions.collections` — un
auteur ne peut donc **pas choisir** une collection hors périmètre pour un
nouveau binding. Le commentaire du fichier documente explicitement que ce
filtre est « d'autorat, pas une frontière de sécurité » — la vraie garde
reste `validate_extension_permissions` côté cœur
(`core/app/configs/extension_permissions.py`, appelée à la sauvegarde par
`core/app/configs/service.py:85` et `core/app/mcp/tools/configs.py:63`).

Le manque réel, plus étroit que ce que dit le GAP : si le binding existant
d'un widget (`item.props[prop_name]`) pointe déjà vers une source devenue
hors périmètre — permissions de l'extension resserrées après coup, config
importée/écrite par MCP en contournant le filtre d'autorat, ou widget copié
depuis un autre AppConfig — le `<select>` de `DataSourceSelect` se retrouve
avec une `value` qui ne correspond à **aucune** de ses `<option>` : le
navigateur affiche un état vide, silencieusement, sans indiquer à l'auteur
*pourquoi* ni que la sauvegarde échouera avec la même
`ExtensionPermissionError` que `validate_extension_permissions` lève déjà
côté cœur (`core/app/configs/extension_permissions.py:9-17`).

### Décision de conception

Dans `makeGeneratedPropsPanel` (`generatedPropsPanel.tsx`), pour chaque prop
`dataSource` : si `props[p.name]` référence un `DataSource` dont `.layer`
n'est pas dans les collections permises (même calcul que
`permittedDataSources`, mais appliqué à la valeur courante plutôt qu'à la
liste des options), afficher un texte d'alerte inline (`role="alert"`) sous
le sélecteur — même patron visuel que `errors.map(...)` dans
`PipelineNodeInspector` (§1) — avant toute tentative de sauvegarde, avec le
même message que produirait `ExtensionPermissionError` côté cœur (pour que
l'utilisateur relie les deux s'il voit un jour l'erreur serveur).

---

## 6. GAP-24 — Aucun déclenchement de pipeline par webhook entrant

C'est le chantier le plus consistant du lot (3-5 j-h estimés par la revue).
Contrairement aux 5 points précédents, il introduit une nouvelle capacité,
pas seulement une UI manquante — **hors périmètre du principe « pas de
changement de comportement fonctionnel » de SP-43**, ce qui est cohérent :
SP-53 n'est pas une suite de SP-43, c'est un chantier produit distinct.

### 6.1 Ce qui existe déjà et doit être réutilisé, pas dupliqué

`core/app/pipelines/service.py::run_pipeline_service()` (extrait par SP-43
Étape 8) est **le** point de passage partagé entre `POST
/pipelines/{id}/run` (REST) et `run_pipeline` (MCP, `actor_kind` distinct
pour l'audit seulement). Il fait, dans cet ordre : `require_pipeline_access`
(action write) → `require_pipeline_config` → garde
`require_data_manage_if_pipeline_writes_dataset` → `pipelines_repo.create_run`
→ `write_audit("pipeline.run")` → **commit avant de déférer** →
`defer_task(run.id, tenant_id)` (qui appelle
`run_pipeline_task.defer(...)`, la tâche procrastinate réelle sur la queue
`"etl"`).

Le balayage cron (`run_pipeline_jobs.py::run_pipeline_sweep_task`, périodique
`*/5 * * * *`) **n'appelle pas** `run_pipeline_service` — il fait sa propre
séquence `create_run` → commit → `run_pipeline_task.defer(...)`, sans
repasser par les gardes d'accès (le pipeline a déjà été validé à la
sauvegarde, cf. `_require_data_manage_if_pipeline_writes_dataset` appelé à
l'écriture de la config). C'est la **2e** implémentation de cette séquence,
distincte du service partagé REST/MCP — **ne pas en créer une 3e** pour le
webhook : le webhook doit appeler `run_pipeline_service` lui-même (comme
REST/MCP), avec un `actor_kind="webhook"` dédié pour l'audit, jamais
réinventer `create_run`+`defer` en ligne une 3e fois. C'est la vérification
demandée explicitement par le brief de cette tâche, confirmée par lecture
directe des deux fichiers (`app/pipelines/service.py`,
`app/pipelines/jobs.py`).

`app.jobs.common.resolve_owner_user(session, tenant_id=, item_id=)` (extrait
par SP-43 Tâche 6) résout déjà l'utilisateur propriétaire d'un item pour
exécuter une action en son nom — c'est le patron « double vérification »
déjà utilisé par `run_pipeline_task`/`evaluate_alert_task`/le futur
déclenchement webhook : un appelant externe non authentifié OIDC ne peut pas
être un `User` FastAPI, donc le webhook s'exécute **avec l'identité du
propriétaire du pipeline**, re-vérifiée par `require_pipeline_access` à
l'intérieur de `run_pipeline_service` exactement comme pour le cron/MCP — si
le propriétaire a perdu l'accès depuis la création du jeton, le
déclenchement échoue proprement (jamais un contournement admin implicite).

Le rate limiter existant (`core/app/ratelimit/limiter.py`, design SP-26 §3.4)
clé déjà sur l'en-tête `Authorization` brut, lu **avant** l'injection de
dépendances FastAPI — un jeton de webhook porté en `Authorization: Bearer
<token>` bénéficie donc du même mécanisme sans aucun changement de son
fonctionnement interne, seulement l'ajout d'un nouveau groupe de route dans
`route_group()`/`_BUDGETS`.

### 6.2 Ce qui n'existe pas et doit être créé

- Aucun modèle de jeton de déclenchement (`grep -rn "webhook" core/app
  --include=*.py` ne montre que le canal **sortant** des alertes/rapports,
  jamais un mécanisme entrant).
- Aucune route publique (sans `get_current_user`) dans tout `core/app` en
  dehors des endpoints déjà publics par nature (santé, OIDC discovery) — ce
  sera la première route métier du dépôt sans dépendance OIDC, à documenter
  explicitement comme telle.

### 6.3 Décision de conception

**Modèle** (`core/app/pipelines/models.py`, migration `0035`) :
`PipelineWebhookToken` — `id` (uuid hex), `tenant_id` (FK `tenants.id`),
`pipeline_item_id` (FK `items.id`), `token_hash` (SHA-256 hex du jeton brut,
**jamais** le jeton en clair — même discipline que le coffre de secrets, qui
ne retourne jamais son ciphertext), `created_by` (FK `users.id`),
`created_at`, `last_used_at` (nullable). Index unique sur `token_hash` (la
recherche au moment du déclenchement se fait par hash seul, sans connaître
le tenant à l'avance — un appelant externe n'a que le jeton).

**Génération** (`core/app/pipelines/service.py`, nouvelle fonction
`create_webhook_token_service`) : `require_pipeline_access(write)` **et**
`require_privilege(Privilege.AUTOMATION_SECRETS_MANAGE.value)` — ce
privilège existe déjà dans le catalogue des 18 (`core/app/roles/
privileges.py:12`) mais ne garde aujourd'hui **aucune** route (`CLAUDE.md`,
`REV-097`, 2 des 18 privilèges orphelins) ; un jeton de déclenchement est
un secret d'automatisation par nature, c'est l'endroit naturel où le câbler
— referme un des deux privilèges de `REV-097` en sous-produit direct de
cette tâche, pas une correction indépendante hors périmètre. Génère
`secrets.token_urlsafe(32)`, hache en SHA-256, persiste le hash, **retourne
le jeton en clair une seule fois** dans la réponse HTTP — jamais recalculable
ni relisible ensuite (même garantie que le coffre de secrets, formulée à
l'envers : lui ne rend jamais le clair, ici on le rend une fois puis plus
jamais).

**Déclenchement** (`core/app/pipelines/service.py`,
`trigger_pipeline_by_webhook_service(session, *, item_id, raw_token,
defer_task) -> str`) :
1. Hacher `raw_token`, chercher par `token_hash` (cross-tenant, index
   unique) — absent ou `pipeline_item_id` différent de `item_id` du chemin
   → `HTTPException(404)` (jamais 401/403 : ne pas révéler si le jeton
   existe mais pour un autre pipeline).
2. `resolve_owner_user(session, tenant_id=row.tenant_id,
   item_id=row.pipeline_item_id)` (`app.jobs.common`).
3. `run_pipeline_service(session, user=owner, item_id=row.pipeline_item_id,
   defer_task=defer_task, actor_kind="webhook")` — **le même appel** que la
   route REST et le tool MCP, seul `actor_kind` diffère (déjà un paramètre
   du service, aucune signature à changer).
4. Mettre à jour `last_used_at` sur la ligne du jeton (best-effort, hors du
   chemin critique).

**Routes** (`core/app/pipelines/routes.py`, toutes sous la garde
`is_etl_enabled()` déjà existante pour ce routeur) :
- `POST /pipelines/{item_id}/webhook-tokens` (authentifié) → crée un jeton,
  répond `{id, token, createdAt}` (le seul moment où `token` apparaît).
- `GET /pipelines/{item_id}/webhook-tokens` (authentifié) → liste
  `{id, createdAt, lastUsedAt}`, **jamais** `token`/`tokenHash`.
- `DELETE /pipelines/{item_id}/webhook-tokens/{token_id}` (authentifié) →
  révocation.
- `POST /pipelines/{item_id}/trigger` — **la seule route sans
  `Depends(get_current_user)`** de tout le dépôt : lit `Authorization:
  Bearer <token>` elle-même (FastAPI `Header` ou parsing direct, à trancher
  à l'implémentation), appelle `trigger_pipeline_by_webhook_service`.
  Répond `202 {"runId": ...}` (même forme que `RunResponse` existant).

**Rate limiting** (`core/app/ratelimit/limiter.py`) : nouveau groupe
`"webhook-trigger"` dans `_BUDGETS` (proposition : 30/60s — à confirmer avec
Tanguy, cf. §7) et un nouveau `_WEBHOOK_TRIGGER_RE = re.compile(r"^/pipelines/
[^/]+/trigger$")` dans `route_group()` — bénéficie automatiquement de la
purge périodique déjà en place, aucun changement à `RateLimiter` lui-même.

**Anti-rejeu** : décision explicite de **ne pas** ajouter de nonce/fenêtre
temporelle signée (façon HMAC de webhook sortant GitHub) pour ce v1. Un
déclenchement dupliqué crée simplement un `PipelineRun` de plus (même
comportement qu'un utilisateur qui clique deux fois sur « Exécuter ») —
mitigé par le rate limiting ci-dessus, pas par un mécanisme de
déduplication dédié. Documenté comme décision assumée, pas un oubli (cf.
§7 si Tanguy veut revenir dessus).

**Shell** : nouveau composant `PipelineWebhookTrigger`
(`shell/src/builder/pipeline/`), inséré dans `PipelineBuilderPage.tsx` juste
après le bloc `PipelineScheduleEditor` existant (même garde `pk !== null`,
lignes 220-228 aujourd'hui) : liste des jetons existants (id tronqué,
créé le, dernier usage), bouton « Générer un jeton » (affiche le jeton en
clair une seule fois, dans un encart avec avertissement explicite « ne sera
plus jamais affiché », plus l'URL complète prête à copier), bouton
« Révoquer » par jeton. Nouveaux hooks dans
`shell/src/api/domains/pipelines.hooks.ts`/`pipelines.ts` (patron identique
aux hooks pipeline déjà là : `usePipelineWebhookTokens`,
`useCreatePipelineWebhookToken`, `useRevokePipelineWebhookToken`).

### Hors périmètre de ce point

- Signature HMAC du corps de requête entrant (façon GitHub/Stripe webhooks)
  — le webhook GeoStudio n'a pas de corps à authentifier (c'est un simple
  déclenchement, pas un événement porteur de données), donc pas de
  signature de payload, seulement un secret bearer.
- Idempotency-Key / déduplication de rejeu — cf. décision ci-dessus.
- Déclenchement d'AlertRule ou de ReportSchedule par webhook — le gap ne
  cite que les pipelines ; les deux autres kinds gardent leur balayage cron
  seul.
- Multi-jeton avec portée restreinte (ex. un jeton par nœud plutôt que par
  pipeline) — un jeton = un pipeline entier, cohérent avec la granularité
  déjà existante de `run_pipeline_service` (aucune notion de sous-graphe
  déclenchable séparément).

---

## 7. Questions ouvertes (à trancher avec Tanguy avant/pendant l'exécution)

1. **Budget du rate limiter `webhook-trigger`** (proposition 30/60s) — à
   confirmer ; un webhook entrant légitime (CI externe, capteur IoT) peut
   avoir un profil d'appel différent des groupes existants (`sql`/`llm`/
   `jobs`/`harvest`).
2. **`smtpSecretName` en texte libre sur `ReportScheduleEditor`** (§3,
   « Hors périmètre ») : une fois `SecretParamSelect` disponible, faut-il
   l'y câbler aussi dans ce même SP (extension naturelle, petit diff) ou le
   laisser au backlog (le gap catalogué ne le cite pas explicitement) ?
3. **Écran d'édition dédié pour `AlertRule`** (§3) : le gap ne le demande
   pas, mais l'absence combinée à l'enrichissement du formulaire de création
   (§3) peut rendre plus visible l'impossibilité de corriger une règle après
   coup — décision produit à confirmer, pas une décision technique.

---

## 8. Hors périmètre global (explicite)

- Tout changement de comportement sur les 5 autres kinds (`bookmark`,
  `report`, `dataset`, `map`, `app`/`dashboard`/`site`) au-delà des points
  cités.
- `REV-097` (privilège `tasks.view_all` orphelin) — seul
  `automation.secrets.manage` (l'autre moitié du même suivi) est refermé,
  en sous-produit direct de la Tâche 6 (§6.3), pas par une correction dédiée.
- Toute nouvelle capacité de moissonnage (connecteurs, formats) au-delà de
  l'exposition du champ déjà supporté par l'API (§2).
- Le découpage structurel plus large de SP-43 (`itemClient.ts`, etc.) — sans
  rapport avec ce document, déjà traité ailleurs.
