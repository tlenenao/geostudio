# Runbook — haute disponibilité bornée (ARC-18, ADR 0019)

> **Mis à jour par ARC-32** : limiteur partagé, élection du `cdc-worker` et MCP sans état sont livrés — voir
> `2026-10-14-haute-disponibilite-reelle.md`. Les passages ci-dessous sur ces trois points décrivent l'état
> d'ARC-18 (mesures historiques conservées).

**Promesse commerciale : « HA documentée et testée », pas « HA réelle ».** Périmètre = un datacenter,
comme Esri (2 portails + LB). Limiteur partagé, élection du `cdc-worker`, `core` sans état total,
Helm : **ARC-32** (hors périmètre).

## 1. Topologie

```
 clients ── Traefik ──┬── core #1 ─┐
 (TLS, LB, events     └── core #2 ─┤── pgbouncer ── Postgres primaire ══streaming══ Postgres standby
  Docker)                          └── MinIO (distribué, §4)
 worker, cdc-worker, export-worker : 1 instance chacun (§3)
```

| Composant | Réplicas | Mécanisme | Testé |
|---|---|---|---|
| `core` | 2 | Traefik (provider Docker) : un conteneur `die` sort du pool | **oui** (§5) |
| Postgres | primaire + 1 standby | réplication physique en streaming, promotion manuelle | **oui**, conteneurs jetables (§2) |
| MinIO | distribué (4 disques mini) | erasure coding natif | **non** : documenté seulement (§4) |
| `worker`, `cdc-worker`, `export-worker` | 1 | voir §3 | non répliqués |

## 2. Deux instances `core` derrière Traefik

Production (l'overlay prod fait déjà `ports: !reset []` sur `core`, vérifié par `docker compose config`) :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale core=2
```

En dev, `core` publie `8200:8200` : deux réplicas ne peuvent pas partager ce port, il faut l'enlever
(`deploy/ha/docker-compose.ha-test.yml` le fait). Aucun `container_name` n'est fixé, Traefik découvre
chaque réplica par ses labels. `alembic upgrade head` est exécuté par chaque réplica au démarrage :
idempotent, mais **démarrer les réplicas l'un après l'autre** sur une migration lourde (pas de verrou
applicatif de migration).

Test scripté : `HA_PORT_OFFSET=10000 scripts/replay/ha-failover.sh` (projet `arc1-ha`, ports décalés,
Traefik isolé du Traefik d'une éventuelle stack de référence ; `HA_KEEP=1` pour inspecter).

## 3. Invariants à 2 réplicas

- **Jobs (procrastinate)** : `core` ne fait que `.defer()` (file dans Postgres) ; les tâches et les
  balayages `periodic` tournent dans `worker`, indépendants du nombre de `core`. Vérifié : la fumée
  complète (import, run de pipeline, export d'app, lien de partage) passe avec 2 `core`. **Non testé** :
  2 `worker` (les `periodic` portent un `queueing_lock`, donc un seul dépôt par échéance en théorie).
- **CSP dynamique (SP-48)** : fichier écrit par le seul `worker` dans le volume `csp-dynamic-conf`, lu
  par Traefik ; `core` n'y touche pas. Invariant tenu quel que soit le nombre de `core`.
- **`cdc-worker`** : mono-writer **par conception** (slot de réplication logique). Ne JAMAIS le passer à 2.
  Perdu = analytique figée jusqu'à son redémarrage (`restart: unless-stopped`), pas de perte de données.
- **Caches process** (`introspection`, requêtes live ArcGIS) : validés par empreinte ou TTL ≤ 30 s ; au pire
  un réplica sert un état périmé de quelques secondes.
- **Limiteur de débit : ÉCART DOCUMENTÉ, NON CORRIGÉ.** `app/ratelimit/limiter.py` est en mémoire par
  process : chaque réplica tient son propre compteur et Traefik répartit en alternance. **Mesuré** :
  groupe `sql` (budget 10/min/appelant), 60 requêtes d'un même `Authorization` à travers Traefik avec
  2 réplicas = **20 acceptées** (1 réplica : 10). Le budget effectif est donc `N x budget`. Le limiteur
  Traefik (`rate-limit`, 100/s, burst 200) est, lui, global. Limiteur partagé (Postgres) = ARC-32.

## 4. Postgres standby et MinIO distribué

**Standby en streaming** (prouvé par `scripts/replay/pg-standby-check.sh` sur 2 conteneurs jetables) :

1. Primaire : `wal_level=replica`, `max_wal_senders>=3`, rôle `REPLICATION`, ligne `pg_hba` `host replication <rôle> <réseau> scram-sha-256`.
2. Standby : `pg_basebackup -h <primaire> -U <rôle> -D <pgdata> -R -X stream` (écrit `standby.signal` + `primary_conninfo`), puis démarrage.
3. Contrôle : `SELECT state, sync_state FROM pg_stat_replication` sur le primaire (`streaming`).
4. Bascule : `pg_ctl promote -D <pgdata> -w` sur le standby, puis repointer `pgbouncer` (hôte `postgis`) et
   redémarrer `core`/`worker`. Le slot de réplication logique du CDC **n'est pas répliqué** (PG16) :
   après bascule, recréer la publication/le slot du `cdc-worker` et laisser la compaction rattraper.
5. L'ancien primaire ne doit jamais redémarrer en l'état (split-brain) : le reconstruire en standby.

**MinIO distribué** : `server http://minio{1...4}/data{1...2}` (image reconstruite `deploy/minio`),
tolère la perte de la moitié des disques en lecture. **Documenté, non exécuté** ici ; les buckets
sauvegardés restent couverts par `deploy/backup` (ARC-19) quel que soit le mode.

## 5. Mesures (2026-10-12, WSL2, machine chargée — ordre de grandeur, pas un SLA)

| Test | Résultat |
|---|---|
| `up --scale core=2` + `stack-smoke.sh` à travers Traefik | passe (`[smoke] OK`) |
| Répartition LB (40 requêtes `/health`) | 44 / 44 (2e passe 23 / 23) requêtes vues par réplica (healthchecks compris) |
| Perte brutale (`docker kill`), client à 50 req/s, connexion neuve par requête | 6 erreurs / 500 ; **fenêtre d'erreurs 2,3 s** (2e passe : 1,3 s) ; plus long trou sans succès 1,07 s ; service rétabli |
| Arrêt propre (`docker stop`) | 4 erreurs / 502 ; **fenêtre 1,2 s** ; trou max 1,07 s ; rétabli |
| Postgres standby, panne du primaire (`kill -9`) sous écriture continue | 0 ligne perdue sur 87 (asynchrone, retard ~1 ms) et sur 93 (`remote_apply`) ; promotion 0,4 s |

Critère ARC-18 « < 5 s » : respecté (fenêtre max 2,3 s). Le trou de ~1 s correspond au `timeout` de 1 s du
client sur une requête collée au réplica mort ; un client avec réessai ne voit rien.

## 6. RPO / RTO annoncés

| Scénario | RPO | RTO |
|---|---|---|
| Perte d'un `core` | 0 | < 5 s (mesuré 2,3 s) |
| Perte du primaire Postgres, standby **asynchrone** | quelques ms de WAL non répliqué (0 observé, **non garanti**) | bascule manuelle : promotion < 1 s + repointage pgbouncer/services + CDC (compter 5-15 min d'opérateur) |
| Idem, standby **synchrone** (`synchronous_standby_names='*'`, `remote_apply`) | 0 pour les commits acquittés | idem ; latence d'écriture +1 RTT, et écritures bloquées si le standby tombe |
| Perte totale du site | dernière sauvegarde (quotidienne, 03 h par défaut : **jusqu'à 24 h**) | **129 s** (machine au repos) à **320 s** (machine chargée par d'autres tâches) mesurés par le drill (ARC-19, `restore.sh` ~44 s, hors récupération de l'archive hors-site et provisionnement de la machine) |

## 7. Corrigés au passage

REV-354 (`CORE_BASE_URL` du worker en production), REV-355 (`install.sh` : profils `export`/`appexport`
=> `CORE_EXPORT_ENABLED`/`CORE_APPEXPORT_ENABLED`), REV-345 (balayage périodique des jobs
`terrain3d`/`tileset3d` zombies, seuil 60 min).

## 8. Hors périmètre (ARC-32)

Limiteur partagé, élection du `cdc-worker`, bascule Postgres automatique (Patroni), MinIO distribué
éprouvé, Helm, support contractuel.
