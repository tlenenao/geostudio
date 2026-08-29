# Fondation de la refonte UI : permissions, tokens, i18n — SP-29a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser la fondation de la refonte UI sans toucher à un seul écran — un contrat de permissions calculé par le cœur et lu par une porte unique côté shell, une couche de tokens en deux ambiances, une couche d'internationalisation — et mesurer la bibliothèque de primitives qui portera SP-29b.

**Architecture:** Trois blocs indépendants. **(1) Cœur** : la décision d'autorisation est extraite de `can()` dans une fonction pure `decide()`, les rôles de groupe sont lus en lot par `roles_for_items()`, et `ItemRead` transporte désormais `permissions: {read, write, delete, share}` — calculé côté serveur, jamais côté client. **(2) Shell** : un composant `Gate` et un module `capabilities` deviennent le seul endroit du code qui compare des droits ; `ItemActions` est câblé dessus, ce qui supprime les boutons qui produisent aujourd'hui un 403. **(3) Design** : `tokens.css` définit la palette, la typographie et les rayons dans les deux ambiances, exposés à Tailwind v4, sans qu'aucun écran ne les consomme encore.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2 (cœur, `uv`) · React 19 + TypeScript + Tailwind v4 + Vitest + MSW + Playwright (shell, `npm`).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-08-29-refonte-ui-triptyque-design.md` (§10 pour ce plan). Maquettes : `docs/design/triptyque-geostudio.html`.
- **Aucun écran ne change**, à une exception près et une seule : `shell/src/shell/ItemActions.tsx` (Task 8, exception §10.1.7 de la spec).
- Le rendu conditionnel côté shell n'est **jamais** une frontière de sécurité. Le cœur reste seul juge. Aucune route du cœur ne perd un contrôle d'autorisation dans ce plan.
- Docs, commentaires et messages utilisateur en **français** ; code et identifiants en **anglais**.
- Commits **conventional**, petits, un sujet : `feat(core): …`, `feat(shell): …`, `test(core): …`, `chore(shell): …`.
- Branche de travail : `dev`.
- **Régénérer la spec OpenAPI et les types TS** dès qu'une route ou un modèle change — classe d'oubli n°1 de ce dépôt. L'incantation exacte (la commande nue échoue en `ModuleNotFoundError: app`) :
  ```bash
  cd core && PYTHONPATH=. \
    CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
    uv run python scripts/export_openapi.py openapi.json
  cd ../shell && npm run gen:api-types
  ```
- Seuils de couverture non régressifs : **85** côté cœur, **88** côté shell. La couverture shell se mesure **après avoir nettoyé `dist/` et `dist-export/`** (la config vitest compte ces artefacts gitignorés comme source non couverte — piège documenté quatre fois) :
  ```bash
  cd shell && rm -rf dist dist-export && npm run test -- --coverage \
    && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
  ```
- Portes de qualité, mêmes invocations qu'en CI :
  ```bash
  cd core && uv run ruff check . && uv run ruff format --check . \
    && uv run mypy --strict app/auth app/secrets app/analytics app/copilot \
    && uv run lint-imports
  cd shell && npm run lint && npm run format:check && npm run build
  ```
- **Une assertion de durée ne prouve jamais une propriété de performance** (piège n°7) : l'anti-N+1 de Task 5 compte des requêtes SQL, il ne chronomètre rien.
- **Le texte d'un plan est régulièrement faux sur les interfaces tierces** (piège n°3). Task 1 et Task 9 imposent une vérification contre le paquet réellement installé, jamais contre la documentation ni la mémoire. Corriger sans re-demander, en consignant.
- Ledgers de session nommés `.superpowers/sdd/sp29a-*`, jamais `task-N-report.md` (piège n°9 : sessions concurrentes sur le même arbre).

## Note de méthode : pourquoi le kit n'est pas dans ce plan

La spec §10.3 liste une quarantaine de primitives. Huit d'entre elles (`Select`, `Combobox`, `Menu`, `Popover`, `Tooltip`, `Tabs`, `Drawer`, `ConfirmDialog`) enveloppent une primitive headless dont **le nom, la signature et le modèle de composition ne sont pas connus** avant le spike de Task 1. Écrire leur code maintenant produirait du texte de plan faux — la classe de défaut n°3 de ce dépôt, payée à répétition.

SP-29a livre donc la fondation qui n'a aucune dépendance tierce. **Le plan de SP-29b s'écrit à la sortie de Task 1**, avec les vraies signatures mesurées.

## Structure des fichiers

**Cœur — créés**

| Fichier | Responsabilité |
|---|---|
| `core/tests/test_sharing_decide.py` | Parité exhaustive `decide()` ↔ `can()` |
| `core/tests/test_sharing_roles_batch.py` | `roles_for_items` / `roles_for_collections` : exactitude et nombre de requêtes |
| `core/tests/test_items_permissions.py` | Sérialisation de `permissions` par profil, y compris anonyme |
| `core/tests/test_items_no_nplus1.py` | Instrument de comptage de requêtes SQL |
| `core/tests/test_auth_me_capabilities.py` | `GET /me` porte les sept capacités |

**Cœur — modifiés**

| Fichier | Changement |
|---|---|
| `app/sharing/authorization.py` | Ajout de `decide()` pure ; `can()` délègue |
| `app/sharing/repository.py` | `roles_for_items()` / `roles_for_collections()` remplacent `has_group_role()` / `has_collection_group_role()` |
| `app/items/schemas.py` | `ItemPermissions` + champ `permissions` sur `ItemRead` |
| `app/items/repository.py` | `_to_read()` reçoit les permissions ; `list_items()` et `get_item()` les calculent en lot |
| `app/items/routes.py` | `get_item` transmet l'utilisateur au dépôt |
| `app/auth/routes.py` | `MeCapabilities` + champ `capabilities` sur `MeResponse` |
| `core/openapi.json` | Régénéré (Task 6) |

**Shell — créés**

| Fichier | Responsabilité |
|---|---|
| `shell/src/auth/permissions.ts` | Types `PermissionAction`, `ItemPermissions`, `usePermission` |
| `shell/src/auth/Gate.tsx` | La porte unique : rend ou remplace selon le droit |
| `shell/src/auth/Locked.tsx` | Le traitement « verrouillé et expliqué » |
| `shell/src/auth/capabilities.ts` | Définition des neuf domaines et de leur état par profil |
| `shell/src/auth/{permissions,Gate,Locked,capabilities}.test.tsx` | Un fichier de test par module |
| `shell/src/i18n/catalog.fr.ts` | Catalogue de messages français |
| `shell/src/i18n/index.ts` | `t()` typée, interpolation `{param}` |
| `shell/src/i18n/index.test.ts` | Interpolation, clés manquantes |
| `shell/src/styles/tokens.css` | Palette, typographie, rayons, ombres, deux ambiances |
| `shell/src/styles/tokens.test.ts` | Contrat : tout token existe dans les deux ambiances |

**Shell — modifiés**

| Fichier | Changement |
|---|---|
| `shell/src/api/types.ts:18-30` | `Item` gagne `permissions` |
| `shell/src/api/itemClient.ts` | Sept constructions littérales d'`Item` gagnent `permissions` |
| `shell/src/staticExport/StaticItemClient.ts` | Idem, en lecture seule |
| `shell/src/test/msw/handlers.ts` | Le mock d'items porte des permissions |
| `shell/src/shell/ItemActions.tsx` | Câblé sur `Gate` + libellés passés par `t()` |
| `shell/src/index.css` | Importe `./styles/tokens.css` |
| `shell/src/api/generated/core-schema.d.ts` | Régénéré (Task 6) |

---

## Task 1: Spike — mesurer la bibliothèque de primitives

**Files:**
- Create: `docs/superpowers/plans/2026-08-29-sp29a-spike-primitives.md`
- Test: aucun test automatisé — le livrable est un relevé de mesures reproductibles

**Interfaces:**
- Consumes: rien
- Produces: le document de spike, dont le plan de SP-29b sera dérivé. Il doit nommer **une** bibliothèque retenue et donner, pour `Select`, `Popover` et `Tabs`, l'import exact et le squelette de composition réel copié depuis le paquet installé.

**Contexte pour l'implémenteur :** la spec §5.5 et §10.2 imposent des primitives *headless* (comportement + accessibilité, zéro style), habillées par nos tokens. Candidat de départ : Radix UI Primitives. Alternatives à mesurer : Base UI, Ark UI. Le projet est en **React 19** (`shell/package.json`), sous **Apache-2.0**, et son shell est réempaqueté en conteneur autoporté (SP-18c) et rendu par un worker Playwright headless (SP-17a).

- [ ] **Step 1: Relever l'état de départ, chiffré**

```bash
cd /home/lenen/projets/geostudio/shell
rm -rf dist
npm run build
du -sb dist
find dist/assets -name '*.js' -printf '%f %s\n' | sort -k2 -rn | head -5
```

Consigner les octets totaux et les trois plus gros chunks : c'est la référence contre laquelle le surcoût de chaque candidat se mesure.

- [ ] **Step 2: Vérifier l'existence et la version réelle de chaque candidat**

```bash
npm view @radix-ui/react-select version peerDependencies license
npm view @base-ui-components/react version peerDependencies license
npm view @ark-ui/react version peerDependencies license
```

Ne **rien** déduire de la mémoire : la sortie de `npm view` fait foi. Si `peerDependencies.react` n'admet pas `^19`, le candidat est écarté immédiatement — le consigner et passer au suivant.

- [ ] **Step 3: Installer le candidat retenu dans une branche jetable et mesurer**

```bash
cd /home/lenen/projets/geostudio/shell
git checkout -b spike/primitives-sp29a
npm i <paquet retenu>@<version exacte relevée>
```

Créer `src/spike/SpikeSelect.tsx` qui rend un `Select` avec trois options, en copiant **le squelette de composition depuis le README du paquet installé** :

```bash
sed -n '1,120p' node_modules/<paquet>/README.md
```

Puis :

```bash
rm -rf dist && npm run build && du -sb dist
```

Consigner le delta d'octets par rapport au Step 1.

- [ ] **Step 4: Vérifier le rendu headless**

Le worker d'export (SP-17a) rend le shell dans Chromium sans interface. Une primitive qui s'appuie sur un portail hors du conteneur capturé, ou qui n'ouvre son contenu qu'au survol réel, casse ce chemin.

```bash
cd /home/lenen/projets/geostudio/shell
npx playwright screenshot --viewport-size=900,600 \
  "http://localhost:5173/spike" /tmp/claude-1000/spike-select.png
```

(Lancer `npm run dev` dans un autre terminal, et exposer la route `/spike` le temps du spike.) Ouvrir la capture et consigner : le `Select` fermé est-il rendu ? ouvert par script, son contenu est-il dans la capture ?

- [ ] **Step 5: Vérifier la forme exacte du `@theme` de Tailwind v4**

Le plan de Task 9 suppose que Tailwind v4 accepte `@theme inline { --color-x: var(--gs-x) }`, seule construction qui rende les tokens commutables entre ambiances. Le vérifier maintenant, contre la version installée :

```bash
cd /home/lenen/projets/geostudio/shell
npm ls tailwindcss
grep -rn "theme inline\|@theme" node_modules/tailwindcss/dist/*.css node_modules/tailwindcss/*.md 2>/dev/null | head -20
```

Si `@theme inline` n'existe pas dans cette version, consigner la construction réellement supportée : **Task 9 devra l'utiliser telle quelle**, et le plan a tort.

- [ ] **Step 6: Écrire le relevé et nettoyer**

Créer `docs/superpowers/plans/2026-08-29-sp29a-spike-primitives.md` avec exactement ces sections : *Candidats écartés et pourquoi* · *Bibliothèque retenue, version épinglée* · *Surcoût mesuré en octets* · *Licence* · *Rendu headless : verdict* · *Forme de `@theme` supportée* · *Squelettes réels de `Select`, `Popover`, `Tabs`* (copiés du paquet, pas réécrits).

```bash
cd /home/lenen/projets/geostudio/shell
git checkout -- package.json package-lock.json
rm -rf src/spike
cd .. && git checkout dev && git branch -D spike/primitives-sp29a
```

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add docs/superpowers/plans/2026-08-29-sp29a-spike-primitives.md
git commit -m "docs(sp29a): spike des primitives headless — relevé de mesures"
```

---

## Task 2: `decide()` — extraire la décision pure de `can()`

**Files:**
- Modify: `core/app/sharing/authorization.py`
- Test: `core/tests/test_sharing_decide.py` (créer)

**Interfaces:**
- Consumes: rien
- Produces:
  ```python
  def decide(
      *,
      action: Action,          # "read" | "write" | "delete" | "share"
      kind: ObjectKind,        # "item" | "collection"
      is_owner: bool,
      is_public: bool,
      is_published: bool,
      roles: frozenset[str],   # sous-ensemble de {"viewer", "editor"}
      actor_is_admin: bool,
  ) -> bool
  ```
  Task 4 l'appelle quatre fois par item pour construire `ItemPermissions`.

**Pourquoi :** `can()` (`app/sharing/authorization.py:30`) mêle aujourd'hui deux choses — aller chercher les rôles en base, et décider. Task 4 doit décider pour douze items d'un coup à partir de rôles déjà chargés (Task 3) ; sans extraction, la règle serait dupliquée et les deux copies divergeraient. `decide()` est la règle ; `can()` devient un de ses deux appelants.

- [ ] **Step 1: Écrire le test de parité**

Créer `core/tests/test_sharing_decide.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Parité `decide()` ↔ `can()`.

`decide()` est la règle d'autorisation ; `can()` est le chemin « une ligne,
une requête » et Task 4 est le chemin « douze lignes, une requête ». Les deux
doivent rendre le même verdict sur toute situation, sinon l'interface finira
par afficher une action que le cœur refuse — exactement ce que la refonte
cherche à supprimer.
"""

import itertools

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.items.models import Item
from app.sharing.authorization import AccessFacts, can, decide
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

ACTIONS = ["read", "write", "delete", "share"]
ROLE_SETS = [frozenset(), frozenset({"viewer"}), frozenset({"editor"}), frozenset({"viewer", "editor"})]


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


def test_decide_owner_can_everything():
    for action in ACTIONS:
        assert decide(
            action=action,
            kind="item",
            is_owner=True,
            is_public=False,
            is_published=False,
            roles=frozenset(),
            actor_is_admin=False,
        ) is True


def test_decide_admin_shortcut_applies_to_collections_only():
    # Spec SP-3 §2 : le rôle admin ne court-circuite QUE les collections.
    assert decide(
        action="write", kind="collection", is_owner=False, is_public=False,
        is_published=False, roles=frozenset(), actor_is_admin=True,
    ) is True
    assert decide(
        action="write", kind="item", is_owner=False, is_public=False,
        is_published=False, roles=frozenset(), actor_is_admin=True,
    ) is False


def test_decide_public_or_published_grants_read_only():
    for flag in ("is_public", "is_published"):
        kwargs = {"is_public": False, "is_published": False, flag: True}
        assert decide(
            action="read", kind="item", is_owner=False, roles=frozenset(),
            actor_is_admin=False, **kwargs,
        ) is True
        assert decide(
            action="write", kind="item", is_owner=False, roles=frozenset(),
            actor_is_admin=False, **kwargs,
        ) is False


def test_decide_viewer_reads_editor_writes():
    base = dict(kind="item", is_owner=False, is_public=False, is_published=False, actor_is_admin=False)
    assert decide(action="read", roles=frozenset({"viewer"}), **base) is True
    assert decide(action="write", roles=frozenset({"viewer"}), **base) is False
    for action in ("write", "delete", "share"):
        assert decide(action=action, roles=frozenset({"editor"}), **base) is True


def test_parity_with_can_over_every_situation(session):
    """Le produit cartésien complet : 4 actions × 4 jeux de rôles × propriétaire
    ou non × public × publié × admin ou non. `can()` et `decide()` doivent
    toujours conclure pareil."""
    tenant = get_or_create_default_tenant(session)
    owner = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-owner", username="owner",
        email=None, first_name="", last_name="",
    )
    other = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-other", username="other",
        email=None, first_name="", last_name="",
    )
    groups = {}
    for role in ("viewer", "editor"):
        group = Group(id=f"g-{role}", tenant_id=tenant.id, name=role, created_by=owner.id)
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=other.id, tenant_id=tenant.id))
        groups[role] = group
    session.flush()

    combos = itertools.product(ROLE_SETS, [False, True], [False, True], [False, True], [False, True])
    for n, (roles, as_owner, is_public, is_published, is_admin) in enumerate(combos):
        item_id = f"item-{n}"
        session.add(Item(
            id=item_id, tenant_id=tenant.id, owner_id=owner.id, resource_type="app",
            title="t", is_public=is_public, is_published=is_published,
        ))
        session.flush()
        for role in roles:
            session.add(ItemShare(
                item_id=item_id, group_id=groups[role].id, tenant_id=tenant.id, role=role,
            ))
        session.flush()

        facts = AccessFacts(
            id=item_id, tenant_id=tenant.id, owner_id=owner.id,
            is_public=is_public, is_published=is_published,
        )
        actor = owner if as_owner else other
        for action in ACTIONS:
            expected = can(
                session, user_id=actor.id, action=action, item=facts,
                kind="item", actor_is_admin=is_admin,
            )
            got = decide(
                action=action, kind="item", is_owner=as_owner,
                is_public=is_public, is_published=is_published,
                roles=frozenset() if as_owner else roles, actor_is_admin=is_admin,
            )
            assert got == expected, (
                f"divergence action={action} roles={sorted(roles)} owner={as_owner} "
                f"public={is_public} published={is_published} admin={is_admin}"
            )
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_sharing_decide.py -v
```

Attendu : `ImportError: cannot import name 'decide' from 'app.sharing.authorization'`.

- [ ] **Step 3: Écrire `decide()` et faire déléguer `can()`**

Dans `core/app/sharing/authorization.py`, remplacer le corps de `can()` (lignes 30 à la fin du fichier) par :

```python
def decide(
    *,
    action: Action,
    kind: ObjectKind,
    is_owner: bool,
    is_public: bool,
    is_published: bool,
    roles: frozenset[str],
    actor_is_admin: bool,
) -> bool:
    """La règle d'autorisation, sans accès à la base.

    Deux appelants : `can()` ci-dessous (une ligne, une requête de rôles) et
    `app.items.repository._permissions()` (douze lignes, une requête de rôles
    pour toutes). Ils doivent conclure pareil — `tests/test_sharing_decide.py`
    le prouve sur le produit cartésien complet des situations.
    """
    # Le rôle admin ne court-circuite QUE les collections (spec SP-3 §2) :
    # la sémantique de partage des items (SP-1, testée) ne bouge pas.
    if kind == "collection" and actor_is_admin:
        return True
    if is_owner:
        return True
    if action == "read":
        if is_public or is_published:
            return True
        return bool(roles & {"viewer", "editor"})
    if action in ("write", "delete", "share"):
        return "editor" in roles
    return False


def can(
    session: Session,
    *,
    user_id: str,
    action: Action,
    item: AccessFacts,
    kind: ObjectKind = "item",
    actor_is_admin: bool = False,
) -> bool:
    # Court-circuits conservés à l'identique : ils évitent une requête de
    # rôles quand la décision est déjà acquise. Sans eux, ce chemin ferait une
    # requête là où l'ancien code n'en faisait aucune.
    if kind == "collection" and actor_is_admin:
        return True
    if item.owner_id == user_id:
        return True
    if action == "read" and (item.is_public or item.is_published):
        return True

    if kind == "item":
        roles = roles_for_items(
            session, tenant_id=item.tenant_id, user_id=user_id, item_ids=[item.id]
        ).get(item.id, frozenset())
    else:
        roles = roles_for_collections(
            session, tenant_id=item.tenant_id, user_id=user_id, collection_ids=[item.id]
        ).get(item.id, frozenset())

    return decide(
        action=action,
        kind=kind,
        is_owner=False,
        is_public=item.is_public,
        is_published=item.is_published,
        roles=roles,
        actor_is_admin=actor_is_admin,
    )
```

Et remplacer l'import en tête de fichier (ligne 7) :

```python
from app.sharing.repository import roles_for_collections, roles_for_items
```

`roles_for_items` et `roles_for_collections` sont écrites en Task 3. **Ce plan les met dans l'ordre inverse de leur dépendance parce que la règle vient avant sa source de données ; si tu exécutes Task 2 en premier, ses tests échoueront à l'import jusqu'à Task 3.** Exécute Task 3 d'abord, puis reviens ici — ou exécute les deux dans la même passe et commite séparément.

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_sharing_decide.py tests/test_sharing_authorization.py \
  tests/test_sharing_acceptance.py tests/test_collections_authorization.py -v
```

Attendu : tout passe. `test_sharing_authorization.py` est la suite historique de `can()` — elle ne doit pas bouger d'un test.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/sharing/authorization.py core/tests/test_sharing_decide.py
git commit -m "refactor(core): extraire decide() de can(), avec parité prouvée"
```

---

## Task 3: `roles_for_items()` — lire les rôles en un seul aller-retour

**Files:**
- Modify: `core/app/sharing/repository.py:11-41` (remplace `has_group_role` et `has_collection_group_role`)
- Test: `core/tests/test_sharing_roles_batch.py` (créer)

**Interfaces:**
- Consumes: rien
- Produces:
  ```python
  def roles_for_items(
      session: Session, *, tenant_id: str, user_id: str, item_ids: Sequence[str]
  ) -> dict[str, frozenset[str]]

  def roles_for_collections(
      session: Session, *, tenant_id: str, user_id: str, collection_ids: Sequence[str]
  ) -> dict[str, frozenset[str]]
  ```
  Les clés absentes signifient « aucun rôle ». Consommées par `can()` (Task 2) et `_permissions()` (Task 4).

**Pourquoi :** `has_group_role()` fait une requête par item et par jeu de rôles. Appelée naïvement depuis la sérialisation d'une page de douze items, elle ferait jusqu'à vingt-quatre requêtes de plus par affichage du catalogue. Les deux fonctions singulières ne sont utilisées **que** par `authorization.py` (vérifié : `grep -rn "has_group_role" app tests` ne sort que cet appelant et des commentaires de test) — elles sont donc remplacées, pas doublées.

- [ ] **Step 1: Écrire le test**

Créer `core/tests/test_sharing_roles_batch.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""`roles_for_items` : exactitude, isolation par tenant, et **une seule
requête** quel que soit le nombre d'items — c'est ce dernier point qui est la
raison d'être de la fonction."""

import pytest
from sqlalchemy import event

from app.db import init_db, make_engine, make_session_factory
from app.items.models import Item
from app.sharing.models import Group, GroupMember, ItemShare
from app.sharing.repository import roles_for_items
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def engine():
    eng = make_engine("sqlite+pysqlite:///:memory:")
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    Session = make_session_factory(engine)
    with Session() as s:
        yield s


def _seed(session, *, n_items: int):
    tenant = get_or_create_default_tenant(session)
    member = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-m", username="member",
        email=None, first_name="", last_name="",
    )
    owner = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-o", username="owner",
        email=None, first_name="", last_name="",
    )
    viewers = Group(id="g-v", tenant_id=tenant.id, name="V", created_by=owner.id)
    editors = Group(id="g-e", tenant_id=tenant.id, name="E", created_by=owner.id)
    session.add_all([viewers, editors])
    session.flush()
    session.add(GroupMember(group_id="g-v", user_id=member.id, tenant_id=tenant.id))
    session.add(GroupMember(group_id="g-e", user_id=member.id, tenant_id=tenant.id))
    session.flush()
    ids = []
    for i in range(n_items):
        item_id = f"i-{i}"
        ids.append(item_id)
        session.add(Item(
            id=item_id, tenant_id=tenant.id, owner_id=owner.id,
            resource_type="app", title="t",
        ))
    session.flush()
    # i-0 partagé en lecture, i-1 en écriture, i-2 les deux, le reste rien.
    session.add(ItemShare(item_id="i-0", group_id="g-v", tenant_id=tenant.id, role="viewer"))
    if n_items > 1:
        session.add(ItemShare(item_id="i-1", group_id="g-e", tenant_id=tenant.id, role="editor"))
    if n_items > 2:
        session.add(ItemShare(item_id="i-2", group_id="g-v", tenant_id=tenant.id, role="viewer"))
        session.add(ItemShare(item_id="i-2", group_id="g-e", tenant_id=tenant.id, role="editor"))
    session.flush()
    return tenant, member, ids


def test_returns_role_sets_per_item(session):
    tenant, member, ids = _seed(session, n_items=4)
    got = roles_for_items(session, tenant_id=tenant.id, user_id=member.id, item_ids=ids)
    assert got["i-0"] == frozenset({"viewer"})
    assert got["i-1"] == frozenset({"editor"})
    assert got["i-2"] == frozenset({"viewer", "editor"})
    assert got.get("i-3", frozenset()) == frozenset()


def test_empty_input_makes_no_query(session):
    tenant, member, _ = _seed(session, n_items=1)
    assert roles_for_items(session, tenant_id=tenant.id, user_id=member.id, item_ids=[]) == {}


def test_other_tenant_never_leaks(session):
    tenant, member, ids = _seed(session, n_items=1)
    intruder_tenant = Tenant(id="t2", slug="t2", name="T2")
    session.add(intruder_tenant)
    session.flush()
    got = roles_for_items(session, tenant_id="t2", user_id=member.id, item_ids=ids)
    assert got == {}


def test_one_query_regardless_of_item_count(engine):
    """Le cœur du sujet : douze items ne coûtent pas plus de requêtes que deux.
    On compte les requêtes émises, on ne mesure aucune durée — une durée ne
    prouverait rien d'autre que l'état de la machine."""
    Session = make_session_factory(engine)
    counts: list[int] = []
    for n in (2, 12):
        with Session() as s:
            tenant, member, ids = _seed(s, n_items=n)
            seen = 0

            def count(conn, cursor, statement, params, context, executemany):
                nonlocal seen
                seen += 1

            event.listen(engine, "before_cursor_execute", count)
            try:
                roles_for_items(s, tenant_id=tenant.id, user_id=member.id, item_ids=ids)
            finally:
                event.remove(engine, "before_cursor_execute", count)
            counts.append(seen)
    assert counts[0] == counts[1] == 1, f"attendu 1 requête dans les deux cas, obtenu {counts}"
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_sharing_roles_batch.py -v
```

Attendu : `ImportError: cannot import name 'roles_for_items'`.

- [ ] **Step 3: Écrire les deux fonctions de lot**

Dans `core/app/sharing/repository.py`, **remplacer** `has_group_role` et `has_collection_group_role` (lignes 11 à 41) par :

```python
def roles_for_items(
    session: Session, *, tenant_id: str, user_id: str, item_ids: Sequence[str]
) -> dict[str, frozenset[str]]:
    """Les rôles de groupe de `user_id` sur chacun des `item_ids`, en **une**
    requête.

    Remplace l'ancien `has_group_role()` (une requête par item et par jeu de
    rôles) : la sérialisation d'une page de catalogue a besoin des rôles de
    douze items à la fois, et le faire ligne par ligne était le N+1 que
    `tests/test_items_no_nplus1.py` interdit désormais.

    Une clé absente du résultat signifie « aucun rôle » — les appelants
    utilisent `.get(id, frozenset())`.
    """
    if not item_ids:
        return {}
    rows = session.execute(
        select(ItemShare.item_id, ItemShare.role)
        .join(GroupMember, GroupMember.group_id == ItemShare.group_id)
        .where(
            ItemShare.item_id.in_(list(item_ids)),
            ItemShare.tenant_id == tenant_id,
            GroupMember.user_id == user_id,
            GroupMember.tenant_id == tenant_id,
        )
    ).all()
    out: dict[str, set[str]] = {}
    for item_id, role in rows:
        out.setdefault(item_id, set()).add(role)
    return {k: frozenset(v) for k, v in out.items()}


def roles_for_collections(
    session: Session, *, tenant_id: str, user_id: str, collection_ids: Sequence[str]
) -> dict[str, frozenset[str]]:
    """Pendant de `roles_for_items` pour les collections. Même contrat."""
    if not collection_ids:
        return {}
    rows = session.execute(
        select(CollectionShare.collection_id, CollectionShare.role)
        .join(GroupMember, GroupMember.group_id == CollectionShare.group_id)
        .where(
            CollectionShare.collection_id.in_(list(collection_ids)),
            CollectionShare.tenant_id == tenant_id,
            GroupMember.user_id == user_id,
            GroupMember.tenant_id == tenant_id,
        )
    ).all()
    out: dict[str, set[str]] = {}
    for collection_id, role in rows:
        out.setdefault(collection_id, set()).add(role)
    return {k: frozenset(v) for k, v in out.items()}
```

Et ajouter l'import de `Sequence` en tête de fichier, après `import uuid` :

```python
from collections.abc import Sequence
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_sharing_roles_batch.py tests/test_sharing_decide.py \
  tests/test_sharing_authorization.py tests/test_sharing_acceptance.py \
  tests/test_collections_authorization.py tests/test_collections_sharing_routes.py -v
```

Attendu : tout passe, y compris la suite historique de `can()`.

- [ ] **Step 5: Vérifier qu'aucun appelant orphelin ne subsiste**

```bash
cd /home/lenen/projets/geostudio/core
grep -rn "has_group_role\|has_collection_group_role" app/ && echo "APPELANT ORPHELIN" || echo "aucun appelant restant : OK"
uv run lint-imports
```

Attendu : « aucun appelant restant : OK », et le contrat de couches passe sans entrée nouvelle (`app.sharing` reste sous `app.items`).

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/sharing/repository.py core/tests/test_sharing_roles_batch.py
git commit -m "feat(core): roles_for_items/roles_for_collections, une requête par lot"
```

---

## Task 4: `ItemRead.permissions` — le cœur dit ce que l'utilisateur peut faire

**Files:**
- Modify: `core/app/items/schemas.py:5-16`
- Modify: `core/app/items/repository.py:64-77` (`_to_read`), `141-151` (`get_item`), `240`, `251`, `286`, `344`, `356`, `379`
- Modify: `core/app/items/routes.py:52-62` (`get_item` transmet l'utilisateur)
- Test: `core/tests/test_items_permissions.py` (créer)

**Interfaces:**
- Consumes: `decide()` (Task 2), `roles_for_items()` (Task 3)
- Produces:
  ```python
  class ItemPermissions(BaseModel):
      read: bool
      write: bool
      delete: bool
      share: bool

  # sur ItemRead : permissions: ItemPermissions
  ```
  Le shell le lit en Task 7 sous le nom TypeScript `ItemPermissions`.

**Contrainte de conception, à ne pas contourner :** `get_item()` a **une vingtaine d'appelants** hors du module (`app/mcp/tools.py` ×9, `app/configs/*_validation.py` ×4, `app/alerts/`, `app/harvest/`, `app/reports/jobs.py`). Rendre `current_user_id` obligatoire imposerait de tous les toucher, pour aucun bénéfice : aucun d'eux ne lit `permissions`. Le paramètre est donc **optionnel**, et son absence produit le repli conservateur `PUBLIC_READ_ONLY` (`read=True`, le reste `False`) — le même que sert la route publique anonyme. Seule `app/items/routes.py::get_item`, celle que consomme le shell, passe l'utilisateur.

- [ ] **Step 1: Écrire le test**

Créer `core/tests/test_items_permissions.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""`ItemRead.permissions` : le cœur calcule, le shell lit.

Objectif produit (spec §6.3) : l'interface ne doit plus proposer une action
que l'API refusera. Ces tests fixent le contrat que `shell/src/auth/Gate.tsx`
consommera.
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
from app.main import create_app
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-owner", username="owner",
            email=None, first_name="", last_name="",
        )
        viewer = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-viewer", username="viewer",
            email=None, first_name="", last_name="",
        )
        editor = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-editor", username="editor",
            email=None, first_name="", last_name="",
        )
        stranger = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-stranger", username="stranger",
            email=None, first_name="", last_name="",
        )
        gv = Group(id="gv", tenant_id=tenant.id, name="V", created_by=owner.id)
        ge = Group(id="ge", tenant_id=tenant.id, name="E", created_by=owner.id)
        s.add_all([gv, ge])
        s.flush()
        s.add(GroupMember(group_id="gv", user_id=viewer.id, tenant_id=tenant.id))
        s.add(GroupMember(group_id="ge", user_id=editor.id, tenant_id=tenant.id))
        s.add(Item(
            id="shared", tenant_id=tenant.id, owner_id=owner.id,
            resource_type="map", title="Réseau d'eau potable",
        ))
        s.add(Item(
            id="pub", tenant_id=tenant.id, owner_id=owner.id, resource_type="site",
            title="Portail eau", is_published=True, slug="portail-eau",
        ))
        s.flush()
        s.add(ItemShare(item_id="shared", group_id="gv", tenant_id=tenant.id, role="viewer"))
        s.add(ItemShare(item_id="shared", group_id="ge", tenant_id=tenant.id, role="editor"))
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    def as_user(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield {"as_user": as_user, "owner": owner, "viewer": viewer,
           "editor": editor, "stranger": stranger}
    engine.dispose()


def _perms(client, item_id: str) -> dict:
    response = client.get(f"/items/{item_id}")
    assert response.status_code == 200, response.text
    return response.json()["permissions"]


def test_owner_gets_every_permission(env):
    client = env["as_user"](env["owner"])
    assert _perms(client, "shared") == {
        "read": True, "write": True, "delete": True, "share": True
    }


def test_viewer_reads_only(env):
    client = env["as_user"](env["viewer"])
    assert _perms(client, "shared") == {
        "read": True, "write": False, "delete": False, "share": False
    }


def test_editor_writes_deletes_shares_but_is_not_owner(env):
    client = env["as_user"](env["editor"])
    assert _perms(client, "shared") == {
        "read": True, "write": True, "delete": True, "share": True
    }


def test_published_item_is_readable_by_a_stranger_but_not_writable(env):
    client = env["as_user"](env["stranger"])
    assert _perms(client, "pub") == {
        "read": True, "write": False, "delete": False, "share": False
    }


def test_listing_carries_the_same_permissions_as_the_detail(env):
    """Le catalogue et la fiche doivent s'accorder : c'est la colonne
    « Votre accès » de la maquette qui en dépend."""
    client = env["as_user"](env["viewer"])
    listing = client.get("/items?scope=all&pageSize=50")
    assert listing.status_code == 200, listing.text
    by_pk = {item["pk"]: item for item in listing.json()["items"]}
    assert by_pk["shared"]["permissions"] == _perms(client, "shared")
    assert by_pk["shared"]["permissions"]["write"] is False


def test_public_route_serves_the_conservative_default(env):
    """`GET /public/items` est anonyme : personne n'a de droit d'écriture,
    et le champ doit quand même être présent — le shell le lit sans savoir
    par quelle route l'item est arrivé."""
    client = env["as_user"](env["stranger"])
    response = client.get("/public/items")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items, "au moins l'item publié doit ressortir"
    for item in items:
        assert item["permissions"] == {
            "read": True, "write": False, "delete": False, "share": False
        }
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_items_permissions.py -v
```

Attendu : `KeyError: 'permissions'` sur le premier test.

- [ ] **Step 3: Ajouter le schéma**

Dans `core/app/items/schemas.py`, avant `class ItemRead` :

```python
class ItemPermissions(BaseModel):
    """Ce que l'utilisateur courant a le droit de faire sur cet item.

    Calculé par le cœur depuis `can()` (une seule porte, spec §6.3) et jamais
    recalculé côté client : le shell affiche ou masque à partir de ces quatre
    booléens, ce qui supprime les commandes qui produisaient un 403 après le
    clic. Ce n'est PAS une frontière de sécurité — le cœur reste seul juge à
    chaque écriture.
    """

    read: bool
    write: bool
    delete: bool
    share: bool
```

Et dans `class ItemRead`, après `keywords` :

```python
    permissions: ItemPermissions
```

- [ ] **Step 4: Calculer les permissions dans le dépôt**

Dans `core/app/items/repository.py`, ajouter aux imports :

```python
from app.items.schemas import ItemPage, ItemPermissions, ItemRead
from app.sharing.authorization import Action, decide
from app.sharing.repository import roles_for_items
```

(adapter la ligne d'import existante de `app.items.schemas` plutôt que d'en ajouter une seconde)

Puis, juste avant `def _to_read` (ligne 64) :

```python
# Repli conservateur, servi partout où l'appelant ne fournit pas d'utilisateur :
# les routes publiques anonymes, et la vingtaine d'appelants internes de
# `get_item()` (MCP, validateurs de configs, jobs) qui ne lisent jamais ce
# champ. `read=True` parce que ces chemins n'exposent que du publié ; tout le
# reste est refusé par défaut.
PUBLIC_READ_ONLY = ItemPermissions(read=True, write=False, delete=False, share=False)


def _permissions(item: Item, *, current_user_id: str, roles: frozenset[str]) -> ItemPermissions:
    is_owner = item.owner_id == current_user_id

    def verdict(action: Action) -> bool:
        # actor_is_admin=False : le rôle admin ne court-circuite QUE les
        # collections (spec SP-3 §2), jamais les items — cf. decide().
        return decide(
            action=action,
            kind="item",
            is_owner=is_owner,
            is_public=item.is_public,
            is_published=item.is_published,
            roles=roles,
            actor_is_admin=False,
        )

    return ItemPermissions(
        read=verdict("read"),
        write=verdict("write"),
        delete=verdict("delete"),
        share=verdict("share"),
    )


def _permissions_by_id(
    session: Session, *, tenant_id: str, current_user_id: str, items: list[Item]
) -> dict[str, ItemPermissions]:
    """Les permissions de toute une page, avec **une** requête de rôles.

    C'est la raison d'être de `roles_for_items` : appeler `can()` item par item
    ferait jusqu'à deux requêtes par ligne — le N+1 qu'interdit
    `tests/test_items_no_nplus1.py`.
    """
    roles_by_id = roles_for_items(
        session,
        tenant_id=tenant_id,
        user_id=current_user_id,
        item_ids=[item.id for item in items],
    )
    return {
        item.id: _permissions(
            item, current_user_id=current_user_id, roles=roles_by_id.get(item.id, frozenset())
        )
        for item in items
    }
```

Changer la signature de `_to_read` (ligne 64) :

```python
def _to_read(
    item: Item, owner_username: str, permissions: ItemPermissions = PUBLIC_READ_ONLY
) -> ItemRead:
```

et ajouter, dans l'appel `ItemRead(...)` de son corps, après `keywords=item.keywords or []` :

```python
        permissions=permissions,
```

- [ ] **Step 5: Câbler les deux chemins qui ont un utilisateur**

`get_item` (ligne 141) devient :

```python
def get_item(
    session: Session, *, tenant_id: str, item_id: str, current_user_id: str | None = None
) -> ItemRead | None:
    row = session.execute(
        select(Item, User.username)
        .join(User, User.id == Item.owner_id)
        .where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).first()
    if row is None:
        return None
    item, owner_username = row
    if current_user_id is None:
        # Appelants internes (MCP, validateurs, jobs) : ils ne lisent pas
        # `permissions`, on ne paie pas la requête de rôles pour eux.
        return _to_read(item, owner_username)
    permissions = _permissions_by_id(
        session, tenant_id=tenant_id, current_user_id=current_user_id, items=[item]
    )[item.id]
    return _to_read(item, owner_username, permissions)
```

Dans `list_items`, remplacer la ligne 240 :

```python
        page_items = [by_id[i][0] for i in page_ids if i in by_id]
        perms = _permissions_by_id(
            session, tenant_id=tenant_id, current_user_id=current_user_id, items=page_items
        )
        items = [
            _to_read(*by_id[i], perms[by_id[i][0].id]) for i in page_ids if i in by_id
        ]
        return ItemPage(items=items, total=total, page=page, pageSize=page_size)
```

et la ligne 251 :

```python
    page_items = [item for item, _owner_username in rows]
    perms = _permissions_by_id(
        session, tenant_id=tenant_id, current_user_id=current_user_id, items=page_items
    )
    items = [_to_read(item, owner_username, perms[item.id]) for item, owner_username in rows]
    return ItemPage(items=items, total=total, page=page, pageSize=page_size)
```

Les trois autres appels (`list_published_items` ligne 286, `update_item` ligne 344, `get_published_item` ligne 356, `get_published_site_by_slug` ligne 379) **restent inchangés** : le repli conservateur est le bon comportement pour chacun.

- [ ] **Step 6: Transmettre l'utilisateur depuis la route**

Dans `core/app/items/routes.py`, dans `get_item` (ligne 60), remplacer :

```python
    result = repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
```

par :

```python
    result = repo.get_item(
        session, tenant_id=user.tenant_id, item_id=item_id, current_user_id=user.id
    )
```

- [ ] **Step 7: Lancer les tests, vérifier qu'ils passent**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_items_permissions.py -v
uv run pytest tests/ -x -q
```

Attendu : la nouvelle suite passe, et la suite complète reste à son état de référence — **1896 passed + 5 skipped + 1 failed**. L'unique échec attendu est `test_features_rls.py::test_scope_preserves_original_sql_error`, **préexistant** (dérive psycopg2/transaction, non diagnostiquée) : ne pas l'imputer à ce travail. Les 5 skips sont le marqueur `qgis` (sidecar réel requis).

- [ ] **Step 8: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/items/schemas.py core/app/items/repository.py \
        core/app/items/routes.py core/tests/test_items_permissions.py
git commit -m "feat(core): ItemRead porte les permissions calculées par can()"
```

---

## Task 5: L'instrument anti-N+1

**Files:**
- Test: `core/tests/test_items_no_nplus1.py` (créer)

**Interfaces:**
- Consumes: `GET /items` tel que livré par Task 4
- Produces: rien pour les tâches suivantes — c'est un garde-fou permanent

**Pourquoi une tâche à part :** Task 4 pourrait passer tous ses tests avec une implémentation naïve qui appelle `can()` douze fois. Ce test est le seul qui l'interdirait, et il mérite d'être jugé séparément : un relecteur peut approuver le contrat de permissions et rejeter son coût, ou l'inverse.

**Ce qu'il ne fait pas :** il ne chronomètre rien. Une assertion de durée mesure la machine, pas une propriété du code (piège n°7). Il compte des requêtes SQL émises.

- [ ] **Step 1: Écrire le test**

Créer `core/tests/test_items_no_nplus1.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde-fou permanent : le nombre de requêtes SQL d'un `GET /items` ne doit
pas croître avec le nombre d'items de la page.

Sans ce test, une implémentation qui appelle `can()` ligne par ligne passe
tous les tests fonctionnels de `test_items_permissions.py` — et ajoute jusqu'à
deux requêtes par item à chaque affichage du catalogue.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
from app.main import create_app
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _build(n_items: int):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-owner", username="owner",
            email=None, first_name="", last_name="",
        )
        reader = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-reader", username="reader",
            email=None, first_name="", last_name="",
        )
        group = Group(id="gv", tenant_id=tenant.id, name="V", created_by=owner.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id="gv", user_id=reader.id, tenant_id=tenant.id))
        for i in range(n_items):
            s.add(Item(
                id=f"i-{i}", tenant_id=tenant.id, owner_id=owner.id,
                resource_type="app", title=f"Item {i}",
            ))
        s.flush()
        for i in range(n_items):
            s.add(ItemShare(
                item_id=f"i-{i}", group_id="gv", tenant_id=tenant.id, role="viewer",
            ))
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: reader
    return engine, TestClient(app)


def _count_queries(engine, fn):
    seen = 0

    def bump(conn, cursor, statement, params, context, executemany):
        nonlocal seen
        seen += 1

    event.listen(engine, "before_cursor_execute", bump)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", bump)
    return seen


@pytest.mark.parametrize("small,large", [(2, 12)])
def test_query_count_does_not_grow_with_page_size(small, large):
    counts = {}
    for n in (small, large):
        engine, client = _build(n)
        try:
            def call():
                response = client.get(f"/items?scope=all&pageSize={n}")
                assert response.status_code == 200, response.text
                assert len(response.json()["items"]) == n
            counts[n] = _count_queries(engine, call)
        finally:
            engine.dispose()
    assert counts[small] == counts[large], (
        f"le nombre de requêtes croît avec la page : {counts} — "
        "c'est un N+1, probablement un can() appelé ligne par ligne"
    )
```

- [ ] **Step 2: Lancer le test, vérifier qu'il passe avec l'implémentation de Task 4**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_items_no_nplus1.py -v
```

Attendu : PASS.

- [ ] **Step 3: Prouver que le test mord**

Ce test ne vaut que s'il échoue quand il doit. Introduire temporairement la régression dans `app/items/repository.py` — remplacer le corps de `_permissions_by_id` par :

```python
    from app.sharing.authorization import can

    return {
        item.id: _permissions(
            item,
            current_user_id=current_user_id,
            roles=roles_for_items(
                session, tenant_id=tenant_id, user_id=current_user_id, item_ids=[item.id]
            ).get(item.id, frozenset()),
        )
        for item in items
    }
```

puis :

```bash
uv run pytest tests/test_items_no_nplus1.py -v
```

Attendu : **FAIL**, avec un message du type `le nombre de requêtes croît avec la page : {2: N, 12: M}`. **Annuler ensuite la régression** :

```bash
cd /home/lenen/projets/geostudio
git checkout -- core/app/items/repository.py
cd core && uv run pytest tests/test_items_no_nplus1.py -v
```

Attendu : PASS de nouveau.

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/tests/test_items_no_nplus1.py
git commit -m "test(core): garde-fou anti-N+1 sur la sérialisation du catalogue"
```

---

## Task 6: `GET /me` porte les capacités — et régénération OpenAPI

**Files:**
- Modify: `core/app/auth/routes.py:18-40`
- Modify: `core/openapi.json` (régénéré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Test: `core/tests/test_auth_me_capabilities.py` (créer)

**Interfaces:**
- Consumes: les sept sondes de `app/auth/dependency.py` (`is_read_only_mode`, `is_etl_enabled`, `is_export_enabled`, `is_appexport_enabled`, `is_tileset3d_enabled`, `is_terrain3d_enabled`, `is_copilot_enabled`)
- Produces:
  ```python
  class MeCapabilities(BaseModel):
      readOnly: bool
      etlEnabled: bool
      exportEnabled: bool
      appExportEnabled: bool
      tileset3dEnabled: bool
      terrain3dEnabled: bool
      copilotEnabled: bool
  # sur MeResponse : capabilities: MeCapabilities
  ```
  `shell/src/auth/capabilities.ts` (Task 7) le consomme sous le nom `InstanceCapabilities`.

**Pourquoi :** la doctrine des droits (spec §6.2) fait dépendre l'état d'un domaine de **deux** sources — le rôle du compte et la capacité de l'instance. Aujourd'hui elles arrivent par deux appels distincts (`GET /me` et `GET /instance`), que chaque écran croise à sa façon. `capabilities.ts` a besoin d'un profil unique ; `GET /me` devient cette source. `GET /instance` **reste** : il est lu avant authentification par la page de connexion et le mode démo, et rien ne le remplace.

**Attention `mypy --strict` :** `app/auth` est l'un des quatre modules sous `mypy --strict`. Les annotations de `MeCapabilities` et de sa construction doivent être complètes.

- [ ] **Step 1: Écrire le test**

Créer `core/tests/test_auth_me_capabilities.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""`GET /me` porte les capacités de l'instance.

Le shell dérive l'état de ses neuf domaines d'un profil unique (spec §6.6) :
rôle du compte + capacités du déploiement. Sans ce champ, il faudrait croiser
deux requêtes dans chaque écran — c'est ce que fait le code d'aujourd'hui, et
c'est ce que la refonte supprime.
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

CAPABILITY_KEYS = {
    "readOnly",
    "etlEnabled",
    "exportEnabled",
    "appExportEnabled",
    "tileset3dEnabled",
    "terrain3dEnabled",
    "copilotEnabled",
}


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-1", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    engine.dispose()


def test_me_exposes_every_capability(client):
    response = client.get("/me")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["capabilities"]) == CAPABILITY_KEYS
    for key, value in body["capabilities"].items():
        assert isinstance(value, bool), f"{key} doit être un booléen, pas {type(value)}"


def test_me_capabilities_match_the_instance_route(client):
    """Les deux routes doivent dire la même chose : `GET /instance` reste servi
    avant authentification (page de connexion, mode démo) et ne disparaît pas.
    Si elles divergent, un écran affichera une capacité que l'autre refuse."""
    me = client.get("/me").json()["capabilities"]
    instance = client.get("/instance").json()
    assert me == instance


def test_me_keeps_its_existing_fields(client):
    """Non-régression : le champ ajouté ne doit rien retirer — le shell lit
    encore `username`, `isAdmin` et `isAnalyst` à quinze endroits."""
    body = client.get("/me").json()
    for key in ("id", "tenantId", "username", "email", "firstName", "lastName",
                "isAdmin", "isAnalyst"):
        assert key in body, f"champ disparu de MeResponse : {key}"


@pytest.mark.parametrize("env_value,expected", [("true", True), ("false", False)])
def test_capability_reflects_the_environment(client, monkeypatch, env_value, expected):
    monkeypatch.setenv("CORE_ETL_ENABLED", env_value)
    assert client.get("/me").json()["capabilities"]["etlEnabled"] is expected
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_auth_me_capabilities.py -v
```

Attendu : `KeyError: 'capabilities'`.

Si `test_capability_reflects_the_environment` échoue pour une autre raison — par exemple parce que `is_etl_enabled()` met sa valeur en cache — **le plan a tort sur ce point** : lire `app/auth/dependency.py:40` et adapter le test au comportement réel (un `monkeypatch` sur la fonction plutôt que sur la variable d'environnement). Consigner la correction.

- [ ] **Step 3: Implémenter**

Dans `core/app/auth/routes.py`, ajouter aux imports depuis `app.auth.dependency` :

```python
from app.auth.dependency import (
    get_current_user,
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
)
```

(fusionner avec l'import existant de `get_current_user` plutôt que d'en ajouter un second)

Avant `class MeResponse` (ligne 18) :

```python
class MeCapabilities(BaseModel):
    """Les capacités du déploiement, servies avec le profil.

    Même contenu que `GET /instance`, qui reste servi sans authentification
    (page de connexion, mode démo). Le doublon est délibéré : le shell dérive
    l'état de ses domaines d'un profil unique (spec §6.6) au lieu de croiser
    deux requêtes dans chaque écran. `tests/test_auth_me_capabilities.py`
    interdit aux deux routes de diverger.
    """

    readOnly: bool
    etlEnabled: bool
    exportEnabled: bool
    appExportEnabled: bool
    tileset3dEnabled: bool
    terrain3dEnabled: bool
    copilotEnabled: bool
```

Dans `class MeResponse`, après `isAnalyst: bool` :

```python
    capabilities: MeCapabilities
```

Et dans `get_me`, ajouter au constructeur `MeResponse(...)` :

```python
        capabilities=MeCapabilities(
            readOnly=is_read_only_mode(),
            etlEnabled=is_etl_enabled(),
            exportEnabled=is_export_enabled(),
            appExportEnabled=is_appexport_enabled(),
            tileset3dEnabled=is_tileset3d_enabled(),
            terrain3dEnabled=is_terrain3d_enabled(),
            copilotEnabled=is_copilot_enabled(),
        ),
```

- [ ] **Step 4: Lancer les tests et `mypy --strict`**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest tests/test_auth_me_capabilities.py -v
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run ruff check . && uv run ruff format --check .
```

Attendu : tests verts, `mypy` sans erreur, `ruff` propre.

- [ ] **Step 5: Régénérer OpenAPI et les types TS**

Deux modèles ont changé dans ce plan — `ItemRead` (Task 4) et `MeResponse` (ici). C'est la classe d'oubli n°1 du dépôt, et le diff attendu ici est **non vide**.

```bash
PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd .. && git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Attendu : les deux fichiers sont modifiés. Vérifier que `ItemPermissions` et `MeCapabilities` apparaissent bien :

```bash
grep -c "ItemPermissions\|MeCapabilities" core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Attendu : un compte non nul pour les deux fichiers.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/auth/routes.py core/tests/test_auth_me_capabilities.py \
        core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): GET /me porte les capacités de l'instance"
```

---

## Task 7: Shell — `Item.permissions`, `hasPermission`, `Gate`, `Locked`

**Files:**
- Create: `shell/src/auth/permissions.ts`, `shell/src/auth/permissions.test.ts`
- Create: `shell/src/auth/Gate.tsx`, `shell/src/auth/Gate.test.tsx`
- Create: `shell/src/auth/Locked.tsx`, `shell/src/auth/Locked.test.tsx`
- Modify: `shell/src/api/types.ts:18-30`
- Modify: `shell/src/api/itemClient.ts` — lignes 595, 823, 928, 956, 991, 1053, 1103
- Modify: `shell/src/staticExport/StaticItemClient.ts`
- Modify: `shell/src/test/msw/handlers.ts:16`

**Interfaces:**
- Consumes: le champ `permissions` de `ItemRead` (Task 4)
- Produces:
  ```ts
  export type PermissionAction = "read" | "write" | "delete" | "share";
  export type ItemPermissions = Record<PermissionAction, boolean>;
  export type HasPermissions = { permissions: ItemPermissions };
  export const OWNER_PERMISSIONS: ItemPermissions;
  export const READ_ONLY_PERMISSIONS: ItemPermissions;
  export function hasPermission(on: HasPermissions | null | undefined, action: PermissionAction): boolean;
  export function Gate(props: { on; can; children; fallback? }): React.ReactNode;
  export function Locked(props: { reason: string; children: React.ReactNode }): React.ReactNode;
  ```
  Task 10 les consomme dans `ItemActions.tsx`.

**Pourquoi `hasPermission` et pas `usePermission` :** ce n'est pas un hook — aucun état, aucun contexte. Le nommer `use*` déclencherait à tort les règles de `eslint-plugin-react-hooks` et interdirait de l'appeler hors composant, alors que Task 8 en a besoin dans des fonctions pures.

- [ ] **Step 1: Écrire les tests des trois modules**

Créer `shell/src/auth/permissions.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  hasPermission,
  OWNER_PERMISSIONS,
  READ_ONLY_PERMISSIONS,
  type ItemPermissions,
} from "./permissions";

const viewer: ItemPermissions = { read: true, write: false, delete: false, share: false };

describe("hasPermission", () => {
  it("lit le verdict rendu par le cœur", () => {
    expect(hasPermission({ permissions: viewer }, "read")).toBe(true);
    expect(hasPermission({ permissions: viewer }, "write")).toBe(false);
    expect(hasPermission({ permissions: OWNER_PERMISSIONS }, "share")).toBe(true);
  });

  it("refuse tout quand la charge utile ne porte pas de permissions", () => {
    // Repli sûr et volontairement visible : si un écran perd soudain ses
    // commandes, c'est que sa source n'a pas été mise à jour — on veut le voir,
    // pas le masquer derrière un « autorisé par défaut ».
    expect(hasPermission(null, "read")).toBe(false);
    expect(hasPermission(undefined, "write")).toBe(false);
  });

  it("expose deux jeux constants, propriétaire et lecture seule", () => {
    expect(OWNER_PERMISSIONS).toEqual({ read: true, write: true, delete: true, share: true });
    expect(READ_ONLY_PERMISSIONS).toEqual({
      read: true,
      write: false,
      delete: false,
      share: false,
    });
  });
});
```

Créer `shell/src/auth/Gate.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Gate } from "./Gate";
import { OWNER_PERMISSIONS, type ItemPermissions } from "./permissions";

const viewer: ItemPermissions = { read: true, write: false, delete: false, share: false };

describe("Gate", () => {
  it("rend ses enfants quand le droit est accordé", () => {
    render(
      <Gate on={{ permissions: OWNER_PERMISSIONS }} can="write">
        <button>Modifier</button>
      </Gate>,
    );
    expect(screen.getByRole("button", { name: "Modifier" })).toBeInTheDocument();
  });

  it("ne rend rien quand le droit est refusé et qu'aucun repli n'est fourni", () => {
    render(
      <Gate on={{ permissions: viewer }} can="write">
        <button>Modifier</button>
      </Gate>,
    );
    expect(screen.queryByRole("button", { name: "Modifier" })).not.toBeInTheDocument();
  });

  it("rend le repli quand il est fourni", () => {
    render(
      <Gate
        on={{ permissions: viewer }}
        can="delete"
        fallback={<span>Réservé aux éditeurs</span>}
      >
        <button>Supprimer</button>
      </Gate>,
    );
    expect(screen.queryByRole("button", { name: "Supprimer" })).not.toBeInTheDocument();
    expect(screen.getByText("Réservé aux éditeurs")).toBeInTheDocument();
  });

  it("couvre les quatre actions", () => {
    const perms: ItemPermissions = { read: true, write: true, delete: false, share: false };
    for (const [action, expected] of [
      ["read", true],
      ["write", true],
      ["delete", false],
      ["share", false],
    ] as const) {
      const { unmount } = render(
        <Gate on={{ permissions: perms }} can={action}>
          <span>{action}</span>
        </Gate>,
      );
      expect(screen.queryByText(action) !== null).toBe(expected);
      unmount();
    }
  });
});
```

Créer `shell/src/auth/Locked.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Locked } from "./Locked";

describe("Locked", () => {
  it("affiche la raison et rend le contenu inopérant", () => {
    render(
      <Locked reason="Écriture réservée aux éditeurs de cet élément.">
        <button>Modifier</button>
      </Locked>,
    );
    const button = screen.getByRole("button", { name: "Modifier" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Écriture réservée aux éditeurs de cet élément.")).toBeVisible();
  });

  it("relie la raison au contenu pour les lecteurs d'écran", () => {
    render(
      <Locked reason="Le partage est réservé au propriétaire.">
        <button>Partager</button>
      </Locked>,
    );
    const group = screen.getByRole("group");
    expect(group).toHaveAccessibleDescription("Le partage est réservé au propriétaire.");
  });
});
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test -- src/auth
```

Attendu : échec de résolution des trois modules `./permissions`, `./Gate`, `./Locked`.

- [ ] **Step 3: Écrire les trois modules**

Créer `shell/src/auth/permissions.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
//
// La porte unique côté interface. Le cœur a la sienne — `can()` dans
// `core/app/sharing/authorization.py` — et calcule le verdict qu'on lit ici.
//
// Règle de la refonte (spec §6.5) : aucune comparaison de droits ailleurs dans
// le shell. Pas de `item.owner === me`, pas de `meQuery.data?.isAdmin === true`
// dans une page. Tout passe par `hasPermission`, `Gate` ou `capabilities.ts`.
//
// Ce n'est PAS une frontière de sécurité : le cœur refuse de toute façon. C'est
// la garantie qu'on n'affiche plus une commande qui produira un 403.

export type PermissionAction = "read" | "write" | "delete" | "share";

export type ItemPermissions = Record<PermissionAction, boolean>;

export type HasPermissions = { permissions: ItemPermissions };

/** Droits d'un objet qu'on vient de créer : on en est le propriétaire. */
export const OWNER_PERMISSIONS: ItemPermissions = {
  read: true,
  write: true,
  delete: true,
  share: true,
};

/** Droits servis par les chemins anonymes et par l'export statique. */
export const READ_ONLY_PERMISSIONS: ItemPermissions = {
  read: true,
  write: false,
  delete: false,
  share: false,
};

export function hasPermission(
  on: HasPermissions | null | undefined,
  action: PermissionAction,
): boolean {
  // Une charge utile sans permissions est un refus. Repli volontairement
  // visible : si un écran perd ses commandes, c'est que sa source n'a pas été
  // mise à jour — mieux vaut le constater que le masquer.
  return on?.permissions?.[action] === true;
}
```

Créer `shell/src/auth/Gate.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { hasPermission, type HasPermissions, type PermissionAction } from "./permissions";

export function Gate({
  on,
  can,
  children,
  fallback = null,
}: {
  on: HasPermissions | null | undefined;
  can: PermissionAction;
  children: ReactNode;
  /**
   * Rendu quand le droit est refusé. `null` (défaut) = traitement « absent ».
   * Passer un `<Locked reason="…">` = traitement « verrouillé et expliqué ».
   * Les deux traitements de la doctrine (spec §6.2) sont donc exprimés ici,
   * et le choix est fait par l'appelant, qui seul sait si l'utilisateur peut
   * légitimement se demander pourquoi.
   */
  fallback?: ReactNode;
}): ReactNode {
  return hasPermission(on, can) ? children : fallback;
}
```

Créer `shell/src/auth/Locked.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useId, type ReactNode } from "react";

/**
 * Le traitement « verrouillé et expliqué » de la doctrine (spec §6.2) : le
 * contrôle reste visible, il est inopérant, et **la raison est écrite**. Jamais
 * un cadenas muet — l'utilisateur doit savoir quoi faire pour l'obtenir.
 *
 * Le `fieldset` désactivé rend inopérant tout ce qu'il contient, sans que
 * l'appelant ait à cloner ses enfants pour leur injecter `disabled`.
 */
export function Locked({ reason, children }: { reason: string; children: ReactNode }): ReactNode {
  const reasonId = useId();
  return (
    <fieldset disabled role="group" aria-describedby={reasonId} className="contents">
      {children}
      <span id={reasonId} className="block px-3 py-1 text-xs text-slate-500">
        {reason}
      </span>
    </fieldset>
  );
}
```

- [ ] **Step 4: Ajouter `permissions` au type `Item` et aux neuf sources**

Dans `shell/src/api/types.ts`, ajouter l'import en tête :

```ts
import type { ItemPermissions } from "../auth/permissions";
```

et le champ dans `export type Item` (ligne 18-30), après `keywords?: string[];` :

```ts
  permissions: ItemPermissions;
```

Le compilateur signale alors chaque construction littérale d'un `Item`. Dans `shell/src/api/itemClient.ts`, ajouter l'import :

```ts
import { OWNER_PERMISSIONS } from "../auth/permissions";
```

et, aux **sept** emplacements qui contiennent `isPublished: false,` (lignes 595, 823, 928, 956, 991, 1053, 1103 avant modification), ajouter juste après cette ligne :

```ts
        // On vient de créer cet objet : on en est le propriétaire.
        permissions: OWNER_PERMISSIONS,
```

Dans `shell/src/staticExport/StaticItemClient.ts`, les items servis proviennent d'un instantané figé : ajouter l'import `READ_ONLY_PERMISSIONS` depuis `../auth/permissions` et le poser sur tout `Item` que ce client fabrique. Un export statique n'écrit jamais.

Dans `shell/src/test/msw/handlers.ts`, ligne 16, après `isPublished: false,` :

```ts
    permissions: { read: true, write: true, delete: true, share: true },
```

(le mock joue le propriétaire — c'est ce que supposent les tests existants qui cliquent les actions)

- [ ] **Step 5: Compiler et lancer toute la suite**

```bash
cd /home/lenen/projets/geostudio/shell
npm run build
npm run test
```

Attendu : `tsc --noEmit` ne signale plus aucun `Item` incomplet, et les 1 463 tests passent. **Si `tsc` signale un emplacement que ce plan n'a pas listé, c'est le plan qui a tort** : le corriger sur place, en consignant lequel.

- [ ] **Step 6: Lancer les tests des nouveaux modules**

```bash
npm run test -- src/auth
```

Attendu : les trois fichiers passent.

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/auth/ shell/src/api/types.ts shell/src/api/itemClient.ts \
        shell/src/staticExport/StaticItemClient.ts shell/src/test/msw/handlers.ts
git commit -m "feat(shell): Gate, hasPermission et Locked — la porte unique des droits"
```

---

## Task 8: `capabilities.ts` — l'état des neuf domaines

**Files:**
- Create: `shell/src/auth/capabilities.ts`, `shell/src/auth/capabilities.test.ts`

**Interfaces:**
- Consumes: `MeCapabilities` de `GET /me` (Task 6)
- Produces:
  ```ts
  export type InstanceCapabilities = {
    readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean;
    appExportEnabled: boolean; tileset3dEnabled: boolean;
    terrain3dEnabled: boolean; copilotEnabled: boolean;
  };
  export type Profile = { isAdmin: boolean; isAnalyst: boolean; capabilities: InstanceCapabilities };
  export type DomainId = "catalog" | "maps" | "data" | "apps" | "automation" | "analytics" | "tasks" | "admin" | "settings";
  export type DomainState = "visible" | "locked" | "hidden";
  export type DomainDef = { id: DomainId; labelKey: MessageKey; requiresRole?: "admin"; requiresCapability?: keyof InstanceCapabilities };
  export const DOMAINS: readonly DomainDef[];
  export function domainState(domain: DomainDef, profile: Profile): DomainState;
  export function navigableDomains(profile: Profile): { domain: DomainDef; state: Exclude<DomainState, "hidden"> }[];
  ```
  SP-30 s'en sert pour la barre de domaines, la palette ⌘K et les onglets du volet gauche.

**La règle encodée (spec §6.2) :** un **rôle** manquant *masque*, une **capacité** coupée *verrouille*. Un rôle est une information sur la personne ; une capacité est une information sur le déploiement, qu'un administrateur doit pouvoir comprendre.

**Limite connue, à consigner et non à contourner :** la matrice de la spec §6.7 décrit un profil « Lecteur » qui ne voit que deux domaines. Ce profil **n'existe pas dans le modèle de données** : il n'y a que `isAdmin` et `isAnalyst`, et « lecteur » n'est que l'absence d'objets où l'on a le droit d'écrire. `capabilities.ts` ne peut donc pas le dériver. La décision — masquer un domaine dont le contenu serait vide pour cet utilisateur — appartient à SP-30, qui aura les compteurs sous la main. Ne pas inventer ici un troisième rôle.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/auth/capabilities.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  DOMAINS,
  domainState,
  navigableDomains,
  type InstanceCapabilities,
  type Profile,
} from "./capabilities";

const ALL_ON: InstanceCapabilities = {
  readOnly: false,
  etlEnabled: true,
  exportEnabled: true,
  appExportEnabled: true,
  tileset3dEnabled: true,
  terrain3dEnabled: true,
  copilotEnabled: true,
};

const admin: Profile = { isAdmin: true, isAnalyst: true, capabilities: ALL_ON };
const creator: Profile = { isAdmin: false, isAnalyst: false, capabilities: ALL_ON };

function stateOf(id: string, profile: Profile) {
  const domain = DOMAINS.find((d) => d.id === id);
  if (!domain) throw new Error(`domaine inconnu dans le test : ${id}`);
  return domainState(domain, profile);
}

describe("domainState", () => {
  it("déclare les neuf domaines de la spec", () => {
    expect(DOMAINS.map((d) => d.id)).toEqual([
      "catalog",
      "maps",
      "data",
      "apps",
      "automation",
      "analytics",
      "tasks",
      "admin",
      "settings",
    ]);
  });

  it("masque un domaine dont le rôle manque", () => {
    expect(stateOf("admin", creator)).toBe("hidden");
    expect(stateOf("admin", admin)).toBe("visible");
  });

  it("verrouille — sans masquer — un domaine dont la capacité est coupée", () => {
    const etlOff: Profile = {
      ...creator,
      capabilities: { ...ALL_ON, etlEnabled: false },
    };
    expect(stateOf("automation", etlOff)).toBe("locked");
    expect(stateOf("automation", creator)).toBe("visible");
  });

  it("le rôle l'emporte sur la capacité : un domaine masqué le reste", () => {
    // Sinon un non-admin apprendrait l'existence d'un domaine par son verrou.
    const both: Profile = {
      isAdmin: false,
      isAnalyst: false,
      capabilities: { ...ALL_ON, etlEnabled: false },
    };
    expect(stateOf("admin", both)).toBe("hidden");
  });

  it("le mode démo ne masque ni ne verrouille aucun domaine", () => {
    // Il retire l'écriture, pas la navigation (spec §6.7).
    const demo: Profile = { ...creator, capabilities: { ...ALL_ON, readOnly: true } };
    for (const domain of DOMAINS) {
      expect(domainState(domain, demo)).toBe(domainState(domain, creator));
    }
  });
});

describe("navigableDomains", () => {
  it("ne rend que le visible et le verrouillé, dans l'ordre déclaré", () => {
    const etlOff: Profile = { ...creator, capabilities: { ...ALL_ON, etlEnabled: false } };
    const rendered = navigableDomains(etlOff);
    expect(rendered.map((r) => r.id ?? r.domain.id)).not.toContain("admin");
    expect(rendered.find((r) => r.domain.id === "automation")?.state).toBe("locked");
    expect(rendered.map((r) => r.domain.id)).toEqual([
      "catalog",
      "maps",
      "data",
      "apps",
      "automation",
      "analytics",
      "tasks",
      "settings",
    ]);
  });
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test -- src/auth/capabilities
```

Attendu : module `./capabilities` introuvable.

- [ ] **Step 3: Écrire le module**

Créer `shell/src/auth/capabilities.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
//
// L'état des neuf domaines du produit, dérivé d'une source unique : le profil
// servi par `GET /me` (rôles + capacités du déploiement).
//
// Doctrine (spec §6.2) : un rôle manquant MASQUE, une capacité coupée
// VERROUILLE. Un rôle est une information sur la personne ; une capacité est
// une information sur le déploiement, qu'un administrateur doit pouvoir
// comprendre.
//
// La barre de domaines, la palette ⌘K et les onglets du volet gauche se
// calculent tous d'ici : retirer un rôle fait disparaître le domaine ET ses
// commandes, sans code supplémentaire.

import type { MessageKey } from "../i18n";

export type InstanceCapabilities = {
  readOnly: boolean;
  etlEnabled: boolean;
  exportEnabled: boolean;
  appExportEnabled: boolean;
  tileset3dEnabled: boolean;
  terrain3dEnabled: boolean;
  copilotEnabled: boolean;
};

export type Profile = {
  isAdmin: boolean;
  isAnalyst: boolean;
  capabilities: InstanceCapabilities;
};

export type DomainId =
  | "catalog"
  | "maps"
  | "data"
  | "apps"
  | "automation"
  | "analytics"
  | "tasks"
  | "admin"
  | "settings";

export type DomainState = "visible" | "locked" | "hidden";

export type DomainDef = {
  id: DomainId;
  labelKey: MessageKey;
  /** Absent = ouvert à tous. Présent et non satisfait = domaine MASQUÉ. */
  requiresRole?: "admin";
  /** Absent = pas de dépendance. Présent et coupé = domaine VERROUILLÉ. */
  requiresCapability?: keyof InstanceCapabilities;
};

// L'ordre de ce tableau est l'ordre d'affichage de la barre de domaines.
export const DOMAINS: readonly DomainDef[] = [
  { id: "catalog", labelKey: "domain.catalog" },
  { id: "maps", labelKey: "domain.maps" },
  { id: "data", labelKey: "domain.data" },
  { id: "apps", labelKey: "domain.apps" },
  { id: "automation", labelKey: "domain.automation", requiresCapability: "etlEnabled" },
  { id: "analytics", labelKey: "domain.analytics" },
  { id: "tasks", labelKey: "domain.tasks" },
  { id: "admin", labelKey: "domain.admin", requiresRole: "admin" },
  { id: "settings", labelKey: "domain.settings" },
] as const;

export function domainState(domain: DomainDef, profile: Profile): DomainState {
  // Le rôle est évalué EN PREMIER : sinon un non-admin apprendrait
  // l'existence d'un domaine par le verrou qu'on lui montrerait.
  if (domain.requiresRole === "admin" && !profile.isAdmin) return "hidden";
  if (domain.requiresCapability && !profile.capabilities[domain.requiresCapability]) {
    return "locked";
  }
  return "visible";
}

export function navigableDomains(
  profile: Profile,
): { domain: DomainDef; state: Exclude<DomainState, "hidden"> }[] {
  const out: { domain: DomainDef; state: Exclude<DomainState, "hidden"> }[] = [];
  for (const domain of DOMAINS) {
    const state = domainState(domain, profile);
    if (state !== "hidden") out.push({ domain, state });
  }
  return out;
}
```

Ce module importe `MessageKey` de `../i18n`, écrit en Task 9. **Exécuter Task 9 avant celle-ci**, ou les deux dans la même passe.

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test -- src/auth
npm run build
```

Attendu : tout passe, `tsc --noEmit` propre.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/auth/capabilities.ts shell/src/auth/capabilities.test.ts
git commit -m "feat(shell): état des neuf domaines dérivé du profil"
```

---

## Task 9: La couche d'internationalisation

**Files:**
- Create: `shell/src/i18n/catalog.fr.ts`, `shell/src/i18n/index.ts`, `shell/src/i18n/index.test.ts`

**Interfaces:**
- Consumes: rien
- Produces:
  ```ts
  export type MessageKey = keyof typeof fr;
  export function t(key: MessageKey, params?: Record<string, string | number>): string;
  ```
  Consommé par `capabilities.ts` (Task 8) et `ItemActions.tsx` (Task 10).

**Périmètre (spec §8, arbitrage A12) :** extraire les libellés, **ne livrer que le français**. SP-29a livre la couche et la prouve sur les libellés que Task 10 touche déjà. La conversion de tous les écrans appartient à SP-30 — c'est le moment où on les réécrit de toute façon.

**Pourquoi une couche maison plutôt qu'une bibliothèque :** le critère est le poids ajouté au bundle et à l'export autoporté (SP-18c), pas le confort. Une seule langue, pas de pluriel, pas de format de date à localiser pour l'instant : trente lignes suffisent, et les clés sont typées, donc une clé inconnue est une erreur de compilation. Si SP-30 fait apparaître un besoin de pluriels ou de langues multiples, le remplacement est local à ces trois fichiers.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/i18n/index.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { t } from "./index";
import { fr } from "./catalog.fr";

describe("t", () => {
  it("rend le message du catalogue", () => {
    expect(t("actions.edit")).toBe("Modifier");
  });

  it("interpole les paramètres nommés", () => {
    expect(t("actions.deleteMessage", { title: "Réseau d'eau potable" })).toBe(
      "Supprimer « Réseau d'eau potable » ? Cette action est irréversible.",
    );
  });

  it("laisse le gabarit en place quand un paramètre manque", () => {
    // Visible plutôt que silencieux : un « {title} » à l'écran se remarque,
    // une chaîne vide non.
    expect(t("actions.deleteMessage", {})).toContain("{title}");
  });

  it("accepte un nombre comme paramètre", () => {
    expect(t("catalog.count", { n: 68 })).toBe("68 éléments");
  });

  it("rejette une clé inconnue à la compilation", () => {
    // @ts-expect-error clé absente du catalogue
    expect(() => t("cle.inexistante")).toBeDefined();
  });
});

describe("catalogue français", () => {
  it("n'a aucune valeur vide", () => {
    for (const [key, value] of Object.entries(fr)) {
      expect(value.trim(), `message vide pour ${key}`).not.toBe("");
    }
  });

  it("nomme ses clés en <domaine>.<intention>", () => {
    for (const key of Object.keys(fr)) {
      expect(key, `clé mal formée : ${key}`).toMatch(/^[a-z][a-zA-Z0-9]*\.[a-zA-Z0-9]+$/);
    }
  });
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test -- src/i18n
```

Attendu : modules `./index` et `./catalog.fr` introuvables.

- [ ] **Step 3: Écrire le catalogue**

Créer `shell/src/i18n/catalog.fr.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
//
// Le catalogue de messages français. Seule langue livrée (arbitrage A12) : la
// couche existe pour que SP-30 extraie les libellés au moment où il réécrit
// les écrans, pas pour livrer une seconde langue aujourd'hui.
//
// Convention de clé : <domaine>.<intention>, en camelCase. Les paramètres
// s'écrivent {nom}.

export const fr = {
  // Actions sur un item
  "actions.menu": "Actions",
  "actions.edit": "Modifier",
  "actions.publish": "Publier",
  "actions.unpublish": "Dépublier",
  "actions.thumbnail": "Miniature",
  "actions.share": "Partager",
  "actions.delete": "Supprimer",
  "actions.scheduleReport": "Programmer un rapport",
  "actions.editTitle": "Modifier l'élément",
  "actions.thumbnailTitle": "Miniature",
  "actions.deleteTitle": "Supprimer l'élément",
  "actions.deleteMessage": "Supprimer « {title} » ? Cette action est irréversible.",
  "actions.saveFailed": "Échec de l'enregistrement.",
  "actions.uploadFailed": "Échec de l'envoi.",
  "actions.deleteFailed": "Échec de la suppression.",
  "actions.publishFailed": "Échec de la publication.",

  // Traitement « verrouillé et expliqué » — la raison ET le recours
  "locked.needWrite": "Modification réservée aux éditeurs de cet élément.",
  "locked.needShare": "Partage réservé au propriétaire et aux éditeurs.",
  "locked.needDelete": "Suppression réservée au propriétaire et aux éditeurs.",
  "locked.capabilityOff": "Désactivé sur cette instance — voir un administrateur.",

  // Domaines
  "domain.catalog": "Catalogue",
  "domain.maps": "Cartes",
  "domain.data": "Données",
  "domain.apps": "Apps & sites",
  "domain.automation": "Automatisation",
  "domain.analytics": "Analytique",
  "domain.tasks": "Tâches",
  "domain.admin": "Administration",
  "domain.settings": "Paramètres",

  // Catalogue
  "catalog.count": "{n} éléments",
} as const;
```

- [ ] **Step 4: Écrire `t()`**

Créer `shell/src/i18n/index.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { fr } from "./catalog.fr";

export type MessageKey = keyof typeof fr;

/**
 * Rend un message du catalogue, en interpolant les `{paramètres}` nommés.
 *
 * Une clé inconnue est une erreur de compilation, pas une erreur d'exécution :
 * `MessageKey` est dérivée du catalogue lui-même. Un paramètre manquant laisse
 * son gabarit visible — un « {title} » à l'écran se remarque, une chaîne vide
 * non.
 */
export function t(key: MessageKey, params?: Record<string, string | number>): string {
  const template: string = fr[key];
  if (params === undefined) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined ? match : String(value);
  });
}
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test -- src/i18n
npm run build
```

Attendu : tout passe.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/i18n/
git commit -m "feat(shell): couche d'internationalisation, catalogue français"
```

---

## Task 10: `ItemActions` — supprimer les commandes qui produisent un 403

**Files:**
- Modify: `shell/src/shell/ItemActions.tsx:65-120`
- Modify: `shell/src/shell/ItemActions.test.tsx`
- Modify: `shell/e2e/mocks.ts` — les cinq items littéraux (lignes 5, 16, 27, 149, 285)
- Create: `shell/e2e/item-permissions.spec.ts`

**Interfaces:**
- Consumes: `Gate`, `Locked` (Task 7), `t()` (Task 9), `Item.permissions` (Task 7)
- Produces: rien pour les tâches suivantes

**C'est l'unique exception visible de SP-29a** (spec §10.1.7). Justification : aujourd'hui `ItemActions` propose Modifier, Publier, Miniature, Partager et Supprimer sur **chaque** item du catalogue, y compris ceux qu'on ne peut que lire — et c'est l'API qui renvoie 403 après le clic. Ce n'est pas un restylage, c'est la correction d'un défaut. Si le relecteur veut la reporter à SP-30, elle s'annule sans rien casser d'autre.

**Correspondance action → droit, vérifiée contre le cœur** (ne pas l'inventer, elle est lisible dans `core/app/items/routes.py`) :

| Commande | Droit exigé | Contrôle du cœur |
|---|---|---|
| Modifier (métadonnées) | `write` | `routes.py:76` — `can(write)` sur `PATCH /items/{id}` |
| Publier / Dépublier | `write` | même route, `isPublished` est un champ du `PATCH` |
| Miniature | `write` | `routes.py:127` — `can(write)` avant l'envoi |
| Partager | `share` | `app/sharing/routes.py` |
| Supprimer | `delete` | `DELETE /items/{id}` |
| Programmer un rapport | *aucun* | crée un nouvel item ; ne touche pas celui-ci |

**Traitement retenu par commande** (doctrine §6.2) : Modifier, Publier et Miniature sont **verrouillées et expliquées** — l'utilisateur peut légitimement se demander pourquoi et peut obtenir le droit. Partager et Supprimer sont **absentes** — les proposer verrouillées sur chaque ligne d'un catalogue partagé encombrerait sans rien apprendre.

> La maquette montrait « Publier est réservé au propriétaire ». Le cœur, lui, l'autorise à tout éditeur (`can(write)`). **On suit le cœur** : masquer une commande qui réussirait est le symétrique du défaut qu'on corrige. Si la restriction au propriétaire est voulue, c'est un changement du cœur, pas de l'interface — à porter en SP-32.

- [ ] **Step 1: Écrire le test unitaire**

Ajouter à `shell/src/shell/ItemActions.test.tsx` (garder les tests existants tels quels) :

```tsx
const viewerItem: Item = {
  pk: "42",
  resourceType: "map",
  title: "Réseau d'eau potable",
  abstract: "",
  owner: "tanguy",
  thumbnailUrl: null,
  date: "2026-08-29T00:00:00Z",
  configId: null,
  isPublished: false,
  permissions: { read: true, write: false, delete: false, share: false },
};

const editorItem: Item = {
  ...viewerItem,
  pk: "43",
  permissions: { read: true, write: true, delete: false, share: false },
};

describe("ItemActions et les droits", () => {
  it("un lecteur ne voit ni Partager ni Supprimer", async () => {
    render(<ItemActions item={viewerItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    expect(screen.queryByRole("button", { name: "Partager" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Supprimer" })).not.toBeInTheDocument();
  });

  it("un lecteur voit Modifier verrouillée, avec sa raison", async () => {
    render(<ItemActions item={viewerItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    const edit = screen.getByRole("button", { name: "Modifier" });
    expect(edit).toBeDisabled();
    expect(
      screen.getByText("Modification réservée aux éditeurs de cet élément."),
    ).toBeVisible();
  });

  it("un éditeur peut modifier et publier, mais pas supprimer ni partager", async () => {
    render(<ItemActions item={editorItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    expect(screen.getByRole("button", { name: "Modifier" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Publier" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Supprimer" })).not.toBeInTheDocument();
  });

  it("le propriétaire garde les cinq commandes", async () => {
    const owned: Item = {
      ...viewerItem,
      pk: "44",
      permissions: { read: true, write: true, delete: true, share: true },
    };
    render(<ItemActions item={owned} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    for (const name of ["Modifier", "Publier", "Miniature", "Partager", "Supprimer"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
  });
});
```

Reprendre le `wrapper` (QueryClientProvider + MemoryRouter + ItemClientProvider) déjà défini en tête du fichier de test existant ; ne pas en créer un second.

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test -- src/shell/ItemActions
```

Attendu : les trois premiers nouveaux tests échouent (les commandes sont toutes rendues et actives aujourd'hui) ; le quatrième passe déjà.

- [ ] **Step 3: Câbler `Gate` et `t()`**

Dans `shell/src/shell/ItemActions.tsx`, ajouter aux imports :

```tsx
import { Gate } from "../auth/Gate";
import { Locked } from "../auth/Locked";
import { t } from "../i18n";
```

Remplacer le bloc `{panel === "menu" && ( … )}` (lignes 71-114) par :

```tsx
      {panel === "menu" && (
        <div className="absolute z-20 mt-8 flex flex-col rounded-md border border-slate-200 bg-white text-sm shadow">
          <Gate
            on={item}
            can="write"
            fallback={
              <Locked reason={t("locked.needWrite")}>
                <button className="px-3 py-1 text-left">{t("actions.edit")}</button>
              </Locked>
            }
          >
            <button
              className="px-3 py-1 text-left hover:bg-slate-100"
              onClick={() => setPanel("edit")}
            >
              {t("actions.edit")}
            </button>
          </Gate>

          {item.resourceType === "bookmark" && exportEnabled && (
            <button
              className="px-3 py-1 text-left hover:bg-slate-100"
              onClick={() => {
                setPanel(null);
                navigate("/reports/new", { state: { bookmarkItemId: item.pk } });
              }}
            >
              {t("actions.scheduleReport")}
            </button>
          )}

          <Gate
            on={item}
            can="write"
            fallback={
              <Locked reason={t("locked.needWrite")}>
                <button className="px-3 py-1 text-left">
                  {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
                </button>
              </Locked>
            }
          >
            <button
              className="px-3 py-1 text-left hover:bg-slate-100"
              onClick={() => void togglePublish()}
            >
              {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
            </button>
          </Gate>

          <Gate
            on={item}
            can="write"
            fallback={
              <Locked reason={t("locked.needWrite")}>
                <button className="px-3 py-1 text-left">{t("actions.thumbnail")}</button>
              </Locked>
            }
          >
            <button
              className="px-3 py-1 text-left hover:bg-slate-100"
              onClick={() => setPanel("thumbnail")}
            >
              {t("actions.thumbnail")}
            </button>
          </Gate>

          {/* Partager et Supprimer : traitement « absent », pas « verrouillé ».
              Les montrer grisées sur chaque ligne d'un catalogue partagé
              encombrerait sans rien apprendre (doctrine §6.2). */}
          <Gate on={item} can="share">
            <button
              className="px-3 py-1 text-left hover:bg-slate-100"
              onClick={() => setPanel("share")}
            >
              {t("actions.share")}
            </button>
          </Gate>

          <Gate on={item} can="delete">
            <button
              className="px-3 py-1 text-left text-red-600 hover:bg-slate-100"
              onClick={() => setPanel("delete")}
            >
              {t("actions.delete")}
            </button>
          </Gate>
        </div>
      )}
```

Et remplacer les six chaînes littérales restantes du fichier par leur clé : `"Actions"` → `t("actions.menu")` (ligne 67, l'`aria-label`), `"Modifier l'élément"` → `t("actions.editTitle")`, `"Miniature"` (titre du `Dialog`) → `t("actions.thumbnailTitle")`, `"Supprimer l'élément"` → `t("actions.deleteTitle")`, le gabarit du message de suppression → `t("actions.deleteMessage", { title: item.title })`, `confirmLabel="Supprimer"` → `t("actions.delete")`, et les quatre messages d'erreur → `t("actions.saveFailed")`, `t("actions.uploadFailed")`, `t("actions.deleteFailed")`, `t("actions.publishFailed")`.

- [ ] **Step 4: Lancer les tests unitaires**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test -- src/shell/ItemActions
npm run test
```

Attendu : les nouveaux tests passent et **aucun test existant ne casse** — le mock MSW joue le propriétaire (Task 7, Step 4), donc les scénarios existants gardent leurs cinq commandes.

- [ ] **Step 5: Mettre les mocks E2E à niveau**

Dans `shell/e2e/mocks.ts`, ajouter à chacun des cinq items littéraux (après leur ligne `isPublished:`) :

```ts
    permissions: { read: true, write: true, delete: true, share: true },
```

- [ ] **Step 6: Écrire l'E2E de la lecture seule**

Créer `shell/e2e/item-permissions.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un item en lecture seule ne propose ni suppression ni partage", async ({ page }) => {
  await mockCore(page);
  // Un seul item, en lecture seule : on surcharge la route APRÈS mockCore,
  // la dernière route enregistrée l'emporte chez Playwright.
  await page.route("**/items*", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            pk: "77",
            resourceType: "map",
            title: "Partagée en lecture",
            abstract: "",
            owner: "tanguy",
            thumbnailUrl: null,
            date: "2026-08-29T00:00:00Z",
            configId: null,
            isPublished: false,
            keywords: [],
            permissions: { read: true, write: false, delete: false, share: false },
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      },
    });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Partagée en lecture" })).toBeVisible();
  await page.getByRole("button", { name: "Actions" }).click();

  await expect(page.getByRole("button", { name: /^supprimer$/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^partager$/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Modifier" })).toBeDisabled();
  await expect(
    page.getByText("Modification réservée aux éditeurs de cet élément."),
  ).toBeVisible();
});
```

- [ ] **Step 7: Lancer la suite E2E complète**

Pas seulement le nouveau fichier : plusieurs régressions cross-tâches de ce dépôt n'ont été trouvées qu'à la première exécution complète (piège n°6).

```bash
cd /home/lenen/projets/geostudio/shell
npm run e2e
```

Attendu : **113 passed / 4 skipped / 0 failed** (112 avant, plus le nouveau fichier). Si un spec existant échoue parce qu'une commande a disparu, c'est que son item de mock n'a pas reçu ses permissions au Step 5 — corriger le mock, pas le composant.

- [ ] **Step 8: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/shell/ItemActions.tsx shell/src/shell/ItemActions.test.tsx \
        shell/e2e/mocks.ts shell/e2e/item-permissions.spec.ts
git commit -m "fix(shell): ItemActions ne propose plus d'action qui produira un 403"
```

---

## Task 11: `tokens.css` — la palette, en deux ambiances

**Files:**
- Create: `shell/src/styles/tokens.css`, `shell/src/styles/tokens.test.ts`
- Modify: `shell/src/index.css`
- Modify: `shell/package.json` (trois paquets de fontes)

**Interfaces:**
- Consumes: le relevé du Step 5 de Task 1 (forme de `@theme` réellement supportée)
- Produces: les utilitaires Tailwind `bg-canvas`, `text-ink`, `border-rule`, `bg-accent`… consommés par SP-29b et SP-30. **Aucun écran ne les utilise dans SP-29a.**

**Le contrat (spec §5.1) :** les six couleurs du `Theme` des apps — `primary`, `background`, `surface`, `text`, `muted`, `border` — sont **les mêmes noms** que les tokens du studio, ce qui rend la marque blanche possible sans second système. Le studio en a davantage (encre à trois niveaux, filets, sémantiques, tokens de carte), dérivés ou fixes. `shell/src/builder/theme.ts` n'est **pas** touché : seul le contrat de nommage est partagé, pas le code.

- [ ] **Step 1: Vérifier les paquets de fontes contre le registre**

Trois rôles typographiques (spec §5.3) : interface, données, textes longs. Servies localement — le shell est réempaqueté en conteneur autoporté (SP-18c) et rendu hors ligne par le worker d'export (SP-17a), un CDN tiers y serait inaccessible.

```bash
cd /home/lenen/projets/geostudio/shell
npm view @fontsource-variable/archivo version license
npm view @fontsource/ibm-plex-mono version license
npm view @fontsource-variable/source-serif-4 version license
```

Attendu : trois versions et trois licences OFL-1.1. **Si un nom de paquet n'existe pas, le plan a tort** : chercher le nom réel (`npm search fontsource archivo`), l'utiliser, et consigner la correction. Ne pas se rabattre sur un `<link>` vers Google Fonts : cela casserait l'export autoporté.

```bash
npm i @fontsource-variable/archivo @fontsource/ibm-plex-mono @fontsource-variable/source-serif-4
```

- [ ] **Step 2: Écrire le test de contrat**

Créer `shell/src/styles/tokens.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
/**
 * Contrat des tokens : tout token défini dans une ambiance doit l'être dans
 * les trois blocs.
 *
 * Le bug classique d'une page à deux thèmes est un token défini uniquement
 * dans le bloc sombre : la page rend alors du texte d'une ambiance sur le fond
 * de l'autre. Ce test l'interdit mécaniquement, plutôt que de compter sur la
 * relecture.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(
  fileURLToPath(new URL("./tokens.css", import.meta.url)),
  "utf8",
);

function block(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `bloc introuvable : ${selector}`).toBeGreaterThan(-1);
  const open = css.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(open + 1, i);
    }
  }
  throw new Error(`bloc non fermé : ${selector}`);
}

function tokensOf(source: string): Set<string> {
  return new Set([...source.matchAll(/--gs-([a-z0-9-]+)\s*:/g)].map((m) => m[1]));
}

const LIGHT = tokensOf(block(":root {"));
const SYSTEM_DARK = tokensOf(block(':root:not([data-theme="light"])'));
const EXPLICIT_DARK = tokensOf(block(':root[data-theme="dark"]'));

describe("contrat des tokens", () => {
  it("définit une palette claire non vide", () => {
    expect(LIGHT.size).toBeGreaterThan(20);
  });

  it("redéfinit exactement les mêmes tokens dans l'ambiance sombre système", () => {
    expect([...SYSTEM_DARK].sort()).toEqual([...LIGHT].sort());
  });

  it("redéfinit exactement les mêmes tokens dans l'ambiance sombre explicite", () => {
    expect([...EXPLICIT_DARK].sort()).toEqual([...LIGHT].sort());
  });

  it("porte les six noms du contrat partagé avec le Theme des apps", () => {
    // spec §5.1 — c'est ce qui rend la marque blanche possible sans second système
    for (const name of ["primary", "background", "surface", "text", "muted", "border"]) {
      expect(LIGHT.has(name), `token du contrat partagé absent : --gs-${name}`).toBe(true);
    }
  });

  it("expose les tokens de carte, qui ne peuvent pas être dérivés", () => {
    for (const name of ["map-land", "map-alt", "map-water", "map-road"]) {
      expect(LIGHT.has(name), `token de carte absent : --gs-${name}`).toBe(true);
    }
  });

  it("ne déclare aucune couleur en dur hors des trois blocs d'ambiance", () => {
    const outside = css
      .replace(block(":root {"), "")
      .replace(block(':root:not([data-theme="light"])'), "")
      .replace(block(':root[data-theme="dark"]'), "");
    expect(outside).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
```

- [ ] **Step 3: Lancer le test, vérifier qu'il échoue**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test -- src/styles
```

Attendu : `ENOENT` sur `tokens.css`.

- [ ] **Step 4: Écrire `tokens.css`**

Créer `shell/src/styles/tokens.css` :

```css
/* SPDX-License-Identifier: Apache-2.0
 *
 * Les tokens de GeoStudio. Première feuille de style réelle du produit :
 * jusqu'ici `index.css` contenait une ligne, et la palette de fait était le
 * gris d'usine de Tailwind.
 *
 * Trois blocs d'ambiance, et l'ordre compte :
 *   1. `:root`                              — la palette claire, complète
 *   2. `prefers-color-scheme: dark` gardé par `:not([data-theme="light"])`
 *      — pour que le choix explicite « clair » l'emporte sur un OS sombre
 *   3. `:root[data-theme="dark"]`           — pour que le choix explicite
 *      « sombre » l'emporte dans l'autre sens
 *
 * `tokens.test.ts` interdit mécaniquement qu'un token n'existe que dans l'un
 * des trois : c'est le bug classique des pages à deux thèmes.
 *
 * Les six noms `primary`, `background`, `surface`, `text`, `muted`, `border`
 * sont exactement ceux du `Theme` des apps (`src/builder/theme.ts`). Ce
 * contrat partagé est ce qui rendra la marque blanche possible sans second
 * système — mais les deux restent deux instances : le thème d'une app ne
 * repeint pas le studio de son auteur.
 */

:root {
  /* Contrat partagé avec le Theme des apps */
  --gs-primary: #0b6e77;
  --gs-background: #eff2f1;
  --gs-surface: #fbfcfb;
  --gs-text: #0e1a20;
  --gs-muted: #6e8087;
  --gs-border: #cfd8d6;

  /* Surfaces propres au studio */
  --gs-raised: #ffffff;
  --gs-sunken: #e4e9e7;

  /* Encre à trois niveaux */
  --gs-ink: #0e1a20;
  --gs-ink-2: #3b4c54;
  --gs-ink-3: #6e8087;

  /* Filets */
  --gs-rule: #cfd8d6;
  --gs-rule-2: #e2e8e6;

  /* Accent — un seul, emprunté à l'hydrographie des planches topographiques */
  --gs-accent: #0b6e77;
  --gs-accent-soft: #d9ebec;
  --gs-accent-ink: #07545b;

  /* Réservé à ce qui vient du copilote : l'utilisateur voit d'un coup d'œil
     ce qui a été fait par l'IA */
  --gs-ai: #6a4c93;
  --gs-ai-soft: #eae3f4;

  /* Sémantiques — distinctes de l'accent, jamais décoratives */
  --gs-ok: #2a6a50;
  --gs-ok-soft: #ddeee5;
  --gs-warn: #8e6410;
  --gs-warn-soft: #f7ebd1;
  --gs-danger: #9a2c45;
  --gs-danger-soft: #f7e1e6;

  /* Carte — non dérivables des neutres : un fond de carte clair sur un studio
     sombre est illisible */
  --gs-map-land: #e8efea;
  --gs-map-alt: #dce7e3;
  --gs-map-water: #bbd8dc;
  --gs-map-road: #ffffff;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --gs-primary: #4fb3bc;
    --gs-background: #0a1316;
    --gs-surface: #101a1e;
    --gs-text: #e7eeec;
    --gs-muted: #7c8f94;
    --gs-border: #243339;

    --gs-raised: #182629;
    --gs-sunken: #16232a;

    --gs-ink: #e7eeec;
    --gs-ink-2: #afc0c2;
    --gs-ink-3: #7c8f94;

    --gs-rule: #243339;
    --gs-rule-2: #1a272c;

    --gs-accent: #4fb3bc;
    --gs-accent-soft: #0f3238;
    --gs-accent-ink: #7fd2d9;

    --gs-ai: #ab8fd4;
    --gs-ai-soft: #241a33;

    --gs-ok: #63c295;
    --gs-ok-soft: #11291f;
    --gs-warn: #d9a441;
    --gs-warn-soft: #2c2311;
    --gs-danger: #e58098;
    --gs-danger-soft: #2f161c;

    --gs-map-land: #16242a;
    --gs-map-alt: #1b2c31;
    --gs-map-water: #1d3a42;
    --gs-map-road: #2c4148;
  }
}

:root[data-theme="dark"] {
  --gs-primary: #4fb3bc;
  --gs-background: #0a1316;
  --gs-surface: #101a1e;
  --gs-text: #e7eeec;
  --gs-muted: #7c8f94;
  --gs-border: #243339;

  --gs-raised: #182629;
  --gs-sunken: #16232a;

  --gs-ink: #e7eeec;
  --gs-ink-2: #afc0c2;
  --gs-ink-3: #7c8f94;

  --gs-rule: #243339;
  --gs-rule-2: #1a272c;

  --gs-accent: #4fb3bc;
  --gs-accent-soft: #0f3238;
  --gs-accent-ink: #7fd2d9;

  --gs-ai: #ab8fd4;
  --gs-ai-soft: #241a33;

  --gs-ok: #63c295;
  --gs-ok-soft: #11291f;
  --gs-warn: #d9a441;
  --gs-warn-soft: #2c2311;
  --gs-danger: #e58098;
  --gs-danger-soft: #2f161c;

  --gs-map-land: #16242a;
  --gs-map-alt: #1b2c31;
  --gs-map-water: #1d3a42;
  --gs-map-road: #2c4148;
}

/* Exposition à Tailwind v4. `inline` est ce qui rend les tokens commutables :
 * sans lui, Tailwind fige la valeur au moment de la compilation et le bloc
 * sombre n'a plus d'effet.
 *
 * ATTENTION : la forme exacte a été relevée au Step 5 de Task 1, contre la
 * version de Tailwind réellement installée. Si le relevé dit autre chose,
 * c'est le relevé qui fait foi — corriger ici et consigner. */
@theme inline {
  --color-primary: var(--gs-primary);
  --color-background: var(--gs-background);
  --color-surface: var(--gs-surface);
  --color-raised: var(--gs-raised);
  --color-sunken: var(--gs-sunken);
  --color-ink: var(--gs-ink);
  --color-ink-2: var(--gs-ink-2);
  --color-ink-3: var(--gs-ink-3);
  --color-rule: var(--gs-rule);
  --color-rule-2: var(--gs-rule-2);
  --color-accent: var(--gs-accent);
  --color-accent-soft: var(--gs-accent-soft);
  --color-accent-ink: var(--gs-accent-ink);
  --color-ai: var(--gs-ai);
  --color-ai-soft: var(--gs-ai-soft);
  --color-ok: var(--gs-ok);
  --color-ok-soft: var(--gs-ok-soft);
  --color-warn: var(--gs-warn);
  --color-warn-soft: var(--gs-warn-soft);
  --color-danger: var(--gs-danger);
  --color-danger-soft: var(--gs-danger-soft);
  --color-map-land: var(--gs-map-land);
  --color-map-alt: var(--gs-map-alt);
  --color-map-water: var(--gs-map-water);
  --color-map-road: var(--gs-map-road);

  --font-ui: "Archivo Variable", "Helvetica Neue", Arial, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", monospace;
  --font-prose: "Source Serif 4 Variable", Georgia, "Times New Roman", serif;

  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-lg: 8px;
}
```

- [ ] **Step 5: Câbler dans `index.css`**

Remplacer le contenu de `shell/src/index.css` par :

```css
/* SPDX-License-Identifier: Apache-2.0 */
@import "tailwindcss";

/* Fontes empaquetées avec l'application : le shell est réempaqueté en
 * conteneur autoporté (SP-18c) et rendu hors ligne par le worker d'export
 * (SP-17a). Un CDN tiers y serait inaccessible. */
@import "@fontsource-variable/archivo";
@import "@fontsource/ibm-plex-mono/400.css";
@import "@fontsource/ibm-plex-mono/500.css";
@import "@fontsource-variable/source-serif-4";

@import "./styles/tokens.css";
```

- [ ] **Step 6: Lancer le test et vérifier que rien ne change à l'écran**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test -- src/styles
npm run build
npm run test
```

Attendu : le contrat passe, la compilation passe, la suite unitaire passe.

**Vérification visuelle explicite** — aucun écran ne consomme encore les tokens, donc aucun rendu ne doit bouger :

```bash
npm run e2e
```

Attendu : **113 passed / 4 skipped / 0 failed**, identique à Task 10. Si un test de rendu bouge, c'est qu'un `@import` de fonte a changé la métrique par défaut du corps de page : le consigner et décider — soit fixer explicitement `font-family` sur `body`, soit reporter les fontes à SP-30.

- [ ] **Step 7: Mesurer le coût des fontes**

```bash
rm -rf dist && npm run build && du -sb dist
```

Comparer au relevé du Step 1 de Task 1. Consigner le delta dans le rapport de tâche : c'est la seule occasion de le voir isolément, avant que SP-29b n'ajoute la bibliothèque de primitives.

- [ ] **Step 8: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/styles/ shell/src/index.css shell/package.json shell/package-lock.json
git commit -m "feat(shell): tokens de design en deux ambiances, fontes empaquetées"
```

---

## Task 12: Vérification finale de la branche

**Files:**
- Modify: `CLAUDE.md` (une ligne dans `### Livré`)

**Interfaces:**
- Consumes: tout ce qui précède
- Produces: la preuve que SP-29a est clos

**Ne pas déléguer cette tâche à la relecture de la tâche précédente.** Les défauts de croisement entre tâches — un garde-fou écrit d'un côté et jamais reporté sur sa jumelle, un chemin de lecture qui ne round-trippe pas un nouveau champ — ne sont visibles qu'à la revue de branche (piège n°4).

- [ ] **Step 1: Suites complètes**

```bash
cd /home/lenen/projets/geostudio/core && uv run pytest
cd ../shell && npm run test && npm run e2e
```

Attendu : cœur **1896 + N passed, 5 skipped, 1 failed** — l'unique échec étant `test_features_rls.py::test_scope_preserves_original_sql_error`, **préexistant**. Shell : suite unitaire verte, E2E **113 / 4 / 0**.

- [ ] **Step 2: Toutes les portes de qualité**

```bash
cd /home/lenen/projets/geostudio/core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run lint-imports
cd ../shell
npm run lint && npm run format:check && npm run build
uvx pre-commit run --all-files
```

Attendu : tout vert. `lint-imports` en particulier : ce plan fait importer `app.sharing` par `app.items`, ce que le contrat autorise déjà — aucune entrée nouvelle ne doit être nécessaire. **Si `lint-imports` échoue, ne pas ajouter d'exception au contrat sans comprendre** : c'est le signe qu'un import est parti dans le mauvais sens.

- [ ] **Step 3: Couverture, mesurée proprement**

```bash
cd /home/lenen/projets/geostudio/core
uv run pytest --cov=app --cov-report=xml
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell
rm -rf dist dist-export
npm run test -- --coverage
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```

Le `rm -rf dist dist-export` n'est pas optionnel : la config vitest de ce dépôt compte ces artefacts gitignorés comme source non couverte, et la mesure est fausse sans lui (piège documenté quatre fois).

Attendu : ≥ 85 côté cœur, ≥ 88 côté shell.

- [ ] **Step 4: Vérifier qu'aucune comparaison de droits ne subsiste hors de la porte**

```bash
cd /home/lenen/projets/geostudio/shell
grep -rn "isAdmin === true\|isAnalyst === true\|isAdmin !== true\|isAnalyst !== true\|owner ===" \
  src --include=*.tsx --include=*.ts | grep -v "\.test\." | grep -v "src/auth/"
```

Attendu : **neuf occurrences dans cinq fichiers** — `SqlLabPage.tsx`, `AdminExtensionsPage.tsx`, `HarvestSourcesAdminPage.tsx`, `CollectionsAdminPage.tsx`, `AppLayout.tsx`. Elles sont **normales à ce stade** : ces écrans ne sont réécrits qu'en SP-30. Ce que ce contrôle interdit, c'est qu'il y en ait **davantage** qu'avant. Les compter et le consigner.

- [ ] **Step 5: Vérifier que la spec OpenAPI est à jour**

```bash
cd /home/lenen/projets/geostudio/core
PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd .. && git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Attendu : **diff vide** — Task 6 les a déjà régénérés. Un diff non vide ici signifie qu'une modification postérieure de modèle a été oubliée : la commiter.

- [ ] **Step 6: Inscrire SP-29a dans CLAUDE.md**

Dans la section `### Livré`, après l'entrée SP-28, ajouter :

```markdown
- **SP-29a** (12 tâches) — fondation de la refonte UI (spec
  `2026-08-29-refonte-ui-triptyque-design.md`, socle triptyque retenu parmi
  quinze directions) : `decide()` extraite de `can()` avec parité prouvée,
  `roles_for_items()` en une requête, **`ItemRead.permissions`** calculé par le
  cœur et lu côté shell par une porte unique (`Gate`/`hasPermission`), état des
  neuf domaines dérivé du profil (`capabilities.ts`), `GET /me` porte les sept
  capacités, couche i18n (français seul, A12), tokens en deux ambiances
  (`styles/tokens.css`) et fontes empaquetées. Aucun écran modifié **sauf**
  `ItemActions`, qui cesse de proposer les actions produisant un 403 (exception
  assumée §10.1.7). E2E 112/4/0 → **113/4/0**. Le kit de primitives est SP-29b,
  planifié à partir du spike de Task 1.
```

- [ ] **Step 7: Commit final**

```bash
cd /home/lenen/projets/geostudio
git add CLAUDE.md
git commit -m "docs(sp29a): clôture — fondation permissions, tokens, i18n"
git log --oneline 2f2717a..HEAD
```

Attendu : onze à douze commits, un sujet chacun.

---

## Self-Review Notes (pour l'auteur du plan, pas une tâche)

**Couverture de la spec §10.1 :**

| Exigence | Tâche |
|---|---|
| `styles/tokens.css`, deux ambiances, `@theme` | Task 11 |
| Fontes servies localement | Task 11, Steps 1 et 5 |
| Kit de composants | **SP-29b** — hors périmètre de ce plan, cf. « Note de méthode » |
| `src/i18n/` + catalogue français | Task 9 |
| `ItemPermissions` sur `ItemRead` | Task 4 |
| Permissions sur les collections | **Non couvert** — voir ci-dessous |
| Capacités sur `GET /me` | Task 6 |
| `roles_for_items()` + `decide()` partagée | Tasks 2 et 3 |
| `auth/{Gate.tsx,capabilities.ts}` + types régénérés | Tasks 7, 8 et 6 Step 5 |
| Exception `ItemActions` | Task 10 |
| Test de parité `decide()`/`can()` | Task 2, Step 1 |
| Anti-N+1 par comptage de requêtes | Task 5 |
| Portes de qualité, couverture, OpenAPI | Task 12 |
| Galerie des primitives (critère de sortie 5) | **SP-29b** — elle rend des primitives qui n'existent pas encore |

**Écart assumé n°1 — les permissions de collection.** La spec §6.3 demande que les collections passent, elles aussi, d'un `canWrite` isolé à un objet de permissions complet. Ce plan livre `roles_for_collections()` (Task 3), qui est la moitié coûteuse du travail, mais ne touche pas `app/collections/routes.py:143`. Raison : aucun consommateur de SP-29a n'en a besoin, et l'écran d'administration des collections est réécrit en SP-30, qui saura exactement quelle forme lui donner. **À reprendre en tête de SP-30.**

**Écart assumé n°2 — le profil « Lecteur ».** La matrice §6.7 le décrit ; le modèle de données ne le connaît pas (il n'y a que `isAdmin` et `isAnalyst`). `capabilities.ts` ne peut donc pas le dériver, et Task 8 le documente en commentaire plutôt que d'inventer un troisième rôle. La décision — masquer un domaine dont le contenu serait vide — appartient à SP-30.

**Écart assumé n°3 — « Publier ».** La maquette montrait cette commande réservée au propriétaire ; le cœur l'autorise à tout éditeur. Task 10 suit le cœur, et le dit. Restreindre est un changement du cœur, à porter en SP-32.

**Dépendances entre tâches, à respecter à l'exécution :**

- Task 2 importe ce que Task 3 écrit → **exécuter Task 3 avant Task 2**, ou les deux ensemble.
- Task 8 importe `MessageKey` de Task 9 → **exécuter Task 9 avant Task 8**.
- Task 10 consomme Tasks 7 et 9.
- Task 5 vérifie l'implémentation de Task 4.
- Tasks 1 et 11 sont indépendantes de tout le reste ; Task 11 consomme le Step 5 de Task 1.

**Cohérence des noms, vérifiée :** `decide()` (Tasks 2, 4) · `roles_for_items` / `roles_for_collections` (Tasks 2, 3, 4) · `ItemPermissions` (Tasks 4, 6, 7) · `PUBLIC_READ_ONLY` côté cœur / `READ_ONLY_PERMISSIONS` côté shell — **noms différents pour deux langages différents, valeurs identiques**, c'est délibéré et testé des deux côtés · `hasPermission` (pas `usePermission` : ce n'est pas un hook) · `MessageKey` (Tasks 8, 9) · `navigableDomains` (Task 8).
