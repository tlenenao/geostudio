# SP-47 — Audit, gouvernance des privilèges et vue d'usage

## 1. Contexte & objectif

Deux manques du backlog SP-42 (`docs/revue/2026-09-04-analyse-gaps.md`), non
liés en apparence mais qui se referment par la même surface une fois
creusés :

- **GAP-03** : sur les 18 privilèges du catalogue
  (`core/app/roles/privileges.py:5-23`), 2 ne gardent **aucune** route ni
  domaine — `automation.secrets.manage` et `tasks.view_all`. Cochables dans
  un rôle sur mesure, sans le moindre effet observable. Les 16 autres ont
  déjà été refermés par les lots de correctifs SP-42 (10/18 ungated mesurés
  à l'ouverture de cette revue, CLAUDE.md n'en annonçait que 5).
- **GAP-71 / GAP-28** (paire cross-référencée, comptée une fois) :
  `audit_log` est en écriture seule depuis SP-1a — aucune route, aucun
  écran, aucun outil MCP ne permet de le **consulter**. Aucune vue
  d'usage/monitoring applicatif n'est exposée aux administrateurs (activité
  par utilisateur, popularité des ressources).

Vérifié dans le code réel avant d'écrire cette spec (piège CLAUDE.md n°3 —
ne jamais faire confiance au texte d'un gap sans revérifier) :

- `core/app/roles/kind_registry.py` **existe déjà** (mergé par SP-43,
  vérifié en session) : registre unique `privilege_for_kind(kind: str) ->
  str`, consulté par `app.configs.routes`, `app.mcp.tools`,
  `app.tileset3d.routes`, `app.terrain3d.routes`, `app.pipelines.routes`. Il
  ne mappe QUE des `kind` de config (`app`, `dashboard`, `site`, `map`,
  `dataset`, `pipeline`, `alert`, `report`, `bookmark`, `tileset3d`,
  `terrain3d`) — ni `automation.secrets.manage` ni `tasks.view_all` n'ont
  vocation à y entrer : ce ne sont pas des kinds de config, cette spec ne
  touche pas ce fichier. La recommandation de « faire GAP-03 après
  `kind_registry.py` » (issue de l'analyse de gaps) portait sur l'hygiène de
  session — nettoyer sur une base déjà consolidée par SP-43 plutôt que sur
  des implémentations divergentes en cours de refactor — pas sur une
  dépendance mécanique entre les deux fichiers.
- `core/app/secrets/routes.py` (3 routes : `POST/GET/DELETE /secrets`, coffre
  de connecteurs SP-15e) est gardé uniquement par `ADMIN_SECRETS_MANAGE` —
  `AUTOMATION_SECRETS_MANAGE` n'apparaît nulle part hors sa propre
  déclaration (`grep` vide confirmé, y compris côté shell
  `capabilities.ts`).
- Le domaine `tasks` du shell (`shell/src/auth/capabilities.ts`, entrée
  `requiresPrivilege: "tasks.view"`) pointe vers `/tasks`
  (`domainRoutes.ts`), qui rend **`TasksComingSoonPage`** — un `EmptyState`
  littéral, aucun contenu. `tasks.view` lui-même ne garde donc aujourd'hui
  qu'une visibilité de navigation vers une page vide ; `tasks.view_all`
  ne garde rien du tout.
- Aucune table ni endpoint ne liste les jobs procrastinate en cours/passés :
  `core/app/jobs/__init__.py` est l'`App` procrastinate partagée, mais rien
  ne lit `procrastinate_jobs` pour un usage applicatif. Construire un
  navigateur de queue procrastinate direct pose un problème réel non
  budgété par le gap (0.5-1j pour GAP-03 en tout) : cette table est possédée
  par la bibliothèque, sans colonne `tenant_id`, avec des arguments de tâche
  en JSON hétérogènes par domaine — l'isolation tenant y serait à
  reconstruire au cas par cas. **Décision de cette spec (§3.2)** : ne pas
  aller chercher cette table ; `audit_log` écrit déjà, à chaque déclenchement
  de job (`ingestion.job_create`, `pipeline.run`, `export.run`,
  `report.run`, `alert.evaluate`/`alert.notify`, `harvest_source.run`,
  `tileset3d.job_create`, `terrain3d.job_create`, `appexport.create`), une
  ligne `tenant_id`+`actor_id`+`created_at` — c'est un journal de tâches
  déjà tenant-scopé, juste jamais exposé en lecture. Utiliser cette source
  ferme GAP-03 (tasks.view_all) ET GAP-71/28 (vue d'usage) par la même
  construction, sans nouvelle infrastructure.

## 2. Décisions de conception (à valider, exécutées par défaut — mode auto)

1. **GAP-03a — `automation.secrets.manage`** : élargir la garde des 3 routes
   `/secrets` pour accepter `ADMIN_SECRETS_MANAGE` **OU**
   `AUTOMATION_SECRETS_MANAGE` (nouvelle primitive `require_any_privilege`,
   §3.1). Un porteur du privilège automation peut gérer les secrets de
   connecteur (utilisés par les pipelines qu'il construit) sans avoir besoin
   du privilège admin complet.
2. **GAP-03a (suite) — rôle Créateur** : ajouter
   `AUTOMATION_SECRETS_MANAGE` à `BUILT_IN_ROLE_PRIVILEGES["creator"]`
   (`core/app/roles/privileges.py`). Le Créateur porte déjà
   `AUTOMATION_MANAGE` (construit des pipelines) — sans ce privilège, il ne
   peut aujourd'hui pas créer les secrets que ses propres connecteurs
   (`reader.connector.rest/postgres`, SP-15f) consomment, sans passer par un
   administrateur. `ensure_built_in_roles()` resynchronise les rôles
   prédéfinis à chaque requête authentifiée (`core/app/roles/repository.py`
   docstring) : ce changement atteint tous les tenants existants sans
   migration. **Point à confirmer avec Tanguy** si cette extension de
   périmètre du Créateur n'est pas voulue — dans ce cas, ne garder que le
   point 1 (la primitive OR reste utile telle quelle : un rôle sur mesure
   peut alors porter `automation.secrets.manage` seul).
3. **GAP-03b + GAP-71/28 — vue d'usage unique** : nouveau domaine
   `core/app/usage/`, deux endpoints (§3.2/3.3) :
   - `GET /usage/tasks` — journal des actions de job (allowlist fixe
     d'actions `audit_log`), gardé par `tasks.view` (restreint à ses
     propres actions, `actor_id == soi`) **ou** `tasks.view_all` (toutes les
     actions du tenant, filtre `actorId` libre). Ferme GAP-03b : ces deux
     privilèges gardent enfin une route réelle, avec une sémantique fidèle
     à leur libellé i18n déjà en place (`roles.privilege.tasksView` = « Voir
     ses tâches », `roles.privilege.tasksViewAll` = « Voir les tâches de
     tout le tenant » — `shell/src/i18n/catalog.fr.ts:125-126`, non modifiés
     par cette spec).
   - `GET /usage/summary` — agrégats sur `audit_log` complet (pas
     seulement les actions de job) : activité par acteur (top N, fenêtre
     temporelle) et popularité des ressources (top N par `object_type`+
     `object_id`). Gardé par `tasks.view_all` seul (vue d'ensemble
     réservée à un rôle avec supervision tenant — Administrateur par
     défaut, tout rôle sur mesure qui coche ce privilège).
   - Remplace `TasksComingSoonPage` par une vraie page : section « Mes
     tâches récentes » toujours visible (tasks.view), section « Usage de la
     plateforme » visible seulement si le profil porte `tasks.view_all`.
4. **Pas de nouveau privilège.** Les deux endpoints se gardent
   intégralement avec `tasks.view`/`tasks.view_all`, déjà existants — évite
   d'ajouter un 19e privilège qui répéterait la classe de défaut visée par
   cette spec.
5. **Primitive `require_any_privilege`** (`core/app/roles/guards.py`) :
   utilisée par (1) et (3) — évite de dupliquer la même disjonction
   `has_privilege(...) or has_privilege(...)` sur 2 sites distincts, la
   classe exacte de défaut que SP-43 vient de refermer pour
   `privilege_for_kind`.

## 3. Périmètre

### 3.1 `require_any_privilege` (`core/app/roles/guards.py`)

```python
def require_any_privilege(session: Session, user: User, privileges: Sequence[str]) -> None:
    """Autorise si l'utilisateur porte AU MOINS UN des privilèges donnés.
    HTTPException 403 sinon, message citant tous les privilèges acceptés
    (pas un seul, pour qu'un rôle sur mesure sache quoi cocher)."""
```

Réutilisée immédiatement par `core/app/secrets/routes.py` (les 3 routes).
Pas d'usage ailleurs dans ce périmètre — mais primitive publique, pas un
détail privé de `app.secrets`, pour que le prochain site à avoir besoin
d'un OR de privilèges ne duplique pas la même boucle (c'est très
exactement la classe de défaut qui a justifié `privilege_for_kind`, cf.
`docs/superpowers/specs/2026-09-04-sp43-refactorisation-structurelle-design.md`
§1.1 — ne pas la rouvrir une 5e fois sur ce nouveau site).

### 3.2 `core/app/usage/` — nouveau domaine

Fichiers : `__init__.py` (vide), `service.py`, `schemas.py`, `routes.py`.
Aucun modèle SQLAlchemy propre — lit `app.audit.models.AuditLog` (déjà
`tenant_id`-scopée) et `app.users.models.User` (résolution du nom d'acteur,
jointure `LEFT OUTER` tolérante à un acteur système/agent ou supprimé).

**Contrat de couches** (`core/pyproject.toml`, `[[tool.importlinter.contracts]]`,
`layers`) : `app.usage` doit être ajouté **au-dessus** de `app.roles` (qui
est lui-même au-dessus d'`app.auth`/`app.audit`/`app.users`) pour importer
`app.roles.guards`/`app.roles.privileges`, `app.auth.dependency`, `app.db`,
`app.audit.models` et `app.users.models` sans qu'aucune exemption nommée ne
soit nécessaire — contrairement à `app.auth.routes` (même tension
documentée dans ce même fichier pour 3 arêtes exemptées explicitement).
Emplacement proposé : juste après `app.admin_tools` (un pair — module de
routes admin fines, sans dépendant montant, qui a besoin des mêmes couches
basses).

**Allowlist d'actions « tâche »** (`JOB_AUDIT_ACTIONS`, constante de
`service.py`), calée sur les valeurs `action=` réellement écrites
aujourd'hui (`grep` exhaustif effectué en session, cf. sites d'appel de
`write_audit` sous `core/app/*/jobs.py`, `*/routes.py`,
`*/importer.py`, `*/service.py`, `mcp/tools/pipelines.py`) :

```
ingestion.job_create, pipeline.run, export.create, export.run,
appexport.create, report.run, report.notify, alert.evaluate, alert.notify,
harvest_source.run, tileset3d.job_create, terrain3d.job_create
```

Exclus délibérément : `*.purge`/`*.upload_complete` (cycle de vie, pas un
déclenchement de job), `analytics.sql` (requête synchrone, pas un job en
arrière-plan), toute action CRUD de configuration (`config.*`,
`collection.*`, `role.*`, `secret.*`, `item.*`, …) — celles-ci nourrissent
`GET /usage/summary` (agrégat pleine largeur) mais pas `GET /usage/tasks`
(vue « tâches » au sens strict, cohérente avec le libellé i18n existant).

**Fonctions de `service.py`** (query-only, testables sans FastAPI) :

- `list_tasks(session, *, tenant_id, actor_id=None, page, page_size) ->
  tuple[list[AuditLog], int]` — filtre `tenant_id` + `action IN
  JOB_AUDIT_ACTIONS`, `actor_id` optionnel, tri `created_at DESC`,
  pagination page/page_size (même patron que
  `app.notifications.repository.list_notifications`).
- `summarize(session, *, tenant_id, since, until, limit) -> UsageSummary`
  (structure interne) — deux group-by sur `audit_log` complet (toutes
  actions) dans la fenêtre `[since, until]` :
  - par acteur : `actor_id`, jointure `User.username`, `COUNT(*)`, ordre
    décroissant, `LIMIT limit`.
  - par ressource : `object_type`, `object_id`, `COUNT(*)`, ordre
    décroissant, `LIMIT limit`.
  - `total_actions` (compte brut sur la fenêtre, toutes actions confondues,
    hors filtre par acteur).

### 3.3 Routes (`core/app/usage/routes.py`)

```
GET /usage/tasks?page=1&pageSize=50&actorId=<id>&since=<iso>&until=<iso>
```
- `require_any_privilege(session, user, [TASKS_VIEW, TASKS_VIEW_ALL])`.
- Si le profil ne porte PAS `tasks.view_all` : `actor_id` forcé à
  `user.id` côté serveur ; si `actorId` est fourni et diffère de `user.id`
  → 403 (jamais un simple silencieux repli — un utilisateur qui tente
  explicitement de voir les tâches d'un autre doit obtenir un refus net,
  pas une liste vide qui ressemblerait à un bug).
- Si le profil porte `tasks.view_all` : `actorId` optionnel, absent =
  toutes les actions du tenant.
- Réponse : `{ tasks: UsageTaskRead[], total: int, page: int, pageSize: int
  }`, `UsageTaskRead` = `{ id, actorId, actorUsername: str | null, action,
  objectType, objectId, createdAt }` (pas de `payload` brut exposé dans ce
  premier périmètre — cf. §5 Hors périmètre).

```
GET /usage/summary?since=<iso>&until=<iso>&limit=10
```
- `require_privilege(session, user, TASKS_VIEW_ALL)` — pas de repli
  « soi-même » ici : un agrégat pleine largeur (toutes actions, tous
  types d'objet) n'a pas de version « personnelle » qui ait un sens produit
  (agréger ses propres actions par acteur donnerait toujours une seule
  ligne).
- Défaut de fenêtre si `since` absent : `until - 30 jours` (`until` défaut
  = maintenant).
- Réponse : `{ byActor: [{ actorId, actorUsername, count }], byResource:
  [{ objectType, objectId, count }], totalActions, windowStart, windowEnd
  }`.

### 3.4 Shell

- `shell/src/api/types.ts` : types `UsageTask`, `UsageActorStat`,
  `UsageResourceStat`, `UsageSummary` + signatures `listUsageTasks`/
  `getUsageSummary` sur `ItemClient`.
- `shell/src/api/domains/usage.ts` (`createUsageMethods`) +
  `shell/src/api/domains/usage.hooks.ts` (`useUsageTasks`/
  `useUsageSummary`, React Query) — même patron exact que
  `domains/notifications.ts`/`.hooks.ts`. Composition dans
  `itemClient.ts` (import + spread, ordre alphabétique après
  `createTiles3dMethods`) et ré-export dans le barrel `hooks.ts`.
- Nouvelle page `shell/src/pages/UsagePage.tsx` (remplace
  `TasksComingSoonPage.tsx`, supprimé) : `TriptychLayout` (patron
  `UsersAdminPage`), section « Mes tâches récentes » (table paginée,
  libellé français par action via une table de correspondance i18n),
  section « Usage de la plateforme » rendue seulement si
  `useMe().data.privileges.includes("tasks.view_all")` — deux listes
  classées (par acteur, par ressource), pas de bibliothèque de graphique
  (hors périmètre, cf. §5).
- `shell/src/shell/routes.tsx` : `<Route path="/tasks" element={
  <RequirePrivilege privilege="tasks.view" deniedMessage="…"><UsagePage
  /></RequirePrivilege> } />`.
- i18n (`catalog.fr.ts`) : retrait de `comingSoon.tasks` (page réelle
  maintenant), ajout des clés de la nouvelle page + libellés français des
  ~12 actions de `JOB_AUDIT_ACTIONS` (ex. `pipeline.run` → « Exécution de
  pipeline »).
- Fixtures à resynchroniser avec la décision §2.2 (Créateur gagne
  `automation.secrets.manage`) : `shell/src/auth/capabilities.test.ts`
  (fixture Créateur), `shell/e2e/mocks.ts` (`CREATOR_ME`).

### 3.5 Régénération OpenAPI + types TS

Obligatoire (piège CLAUDE.md n°1) : `/secrets` change de garde interne sans
changer de forme de requête/réponse → diff **attendu vide** sur cette
partie (documenté explicitement, pas un oubli — cf. CLAUDE.md « diff vide
attendu et légitime »). `/usage/tasks` et `/usage/summary` sont des routes
neuves → diff non vide attendu là.

## 4. Tests

- **Core** :
  - `require_any_privilege` : accorde si au moins un privilège présent,
    refuse (403) si aucun, message d'erreur citant les privilèges acceptés.
  - `/secrets` (mise à jour `test_secrets_routes.py`) : un utilisateur avec
    seulement `automation.secrets.manage` (rôle sur mesure) peut
    créer/lister/supprimer un secret ; un utilisateur avec ni l'un ni
    l'autre privilège reste 403 ; le comportement `admin.secrets.manage`
    seul est inchangé (non-régression).
  - Rôle Créateur : `BUILT_IN_ROLE_PRIVILEGES["creator"]` contient
    `automation.secrets.manage` (test caractéristique, échoue si retiré par
    inadvertance) ; `ensure_built_in_roles()` resynchronise un tenant
    existant vers le nouveau jeu (déjà couvert par
    `test_roles_repository.py`, pas de nouveau test nécessaire — vérifier
    qu'il passe toujours).
  - `service.list_tasks`/`service.summarize` : fixtures d'audit_log
    insérées directement (plusieurs tenants, plusieurs acteurs, mélange
    d'actions job/non-job) — vérifient l'étanchéité tenant, le filtre
    d'action, l'ordre, la pagination, l'agrégation top-N, la fenêtre
    temporelle, la jointure `username` tolérante à un `actor_id` orphelin
    (agent/système, `actor_kind != "user"`).
  - Routes `/usage/tasks`/`/usage/summary` : la matrice des 3 profils
    (aucun privilège tasks → 403 ; `tasks.view` seul → restreint à soi,
    403 sur `actorId` explicite différent, 403 sur `/usage/summary` ;
    `tasks.view_all` → accès complet aux deux endpoints, `actorId` libre).
  - Contrat de couches : `uv run lint-imports` passe avec `app.usage`
    ajouté, sans exemption nommée.
- **Shell** : `itemClient.test.ts` (2 tests contrat, patron déjà en place
  dans ce fichier — URL, query params, mapping de réponse) ;
  `UsagePage.test.tsx` (section admin visible/masquée selon privilège,
  état vide, pagination, libellé d'action affiché) ;
  `capabilities.test.ts` mis à jour (fixture Créateur).
- **E2E** : `shell/e2e/tasks.spec.ts` — persona Créateur voit sa propre
  liste, pas la section usage ; persona Administrateur voit les deux.

## 5. Hors périmètre (explicite, pour ne pas sur-scoper)

- Navigateur de queue procrastinate (table `procrastinate_jobs`) — cf. §1,
  écarté par construction, pas juste reporté.
- Politique de rétention/export d'`audit_log`, purge RGPD (GAP-74, GAP-75)
  — gaps distincts, non traités ici.
- Filtre par `action`/`objectType` sur `GET /usage/tasks` (v1 : filtre
  `actorId`+fenêtre temporelle seulement) — extension facile si demandée.
- Exposition du champ `payload` brut d'`audit_log` sur `/usage/tasks` —
  gardé côté serveur dans ce premier périmètre (évite d'exposer par
  inadvertance un futur payload plus riche qu'aujourd'hui sans revue
  dédiée).
- Outil MCP de consultation d'usage — l'architecture MCP (`app.mcp`) est
  au-dessus de tout le reste du contrat de couches, rien n'empêche de
  l'ajouter plus tard sur `app.usage.service`, mais ce n'est demandé par
  aucun des deux gaps.
- Résolution de titre pour `byResource` (l'objet référencé par
  `object_type`+`object_id` n'est pas systématiquement un `Item` — pas de
  jointure générique praticable sans logique par type) : le premier
  périmètre affiche l'identifiant brut.
- Graphique/visualisation (`dataviz`) : deux listes classées suffisent pour
  ce premier périmètre, pas de bibliothèque de chart.
- Page dédiée de gestion des secrets pipeline côté shell — n'existe pas
  aujourd'hui (vérifié : aucun composant ne consomme `/secrets`, seul le
  commentaire de `domainRoutes.ts:36` l'anticipe) ; cette spec ferme
  uniquement la garde backend, pas cette UI absente (gap distinct, non
  demandé ici).

## 6. Critères de sortie

- `automation.secrets.manage` et `tasks.view_all` gardent chacun au moins
  une route réelle, vérifiable par un test qui échoue si la garde est
  retirée.
- `GET /usage/tasks` et `GET /usage/summary` existent, tenant-scopés,
  testés sur les 3 profils de privilège.
- `/tasks` rend une page réelle (plus de `TasksComingSoonPage`).
- OpenAPI + types TS régénérés, diff cohérent avec les routes changées.
- Suite complète verte (`core` : `uv run pytest` ; `shell` : `npm run
  test`, `npm run e2e` ciblé sur le nouveau spec au minimum) ; `uv run
  lint-imports` vert avec `app.usage` dans le contrat.

## 7. Risques et limites connues

- Le choix de fonder `tasks.view`/`tasks.view_all` sur `audit_log` plutôt
  que sur un état de job en direct (procrastinate) signifie que
  `/usage/tasks` montre des **actions déclenchées**, pas leur statut final
  temps réel (`succeeded`/`failed` n'est pas dans `audit_log` pour toutes
  les familles — `alert.evaluate` puis `alert.notify` sont deux lignes
  distinctes, par exemple). Ce n'est pas un tableau de bord de supervision
  de jobs en cours (ça, c'est Grafana/OTel, hors périmètre CLAUDE.md
  §"Post-v0.1"), c'est un journal d'activité — à documenter clairement dans
  la page pour ne pas laisser croire à un statut live.
- Étendre le rôle Créateur (décision §2.2) est un changement de
  comportement produit pour tout tenant existant dès la prochaine requête
  authentifiée (resynchronisation automatique) — pas une migration
  silencieuse en base, mais un effet immédiat à l'exécution qu'il faut
  assumer consciemment (cf. point à confirmer avec Tanguy).
- `GET /usage/summary` sur un tenant à fort volume d'`audit_log` (pas
  d'index dédié sur `(tenant_id, created_at)` au-delà de la PK actuelle,
  vérifier le modèle `core/app/audit/models.py` — aucun index composite
  déclaré) peut coûter cher en `COUNT`/`GROUP BY` à mesure que la table
  grossit ; pas un problème à l'échelle actuelle du produit (pré-v0.1,
  aucun tenant réel identifié — Q2 du comparatif §8, toujours ouverte), mais
  à surveiller si retenu dans une revue de performance ultérieure.
