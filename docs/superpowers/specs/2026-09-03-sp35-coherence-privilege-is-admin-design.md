# SP-35 — Cohérence privilège/`is_admin` sur 4 sites

Date : 2026-09-03
Statut : validé (brainstorming), prêt pour plan d'exécution

## Motivation

SP-31 (rôles à base de privilèges) a remplacé `User.is_admin`/`is_analyst`
par un modèle de rôles nommés à privilèges cochés, et a migré la quasi-
totalité des gardes d'autorisation vers `require_privilege(session, user,
Privilege.X.value)`. Sa revue finale de branche a documenté, en suivi non
bloquant, **3 sites** où une vérification directe de `user.is_admin`
subsistait à la place d'un privilège nommé — un rôle sur mesure qui
détiendrait ce privilège sans être le rôle prédéfini `admin` est traité
comme non-privilégié, alors qu'un `admin` sans ce privilège précis (cas
aujourd'hui impossible, le rôle `admin` prédéfini porte tous les privilèges
et les rôles prédéfinis sont immuables) serait laissé passer à tort.

Cette session a demandé un audit plus large avant de clore le sujet.
L'audit (grep de tous les usages de `user.is_admin`/`actor_is_admin` sous
`core/app`) confirme :

- Les 3 sites déjà documentés par SP-31 sont réels et toujours ouverts.
- **Un 4e site réel**, non documenté par SP-31 car livré par la session
  Traefik concurrente (SP-32, `docs/superpowers/specs/
  2026-09-01-traefik-admin-tools-design.md`) qui n'avait pas encore le
  module de rôles sous les yeux : `app/admin_tools/routes.py::_require_admin`
  garde `POST /admin-tools/launch/{tool}` sur `user.is_admin` directement.
  Le shell, lui, gate déjà `/admin/infrastructure` côté route sur le
  privilège `settings.instance.manage` (`shell/src/shell/routes.tsx`) — un
  rôle sur mesure porteur de ce privilège verrait donc le bouton dans l'UI
  et recevrait un 403 réel au clic. C'est la même classe de défaut que les
  3 autres, mais avec une conséquence utilisateur visible immédiate plutôt
  que purement une divergence de modèle de données.
- **Aucun autre site** : tous les autres usages de `user.is_admin`/
  `actor_is_admin` sous `core/app` alimentent `decide()`/`can()` comme
  paramètre `actor_is_admin` — c'est le bypass admin volontaire et
  documenté de ce mécanisme (SP-31 : « `is_admin` **survit** comme colonne
  synchronisée exclusivement par la logique de rôle », précisément pour ne
  pas avoir à réécrire `decide()`). Ce n'est pas un défaut, ne fait pas
  partie du périmètre de ce plan.

## Périmètre — 4 sites, tous sous `core/app`

1. `app/collections/repository.py::list_visible_collections` — le paramètre
   `is_admin: bool` (contrôle : voit toutes les collections du tenant, pas
   seulement publiques/partagées) est aujourd'hui `user.is_admin` passé par
   l'appelant (`app/collections/routes.py::list_collections`). Devient
   calculé via le privilège `admin.collections.manage`. Le paramètre est
   renommé `can_see_all: bool` — `is_admin` était déjà un abus de langage
   avant même ce plan (un admin sans le rôle prédéfini n'existe pas
   aujourd'hui, mais le nom décrivait la colonne, pas l'intention).
2. `app/collections/repository.py::_collection_permissions` (et son appelant
   pagé `collection_permissions_by_id`) — le calcul de `delete`
   (`return actor_is_admin`) devient le même privilège
   `admin.collections.manage`. Le docstring de `CollectionPermissions`
   (`app/collections/schemas.py`) qui documente explicitement cet écart
   est mis à jour pour refléter la correction, pas seulement le constat.
3. `app/extensions/routes.py::list_extensions` — `include_disabled =
   bool(user and user.is_admin and all)` devient le privilège
   `admin.extensions.manage`, cohérent avec les routes de mutation de ce
   même module qui l'utilisent déjà (`register_extension` et voisines,
   migrées par SP-31).
4. `app/admin_tools/routes.py::launch_admin_tool` — `_require_admin(user)`
   supprimé, remplacé par `require_privilege(session, user,
   Privilege.SETTINGS_INSTANCE_MANAGE.value)` (lève 403, même sémantique
   que l'ancien helper local). La route gagne une dépendance `session:
   Session = Depends(get_session)`, patron déjà en place sur les 5 modules
   migrés par SP-31 (`harvest`, `secrets`, `extensions`, `collections`,
   `analytics`/SQL Lab).

## Nouveau helper : `has_privilege`

`app/roles/guards.py` gagne `has_privilege(session: Session, user: User,
privilege: str) -> bool`, symétrique à `require_privilege` (même lookup de
rôle via `get_role`) mais qui **retourne** un booléen au lieu de lever une
`HTTPException`. `require_privilege` reste inchangé et continue de servir
les gardes qui doivent bloquer une route (site 4 ci-dessus, et tout site
déjà migré par SP-31). `has_privilege` sert les 3 sites qui calculent une
visibilité/portée plutôt que de refuser une requête (sites 1–3) — jamais
d'exception utilisée comme contrôle de flux pour dériver un booléen.

Pas de duplication de logique entre les deux : la façon la plus simple d'
implémenter `has_privilege` sans dupliquer le lookup est de le factoriser
(`require_privilege` devient un appel à `has_privilege` qui lève si faux),
au choix de l'implémenteur — les deux fonctions doivent rester
comportementalement identiques sur la question « ce rôle porte-t-il ce
privilège ».

## Hors périmètre, explicitement

- Tout usage de `user.is_admin`/`actor_is_admin` qui alimente `decide()`/
  `can()` (mécanisme volontaire, cf. Motivation) — `pipelines/runtime.py`,
  `pipelines/config_validation.py`, `collections/dataset_validation.py`,
  `mcp/tools.py`, `mcp/form_app.py`, `features/routes.py`, `dcat/routes.py`,
  `stac/routes.py`, `sharing/authorization.py`, `items/repository.py`.
- `User.is_admin` comme colonne — reste synchronisé exclusivement par
  `app/users/repository.py` (logique de rôle), comme tranché par SP-31.
  Aucun changement à ce mécanisme.
- Le profil « Lecteur » et la barre de domaines shell (`capabilities.ts`)
  — déjà résolus par SP-31, confirmé par lecture directe du code avant
  d'écrire cette spec : `DOMAINS` et `RequirePrivilege` sont déjà
  entièrement privilège-driven, aucune trace de `isAdmin` résiduelle.
- Toute nouvelle fonctionnalité produit, tout nouveau privilège.
- Les 8 autres suivis non bloquants hérités de SP-31 (visibilité `is_admin`
  vs `require_privilege` était l'un des neuf ; les huit autres — casts
  `labelKey` non gardés, 5 privilèges qui n'imposent rien, `GET /users` en
  N+1, etc. — restent des suivis séparés, non traités ici).

## Vérification & garde-fous

**Comportement attendu à changer uniquement pour un rôle sur mesure**
portant l'un des 4 privilèges concernés sans être le rôle prédéfini
`admin` — avant cette branche il était traité comme non-privilégié sur ces
4 sites, après il est traité correctement. Pour tout utilisateur avec le
rôle prédéfini `admin` (qui porte tous les privilèges), aucun changement de
comportement observable.

Tests à ajouter/adapter (TDD, cf. `superpowers:test-driven-development`) :

- `app/roles/guards.py::has_privilege` : test direct (rôle avec/sans le
  privilège, rôle introuvable).
- Site 1 (`list_visible_collections`) : un rôle sur mesure avec
  `admin.collections.manage` voit une collection privée non partagée ; un
  rôle sans ce privilège ne la voit pas (cas déjà couvert pour `admin`/non-
  admin, à étendre à un rôle sur mesure).
- Site 2 (`_collection_permissions`/`collection_permissions_by_id`) : même
  rôle sur mesure obtient `delete: true` sur une collection dont il n'est
  pas propriétaire.
- Site 3 (`list_extensions`) : un rôle sur mesure avec
  `admin.extensions.manage` et `?all=true` voit les extensions désactivées.
- Site 4 (`admin_tools`) : test HTTP direct sur `POST
  /admin-tools/launch/{tool}` — 403 sans le privilège `settings.instance.
  manage` (y compris pour un rôle sur mesure qui ne le porte pas), 200 avec
  un rôle sur mesure qui le porte sans être `admin`. Nécessite que
  `CORE_ADMIN_TOOLS_ENABLED` soit actif dans le test, comme les tests
  existants de ce module.

Vérifications de clôture (à détailler dans le plan d'exécution) :

- `mypy --strict` sur `app/roles` (déjà dans le périmètre CI depuis SP-31)
  et sur les modules touchés s'ils y sont déjà (`app/admin_tools` n'y est
  pas aujourd'hui — ne pas l'y ajouter dans ce plan, hors périmètre).
- Suite pytest complète (pas seulement les modules touchés) — les 3 sites
  déjà existants ont des tests actuels sur le cas `admin`/non-admin simple ;
  vérifier qu'aucun ne suppose implicitement que seul `is_admin` peut
  produire `True`.
- Régénération OpenAPI/TS **non nécessaire a priori** (aucune route ni
  schéma de réponse ne change de forme — seul le calcul interne d'un champ
  booléen déjà existant change) ; à vérifier par un diff vide de
  `openapi.json` avant de clore (piège n°1 de `CLAUDE.md`).
- `docker compose config` — site 4 ne change aucune variable d'environnement
  ni service, juste de la logique applicative ; pas de vérification de
  câblage nécessaire.

## Risques identifiés

- Le renommage `is_admin` → `can_see_all` sur `list_visible_collections`
  touche ~11 sites d'appel dans les tests (`test_collections_repository.py`,
  `test_ingestion_importer.py`, `test_collections_routes.py`) — mécanique
  (renommage de kwarg), pas de changement de valeur attendue sur les cas
  déjà couverts par `admin`/non-admin.
- Le changement de signature de `_collection_permissions`/
  `collection_permissions_by_id` (ajout d'un besoin de résoudre le
  privilège par rôle plutôt que de recevoir un bool déjà calculé) doit
  rester à **une requête de rôle par page**, doctrine SP-29a déjà en place
  pour `roles_for_collections` — ne pas réintroduire un lookup par
  collection dans la boucle.
- `app/admin_tools/routes.py` n'a aujourd'hui aucune dépendance `Session` —
  vérifier que l'ajouter ne casse pas un test qui construisait la requête
  sans session de base (peu probable, le module a déjà une base de test
  avec DB pour ses autres routes, mais à vérifier plutôt que supposer).
