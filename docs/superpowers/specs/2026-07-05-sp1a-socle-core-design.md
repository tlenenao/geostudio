# GeoStudio SP-1a — Socle du cœur (tenants, users, JWT OIDC, audit, frontières)

> Design / spec. Première sous-phase de SP-1 (le plus gros chantier « invisible » de
> la feuille de route : remplacer GeoNode par le cœur). Pose les fondations
> transverses dont SP-1b/c/d dépendent : authentification, multi-tenant (au sens
> schéma — un seul tenant réel en v0), audit, et discipline de modules.
>
> Date : 2026-07-05.
> Statut : design proposé — prêt pour `writing-plans` après relecture.
> Prérequis : renommage `builder-service/` → `core/` (A14, fait le 2026-07-05).

---

## 1. Contexte et périmètre

Le cœur (`core/`) ne fait aujourd'hui qu'une chose : stocker et versionner des
`BuilderConfig` (table `configs`/`config_revisions`), avec un `item_id` opaque qui
référence une ressource **GeoNode** distante (créée via `GeoNodeItemClient`, un
appel HTTP réseau). Il n'y a ni authentification, ni notion d'utilisateur, ni de
tenant, ni d'audit : `POST /configs` accepte n'importe quel `owner: str` non
vérifié.

SP-1a construit le socle que SP-1b (items), SP-1c (partage) et SP-1d (bascule)
vont réutiliser :

- **Authentification JWT OIDC** validée contre les JWKS de Keycloak, avec un
  **mode mock** symétrique à celui du shell (`VITE_AUTH_MODE=mock`), pour que
  tests unitaires, e2e Playwright et CI tournent sans Keycloak.
- **Tables `tenants` et `users`** — provisionnement JIT (just-in-time) de
  l'utilisateur à partir des claims du token, pas d'admin manuel.
- **Table `audit_log`** générique, et son branchement sur les endpoints
  `configs` existants (premiers exemples d'utilisation réelle).
- **`GET /me`** — reflet de l'utilisateur authentifié résolu par le cœur.
- **Lint de frontières de modules** — le cœur va grossir vite (items en 1b,
  sharing en 1c) ; on pose la structure en paquets et l'outillage qui empêche un
  big ball of mud, avant d'avoir plusieurs domaines à démêler après coup.
- **CI OpenAPI → TS** (arbitrage A11, à ouvrir dès SP-1a) — génère les types TS
  du shell depuis le schéma OpenAPI du cœur et échoue si le fichier généré committé
  a divergé.

**Hors périmètre (renvoyé à des sous-phases suivantes) :** table `items` (SP-1b),
`groups`/`item_shares`/`can()` (SP-1c), bascule du shell sur le cœur et retrait de
GeoNode (SP-1d). Rien ici ne change le comportement observable du shell : le
shell continue de parler à GeoNode jusqu'à SP-1d.

## 2. Décisions de cadrage

| Sujet | Décision |
|---|---|
| Multi-tenant | Colonne `tenant_id` sur **toute** table dès cette migration (règle CLAUDE.md) ; **un seul tenant réel en v0** (`slug="default"`), créé par la migration elle-même. La plomberie est réelle, pas un stub — elle sert le jour où un second tenant existe, sans nouvelle migration de fond. |
| Résolution du tenant | v0 : toujours le tenant `default` (un déploiement = un tenant pour l'instant). Le point d'extension (claim `tenant` du token, sinon repli sur `default`) est déjà dans le code d'auth pour ne pas re-toucher tous les appelants plus tard. |
| Provisionnement utilisateur | **JIT à la première requête authentifiée** (get-or-create par `(tenant_id, oidc_sub)`), pas d'écran d'admin. Cohérent avec « identité déléguée à Keycloak, jamais de mot de passe dans le cœur ». |
| Bibliothèque JWT | `PyJWT` + `cryptography`, JWKS récupéré en HTTP (`httpx`, déjà une dépendance) et caché en mémoire (TTL 10 min). Pas de nouvelle dépendance lourde (`python-jose` évité). |
| Mode mock serveur | `CORE_AUTH_MODE=mock` (miroir de `VITE_AUTH_MODE`) : la validation JWKS est court-circuitée, tout `Authorization: Bearer <n'importe quoi>` est accepté et résolu vers un utilisateur mock stable `username="mockuser"` — **même valeur que `MOCK_STATE.username` côté shell**, pour que `/me` renvoie une identité cohérente en e2e. |
| Frontières de modules | Restructuration de `core/app` en paquets par domaine (`tenants/`, `users/`, `auth/`, `audit/`, `configs/`) + **import-linter** (`layers` contract) en CI. Chaque domaine a son modèle, son repository, son router ; `main.py` assemble. |
| Audit dès SP-1a | La table existe et est déjà branchée sur les 5 mutations `configs` existantes (create/update/delete/rollback + creation d'item implicite), pour valider le mécanisme avant que SP-1b/1c l'utilisent sur items/sharing. |
| CI OpenAPI→TS | Script `core/scripts/export_openapi.py` (dump statique, pas besoin de DB/serveur qui tourne) + `openapi-typescript` côté shell → `shell/src/api/generated/core-schema.d.ts` committé ; CI échoue sur `git diff --exit-code` si le fichier généré diverge. |

## 3. Modèle de données

Toutes les tables ci-dessous portent `tenant_id` (String FK, non nul). Types
choisis pour rester compatibles SQLite (tests unitaires rapides, `create_all`)
et PostgreSQL (déploiement).

```python
class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String, primary_key=True)       # uuid hex
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime]

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)        # uuid hex
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    oidc_sub: Mapped[str] = mapped_column(String, nullable=False)     # claim `sub`
    username: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str] = mapped_column(String, default="")
    last_name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    # contrainte unique (tenant_id, oidc_sub)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)   # users.id, nul si system
    actor_kind: Mapped[str] = mapped_column(String, nullable=False)       # "user" | "agent" | "system"
    action: Mapped[str] = mapped_column(String, nullable=False)           # "config.create", …
    object_type: Mapped[str] = mapped_column(String, nullable=False)      # "config", "item", …
    object_id: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)             # diff/snapshot minimal
    created_at: Mapped[datetime]
```

**`configs` / `config_revisions`** gagnent `tenant_id` (non nul) dans la même
migration Alembic : la révision insère d'abord la ligne `tenants` `default`, puis
ajoute la colonne avec `server_default` pointant sur son id, puis retire le
default (pattern standard « ajouter une colonne NOT NULL sur une table
existante »). Aucune ligne de `configs` n'est perdue ou renommée.

`actor_kind = "agent"` existe dès cette migration bien qu'inutilisé avant SP-2
(serveur MCP) — c'est un champ, pas un chantier, autant l'avoir dans le schéma
une fois pour toutes.

## 4. Arborescence cible et frontières

```
core/app/
  db.py            # Base, engine, session factory (inchangé)
  main.py          # assemble les routers, lifespan (seed tenant default)
  auth/
    jwt.py         # validation JWKS + décodage claims, ou court-circuit mock
    dependency.py  # get_current_user() : résout tenant + JIT-provisionne User
  tenants/
    models.py, repository.py
  users/
    models.py, repository.py
  audit/
    models.py
    writer.py      # write_audit(session, actor, action, object_type, object_id, payload)
  configs/
    models.py, schemas.py, repository.py, routes.py   # contenu actuel de
                                                        # app/models.py, schemas.py,
                                                        # repository.py, routes.py, déplacé tel quel
```

`app/geonode.py` (le `ItemClient` GeoNode) reste en l'état pour l'instant — il
est encore utilisé par `configs/routes.py` jusqu'à SP-1b, qui le remplace par un
appel local à `items/repository.py` dans la même transaction.

**Contrat de frontières (`import-linter`, `layers`)** :

```
app.main
app.configs
app.auth
app.audit
app.users
app.tenants
```

Un module ne peut importer que des couches strictement en dessous de lui dans
cette liste (`configs` peut importer `auth`/`audit`/`users`/`tenants` ; `tenants`
n'importe rien du domaine). `audit.writer` ne référence `users.models` qu'au
niveau SQL (`ForeignKey("users.id")` en chaîne), donc pas d'import Python
circulaire à gérer. Exécuté en CI via `lint-imports` (nouvelle étape, échoue le
build sur violation).

## 5. Authentification — flux

1. Middleware/dépendance FastAPI `get_current_user(authorization: str = Header())`.
2. Si `CORE_AUTH_MODE=mock` : ignore la validité du token, résout
   `oidc_sub="mock-sub"`, `username="mockuser"`, tenant `default`.
3. Sinon : extrait le `kid` du header JWT, récupère la clé JWKS correspondante
   (cache TTL 10 min, `CORE_OIDC_ISSUER` + `/protocol/openid-connect/certs` par
   convention Keycloak, ou `CORE_OIDC_JWKS_URL` en override), vérifie signature +
   `exp` + `aud` (`CORE_OIDC_AUDIENCE`).
4. Résout le tenant (v0 : toujours `default`).
5. **JIT get-or-create** `User` par `(tenant_id, oidc_sub)` ; si créé, les champs
   `username`/`email`/`first_name`/`last_name` viennent des claims
   (`preferred_username`, `email`, `given_name`, `family_name`) ; si l'utilisateur
   existe déjà, ces champs sont rafraîchis (l'IdP reste la source de vérité).
6. Retourne l'`User` résolu ; les routes en dépendent via `Depends(get_current_user)`.

`GET /me` renvoie `{id, tenantId, username, email, firstName, lastName}`. Non
câblé au shell pour l'instant (le shell continue d'appeler l'API GeoNode
`getMe()` jusqu'à SP-1d) — cet endpoint est testé directement (pytest + `curl`
manuel), pas encore consommé.

## 6. Gestion d'erreurs

- Token absent/malformé/signature invalide/expiré → `401`.
- `aud` ne correspond pas → `401` (pas de détail dans le corps, pour ne pas aider
  un attaquant à deviner l'audience attendue).
- JWKS injoignable et cache froid → `503` (le déploiement est mal configuré,
  pas la faute du client) ; si un cache existe déjà (juste expiré), on l'utilise
  en dégradé et on logue un warning plutôt que de casser toutes les requêtes sur
  un blip réseau.
- `CORE_AUTH_MODE` absent → défaut `oidc` (fail-safe : jamais mock par accident
  en prod si la variable n'est pas positionnée).

## 7. Stratégie de tests

- **Unitaires (pytest, SQLite in-memory)** : JIT provisioning (create puis
  update), résolution tenant, `write_audit` appelé et lisible, `import-linter`
  passe (nouvelle commande CI, pas un test pytest).
- **JWT** : keypair RSA généré dans un fixture pytest, jeton signé localement,
  JWKS servi via `httpx.MockTransport` (même pattern que `test_geonode_http.py`)
  — pas de dépendance à un vrai Keycloak pour ces tests.
- **Mode mock** : un test vérifie que `CORE_AUTH_MODE=mock` accepte un bearer
  arbitraire et résout `username="mockuser"`.
- **Migration** : un test d'intégration exécute `alembic upgrade head` puis
  `alembic downgrade base` sur une Postgres éphémère (le service `postgis` du
  compose, ou équivalent CI) pour garantir la réversibilité ; les tests pytest
  du quotidien restent sur SQLite pour la vitesse.
- **CI OpenAPI→TS** : étape qui régénère le fichier et échoue sur diff non
  committé.

## 8. Critères d'acceptation

- `alembic upgrade head` sur une base vierge crée `tenants`, `users`,
  `audit_log`, et ajoute `tenant_id` à `configs`/`config_revisions` sans perte de
  données existantes (testé sur un jeu de données de dev).
- Un jeton valide (signé par les JWKS mockées en test) résout un `User` en base ;
  un second appel avec le même `sub` ne recrée pas de doublon.
- `CORE_AUTH_MODE=mock` fonctionne sans aucun accès réseau à Keycloak.
- Chaque `create_config`/`update_config`/`delete_config`/`rollback_config`
  produit une ligne `audit_log` avec le bon `actor_id`/`tenant_id`.
- `lint-imports` passe en CI et casse si un import remonte une couche.
- Le job CI OpenAPI→TS échoue si `core-schema.d.ts` committé ne correspond plus
  au schéma généré.

## 9. Risques

Faibles à ce stade (rien n'est encore observable par le shell). Le risque
principal est le temps passé à découper `app/` en paquets — mitigé par le fait
que le contenu de `configs/` est un simple déplacement de fichiers existants,
sans réécriture de logique. Le mode mock serveur doit être clairement
**refusé par défaut** (pas de valeur par défaut à `mock`) pour ne jamais finir
en prod par erreur de configuration.
