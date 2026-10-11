# 0016 — Clés d'API de service : un secret machine, vérifié par la porte unique

Statut: acceptée
Source : ARC-06 (comparatif FME/ArcGIS Enterprise 2026-10-11 §6.1.2) ; ADR 0001 (`can()`), SP-31 (rôles).

## Contexte

Les scripts, CI et capteurs n'ont aujourd'hui que des jetons OIDC (interactifs, courts) ou des liens de partage (lecture d'un objet). Il manque un identifiant machine durable, révocable, rattaché à un humain responsable.

## Décision

- Une clé d'API est un **secret machine à haute entropie** (`gsk_<préfixe>_<secret 256 bits>`), pas un mot de passe : la règle « jamais de mots de passe dans le cœur » reste vraie.
- Stockage : SHA-256 du jeton complet + préfixe public (12 caractères, affichable). Le secret n'est montré **qu'une fois**, à la création. Comparaison des condensats à temps constant (`hmac.compare_digest`) après recherche par préfixe.
- **Identité = celle du créateur**, résolue à chaque requête (rôle courant, partages courants) : la clé ne peut jamais dépasser les privilèges du créateur, et les perd s'il est rétrogradé, effacé (RGPD) ou si la clé expire/est révoquée. Aucune table de privilèges propre à la clé, donc une seule porte `can()`/`require_privilege`.
- Expiration obligatoire, ≤ 365 jours ; révocation immédiate (`revoked_at`). Tout échec (inconnue, expirée, révoquée, créateur effacé) répond le même 401 `invalid api key` (pas d'oracle).
- Usage tracé dans `audit_log` (`api_key.use`, au plus une fois par minute et par clé, pour borner l'écriture sur les lectures chaudes ; création/révocation toujours auditées).
- Les routes de gestion des clés refusent l'authentification par clé (une clé ne crée pas de clés).
- Le rate limiter existant s'applique tel quel (clé = en-tête Authorization).

## Conséquences

- Point d'entrée unique : `app.auth.dependency.get_current_user` (REST, OGC, tuiles, STAC y passent). Le **MCP** garde son vérificateur OIDC à audience distincte : les clés n'y sont pas acceptées (suivi possible).
- Pas de portée (scope) par clé en v1 : une clé = tout ce que peut le créateur. Alternative écartée pour l'instant : sous-ensemble de privilèges par clé (complexité, second chemin de décision).
