# Piloter GeoStudio avec un agent IA (MCP)

Le cœur est aussi un **serveur MCP** (Model Context Protocol) : un agent externe
(Claude, Cursor…) agit avec **les permissions de l'utilisateur** qui s'est
authentifié, sur la même logique que l'API REST — aucune règle dupliquée. Chaque
appel d'outil est **audité** (`mcp.tool_call`).

## Se connecter

- **Endpoint** : `https://<hôte>/mcp` (transport *streamable HTTP*), hors du
  préfixe `/v1`. Sur la stack locale : `http://localhost:8200/mcp`.
- **Authentification** : OAuth 2.1 avec PKCE. Le client découvre l'autorité via
  `/.well-known/oauth-protected-resource/mcp` (RFC 9728), s'authentifie auprès de
  Keycloak et présente un jeton dont l'audience est `CORE_MCP_AUDIENCE`
  (`geostudio-mcp`). Les jetons de l'API REST ne sont **pas** valides ici, et
  inversement.
- **URL publique** : `CORE_BASE_URL` / `PUBLIC_BASE_URL` doivent être l'URL
  joignable de l'extérieur, sinon la découverte OAuth échoue.

Exemple de configuration d'un client (Claude Code) :

```bash
claude mcp add --transport http geostudio https://gis.exemple.fr/mcp
```

Le client ouvre alors le navigateur pour la connexion. En local avec
`CORE_AUTH_MODE=mock`, l'authentification OIDC n'est pas disponible : l'endpoint
est conçu pour un vrai Keycloak.

## Ce qu'on peut faire

Le catalogue complet, **généré depuis le code**, est dans
[`mcp-outils.md`](mcp-outils.md). Familles principales : recherche et lecture du
catalogue, création d'apps/dashboards/datasets, formulaires, partage et groupes,
requêtes analytiques (`run_analytics_query`, `generate_sql_query` — un brouillon
n'est jamais exécuté sans revue), pipelines, alertes, rapports, géocodage,
lineage/impact, pièces jointes. Les outils de pipeline n'existent que si
`CORE_ETL_ENABLED=true`.

Exemples d'instructions : « Crée une app de suivi des incidents avec carte et
tableau sur la collection `incidents` », « Quels objets dépendent du dataset
`parcelles` ? », « Propose une requête qui compte les incidents par commune ».

## Garde-fous

- Mode démo `CORE_READ_ONLY_MODE=true` : tout outil d'écriture est refusé.
- Les écritures respectent `can()`, les quotas et le contrôle de concurrence
  (`expectedUpdatedAt` pour `update_item`).
- Les accès sortants du cœur (garde SSRF) s'appliquent comme en REST.
- `CORE_MCP_STATELESS=true` (défaut des déploiements multi-réplicas) : pas de
  session serveur, les clients n'ont pas à conserver `mcp-session-id`.

## Le copilote du builder

Dans le builder, le **copilote** orchestre un sous-ensemble allowlisté de ces
outils (lecture/recherche, création, génération de requêtes) en rappelant `/mcp`
avec le jeton de l'utilisateur. Il est activé par `CORE_LLM_PROVIDER` ; les écritures
qu'il propose sont **confirmées par un clic** avant d'être appliquées.
