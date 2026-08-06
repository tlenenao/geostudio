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
> connecteurs de moissonnage existants (ArcGIS SP-12d, WMS/WFS/WMTS SP-12e,
> CSW SP-12f, CKAN SP-12g) ont tous délibérément évité le problème en se
> limitant aux services publics (« pas de token/OAuth distant », `CLAUDE.md`
> « Suivis non bloquants »). Un lecteur Postgres ne peut pas suivre cette même
> échappatoire (pas de notion réaliste de « Postgres public »). D'où la
> décision de scinder :
> - **SP-15e (ce document)** : coffre de secrets générique, chiffré au repos,
>   **sans lien exclusif avec les pipelines** — brique autonome et démontrable
>   seule, **conçue dès le départ comme un service partagé pour deux familles
>   de consommateurs** (précision apportée après relecture) : le futur
>   `reader.connector` (SP-15f) **et** les connecteurs de moissonnage SP-12
>   existants (ArcGIS FS, WFS/WMS/WMTS, CSW, CKAN) — cf. §3.1 pour la
>   contrainte de couches import-linter que cela impose.
> - **SP-15f (à venir)** : `reader.connector` dlt (REST + Postgres),
>   consommant ce coffre par référence de nom.
> - **Lever la restriction « services publics uniquement » des connecteurs
>   SP-12** est du travail **séparément cadré**, non construit ici — ce
>   sous-plan garantit seulement que la forme du coffre ne bloque pas cette
>   évolution plus tard (cf. non-buts §1, §3.1).
>
> Références : feuille de route (§SP-15, A39) · `CLAUDE.md` (règles d'archi
> #1-4, **`tenant_id` et `audit_log` sur toute table/écriture dès la première
> migration**, une seule porte `can()`, « Suivis non bloquants » — restriction
> services publics des connecteurs ArcGIS/WMS-WFS-WMTS/CSW/CKAN) ·
> [`2026-08-05-sp15a-pipeline-socle-design.md`](2026-08-05-sp15a-pipeline-socle-design.md)
> (`CORE_ETL_ENABLED`, patron de capacité instance-wide admin-gated — repris
> ici pour le gate admin-only) ·
> [`2026-08-06-sp15c-spatial-writer-dataset-design.md`](2026-08-06-sp15c-spatial-writer-dataset-design.md)
> et
> [`2026-08-06-sp15d-qgis-sidecar-design.md`](2026-08-06-sp15d-qgis-sidecar-design.md)
> (les deux mentions « SP-15e à venir » qui ont initié ce sous-plan) ·
> `core/app/harvest/egress.py` (garde SSRF SP-12d, réutilisable telle quelle
> par SP-15f — hors périmètre de ce document, qui ne construit aucun appel
> réseau sortant) · `core/pyproject.toml:74-93` (contrat `layers` import-linter
> — `app.harvest` listé **au-dessus** de `app.pipelines`, cf. §3.1) · SP-3b
> (rôle admin).

## 1. Objectif & non-buts

**Objectif.** Un nouveau module `core/app/secrets/` qui stocke des
identifiants externes (clé d'API REST en header ou en query param, jeton
bearer, couple utilisateur/mot de passe, identifiants OAuth2
client-credentials, DSN Postgres) **chiffrés au repos**, référencés par un
nom lisible, sans jamais les exposer en lecture après création. Brique
générique et **volontairement transverse** : deux familles de consommateurs
anticipées (aucune des deux construite dans ce sous-plan) — le futur
`reader.connector` (SP-15f) et les connecteurs de moissonnage SP-12
existants (ArcGIS Feature Service, WFS/WMS/WMTS, CSW, CKAN), qui pourront un
jour lever leur restriction « services publics uniquement » en s'appuyant
sur ce coffre au lieu d'en inventer un second. C'est pour cette raison que
§3.1 fixe la position du module dans le contrat de couches import-linter
plutôt que de la laisser implicite.

**Non-buts explicites** (reportés, cf. brainstorm) :
- **L'op `reader.connector` elle-même** — SP-15f.
- **La levée effective de la restriction « services publics uniquement »
  des connecteurs SP-12** (ArcGIS FS, WFS/WMS/WMTS, CSW, CKAN) — travail
  séparément cadré, futur, non construit ici. Ce sous-plan ne fait que
  s'assurer que la forme du coffre (kinds §4, position de couche §3.1) ne
  bloque pas cette évolution le jour où elle sera priorisée.
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

### 3.1 Position dans le contrat de couches import-linter

`core/pyproject.toml:74-93` (contrat `layers`, root `app`) ordonne
aujourd'hui, du haut (peut importer tout ce qui suit) vers le bas (ne peut
rien importer au-dessus) : `app.main`, `app.mcp`, `app.public`,
**`app.harvest`**, **`app.pipelines`**, `app.ingestion`, `app.dcat`,
`app.stac`, `app.features`, `app.collections`, `app.configs`,
`app.extensions`, `app.items`, `app.sharing`, `app.auth`, `app.audit`,
`app.users`, `app.tenants`.

**`app.harvest` est au-dessus de `app.pipelines`** dans ce contrat — un
détail qui aurait pu passer inaperçu si `app.secrets` avait été positionné
« à côté » de `app.pipelines` sans vérification : `app.pipelines` ne peut
pas importer `app.harvest` (ni l'inverse ne serait un problème, mais ce
n'est pas le sens dont ce module a besoin). Pour que **les deux** familles
de consommateurs anticipées (§1) puissent importer `app.secrets`,
celui-ci doit être positionné **strictement en dessous des deux** :

```
app.main
app.mcp
app.public
app.harvest
app.pipelines
app.secrets        # NOUVEAU — inséré ici, sous harvest ET pipelines
app.ingestion
app.dcat
...
app.audit           # app.secrets pose des lignes audit_log → doit rester au-dessus
app.users
app.tenants
```

`app.secrets` a aussi besoin d'écrire dans `app.audit` (§3.3) — d'où sa
position juste au-dessus de `app.audit`/`app.users`/`app.tenants`, sans
descendre plus bas que nécessaire. Aucun module entre `app.pipelines` et
`app.audit` (`app.ingestion`, `app.dcat`, `app.stac`, `app.features`,
`app.collections`, `app.configs`, `app.extensions`, `app.items`,
`app.sharing`, `app.auth`) n'a besoin d'importer `app.secrets` dans ce
sous-plan ; rien ne les empêche de le faire plus tard, la position choisie
ne leur ferme pas la porte.

### 3.2 Table `connector_secrets`

Nouvelle table `connector_secrets` (nouvelle migration Alembic) :

```python
class ConnectorSecret(Base):
    __tablename__ = "connector_secrets"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # str(uuid4()), patron du dépôt
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)          # référencé par SP-15f et, plus tard, les connecteurs SP-12
    kind: Mapped[str] = mapped_column(String, nullable=False)          # cf. §4
    ciphertext: Mapped[bytes] = mapped_column(nullable=False)
    nonce: Mapped[bytes] = mapped_column(nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("tenant_id", "name"),)
```

(`id`/`tenant_id`/`created_by` en `str`, `_now()` = `datetime.now(timezone.utc)` — même patron exact que `core/app/pipelines/models.py:PipelineRun`, pas de type `UUID` natif ni de `func.now()` côté serveur.)

### 3.3 Audit

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
    """`location="query"` couvre les services à jeton en paramètre d'URL
    (ex. `?token=...` d'un ArcGIS Feature Service déjà authentifié en amont,
    clé GeoServer sur un WFS) ; `location="header"` couvre le cas générique
    (`X-API-Key`, etc.). Un seul `kind` pour les deux formes plutôt que deux
    kinds séparés — la différence est un simple champ de placement, pas une
    nature de credential différente."""
    kind: Literal["api_key"] = "api_key"
    location: Literal["header", "query"]
    key: str        # nom du header ou du paramètre de requête
    value: str

class BearerTokenPayload(BaseModel):
    kind: Literal["bearer_token"] = "bearer_token"
    token: str

class BasicAuthPayload(BaseModel):
    """Couvre aussi un WFS/WMS/WMTS/CSW gaté par HTTP Basic Auth, et le flux
    ArcGIS Enterprise `generateToken` (nom d'utilisateur/mot de passe) si un
    connecteur choisit de faire l'échange de jeton lui-même — le coffre ne
    porte que le matériel brut, jamais la logique d'échange."""
    kind: Literal["basic_auth"] = "basic_auth"
    username: str
    password: str

class OAuth2ClientCredentialsPayload(BaseModel):
    """Flux OAuth2 client-credentials — couvre notamment l'« app login »
    ArcGIS Online (`https://www.arcgis.com/sharing/rest/oauth2/token`) ainsi
    que toute API tierce (géocodage, météo — cas d'usage #8 de l'étude de
    faisabilité) gatée par ce flux standard. Le coffre stocke les
    identifiants client, jamais le jeton d'accès obtenu (à courte durée de
    vie, à la charge du connecteur consommateur de le renouveler)."""
    kind: Literal["oauth2_client_credentials"] = "oauth2_client_credentials"
    tokenUrl: str
    clientId: str
    clientSecret: str

class PostgresDsnPayload(BaseModel):
    kind: Literal["postgres_dsn"] = "postgres_dsn"
    dsn: str

SecretPayload = Annotated[
    ApiKeyPayload | BearerTokenPayload | BasicAuthPayload
    | OAuth2ClientCredentialsPayload | PostgresDsnPayload,
    Field(discriminator="kind"),
]
```

Additif par construction : un nouveau `kind` (ex. un flux d'auth encore plus
spécifique) est une nouvelle variante Pydantic, aucune migration requise
pour les lignes existantes. C'est délibérément le mécanisme d'extension
retenu plutôt que d'essayer d'anticiper aujourd'hui toutes les formes
d'authentification que les connecteurs SP-12/SP-15f voudront un jour —
`api_key`/`bearer_token`/`basic_auth`/`oauth2_client_credentials`/
`postgres_dsn` couvrent les cas identifiés en brainstorm (REST générique,
Postgres, ArcGIS FS, WFS/WMS/WMTS/CSW), pas une liste close.

Le `kind` apparaît deux fois par construction, pas par redondance accidentelle
: la colonne `connector_secrets.kind` (§3.2) permet de filtrer/afficher sans
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
  tests d'isolation tenant existants sur collections/items) ; un
  aller-retour create→`get_secret_payload` par `kind` (les cinq variantes
  §4, dont les deux placements `header`/`query` de `api_key`) confirme que
  le discriminant Pydantic retrouve la bonne variante après déchiffrement.
- **Frontière de couches** : test import-linter existant (`core` CI) étendu
  pour couvrir `app.secrets` — confirme qu'`app.harvest` et `app.pipelines`
  peuvent tous deux l'importer et qu'il ne peut importer aucun des deux
  (§3.1), sans attendre qu'un vrai import cassé le révèle en review.
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
  module** (`core/app/secrets/`, positionné sous `app.harvest` **et**
  `app.pipelines` dans le contrat de couches import-linter, §3.1 — les deux
  pourront en dépendre, jamais l'inverse), **nouvelle variable
  d'environnement requise** (`CORE_SECRETS_MASTER_KEY`) une fois le module
  câblé dans `app.main`. Aucun changement de route/comportement existant
  (les connecteurs SP-12 restent « services publics uniquement » tant que
  leur extension n'est pas construite — non-but §1).

| Risque | Mitigation |
|---|---|
| `CORE_SECRETS_MASTER_KEY` fuite (dump d'env, mauvaise config de logs) | Compromission totale des secrets de tous les tenants — même surface que tout schéma à clé unique (comparatif §2) ; mitigé en gardant la clé hors `audit_log`/messages d'erreur/spans OTel, jamais loguée nulle part |
| Clé maître perdue (non sauvegardée) | Tous les secrets deviennent définitivement indéchiffrables — note de runbook opérationnel : sauvegarder la clé avec la même rigueur que les sauvegardes DB |
| Gate admin-only bloque un auteur non-admin ayant besoin d'un nouveau credential | Friction acceptée en v0 — même division du travail que `CORE_ETL_ENABLED` ; à revisiter si l'usage réel montre un goulot d'étranglement |
| Un `kind` a besoin d'un champ supplémentaire plus tard (ex. un flux SAML/mTLS non anticipé aujourd'hui) | Union discriminée additive — nouveau kind = nouvelle variante Pydantic, aucune migration requise pour les lignes existantes |
| Contexte de déploiement change (hébergement multi-tenant à grande échelle) et l'option C (KMS) redevient pertinente | Documentée ici comme piste d'évolution explicite, non construite — pas un mur à contourner plus tard |
