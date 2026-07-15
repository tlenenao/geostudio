# SP-9 — Sécurité minimale : design

> Sous-partie de SP-9 (Durcissement produit public v0.1). Brainstormée le
> 2026-07-15, en même temps que le reste de SP-9 — planifiable et exécutable
> indépendamment, comme `2026-07-13-sp9-gestion-collections-design.md`.

## 1. Contexte et objectif

**Constat, vérifié en lisant `docker-compose.yml` intégralement et en
listant les fichiers de test authz existants :**
- **Traefik n'est aujourd'hui pas réellement câblé** : le service existe
  (résolveur ACME, entrypoints `web`/`websecure`) mais **aucun `label:
  traefik.*` n'existe sur `core` ou `shell`** — `DOMAIN` (défini dans
  `.env.example`) n'est référencé nulle part dans `docker-compose.yml`. Les
  deux bullets roadmap « en-têtes Traefik » et « rate limiting basique » sont
  donc sans ingress réel auquel s'attacher — les câbler suppose de finir le
  branchement Traefik lui-même, pas seulement d'ajouter un middleware à une
  route qui n'existe pas encore.
- **`--api.insecure=true`** expose le dashboard Traefik (port `8090`) sans
  authentification — acceptable en dev, pas dans un compose destiné à un
  déploiement public documenté.
- **Couverture authz existante, large** (fichiers déjà présents, à auditer
  plutôt qu'à réécrire) : `test_auth.py`, `test_sharing_authorization.py`,
  `test_sharing_acceptance.py`, `test_sharing_routes.py`,
  `test_collections_authorization.py`, `test_collections_sharing_routes.py`,
  `test_mcp_auth.py`, `test_mcp_tools_sharing.py` — couvrant déjà partage
  groupes×rôles, items publics anonymes, `can()`, RLS, permissions MCP. La
  roadmap demande une **revue**, pas une construction depuis zéro.
- **Aucun audit de dépendances** : ni `pip-audit`/`uv` ni `npm audit` ne
  tournent en CI aujourd'hui ; `core/pyproject.toml` n'a pas `pip-audit` en
  dev-dependency.

**Objectif.** Le dépôt expose un ingress Traefik réellement fonctionnel avec
des en-têtes de sécurité standards et un rate limiting global ; la
couverture authz existante est auditée et tout trou réel trouvé (pas
supposé) est comblé par un test qui le prouve d'abord rouge ; les
dépendances cœur et shell sont auditées à chaque CI, bloquant sur
High/Critical (décision utilisateur).

## 2. Périmètre

**Dans le périmètre v1 :**
- **Câblage Traefik minimal** : un seul `DOMAIN` (déjà l'unique variable de
  ce nom dans `.env.example`, aucun DNS supplémentaire à documenter) —
  `shell` répond sur `Host(\`${DOMAIN}\`)`, `core` sur `Host(\`${DOMAIN}\`) &&
  PathPrefix(\`/api\`)` avec priorité de routage plus élevée que `shell`
  (règle Traefik la plus spécifique gagnante par défaut, à vérifier en
  tâche). `VITE_CORE_URL` (baked au build du shell, cf. spec CI/release §2)
  pointe alors vers `https://${DOMAIN}/api`. Labels
  `traefik.http.routers.{core,shell}.tls.certresolver=letsencrypt` sur les
  deux services. Sans ce câblage minimal, rien d'autre dans cette
  sous-partie n'a de prise réelle.
- **Middleware d'en-têtes de sécurité** (`traefik.http.middlewares.security-
  headers.headers.*`) appliqué aux deux routers : `stsSeconds` (HSTS),
  `contentTypeNosniff: true`, `frameDeny: true`, `referrerPolicy:
  strict-origin-when-cross-origin`. Pas de CSP stricte en v1 (le shell charge
  des tuiles/imagerie de sources variables selon la config d'app — une CSP
  mal calibrée casserait des widgets légitimes ; différé, cf. hors périmètre).
- **Middleware de rate limiting global** (`traefik.http.middlewares.rate-
  limit.ratelimit.average`/`.burst`), appliqué aux deux routers — décision
  utilisateur déjà actée (global via Traefik, pas par route).
- **`--api.insecure=true` retiré entièrement** du compose documenté pour un
  déploiement public — le diagnostic Traefik reste possible via
  `docker compose logs traefik` sans dashboard exposé.
- **Revue authz** : relecture des 8 fichiers de test existants +
  vérification croisée avec les endpoints réels exposés
  (`core/app/**/routes.py`) pour repérer un endpoint sans test de son cas
  `403`/anonyme — pas une réécriture, un audit qui **documente ce qu'il
  trouve** (fichier `docs/superpowers/specs/2026-07-15-sp9-securite-
  minimale-revue-authz.md` ou section dédiée du rapport de tâche, cf. plan) ;
  tout trou réel comblé par un test rouge→vert, à la manière des revues
  finales de branche déjà pratiquées dans ce projet (cf. entrées SP-7/SP-8c
  de `CLAUDE.md`).
- **Audit de dépendances en CI** : job `core-deps-audit` (`uv run pip-audit`
  — ou `uv export` + `pip-audit -r` si `uv` n'expose pas de sous-commande
  dédiée, à vérifier en tâche) et job `shell-deps-audit` (`npm audit
  --audit-level=high`), tous deux bloquants (`exit 1`) sur High/Critical,
  informatifs (log, pas d'échec) en dessous — décision utilisateur.

**Hors périmètre v1 (explicitement différé) :**
- Content-Security-Policy stricte — nécessite un inventaire des sources
  externes légitimes (tuiles Martin/TiTiler, futures extensions WC tierces
  cross-origin comme celle de SP-8c) qui dépasse le « minimal » de la
  roadmap ; noté comme suivi.
- WAF applicatif, détection d'intrusion, fail2ban sur les tentatives
  d'authentification répétées — au-delà du rate limiting basique demandé.
- Scan de sécurité applicatif type SAST/DAST en CI (Semgrep, ZAP) — pas
  demandé par la roadmap SP-9, resterait à arbitrer séparément.
- Chiffrement au repos (déjà géré par l'hébergeur/volume Docker dans la
  plupart des déploiements cibles v0.1, hors périmètre applicatif).

## 3. Architecture

### 3.1 `docker-compose.yml`

Labels ajoutés sur `shell` :
```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.shell.rule=Host(`${DOMAIN}`)
  - traefik.http.routers.shell.entrypoints=websecure
  - traefik.http.routers.shell.tls.certresolver=letsencrypt
  - traefik.http.routers.shell.middlewares=security-headers,rate-limit
  - traefik.http.services.shell.loadbalancer.server.port=8300
```
Labels équivalents sur `core`, distingués par
`traefik.http.routers.core.rule=Host(\`${DOMAIN}\`) &&
PathPrefix(\`/api\`)`, avec une priorité de routage explicite
(`traefik.http.routers.core.priority=10`, supérieure à celle de `shell`) et
un middleware `traefik.http.middlewares.strip-api.stripprefix.prefixes=/api`
ajouté à la chaîne de `core` — le cœur route lui-même ses endpoints à la
racine (`/items`, `/me`, …), le préfixe `/api` n'existe que côté Traefik/
client public. Les deux middlewares partagés (`security-headers`,
`rate-limit`) déclarés une fois (labels sur `traefik` lui-même via
`--providers.file`, ou dupliqués sur les deux services — pattern Traefik
standard à trancher en tâche selon la version 3.0 exacte).

### 3.2 Revue authz — méthode

1. Lister tous les endpoints (`grep -rn "@router\.(get|post|put|patch|
   delete)" core/app/**/routes.py`).
2. Pour chacun, vérifier qu'existe au moins un test couvrant : accès
   autorisé (owner/partage), accès refusé (non-owner sans partage → 403/404
   selon la convention déjà en place), accès anonyme si la route le permet
   (items/collections publics).
3. Vérification spécifique cross-tenant (un token tenant A ne voit/modifie
   jamais une ressource tenant B) — déjà testée pour `items`/`collections`
   selon `CLAUDE.md` (SP-1b, SP-3a) ; vérifier que la même garantie est
   testée pour les ajouts plus récents (extensions SP-8b/8c, recherche
   sémantique SP-7).
4. Tout trou trouvé devient un test ajouté au fichier de test existant le
   plus proche (pas un nouveau fichier `test_security_audit.py` fourre-tout
   — cohérent avec l'organisation actuelle par domaine).

### 3.3 CI — audit de dépendances

Deux nouveaux jobs indépendants dans `ci.yml` (pas dans `release.yml` — ce
sont des vérifications de routine, pas liées à un tag) :
```yaml
core-deps-audit:
  steps:
    - uv sync
    - uv run pip-audit --strict  # échoue sur toute vulnérabilité connue résolue
shell-deps-audit:
  steps:
    - npm ci
    - npm audit --audit-level=high
```
(niveau de `pip-audit --strict` vs un filtrage explicite High/Critical à
affiner en tâche selon ce que l'outil expose réellement — `npm audit
--audit-level=high` couvre nativement High+Critical, `pip-audit` n'a pas de
notion de sévérité native aussi fine sans base CVSS externe, à vérifier).

## 4. Flux et gestion d'erreurs

**Requête normale via Traefik :** `Host(DOMAIN)` → routeur → middlewares
(headers ajoutés, comptage rate-limit) → service. Un dépassement du rate
limit renvoie `429` (comportement Traefik natif, rien à coder côté cœur).

**Audit dépendances en échec :** la CI échoue sur une vulnérabilité
High/Critical réelle — le correctif (bump de version) est un changement de
dépendance normal, pas une logique applicative à écrire dans cette
sous-partie.

**Revue authz, trou trouvé :** documenté avec repro (comme les revues de
branche déjà pratiquées dans ce projet), test rouge écrit d'abord, puis
correctif au niveau route/`can()` si le trou est réel (pas seulement un
défaut de couverture de test sur un comportement déjà correct).

## 5. Tests

**Traefik :** vérification manuelle en environnement réel (domaine de test/
`nip.io`, ou `curl -H "Host: ..."` en local) — les en-têtes de sécurité
apparaissent dans la réponse (`curl -I`), un dépassement de rate limit
produit un `429` après N requêtes rapides. Pas de test automatisé pour la
config Traefik elle-même (config d'infra, testée en la faisant tourner,
comme `sp9-install-secrets`).

**Revue authz (pytest, core) :** chaque trou trouvé devient un test qui
échoue avant correctif, passe après — même discipline TDD que le reste du
projet. Nombre de tests ajoutés = nombre de trous réels trouvés (pas un
chiffre fixé à l'avance, déterminé par l'audit).

**Audit dépendances :** vérifié en observant un run CI réel — introduire
temporairement une dépendance à vulnérabilité connue (dans une branche
jetable) pour prouver que le job échoue bien, puis la retirer.

## 6. Critères d'acceptation

- Un `curl -I` vers le domaine configuré montre HSTS, `X-Content-Type-
  Options: nosniff`, `X-Frame-Options: DENY` (ou équivalent Traefik).
- Une rafale de requêtes déclenche un `429` (rate limiting actif).
- Le dashboard Traefik non authentifié n'est plus exposé par défaut dans le
  compose documenté pour un déploiement public.
- La revue authz produit un rapport écrit (trous trouvés + corrigés, ou
  confirmation qu'aucun trou réel n'a été trouvé) — pas seulement une
  affirmation non vérifiée.
- Les jobs `core-deps-audit`/`shell-deps-audit` tournent en CI, bloquants sur
  High/Critical.
- Aucune régression sur les 384 tests cœur / 445 tests shell / 34 specs E2E
  existants.
