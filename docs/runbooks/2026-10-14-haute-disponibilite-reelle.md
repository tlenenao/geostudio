# Runbook — haute disponibilité réelle multi-réplicas (ARC-32)

Complète `2026-10-12-haute-disponibilite-bornee.md` (ADR 0019) : les trois écarts qu'il listait
(limiteur en mémoire, `cdc-worker` mono-instance, `core` non totalement sans état) sont fermés.
**Périmètre : un datacenter.** Bascule Postgres toujours manuelle (pas de Patroni) ; MinIO distribué
documenté, non exécuté. Support « contractuel » (astreinte, SLA) : **hors code**, à contractualiser
séparément — ce runbook donne les RPO/RTO techniques, pas un engagement de service.

## 1. Ce qui a changé

| Sujet | Avant | Maintenant |
|---|---|---|
| Limiteur de débit | mémoire par process (budget x N) | `CORE_RATELIMIT_BACKEND=postgres` (défaut compose/Helm) : compteur UPSERT à fenêtre fixe de 60 s dans `rate_limit_counters` (migration 0068, table UNLOGGED, clé hachée SHA-256) |
| Base lente / injoignable | — | timeout 250 ms + pool dédié (2 connexions, attente 0,25 s) puis **repli sur le compteur mémoire** avec disjoncteur 5 s : la limitation ne rend jamais l'API indisponible (budget redevient par réplica pendant l'incident) |
| `cdc-worker` | 1 instance, ne jamais passer à 2 | N instances sûres : verrou consultatif de session (`app/cdc/election.py`), un leader, les autres attendent (sondage 2 s) ; le leader sort du process s'il perd sa connexion de garde (sonde 3 s) |
| Sessions MCP | en mémoire (404 sur l'autre réplica) | `CORE_MCP_STATELESS=true` (défaut compose/Helm) : pas d'`mcp-session-id`, chaque requête est autonome ; le loopback du copilote le tolère |
| Helm | 1 réplica partout | `core.replicas: 2`, `PodDisruptionBudget` (`core.pdb.minAvailable: 1`, rendu si replicas > 1), anti-affinité douce, `RollingUpdate maxUnavailable 0`, `cdcWorker.replicas: 2` (RollingUpdate maxSurge 0) ; sondes inchangées (`/health`) |

Revue « `core` sans état » (caches process recensés) : `introspection_pg` (empreinte pg + TTL 30 s),
`live_query`/Nominatim (TTL, lecture seule), clients JWKS (`lru_cache`, rechargés par durée de vie 600 s),
`geocoding/batch` (pacer et verrou **par process** : plafond amont BAN multiplié par N, déjà annoté
`ponytail`). Aucun état de session/utilisateur en mémoire hors MCP (corrigé). Les tâches de fond vivent dans
`worker` (procrastinate, `queueing_lock` sur les `periodic`) ; `core` ne fait que `.defer()`.

## 2. Exploitation

```bash
# compose
docker compose up -d --scale core=2 --scale cdc-worker=2
# Helm
helm upgrade --install geostudio deploy/helm/geostudio --set core.replicas=3
```

- Démarrer les `core` l'un après l'autre sur une migration lourde (chaque réplica exécute `alembic upgrade head`).
- Revenir au budget par process : `CORE_RATELIMIT_BACKEND=memory`.
- Identifier le leader CDC : `select a.client_addr from pg_locks l join pg_stat_activity a using(pid) where l.locktype='advisory' and l.granted` (clé = `app.cdc.election.LOCK_KEY`).
- Limite assumée du limiteur partagé : fenêtre **fixe** (une rafale à cheval sur deux fenêtres peut passer jusqu'à 2x le budget) ; un aller-retour Postgres par requête limitée (routes coûteuses seulement).
- Limite assumée de l'élection : le verrou est lié à la session ; une **partition réseau** sans RST laisse le verrou tenu jusqu'à la détection TCP (keepalives Postgres : `tcp_keepalives_idle/interval/count`, à régler < 30 s en production). Le slot de réplication reste, lui, un second garde-fou (un seul consommateur actif).

## 3. Postgres primaire / standby (inchangé, voir runbook 2026-10-12 §4)

Réplication physique en streaming, promotion manuelle, `scripts/replay/pg-standby-check.sh`.
Après bascule : repointer pgbouncer, redémarrer `core`/`worker`, **recréer le slot/la publication CDC**
(le slot logique n'est pas répliqué en PG16) — le `cdc-worker` rejoue un backfill au démarrage ; les
doublons éventuels sont absorbés par la réduction par PK côté lecteur (invariant `consumer.py`).
Pour une bascule automatique (Patroni/pg_auto_failover) : hors périmètre.

## 4. MinIO distribué

`server http://minio{1...4}/data{1...2}` (image `deploy/minio`, erasure coding) ; tolère la perte de la moitié des
disques en lecture, d'un nœud entier en écriture avec 4 nœuds. **Documenté, non exécuté** (4 nœuds x 2 disques :
hors budget RAM de cette machine). Buckets sauvegardés par `deploy/backup` quel que soit le mode.

## 5. RPO / RTO annoncés

| Scénario | RPO | RTO |
|---|---|---|
| Perte d'un `core` (2+ réplicas) | 0 écriture acquittée (mesuré) | **3,3 s** mesuré (cible < 30 s) |
| Perte du `cdc-worker` leader | 0 (le slot retient le WAL) | **1-2 s** mesuré (cible < 30 s) ; la fraîcheur GeoParquet prend du retard le temps de la reprise |
| Perte du primaire Postgres, standby asynchrone | quelques ms de WAL (0 observé, non garanti) | 5-15 min (bascule manuelle) |
| Idem, standby synchrone `remote_apply` | 0 pour les commits acquittés | idem |
| Perte du site | dernière sauvegarde (jusqu'à 24 h) | 129-320 s mesurés hors récupération de l'archive (ARC-19) |

## 6. Mesures

Rejeu `scripts/replay/ha-failover.sh` (2026-10-14, WSL2, projet jetable `arc4-o-ha`, `core` x2 + `cdc-worker` x2,
machine partagée avec d'autres tâches — ordre de grandeur, pas un SLA) :

| Mesure | Résultat |
|---|---|
| Fumée de bout en bout à travers Traefik, 2 `core` | passe |
| Budget limiteur (groupe `sql`, 10/min), 60 requêtes d'un même jeton à travers les 2 réplicas | **10 acceptées** (mémoire : 20 ; 1re passe avec un défaut de config PgBouncer : repli mémoire, 30 — corrigé, cf. §2) |
| Perte brutale d'un `core` (`docker kill`), sonde de santé 50 req/s | fenêtre d'erreurs 1,2 s (2,3 s en 1re passe), trou max 1,05 s |
| Arrêt propre (`docker stop`) | fenêtre 1,2 s |
| **Perte d'un `core` sous 4 fils d'écriture** (`POST /v1/configs`) | 632 écritures, 622 acquittées, 10 en vol coupées ; **0 acquittée absente** à la relecture ; reprise des écritures **3,3 s** après le kill (même valeur sur les 2 passes) |
| Perte du leader `cdc-worker` (`docker kill`) | un seul détenteur du verrou avant ; **reprise 1,1 s et 1,8 s** (verrou repris par l'autre pod + slot de réplication de nouveau actif) |

PgBouncer en mode transaction : le moteur du limiteur désactive les requêtes préparées
(`prepare_threshold=None`) ; sans cela, psycopg 3 plante à partir de la 5e exécution et le limiteur
retombe silencieusement en mémoire (c'est ce que la 1re passe a révélé — la dégradation fonctionne,
mais masque la panne : surveiller le log `ratelimit: Postgres indisponible`).

**Non mesuré** : bascule sous charge de production réelle (la charge est synthétique, 4 fils) ; partition
réseau (seul le kill de conteneur est rejoué) ; absence de doublon GeoParquet après reprise (garantie par
conception — backfill + réduction par PK — mais pas comptée objet par objet) ; MinIO distribué ; bascule
Postgres sous charge avec les 2 `core` branchés.
