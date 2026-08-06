# SP-15e — Coffre de secrets pour connecteurs externes (design)

> **Date : 2026-08-06 · Statut : validé (brainstorm tenu en session)**
> Cinquième sous-partie de **SP-15 — ETL no-code « équivalent FME »** (feuille de
> route, jalon **M14**, arbitrage **A39**), positionnée en préalable à la partie
> `reader.connector` de la Phase 3 de l'étude de faisabilité
> [`2026-07-22-etude-faisabilite-etl-fme-nocode-design.md`](2026-07-22-etude-faisabilite-etl-fme-nocode-design.md)
> (§5 « Spatial & largeur FME », D5 « Qualité/versioning des sources dlt »).
>
> **Re-découpage décidé en brainstorm** : SP-15c/SP-15d annonçaient toutes deux
> « SP-15e (à venir) : `reader.connector` dlt (REST + Postgres) » comme un seul
> sous-plan. En le préparant, il est apparu que `reader.connector` a besoin
> d'authentifier des sources externes (API REST à clé, Postgres distant), et
> qu'**aucun mécanisme de stockage de secret n'existe dans le dépôt** — les
> deux connecteurs de moissonnage existants (ArcGIS SP-12d, CKAN SP-12g) ont
> délibérément évité le problème en se limitant aux services publics. Un
> lecteur Postgres ne peut pas suivre cette même échappatoire (pas de notion
> réaliste de « Postgres public »). D'où la décision de scinder :
> - **SP-15e (ce document)** : coffre de secrets générique, chiffré au repos,
>   sans lien avec les pipelines — brique autonome et démontrable seule.
> - **SP-15f (à venir)** : `reader.connector` dlt (REST + Postgres),
>   consommant ce coffre par référence de nom.
>
> Références : feuille de route (§SP-15, A39) · `CLAUDE.md` (règles d'archi
> #1-4, **`tenant_id` et `audit_log` sur toute table/écriture dès la première
> migration**, une seule porte `can()`) ·
> [`2026-08-05-sp15a-pipeline-socle-design.md`](2026-08-05-sp15a-pipeline-socle-design.md)
> (`CORE_ETL_ENABLED`, patron de capacité instance-wide admin-gated — repris
> ici pour le gate admin-only) ·
> [`2026-08-06-sp15c-spatial-writer-dataset-design.md`](2026-08-06-sp15c-spatial-writer-dataset-design.md)
> et
> [`2026-08-06-sp15d-qgis-sidecar-design.md`](2026-08-06-sp15d-qgis-sidecar-design.md)
> (les deux mentions « SP-15e à venir » qui ont initié ce sous-plan) ·
> `core/app/harvest/egress.py` (garde SSRF SP-12d, réutilisable telle quelle
> par SP-15f — hors périmètre de ce document, qui ne construit aucun appel
> réseau sortant) · SP-3b (rôle admin).

## 1. Objectif & non-buts

**Objectif.** Un nouveau module `core/app/secrets/` qui stocke des
identifiants externes (clé d'API REST, jeton bearer, couple utilisateur/mot
de passe, DSN Postgres) **chiffrés au repos**, référencés par un nom
lisible, sans jamais les exposer en lecture après création. Brique
générique — aucun consommateur n'existe encore ; SP-15f sera le premier.

**Non-buts explicites** (reportés, cf. brainstorm) :
- **L'op `reader.connector` elle-même** — SP-15f.
- **Rotation en tant qu'opération de première classe** (`PUT`, historique de
  versions) — v0 est *supprimer puis recréer*.
- **Partage/délégation granulaire (`can()` par secret)** — v0 est admin-only
  par tenant, pas de groupes.
- **Outillage de rotation de la clé maître** — un script de
  déchiffrement/rechiffrement de masse est *possible* manuellement (note de
  runbook opérationnel, §9), pas construit comme API/CLI dans ce sous-plan.
- **Intégration KMS/Vault** — écarté en brainstorm (comparatif §2), documenté
  comme piste d'évolution future si le contexte de déploiement change
  (multi-tenant hébergé à grande échelle), pas construit en v0.
- **UI builder/canvas de gestion des secrets** — v0 est REST-only (comme
  SP-15a Phase 1 « MCP/REST/JSON avant canvas ») ; une page de réglages est
  une suite naturelle une fois `reader.connector` livré (SP-15f+).
- **Un nouveau kind `BuilderConfig`** — délibérément **pas** modélisé comme
  objet de plateforme déclaratif (règle d'archi #2 vise les objets de
  *contenu* génerables/relisibles par un agent ; un secret est précisément
  ce qui ne doit jamais être ni l'un ni l'autre) — table dédiée à la place,
  même posture que `users`/`tenants`.

## 2. Comparatif chiffrement (décision de brainstorm)

Trois options évaluées en session, dimension par dimension (blast radius,
rotation, audit, empreinte infra, conformité) :

| Dimension | A — AES-GCM applicatif | B — Postgres `pgcrypto` | C — KMS externe |
|---|---|---|---|
| Où vit la clé | Env process, jamais en DB | Transite dans les appels SQL | Détenue par le KMS |
| Compromission DB seule (dump/backup) | Chiffré, inutile sans la clé | Idem, sauf accès exécution + clé | Chiffré, inutile sans la clé |
| Injection SQL seule (sans RCE) | Sûr — récupère du chiffré | Vulnérable si la clé transite/fuite via les logs SQL | Sûr |
| Rotation de clé | Manuelle (script déchiffrer/rechiffrer) | Idem, avec la clé exposée sur le fil pendant la rotation | Native (rewrap sans toucher au chiffré) |
| Nouvelle infra | Aucune (+1 dépendance Python) | Aucune (extension Postgres) | Service à exploiter/payer |
| Conformité (hébergement France/UE) | Clé et chiffré restent sur l'infra maîtrisée | Idem | Un KMS cloud US pose une question de confiance/résidence des données |

**Retenu : A — chiffrement applicatif AES-GCM**, clé maître dans
`CORE_SECRETS_MASTER_KEY` (env, générée une fois au déploiement, même
posture que les clés S3/embedding déjà gérées ainsi). Bat B sur l'axe
injection-SQL (aucun bénéfice de B ne compense ce risque) ; C écarté pour la
même raison que Redis/Iceberg-KMS ailleurs dans la feuille de route (nouvelle
infra hors du budget maintenance solo), documenté en risque §9 comme piste
si le contexte change.

## 3. Modèle de données

Nouvelle table `connector_secrets` (nouvelle migration Alembic) :

```python
class ConnectorSecret(Base):
    __tablename__ = "connector_secrets"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # str(uuid4()), patron du dépôt
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)          # référencé par SP-15f
    kind: Mapped[str] = mapped_column(String, nullable=False)          # cf. §4
    ciphertext: Mapped[bytes] = mapped_column(nullable=False)
    nonce: Mapped[bytes] = mapped_column(nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("tenant_id", "name"),)
```

(`id`/`tenant_id`/`created_by` en `str`, `_now()` = `datetime.now(timezone.utc)` — même patron exact que `core/app/pipelines/models.py:PipelineRun`, pas de type `UUID` natif ni de `func.now()` côté serveur.)

`tenant_id` + `audit_log` sur toute écriture (règle non négociable) : chaque
`create_secret`/`delete_secret` pose une ligne `audit_log` (`action=
"secret.create"|"secret.delete"`, `object_id=secret.id`) — **jamais** la
valeur en clair ni le `payload` déchiffré dans l'entrée d'audit, seulement
`name`/`kind`/`id`.

## 4. Chiffrement — `core/app/secrets/crypto.py`

```python
def encrypt(payload: dict[str, str]) -> tuple[bytes, bytes]:
    """AES-256-GCM. Retourne (ciphertext, nonce). `payload` sérialisé en JSON
    avant chiffrement."""

def decrypt(ciphertext: bytes, nonce: bytes) -> dict[str, str]:
    """Lève sur échec du tag d'authentification (chiffré altéré / mauvaise clé)."""
```

- Implémentation : `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
  (nouvelle dépendance `cryptography` dans `core/pyproject.toml` — absente à
  ce jour, vérifié). AES-GCM directement plutôt que l'enveloppe Fernet : GCM
  est déjà authentifié, pas besoin du versioning/timestamp intégré de Fernet.
- Clé maître : `CORE_SECRETS_MASTER_KEY`, 32 octets encodés base64, lue une
  fois au démarrage du process (`app.main`), **échec rapide** (le process ne
  démarre pas) si absente ou mal formée — même posture que les autres
  variables d'environnement requises déjà vérifiées au boot.
- La clé ne doit **jamais** apparaître dans un log, un message d'erreur, un
  span OTel ou une entrée `audit_log` — vérifié par test (§8).

`kind` (discriminated union Pydantic, `payload` shape par kind) :

```python
class ApiKeyPayload(BaseModel):
    kind: Literal["api_key"] = "api_key"
    header: str
    value: str

class BearerTokenPayload(BaseModel):
    kind: Literal["bearer_token"] = "bearer_token"
    token: str

class BasicAuthPayload(BaseModel):
    kind: Literal["basic_auth"] = "basic_auth"
    username: str
    password: str

class PostgresDsnPayload(BaseModel):
    kind: Literal["postgres_dsn"] = "postgres_dsn"
    dsn: str

SecretPayload = Annotated[
    ApiKeyPayload | BearerTokenPayload | BasicAuthPayload | PostgresDsnPayload,
    Field(discriminator="kind"),
]
```

Additif par construction : un nouveau `kind` (ex. OAuth2 client-credentials)
est une nouvelle variante Pydantic, aucune migration requise pour les lignes
existantes.

Le `kind` apparaît deux fois par construction, pas par redondance accidentelle
: la colonne `connector_secrets.kind` (§3) permet de filtrer/afficher sans
déchiffrer (ex. `GET /secrets`, §6) ; le champ `kind` du payload (ici) est
le discriminant qui permet à Pydantic de parser le JSON déchiffré dans la
bonne variante. Les deux doivent rester synchronisés à l'écriture
(`create_secret` déduit la colonne du `kind` du payload reçu, jamais l'un
sans l'autre).

## 5. Repository — `core/app/secrets/repository.py`

```python
def create_secret(session, *, tenant_id: str, user, name: str, payload: SecretPayload) -> ConnectorSecretMeta: ...
def list_secrets(session, *, tenant_id: str) -> list[ConnectorSecretMeta]: ...
def delete_secret(session, *, tenant_id: str, secret_id: str) -> None: ...
def get_secret_payload(session, *, tenant_id: str, name: str) -> SecretPayload | None:
    """Déchiffre. Usage interne uniquement (ex. futur runtime SP-15f) — jamais
    appelé depuis un handler de route qui sérialise sa sortie en JSON."""
```

`ConnectorSecretMeta` = `{id, name, kind, created_at, updated_at}` — jamais
`ciphertext`/`nonce`/valeur déchiffrée. `list_secrets`/`create_secret`
retournent exclusivement ce type ; `get_secret_payload` est le seul point
d'entrée qui déchiffre, et n'est exposé à aucune route REST.

## 6. API REST — `core/app/secrets/routes.py`

| Route | Comportement |
|---|---|
| `POST /secrets` | Body `{name, payload}` (payload = union §4, discriminée par son propre champ `kind`). Retourne `ConnectorSecretMeta` — jamais le payload. `409` si `name` déjà pris pour ce tenant. |
| `GET /secrets` | Liste `ConnectorSecretMeta[]` du tenant courant. |
| `DELETE /secrets/{id}` | Suppression. `404` si absent/autre tenant (même posture no-leak que `config_validation.py` pour les collections). |

Pas de `GET /secrets/{id}` retournant une valeur, pas de `PUT` — rotation =
supprimer puis recréer (évite la sémantique ambiguë d'une mise à jour
partielle d'un blob chiffré). Une future `reader.connector` (SP-15f) qui
référence un secret supprimé échoue à l'**exécution** avec un message clair
(« secret 'nom' introuvable ») — jamais un blocage à la sauvegarde du
pipeline, même philosophie que les expressions CEL et `transform.qgis`.

**Permissions : admin-only, scope tenant**, sur les trois routes. Justifié
en brainstorm : ce n'est pas un objet de contenu partageable via `can()`
(pas de story de délégation granulaire aujourd'hui), c'est une primitive
opérationnelle/sécurité comparable à `CORE_ETL_ENABLED` — un admin la
configure, un auteur de pipeline non-admin référence ensuite un secret
existant par son nom (division du travail acceptée en v0 ; à revisiter si
l'usage réel montre un goulot d'étranglement).

## 7. Exposition MCP — référence uniquement, jamais de valeur

Aucun nouvel outil MCP pour **créer** un secret (décision de brainstorm : un
agent ne doit jamais recevoir une valeur brute dans son contexte d'appel
d'outil). La liste des `ConnectorSecretMeta` (nom/kind/id, jamais la valeur)
sera exposée aux outils MCP d'auteur de pipeline de SP-15f
(`explain_pipeline` et équivalents) pour guider un agent vers un nom de
secret existant — même esprit que l'exposition du catalogue d'op (SP-15a
§5) ou de l'allowlist QGIS (SP-15d §5). Créer/faire tourner un secret reste
strictement humain, via la route REST §6.

## 8. Tests (`core/tests/secrets/`)

- **Chiffrement** : aller-retour `encrypt`/`decrypt` ; rejet propre sur
  chiffré altéré ou mauvaise clé (échec du tag d'authentification GCM).
- **Repository** : create/list/delete ; isolation tenant (le tenant A ne
  peut ni lister ni supprimer un secret du tenant B — même forme que les
  tests d'isolation tenant existants sur collections/items).
- **Routes** : 403 non-admin sur les trois routes ; **assertion explicite
  qu'aucune valeur/payload/ciphertext n'apparaît dans un corps de réponse**
  (scan du JSON de réponse) ; ligne `audit_log` posée sur create/delete sans
  fuite de valeur dans l'entrée d'audit.
- **Boot** : `CORE_SECRETS_MASTER_KEY` absente ou mal formée → échec rapide
  au démarrage du process (pas un échec différé à la première requête).
- Suites existantes (`core` pytest, `shell` vitest/e2e) restent vertes —
  extension additive pure, aucune route/comportement existant modifié.

## 9. Compatibilité & risques

- **Nouvelle migration Alembic** (table `connector_secrets`), **nouveau
  module** (`core/app/secrets/`, frontière import-linter propre — SP-15f en
  dépendra, jamais l'inverse), **nouvelle variable d'environnement requise**
  (`CORE_SECRETS_MASTER_KEY`) une fois le module câblé dans `app.main`.
  Aucun changement de route/comportement existant.

| Risque | Mitigation |
|---|---|
| `CORE_SECRETS_MASTER_KEY` fuite (dump d'env, mauvaise config de logs) | Compromission totale des secrets de tous les tenants — même surface que tout schéma à clé unique (comparatif §2) ; mitigé en gardant la clé hors `audit_log`/messages d'erreur/spans OTel, jamais loguée nulle part |
| Clé maître perdue (non sauvegardée) | Tous les secrets deviennent définitivement indéchiffrables — note de runbook opérationnel : sauvegarder la clé avec la même rigueur que les sauvegardes DB |
| Gate admin-only bloque un auteur non-admin ayant besoin d'un nouveau credential | Friction acceptée en v0 — même division du travail que `CORE_ETL_ENABLED` ; à revisiter si l'usage réel montre un goulot d'étranglement |
| Un `kind` a besoin d'un champ supplémentaire plus tard (ex. flux OAuth2 client-credentials) | Union discriminée additive — nouveau kind = nouvelle variante Pydantic, aucune migration requise pour les lignes existantes |
| Contexte de déploiement change (hébergement multi-tenant à grande échelle) et l'option C (KMS) redevient pertinente | Documentée ici comme piste d'évolution explicite, non construite — pas un mur à contourner plus tard |
