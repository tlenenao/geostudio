# Notifications in-app (SP-39)

> Ferme le chantier 4.19 « Notifications in-app »
> (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md`, vague 4) : « Zéro
> toast/notification dans le shell, pour cinq familles de jobs asynchrones
> (ingestion, pipelines, export, export d'app, rapports). Preuve de sortie :
> un run de pipeline en échec est signalé même si l'utilisateur a quitté le
> panneau de suivi. » Spec brainstormée et validée avec Tanguy le 2026-09-04,
> à la suite de la clôture de SP-38 (4.21, admin des utilisateurs).

## 1. Contexte & objectif

Vérifié par lecture directe du code (pas supposé) : **zéro** mécanisme de
notification n'existe aujourd'hui.

- `shell/src/ui/kit/Toast.tsx` (SP-29b) existe mais n'est **jamais consommé
  en production** — seul `KitGalleryPage.tsx` le monte, à titre de démo.
  C'est un composant entièrement contrôlé (`open`/`onOpenChange`), sans file
  d'attente ni API impérative.
- Les 5 familles de jobs asynchrones (`ingestion_jobs`, `pipeline_runs`,
  `export_jobs`, `app_export_jobs`, `report_runs`) n'exposent chacune qu'un
  statut **par item/job**, jamais de liste agrégée « mes jobs » — confirmé
  par grep exhaustif sur `shell/src/api/itemClient.ts` (aucune méthode
  `listMyJobs`/équivalent).
- Le suivi de statut existant (`PipelineRunPanel`, `ExportPanel`,
  `AppExportPanel`, `ReportRunPanel`, `ImportFileButton`) sonde en `state`
  React **local au composant** — la boucle de sondage meurt (ou continue
  silencieusement sans plus jamais être écoutée, pour `PipelineRunPanel`/
  `ImportFileButton`, qui n'ont pas de garde de démontage) dès que
  l'utilisateur quitte le panneau. C'est exactement ce que la preuve de
  sortie du chantier vise à corriger.
- Aucune infrastructure temps réel n'existe dans `core/` (ni WebSocket, ni
  SSE serveur — confirmé, les deux faux positifs identifiés lors de
  l'exploration, `StreamingResponse` de téléchargement et un header SSE
  côté *client* MCP sortant, ne sont pas des event streams).
- `AlertRule` (SP-16b) a déjà un mécanisme de notification (webhook/email,
  `app/alerts/notify.py`), mais **aucun mode in-app** — hors périmètre ici,
  ce chantier ne touche pas aux alertes.

## 2. Décisions actées avec Tanguy (brainstorming)

1. **Persistance côté cœur**, pas seulement en mémoire navigateur — une
   notification doit être visible même après un rechargement de page ou une
   nouvelle session.
2. **États terminaux seulement** (succès/échec) — pas de notification sur
   les transitions intermédiaires (démarrage, progression).
3. **Cloche + panneau persistant** dans la `TopBar`, pas de toast éphémère
   dans cette v1 (le kit `Toast` reste non consommé après ce chantier — sujet
   ouvert pour une itération future, hors périmètre).
4. **Sondage périodique léger** (30-60 s) pour le badge de compte non-lus et
   la liste, pas de WebSocket/SSE — le dépôt n'a aucune brique temps réel
   aujourd'hui, en construire une pour un badge de notification serait un
   chantier à part entière très au-dessus du calibrage « M » de 4.19.
5. **Réglage d'affichage persisté côté cœur** (pas un simple filtre local
   non mémorisé) : `all | failures_only | none`, un seul réglage global
   (pas par famille de job).
6. **Destinataire pour `PipelineRun`/`ReportRun`** (qui n'ont aucune colonne
   utilisateur, un run pouvant être déclenché par cron) : le **propriétaire
   de l'item**, résolu de la même façon que le fait déjà
   `reports/jobs.py::_owner_user` pour le canal email/webhook existant.

## 3. Périmètre

### 3.1 Cœur — nouveau domaine `core/app/notifications/`

**Modèle de données** (migration Alembic, testée dans les deux sens sur
base non vide — piège n°8) :

- **`notifications`** :
  - `id: str` (PK)
  - `tenant_id: str` (FK `tenants.id`)
  - `recipient_user_id: str` (FK `users.id`)
  - `kind: str` — `"ingestion" | "pipeline" | "export" | "appexport" |
    "report"`
  - `status: str` — `"success" | "failure"`
  - `item_id: str | None` (FK `items.id`, `ondelete="SET NULL"`) — sert
    uniquement à construire le lien « ouvrir » ; `None` sur un échec
    d'ingestion (rien n'a été créé)
  - `item_resource_type: str | None` — le `ResourceType` du shell
    correspondant à `item_id`, nécessaire pour réutiliser tel quel le
    routeur d'ouverture existant côté shell (§3.2) ; fixe par famille sauf
    `export`, où il vaut `"map"` ou `"app"` selon `config.kind` (le job
    d'export rend déjà l'un ou l'autre, `export/jobs.py:111`)
  - `item_title: str` — **capturé à l'écriture**, pas de jointure au moment
    de la lecture : un item supprimé plus tard n'efface pas l'historique,
    même logique que les snapshots `payload` JSON d'`audit_log`
  - `error_message: str | None` — recopié depuis la colonne d'erreur du job
    source (`error`/`error_message` selon la famille) quand `status ==
    "failure"`
  - `created_at: datetime`
  - `read_at: datetime | None`
  - Index `(tenant_id, recipient_user_id, created_at)` (liste),
    `(tenant_id, recipient_user_id, read_at)` (compte non-lus)
- **`notification_preferences`** :
  - `user_id: str` (PK, FK `users.id`)
  - `tenant_id: str`
  - `value: str` — `"all" | "failures_only" | "none"`, défaut `"all"`
  - `updated_at: datetime`
  - Table dédiée plutôt qu'une colonne sur `User` : `app/users/models.py`
    est un module fondation, très bas dans le contrat de couches
    (`core/pyproject.toml::[tool.importlinter]`) ; un domaine qui doit
    justement se situer au-dessus n'a pas à le modifier. Absence de ligne
    = valeur par défaut `"all"` (pas de migration de données requise).

**Placement dans le contrat de couches** (vérifié contre
`core/pyproject.toml`, `[[tool.importlinter.contracts]]` « layered
architecture ») : `app.notifications` doit être en dessous des 5 familles
émettrices (`app.pipelines`, `app.reports`, `app.export`, `app.appexport`,
`app.ingestion`, toutes doivent pouvoir l'importer) et au-dessus
d'`app.items` (résolution du titre/propriétaire) et `app.auth`
(`get_current_user` dans ses propres routes). Une seule bande satisfait les
deux contraintes dans l'ordre actuel du contrat : entre `app.ingestion` et
`app.dcat`.

**Écriture — best-effort, jamais bloquante pour le job lui-même.** Chaque
famille appelle `create_notification(session, ...)` (nouveau,
`app/notifications/repository.py`) dans un bloc `try/except` **séparé**,
juste après son propre `mark_done`/`mark_error`/`mark_succeeded`/
`mark_failed` déjà committé — une erreur d'écriture de notification (index
UO, session cassée) est loguée et avalée, elle ne doit jamais faire échouer
le job dont le statut est déjà persisté. Écriture **inconditionnelle** quel
que soit `notification_preferences.value` du destinataire — le filtre ne
s'applique qu'à la lecture (§3.1, `GET /notifications`), pour que changer le
réglage plus tard ne perde pas l'historique déjà écrit.

| Famille | Site d'écriture (vérifié par lecture directe) | Destinataire | `item_resource_type` |
|---|---|---|---|
| Ingestion | `ingestion/tasks.py::run_ingestion_task` — succès l.71-76, échec l.79 et 82-85 | `job.created_by` (déjà en scope local) | `"dataset"` (fixe) ; `item_id=None` sur échec |
| Pipeline | `pipelines/jobs.py::run_pipeline_task` — succès l.136-140, échec l.143 et 147 | propriétaire de l'item (résolution identique à `_acting_user`, déjà défini dans ce fichier, l.39-54) | `"pipeline"` (fixe) |
| Export | `export/jobs.py::render_export_task` — succès l.155, échec l.91 et 159 | `job.user_id` (déjà en scope local, l.100) | `"map"` ou `"app"` selon `config.kind` (déjà résolu l.111) |
| Export d'app | `appexport/jobs.py::build_app_export_task` — succès l.111, échec l.74-76 et 115 | `job.user_id` (à capturer en local — pas encore fait à ce jour, seuls `item_id`/`mode` le sont, l.83-84) | `"app"` (fixe) |
| Rapport | `reports/jobs.py::_notify_pending_reports` (l.242-362) et le run à `export_job_id is None` de `_record_trigger_failure` (l.73-97, toujours un échec) | propriétaire de l'item rapport (même `_owner_user`, l.49-57, déjà utilisé pour le canal email/webhook) | `"report"` (fixe) |

**Deux pièges évités, vérifiés en amont plutôt que découverts en revue
finale :**

- **Double notification sur un export interne à un rapport.** Un rapport
  planifié crée un `ExportJob` avec `page_id` renseigné
  (`reports/jobs.py:153`, `page_id=bookmark.pageId` — champ documenté comme
  « renseigné uniquement par le sweep de `app.reports.jobs` »,
  `export/models.py:24-26`). Le site d'écriture d'`export/jobs.py` **saute**
  la création d'une notification `kind="export"` quand `job.page_id is not
  None` : l'issue de ce rendu sera déjà notifiée comme `kind="report"` par
  `_notify_pending_reports`.
- **Notification indépendante des canaux email/webhook configurés.**
  `_notify_pending_reports` boucle aujourd'hui sur `payload.channels` (email/
  webhook, configurables par le propriétaire du rapport, potentiellement
  vides). La notification in-app n'est **pas** un canal au même sens — elle
  s'écrit une fois par run, que `channels` soit vide ou non.

**API** (`core/app/notifications/routes.py`, self-service — aucun privilège
dédié requis, même porte d'entrée que `GET /me` : chaque utilisateur ne lit
et ne modifie que ses propres notifications/préférence, filtrées par
`tenant_id` **et** `recipient_user_id == current_user.id`) :

- `GET /notifications?cursor=&limit=` — paginé par curseur, plus récent
  d'abord, filtré selon `notification_preferences.value` du demandeur.
- `GET /notifications/unread-count` — même filtre ; c'est cet endpoint que
  la `TopBar` sonde en arrière-plan.
- `POST /notifications/{id}/read` — idempotent, 404 si hors tenant ou hors
  destinataire.
- `POST /notifications/read-all` — marque lu tout ce qui est actuellement
  non lu **et** visible sous le filtre courant.
- `GET /notifications/preference` / `PATCH /notifications/preference`
  (`{value: "all" | "failures_only" | "none"}`, 400 sur valeur hors enum).

### 3.2 Shell

- `ItemClient` (`shell/src/api/itemClient.ts`) : `listNotifications`,
  `getUnreadNotificationCount`, `markNotificationRead`,
  `markAllNotificationsRead`, `getNotificationPreference`,
  `updateNotificationPreference` + types `NotificationSummary`,
  `NotificationPreference`.
- Hooks (`shell/src/api/hooks.ts`) : `useNotifications({cursor, limit})`,
  `useUnreadNotificationCount()` (React Query, `refetchInterval: 45_000`,
  actif quelle que soit la page — monté une fois, pas par page),
  `useMarkNotificationRead()`, `useMarkAllNotificationsRead()`,
  `useNotificationPreference()`, `useUpdateNotificationPreference()`.
- `NotificationBell` (nouveau, `shell/src/shell/chrome/`), monté dans
  `TopBar.tsx` à côté d'`AccountMenu` : icône + badge de compte (masqué si
  0), ouvre un `Popover` du kit contenant `NotificationPanel` — liste
  paginée (icône par `kind`, `item_title` ou libellé générique si `item_id`
  est `null`, statut, horodatage relatif, `error_message` si échec),
  sélecteur de réglage (`Tous / Échecs seulement / Aucune`), bouton « Tout
  marquer comme lu ».
- **Navigation au clic** : réutilise **tel quel** le routeur d'ouverture
  déjà existant, `useOpenItem()` (`shell/src/shell/routes.tsx:45-116`) —
  `onOpenItem(notification.itemId, notification.itemResourceType)` couvre
  déjà les 5 familles concernées (`dataset`, `pipeline`, `map`/`app`,
  `report`) sans code de routage dupliqué. Une ligne dont `itemId` est
  `null` (échec d'ingestion) n'est pas cliquable.
- **Marquage lu** : au clic sur une ligne (navigation) et via « Tout marquer
  comme lu » — **pas** d'auto-marquage à l'ouverture du panneau, pour ne pas
  faire disparaître le badge avant lecture réelle par l'utilisateur.
- **Pas de nouveau flag de capacité** (`CORE_*_ENABLED`) pour la cloche
  elle-même — `NotificationBell` est monté inconditionnellement dans
  `TopBar`. Chaque famille de job reste gouvernée par sa propre capacité
  existante (`CORE_ETL_ENABLED`, `CORE_EXPORT_ENABLED`, etc.) : si une
  capacité est coupée, ses jobs ne tournent jamais et ne produisent donc
  jamais de notification — la cloche est simplement silencieuse pour cette
  famille, pas besoin de la masquer explicitement.

### 3.3 CLAUDE.md

Ligne `### Livré` datée SP-39 à la clôture ; 4.19 retiré de toute liste de
suivi informelle si elle y apparaît (le document de référence
`2026-08-20-revue-projet-et-plan-daction.md` n'est pas modifié, seule
CLAUDE.md liste les chantiers vague 4 restants de façon informelle — même
règle que SP-38 §2.7).

## 4. Hors périmètre, explicitement

- **Toast éphémère en direct** — décision actée §2.3 : cloche + panneau
  seuls dans cette v1.
- **WebSocket/SSE** — décision actée §2.4.
- **Réglage par famille de job** — décision actée §2.5, un seul réglage
  global.
- **Notifications pour `AlertRule`** — a déjà webhook/email
  (`app/alerts/notify.py`), hors des 5 familles nommées par le chantier.
- **Purge/rétention** — aucune purge automatique dans cette v1, même
  posture que `audit_log` (déjà non purgé dans ce dépôt) ; seule la
  pagination par curseur borne le coût de lecture. À revisiter si le volume
  devient un problème réel.
- **Notification sur le chemin « capacité désactivée après mise en file »**
  — `export/jobs.py:89-92` et son jumeau `appexport/jobs.py` retournent tôt
  (`mark_error`) **avant** d'avoir chargé `item_id`/`user_id`/`page_id`
  depuis la ligne de job ; ce chemin ne déclenche pas de notification
  (nécessiterait une lecture supplémentaire pour un cas déjà rarissime — un
  admin coupe la capacité entre la mise en file et l'exécution du job). Même
  limite que l'absence d'audit sur ce chemin aujourd'hui (vérifié : ce
  chemin n'est audité nulle part non plus).
- **Email/push/autre canal de sortie** — in-app uniquement.
- **Toute modification d'`app/alerts/`** — consommé tel quel.

## 5. Tests

1. **Cœur** (`core/tests/test_notifications_*.py`, nouveau module) :
   - Migration testée dans les deux sens sur base non vide.
   - `create_notification` : écrit une ligne correcte pour chacune des 5
     familles (fixture par famille), y compris le cas `item_id=None`
     (échec d'ingestion) et `item_resource_type` correct pour `export`
     (`"map"` et `"app"` selon `config.kind`, deux cas).
   - **Le cas du double-comptage évité** : un `ExportJob` avec `page_id`
     renseigné ne produit **pas** de notification `kind="export"` — seule
     `kind="report"` apparaît après le passage de
     `_notify_pending_reports`.
   - `GET /notifications` : pagination par curseur, filtre
     `all`/`failures_only`/`none` appliqué, isolation tenant + destinataire
     (un autre utilisateur du même tenant ne voit pas la notification).
   - `GET /notifications/unread-count` : reflète le même filtre.
   - `POST /notifications/{id}/read`, `/read-all` : idempotence, 404
     cross-tenant/cross-destinataire.
   - `GET`/`PATCH /notifications/preference` : 400 sur valeur hors enum,
     valeur par défaut `"all"` en l'absence de ligne.
   - Écriture de notification défaillante (mock d'erreur) ne fait **pas**
     échouer `mark_done`/`mark_error` du job source (test dédié par
     famille, ou au moins un cas représentatif).
   - Non-régression : les 5 tâches procrastinate existantes continuent de
     passer sans modification de comportement observable côté statut du
     job.
2. **Shell — Vitest** :
   - `NotificationBell`/`NotificationPanel` : badge masqué à 0, affiché
     sinon ; liste rendue avec icône/titre/statut/horodatage ; ligne sans
     `itemId` non cliquable ; clic sur une ligne avec `itemId` appelle
     `onOpenItem` avec les bons `pk`/`type` (mock de `useOpenItem`) et
     marque la ligne lue ; « Tout marquer comme lu » appelle la mutation
     correspondante ; changement de réglage appelle
     `updateNotificationPreference` avec la bonne valeur.
   - `useUnreadNotificationCount` : `refetchInterval` configuré (assertion
     sur la config React Query, pas sur un vrai minuteur — cf. piège n°7,
     une durée ne prouve rien).
3. **Pas de nouveau spec E2E dédié dans cette v1** — cohérent avec le
   périmètre des pages admin précédentes (SP-38 n'en a pas ajouté non plus)
   ; si la suite E2E complète (piège n°6, à lancer avant clôture) révèle une
   régression croisée, la corriger comme d'habitude. À reconsidérer si le
   contrôle manuel de bout en bout (stack complète, cf. §6) révèle un besoin
   réel non couvert par Vitest+pytest.
4. `npm run test`, `uv run pytest`, `npm run e2e` verts ; couverture shell
   non régressée (seuil 88, mesurée après nettoyage de `dist/`/
   `dist-export/`), couverture cœur non régressée (seuil 85).
5. **Régénération OpenAPI/types TS obligatoire** (piège n°1) : 6 nouvelles
   routes — incantation habituelle (`cd core && PYTHONPATH=.
   CORE_SECRETS_MASTER_KEY=... uv run python scripts/export_openapi.py
   openapi.json` puis `npm run gen:api-types`).
6. **Contrôle manuel recommandé, non bloquant** (comme SP-38) : si une stack
   `docker compose up -d` est disponible pendant l'exécution, déclencher au
   moins un job par famille (upload GeoJSON, run de pipeline, export de
   carte, export d'app, run de rapport manuel) et vérifier la notification
   de bout en bout — sans quoi, documenter explicitement l'absence de ce
   contrôle, comme SP-38 §Livré l'a fait.

## 6. Critères de sortie

1. Un run de pipeline en échec est signalé dans la cloche même si
   l'utilisateur a quitté `PipelineRunPanel` avant la fin (preuve de sortie
   littérale du chantier 4.19).
2. Les 5 familles (ingestion, pipeline, export, export d'app, rapport)
   produisent chacune une notification correcte sur succès et sur échec,
   sans double-comptage pour les rapports planifiés.
3. Le badge de compte non-lus se met à jour sans rechargement de page
   (sondage périodique), quelle que soit la page affichée.
4. Le réglage `all`/`failures_only`/`none` persiste côté cœur (survit à un
   rechargement/reconnexion) et filtre à la fois la liste et le compte.
5. Cliquer une notification liée à un item existant ouvre son écran
   d'édition via le routeur d'ouverture existant, sans code de routage
   dupliqué.
6. Suites cœur et shell vertes, OpenAPI/types régénérés, CLAUDE.md à jour
   (entrée `### Livré` SP-39).

## 7. Risques et limites connues

- **Best-effort explicite** : une notification peut se perdre (erreur
  d'écriture avalée) sans que le job source en soit affecté — c'est une
  garantie **plus faible** que le statut du job lui-même, assumé
  délibérément (§3.1) plutôt que de risquer de faire échouer un job pour un
  problème de notification.
- **Aucune notification sur le chemin « capacité désactivée » d'export/
  export d'app** — cf. §4, limite connue et documentée, pas une régression.
- **Croissance non bornée de la table `notifications`** — pas de purge en
  v1 (cf. §4) ; à surveiller sur un tenant à fort volume de jobs, comme
  `audit_log` déjà aujourd'hui.
- **Pas de temps réel** — un badge peut rester périmé jusqu'à 45 s après
  l'événement réel (intervalle de sondage), assumé §2.4.
- **`item_resource_type` dupliqué avec `item.resourceType`** — dénormalisé
  à l'écriture plutôt que rejoint à la lecture (même choix que
  `item_title`, §3.1) ; si `ResourceType` gagne une valeur qui change le
  mapping `kind`→type pour une famille existante, ce mapping devra être mis
  à jour ici aussi — pas de source de vérité unique, risque de dérive
  documenté.
