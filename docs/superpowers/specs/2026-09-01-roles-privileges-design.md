# Rôles à base de privilèges — remplacement de `is_admin`/`is_analyst`

Date : 2026-09-01
Statut : brainstorming validé, en attente de plan d'implémentation.

## 0. Pourquoi

Aujourd'hui, `core/app/users/models.py:25-26` ne porte que deux booléens plats
(`is_admin`, `is_analyst`). Tout le reste (« Créateur », « Lecteur ») est un
profil implicite non stocké. La spec triptyque
(`docs/superpowers/specs/2026-08-29-refonte-ui-triptyque-design.md` §6.7) a
déjà esquissé une matrice à 4 profils × 9 domaines, jamais implémentée — et
CLAUDE.md note explicitement que « le profil Lecteur n'est pas dérivable du
modèle actuel ». Ce document remplace les deux booléens par une notion de
**rôle = ensemble de privilèges nommés**, avec 4 rôles prédéfinis (repris de
cette matrice) et la possibilité de créer des rôles sur mesure par tenant.

## 1. Périmètre

**Dans le périmètre** : les privilèges liés à la **personne** (accès aux
domaines/fonctionnalités — SQL Lab, administration, gestion des secrets de
pipeline, etc.), aujourd'hui portés par `isAdmin`/`isAnalyst` et consommés par
`shell/src/auth/capabilities.ts`, `RequireRole.tsx`, `_require_admin`
(`core/app/auth/routes.py:99-101`).

**Hors périmètre, explicitement inchangé** :
- `can(session, user_id, action, item, kind, actor_is_admin)` /
  `decide(...)` (`core/app/sharing/authorization.py`) — permissions par objet
  (read/write/delete/share sur un item ou une collection précis, via
  propriété + rôles de partage `viewer`/`editor`). C'est un système différent
  : autorisation contextuelle à un objet, pas une capacité globale de rôle.
  L'arbitrage « tables maison + porte unique `can()` » est un choix déjà
  tranché par la feuille de route, non remis en cause ici.
- RLS PostGIS par collection, `CollectionPermissions`.
- Groupes de partage (`Group`/`GroupMember`/`ItemShare`/`CollectionShare`).
- « Capacités d'instance » (`MeCapabilities`/`InstanceCapabilities` — 7
  drapeaux de déploiement : `readOnly`, `etlEnabled`, `exportEnabled`,
  `appExportEnabled`, `tileset3dEnabled`, `terrain3dEnabled`,
  `copilotEnabled`). Vocabulaire volontairement distinct de la nouvelle
  notion : une **capacité d'instance** est une propriété du déploiement,
  identique pour tout le monde ; un **privilège** est une propriété de la
  personne, via son rôle. Les deux continuent de se combiner exactement
  comme avant (« un privilège manquant masque, une capacité d'instance
  coupée verrouille » — reformulation de la doctrine §6.2 de la spec
  triptyque, qui parlait de « rôle manquant » et garde le même sens).
- A14 (propriété des tâches planifiées par le créateur du cron) — déjà noté
  pour SP-31, indépendant de ce chantier.

## 2. Modèle de données (cœur)

Nouvelle table `roles`, respectant l'arbitrage non négociable « `tenant_id`
sur toute table » : plutôt qu'un rôle built-in global avec `tenant_id` nul
(qui serait une exception à ce non-négociable), **chaque tenant reçoit sa
propre copie des 4 rôles prédéfinis**, marquée `is_built_in=true`. Le cœur
refuse toute écriture (renommage, édition des privilèges, suppression) sur
une ligne `is_built_in=true`, quel que soit le tenant — c'est cette garde
applicative, et non le partage d'une ligne unique, qui garantit que
Administrateur/Créateur/Analyste/Lecteur restent identiques partout.

```
roles
  id            uuid pk
  tenant_id     uuid fk NOT NULL       -- jamais nul, même pour un built-in
  name          text                   -- nom affiché, éditable pour le sur-mesure
  slug          text                   -- "admin" | "creator" | "analyst" | "reader" | libre
  is_built_in   bool
  privileges    text[]                 -- identifiants du catalogue (§3), validés à l'écriture
  created_at / updated_at
  -- audit_log sur toute écriture, comme toute table (arbitrage déjà tranché)
```

`User` (`core/app/users/models.py`) perd `is_admin`/`is_analyst`, gagne
`role_id` (FK `roles.id`, NOT NULL). **Un seul rôle par utilisateur** (pas de
cumul) — plus simple à auditer et à afficher ; un besoin de mélange inhabituel
se résout en créant un rôle sur mesure qui combine les privilèges voulus,
plutôt qu'en cumulant des rôles.

### Migration Alembic

1. Créer les 4 rôles built-in pour chaque tenant existant, avec les
   privilèges figés du §3.3.
2. Pour chaque utilisateur : `is_admin` → rôle Administrateur du tenant ;
   sinon `is_analyst` → rôle Analyste ; sinon → **rôle Créateur** (préserve
   exactement le comportement actuel — un utilisateur ni admin ni analyste a
   aujourd'hui les droits d'un éditeur normal ; basculer vers Lecteur serait
   une régression de droits silencieuse au déploiement).
3. Supprimer les colonnes `is_admin`/`is_analyst`.

Testée sur base non vide, dans les deux sens (piège n°8 de CLAUDE.md). Le
`downgrade()` restaure `is_admin`/`is_analyst` depuis `role.slug` — limite
acceptée : un rôle sur mesure créé entre l'`upgrade` et le `downgrade` n'a pas
d'équivalent booléen et sera approximé (`is_admin=False, is_analyst=False`),
documentée comme limite du rollback, pas à résoudre.

## 3. Catalogue de privilèges

Un `Enum` Python (module à nommer à l'implémentation, ex.
`core/app/roles/privileges.py`), chaque membre portant un domaine en
métadonnée — source de vérité unique, pas de duplication. Le libellé affiché
**n'est pas** une chaîne française portée par le cœur : chaque privilège
porte une **clé i18n** (`labelKey`), résolue côté shell par `t()`
(`shell/src/i18n/index.ts`, source unique `catalog.fr.ts`, français seul —
A12). Un ajout de privilège = une entrée d'enum + une entrée dans
`catalog.fr.ts`, jamais une liste dupliquée en dur côté TypeScript (piège
n°5).

### 3.1 Exposition

Un endpoint dédié (`GET /roles/catalog`, ou intégré à `GET /instance` — à
trancher à l'implémentation) répond :

```json
[{"privilege": "automation.secrets.manage", "domain": "automation", "labelKey": "roles.privilege.automation.secrets_manage"}, ...]
```

Les types TS sont générés depuis l'OpenAPI (`npm run gen:api-types` —
décision déjà tranchée pour tout le cœur) : aucune liste de privilèges
dupliquée à la main côté shell.

### 3.2 Structure indicative (à finaliser en écrivant le plan)

Dérivée de la matrice §6.7 de la spec triptyque :

- Par domaine, une paire `<domaine>.view` / `<domaine>.manage` pour
  Catalogue, Cartes, Données, Apps & sites, Automatisation.
- Analytique : `analytics.view` (widgets/dashboards) et
  `analytics.sql_lab.access` (privilège séparé — distingue Analyste de
  Créateur dans la matrice).
- `automation.secrets.manage` (voir/gérer les *noms* de secrets — jamais les
  valeurs, contrat déjà fixé par SP-15e) distinct de `automation.manage`.
- Administration, 6 privilèges indépendants, pour que les rôles sur mesure
  soient réellement utiles (sans ça, la personnalisation resterait limitée
  aux domaines non-admin) : `admin.users.manage`, `admin.roles.manage`,
  `admin.harvest.manage`, `admin.collections.manage`,
  `admin.extensions.manage`, `admin.secrets.manage` (noms de secrets, A15).
  `admin.roles.manage` est **délibérément séparé** de `admin.users.manage` :
  sans cette séparation, un rôle sur mesure habilité à « gérer les
  utilisateurs » pourrait se fabriquer un rôle à privilèges complets puis se
  l'auto-attribuer — escalade de privilège indirecte.
- `tasks.view_all` (voir toutes les tâches du tenant, pas seulement les
  siennes — la portée « ses tâches » reste gérée par la propriété d'objet,
  hors périmètre), `settings.instance.manage`.

### 3.3 Rôles prédéfinis (built-in)

Repris de la matrice §6.7, chaque case traduite en privilèges cochés :

| Rôle | Privilèges |
|---|---|
| Administrateur | **Tous** — rôle ordinaire à capacités complètes, aucun court-circuit `if is_admin` dans le code (contrairement à `decide()` aujourd'hui pour les collections, qui lui reste inchangé). |
| Créateur | tous les `.manage`/`.view` sauf `analytics.sql_lab.access`, `automation.secrets.manage`, `tasks.view_all`, `admin.*`, `settings.instance.manage` |
| Analyste | tous les `.view` + `analytics.sql_lab.access` |
| Lecteur | `catalog.view`, `maps.view`, `data.view` (préférences seulement pour Paramètres) |

## 4. API & garde-fous

- `GET /me` gagne `role: {id, name, slug}` et `privileges: string[]`
  (résolus depuis le rôle) — remplace `isAdmin`/`isAnalyst`. `GET /instance`
  garde ses 7 capacités d'instance inchangées.
- `GET /roles` (liste, filtrée tenant), `POST /roles` (créer un sur-mesure),
  `PATCH /roles/{id}` (renommer/changer les privilèges — refusé si
  `is_built_in`), `DELETE /roles/{id}` (refusé si des utilisateurs le
  portent, ou si `is_built_in`). Toutes gardées par `admin.roles.manage`.
- `PATCH /users/{id}` (changer le `role_id` d'un utilisateur) gardé par
  `admin.users.manage`.
- **Anti-lockout**, appliqué dans la couche service (pas seulement
  l'endpoint, pour couvrir un futur outil MCP) : avant toute
  réassignation/suppression, compter les utilisateurs du tenant qui
  auraient encore `admin.users.manage` **et** `admin.roles.manage` après
  l'opération ; refuser (409, message explicite) si ce compte tombe à zéro.
  Le rôle Administrateur (built-in) ne peut jamais être supprimé ni modifié
  (cf. §2) — c'est la même garde qui l'interdit.
- Suppression d'un rôle sur mesure encore attribué à des utilisateurs :
  **refusée** (« N utilisateurs ont ce rôle »), pas de réassignation
  silencieuse vers Lecteur — pas de dégradation de droits sans action
  explicite d'un admin.
- `_require_admin` (`core/app/auth/routes.py:99-101`) disparaît, remplacé par
  des vérifications de privilège ciblées (`require_privilege(user,
  "admin.harvest.manage")`, etc.) sur chacune des routes admin existantes.
- `can()`/`decide()` (permissions par objet) restent **inchangées**.

## 5. Shell

- `capabilities.ts` : `Profile` devient `{privileges: Set<string>,
  instanceCapabilities}` (au lieu de `{isAdmin, isAnalyst, capabilities}`).
  `requiresRole` devient `requiresPrivilege: string | string[]` — un domaine
  peut rester visible avec un privilège large (`analytics.view`) tandis
  qu'une commande précise de sa palette (« SQL Lab ») exige un privilège
  plus fin (`analytics.sql_lab.access`). La doctrine « absent / verrouillé et
  expliqué / lecture seule » (§6.2 de la spec triptyque) ne change pas de
  sens, juste de nom (« privilège manquant masque »).
- `RequireRole.tsx` → `RequirePrivilege.tsx`, remplace ses deux consommateurs
  actuels (lui-même, `shell/routes.tsx`) et les 3 pages admin déjà migrées
  vers `RequireRole` par SP-30j (`SqlLabPage`, `AdminExtensionsPage`,
  `HarvestSourcesAdminPage`, `CollectionsAdminPage`), qui passent le
  privilège correspondant au lieu de `role="admin"`.
- Nouvel écran `RolesAdminPage` (domaine Administration, `TriptychLayout`,
  même patron que `CollectionsAdminPage`/`HarvestSourcesAdminPage`) : liste
  des rôles du tenant, création/édition d'un rôle sur mesure avec cases à
  cocher groupées par domaine (rendues depuis le catalogue via les types
  générés), gardée par `admin.roles.manage`. L'écran de changement de rôle
  d'un utilisateur (gardé par `admin.users.manage`) est à situer précisément
  au moment du plan.
- Les 4 comparaisons de droits en dur restantes (`KitGalleryPage.tsx:203`,
  `AppLayout.tsx:29-30`, `AccountMenu.tsx:12-13`, mapping DTO
  `itemClient.ts:540-551`) migrent vers `role.slug`/`privileges` ;
  `AccountMenu` affiche le nom du rôle au lieu d'un badge admin/analyste en
  dur.

## 6. Tests

- **Test de parité migration** : pour chaque combinaison possible de
  `(is_admin, is_analyst)` avant migration, le rôle assigné après migration
  donne des privilèges au moins aussi larges que l'ancien comportement
  (`_require_admin`, `capabilities.ts` avant/après) — non-régression
  prouvée, pas supposée. Même esprit que le test cartésien existant pour
  `decide()` (`tests/test_sharing_decide.py`).
- Migration Alembic testée sur base non vide, dans les deux sens.
- Test anti-lockout : scénario « dernier `admin.roles.manage` du tenant »
  refusé, avec message explicite.
- Test de suppression de rôle bloquée si en usage.
- Régénération OpenAPI/TS obligatoire dès que `GET /me`/`/roles*` changent
  (piège n°1 — classe d'oubli la plus fréquente du dépôt).

## 7. Risques et découpage

Ce chantier touche `_require_admin` sur toutes les routes admin existantes
(harvest, collections, extensions, secrets, users) — surface large, à
découper en tâches par sous-domaine admin plutôt qu'une tâche monolithique,
avec revue par tâche **et** revue finale de branche (piège n°4).

## 8. Décisions actées (résumé)

1. Modèle de capacité : liste plate de privilèges nommés.
2. Périmètre : privilèges de rôle/fonctionnalité uniquement, `can()`/`decide()`
   inchangés.
3. Admin = rôle ordinaire à capacités complètes, pas de bypass codé en dur.
4. Un seul rôle par utilisateur.
5. Rôles prédéfinis = les 4 profils de la matrice §6.7.
6. Rôles built-in identiques par construction (garde applicative) dans
   chaque tenant + rôles sur mesure par tenant.
7. Vocabulaire : « capacité d'instance » (inchangé, déploiement) vs
   « privilège » (nouveau, personne).
8. Migration par défaut des utilisateurs ni admin ni analyste → Créateur.
9. Administration découpée en 6 privilèges fins, dont `admin.roles.manage`
   séparé de `admin.users.manage` pour éviter l'escalade indirecte.
10. Catalogue = Enum Python + endpoint, labels via clé i18n résolue côté
    shell (`catalog.fr.ts`), pas de liste dupliquée.
11. Anti-lockout explicite sur le rôle Administrateur et sur le dernier
    porteur de `admin.users.manage`/`admin.roles.manage`.
12. Suppression d'un rôle en usage : bloquée, jamais de réassignation
    silencieuse.
