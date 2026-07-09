# GeoStudio SP-2a — Serveur de ressources OAuth pour le MCP

> Design / spec. Première sous-phase de SP-2 (serveur MCP v0). Pose
> l'authentification OAuth d'un serveur MCP monté dans le cœur, sans encore
> construire aucun outil MCP réel — c'est le tuyau, pas le contenu. SP-2b
> (outils `list_items`/`get_item`/`get_app_config`/`save_app_config`/
> `create_item`/`get_sharing`/`set_sharing`, schémas JSON publiés,
> `actor_kind=agent`) vient se brancher dessus une fois ce sous-plan livré.
>
> Date : 2026-07-09.
> Statut : design proposé.
> Prérequis : SP-1 (a→d) livré — auth JWT OIDC du cœur, realm Keycloak
> `geostudio` réel et validé end-to-end (SP-1d.2).

---

## 1. Contexte et périmètre

La feuille de route (arbitrage A13) a déjà tranché la forme du MCP : **module
du cœur, même process**, SDK MCP Python, transport HTTP/streamable. Ce qui
restait à concevoir : comment un client MCP (Claude Desktop et équivalents)
s'authentifie concrètement — la feuille de route dit seulement
« authentification = token de l'utilisateur », sans préciser le mécanisme
d'obtention de ce token côté agent.

**Décision retenue (brainstorm de session) :** implémenter la spec officielle
*MCP Authorization* — OAuth 2.1 + PKCE, Keycloak comme Authorization Server
externe (déjà en place depuis SP-1d.2, realm `geostudio`), avec enregistrement
dynamique de client (RFC 7591, DCR) pour une expérience « vraiment
zero-config » côté utilisateur : pas de client_id à copier-coller, pas de
token à récupérer à la main.

**Contenu.**
- Nouveau package `core/app/mcp/` : montage ASGI du SDK MCP Python
  (transport `streamable-http`) à `/mcp`, avec un serveur MCP minimal
  (zéro outil réel, ou un outil `ping` trivial) — juste de quoi prouver que
  le handshake OAuth fonctionne de bout en bout.
- `GET /.well-known/oauth-protected-resource` (RFC 9728) : métadonnées de
  ressource protégée, pointant vers Keycloak comme Authorization Server.
- Challenge `401` + `WWW-Authenticate: Bearer resource_metadata="..."` sur
  toute requête `/mcp` non authentifiée.
- Nouvelle dépendance d'auth cœur `get_current_mcp_actor` (`app/mcp/auth.py`)
  — même validation JWT que `get_current_user`, audience dédiée
  `CORE_MCP_AUDIENCE` (défaut `geostudio-mcp`) au lieu de `CORE_OIDC_AUDIENCE`.
- Configuration Keycloak : DCR activé sur le realm `geostudio` (politique
  d'enregistrement raisonnable pour un realm de dev — pas de whitelist
  d'origine stricte en v0) ; un client scope `geostudio-mcp-audience`
  (mapper d'audience → `geostudio-mcp`) marqué **default** au niveau du
  realm, hérité automatiquement par tout client enregistré (DCR ou non).

**Hors périmètre.** Les outils MCP eux-mêmes (SP-2b). La publication des JSON
Schema d'`AppConfig`/`MapConfig` (SP-2b). `actor_kind=agent` dans
`audit_log` (SP-2b — rien n'est encore audité ici puisqu'aucune action
métier n'existe). Durcissement de la politique DCR pour un déploiement
public multi-tenant (hors v0, cf. Risques §7).

## 2. Décisions de cadrage

| Sujet | Décision |
|---|---|
| Emplacement du module | `core/app/mcp/`, au sommet du layering (`app.main → app.mcp → app.public → app.configs → app.items → app.sharing → app.auth → app.audit → app.users → app.tenants`) — accès transversal comme `app.public`, mais pour un acteur authentifié. |
| Transport | SDK MCP Python officiel, transport `streamable-http`, monté en sous-application ASGI sur le FastAPI existant à `/mcp`. Même process, même port — arbitrage A13. |
| Authentification agent | Spec *MCP Authorization* (OAuth 2.1 + PKCE) — pas de token collé à la main, pas de device-code flow. Keycloak est l'Authorization Server ; le cœur est le Resource Server. |
| Enregistrement client | Dynamique (RFC 7591, DCR), activé sur le realm Keycloak `geostudio`. Aucune configuration manuelle de client_id côté utilisateur. |
| Audience des tokens MCP | `geostudio-mcp` (nouvelle, distincte de `geostudio-core` utilisée par le shell) — portée par un client scope realm **default**, pas par un mapper posé à la main sur un client précis (puisque les clients DCR n'existent pas à l'avance). |
| Validation des tokens MCP | Nouvelle dépendance `get_current_mcp_actor`, réutilisant la même logique JWKS/issuer que `get_current_user` (`app/auth/dependency.py`), mais `audience=CORE_MCP_AUDIENCE` strictement — un token `geostudio-core`/`geostudio-shell` est rejeté sur `/mcp`. |
| Résolution de l'identité | Le même `User` réel que l'API REST (via `get_or_create_user`, déjà existant) — un agent agit *pour* un utilisateur donné, jamais sous une identité distincte. |
| Mode `mock` | Inchangé : `CORE_AUTH_MODE=mock` continue de fonctionner pour `/mcp` sans round-trip Keycloak, pour le dev/CI — cohérent avec le reste du cœur. |
| Portée fonctionnelle de ce sous-plan | Zéro capacité nouvelle. Le seul livrable observable est : « un flow OAuth complet aboutit à un accès authentifié à `/mcp` ». |

## 3. Architecture

```
Client MCP (Claude Desktop, etc.)
  │
  │ 1. GET /mcp (sans token)
  ▼
Cœur (app.mcp)  ──── 401 + WWW-Authenticate: Bearer
  │                  resource_metadata="…/.well-known/oauth-protected-resource"
  │ 2. GET /.well-known/oauth-protected-resource
  ▼
  { resource: ".../mcp", authorization_servers: ["<CORE_OIDC_ISSUER>"] }
  │
  │ 3. Découverte + enregistrement dynamique (DCR) + Authorization Code + PKCE
  ▼
Keycloak (realm geostudio) ──── token audiencé "geostudio-mcp"
  │
  │ 4. GET /mcp  Authorization: Bearer <token>
  ▼
Cœur (app.mcp.auth.get_current_mcp_actor)
  → valide issuer/audience/signature (comme get_current_user, audience différente)
  → get_or_create_user(...) → même User que l'API REST
  → 200, session MCP authentifiée
```

`get_current_mcp_actor` (`app/mcp/auth.py`) :

```python
def get_current_mcp_actor(
    authorization: str = Header(default=""),
    session: Session = Depends(get_session),
) -> User:
    # Identique à get_current_user (app/auth/dependency.py), sauf :
    # audience=os.environ.get("CORE_MCP_AUDIENCE", "geostudio-mcp")
    # au lieu de os.environ["CORE_OIDC_AUDIENCE"].
    ...
```

Duplication délibérée de la logique JWT plutôt que paramétrage de
`get_current_user` par une audience variable : les deux dépendances
protègent des surfaces différentes (API REST du shell vs. serveur MCP) et
doivent pouvoir évoluer indépendamment sans risquer de changer
accidentellement le comportement de l'une en modifiant l'autre — cohérent
avec la règle du cœur de ne jamais avoir de logique d'autorisation
dupliquée *implicitement* (`can()` reste la seule porte pour les objets
métier ; ici il s'agit d'authentification de transport, pas d'autorisation
d'objet).

## 4. Endpoints

```
GET  /.well-known/oauth-protected-resource   → sans auth, RFC 9728
ANY  /mcp                                     → protocole MCP (streamable-http),
                                                 exige get_current_mcp_actor
```

`/mcp` répond `401` avec `WWW-Authenticate` si le bearer token est absent,
invalide, expiré, ou d'audience incorrecte — jamais de tolérance ni de
fallback vers un mode anonyme (contrairement à `/public/*` qui est
délibérément anonyme pour un tout autre usage — accès runtime aux items
publiés).

## 5. Gestion d'erreurs

- Keycloak injoignable → `503` (comme `get_current_user` existant).
- Token valide mais mauvaise audience (`geostudio-core`/`geostudio-shell`
  présenté à `/mcp`) → `401`, message générique (pas de détail sur
  l'audience attendue, cohérent avec le principe anti-énumération déjà en
  place ailleurs dans le cœur).
- DCR sans garde-fou = surface d'abus potentielle en cas d'exposition
  publique du realm — acceptable pour un realm de dev mono-tenant, à
  documenter comme point de durcissement avant tout déploiement public
  (cf. Risques).

## 6. Stratégie de tests

- Pytest pur (sans Keycloak réel) : `GET /.well-known/oauth-protected-resource`
  retourne un JSON conforme RFC 9728 ; `GET /mcp` sans token → `401` +
  header `WWW-Authenticate` correctement formé.
- Pytest avec un realm de test / token forgé : token audiencé
  `geostudio-mcp` valide → accès autorisé, `User` résolu identique à celui
  que l'API REST résoudrait pour le même `sub`. Token audiencé
  `geostudio-core` → `401`.
- Vérification manuelle documentée (README, même format que la vérification
  `oidc` réelle de SP-1d.2) : un client MCP conforme (ou l'inspecteur MCP en
  ligne de commande) complète le flow OAuth+PKCE+DCR contre le Keycloak du
  compose et atteint `/mcp` avec succès.

## 7. Critères d'acceptation

- Un client MCP conforme découvre l'Authorization Server via
  `/.well-known/oauth-protected-resource`, s'enregistre dynamiquement,
  obtient un token audiencé `geostudio-mcp`, et atteint `/mcp` authentifié.
- Un token `geostudio-core`/`geostudio-shell` est rejeté par `/mcp` (401).
- Le mode `mock` continue de fonctionner pour `/mcp` sans dépendance à
  Keycloak.

## 8. Risques

Risque principal signalé par la feuille de route pour SP-2 dans son
ensemble : le scope creep (« et si l'agent pouvait aussi… »). Ce sous-plan
n'y échappe pas seulement en discipline mais structurellement : il ne
construit aucune capacité fonctionnelle, seulement le tuyau d'authentification
— rien à retrancher plus tard par manque de discipline, puisqu'il n'y a
encore rien de fonctionnel à côté du tuyau.

Risque technique propre à ce sous-plan : le DCR ouvert sans whitelist
d'origine est une décision v0 assumée (realm de dev, mono-tenant, pas
d'utilisateurs externes) — mais devra être revisité avant toute exposition
du realm au-delà du poste de développement (ex. limiter les redirect URIs
acceptés par la politique d'enregistrement Keycloak).
