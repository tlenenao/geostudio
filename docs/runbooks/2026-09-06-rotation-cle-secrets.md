# Runbook — rotation de la clé maître des secrets connecteurs

**Date** : 2026-09-06
**Ferme** : GAP-75 (aucune procédure de rotation de la clé maître).
**Documents liés** : `docs/superpowers/specs/2026-09-06-sp59-exploitation-sauvegarde-oidc-design.md`
(§3.1, §3.1.1, §5), `docs/superpowers/specs/2026-08-06-sp15e-connector-secrets-store-design.md`
(§9).

## Ce que fait ce script, ce qu'il ne fait pas

`core/scripts/rotate_secrets_master_key.py` déchiffre l'intégralité des
secrets connecteurs (`connector_secrets`, tous tenants) avec l'ancienne clé
maître, les rechiffre avec la nouvelle, en une transaction atomique
(`app.secrets.rotation.rotate_all_secrets` — voir §3.1 de la spec pour la
garantie exacte : toute ligne déchiffrée avec succès avant qu'aucune ne soit
réécrite ; un échec de déchiffrement abandonne l'opération entière sans avoir
touché la base).

**Ce script ne peut structurellement pas redémarrer le service `core`**
lui-même : il tourne comme un processus ponctuel, séparé du service vivant.
`CORE_SECRETS_MASTER_KEY` est lue par `core` à chaque appel de
`encrypt()`/`decrypt()`, sans cache — mais depuis la variable d'environnement
du **processus** `core`, qui ne change qu'à son redémarrage. D'où la
procédure en plusieurs étapes ci-dessous, avec une fenêtre de risque assumée
entre l'étape 3 (rotation en base) et l'étape 5 (redémarrage de `core`).

**Ni `CORE_SECRETS_MASTER_KEY_NEW` ni ce script ne sont câblés dans
`docker-compose.yml`/`.env.example`** — volontairement. Ce n'est pas une
capacité de service instance-wide (contrairement à `CORE_QUOTAS_ENABLED` et
consorts, patron déjà établi par SP-58) : c'est un paramètre d'une commande
ponctuelle que l'opérateur fournit lui-même au moment de l'exécuter, du même
patron exact que `DATABASE_URL` pour `scripts/seed_demo.py`. Ne pas s'étonner
de son absence du compose dans une session future — ce n'est pas un oubli.

## Procédure

1. **Générer la nouvelle clé** (même incantation que
   `scripts/bootstrap-env.sh`) :

   ```bash
   openssl rand -base64 32
   ```

2. **`--dry-run` d'abord** — confirme que tout secret existant déchiffre
   correctement avec l'ancienne clé actuellement en `.env`, et que la
   nouvelle clé décode correctement (32 octets), sans rien écrire :

   ```bash
   DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5432/gis \
   CORE_SECRETS_MASTER_KEY="<clé actuelle>" \
   CORE_SECRETS_MASTER_KEY_NEW="<nouvelle clé>" \
   uv run python -m scripts.rotate_secrets_master_key --dry-run
   ```

   Ou, via le service `core` déjà construit (mêmes variables en `-e`) :

   ```bash
   docker compose run --rm \
     -e CORE_SECRETS_MASTER_KEY_NEW="<nouvelle clé>" \
     --entrypoint python core -m scripts.rotate_secrets_master_key --dry-run
   ```

3. **Exécuter la rotation réelle** (sans `--dry-run`) — une seule transaction,
   commit unique en fin de run, rollback automatique de la session sur toute
   exception avant ce commit (aucun état intermédiaire ne peut être
   persisté) :

   ```bash
   docker compose run --rm \
     -e CORE_SECRETS_MASTER_KEY_NEW="<nouvelle clé>" \
     --entrypoint python core -m scripts.rotate_secrets_master_key
   ```

   Le résumé affiché donne le nombre de secrets rechiffrés par tenant et le
   total.

4. **Seulement après un succès confirmé** (le script s'est terminé sans
   erreur, résumé affiché) : remplacer la valeur de
   `CORE_SECRETS_MASTER_KEY` dans `.env` par la nouvelle clé, retirer
   `CORE_SECRETS_MASTER_KEY_NEW` (il n'a plus d'usage).

5. **Redémarrer `core`** :

   ```bash
   docker compose up -d core
   ```

6. **Vérifier** : consommer réellement un secret existant — par exemple
   déclencher un pipeline `reader.connector` qui l'utilise — **pas**
   seulement `GET /secrets`, qui liste les métadonnées mais ne déchiffre
   jamais (cf. docstring de `app/secrets/repository.py::get_secret_payload`
   et le module `app/secrets/routes.py`).

7. **Fenêtre de risque assumée et documentée** : entre l'étape 3 (commit en
   base avec la nouvelle clé) et l'étape 5 (redémarrage effectif de `core`),
   tout pipeline qui tenterait de consommer un secret échouerait en
   déchiffrement (le processus `core` encore vivant tente toujours l'ancienne
   clé). **Recommandation explicite** : effectuer cette rotation hors d'une
   fenêtre d'exécution planifiée de pipelines (cron des `PipelineSchedule`).
   Ce risque n'est pas éliminé par construction — une rotation « à chaud »
   (double lecture de clé côté `core` vivant, ancienne+nouvelle, le temps
   d'une fenêtre de transition) est explicitement hors périmètre de ce
   chantier (spec §2.2) : compromis jugé acceptable pour un opérateur unique
   aujourd'hui.

## Ce que ce runbook ne couvre pas

- Rotation automatique planifiée (cron) — hors périmètre (même décision que
  SP-15e §2).
- Intégration KMS/Vault — hors périmètre.
- Un crash **entre** la fin du rechiffrement en mémoire et le commit final
  perd tout le travail (acceptable, rejouable sans dommage : aucune ligne
  n'a encore changé en base). Un crash **après** le commit mais avant que
  l'opérateur ne swap `.env` laisse la base sur la nouvelle clé et `core`
  vivant sur l'ancienne — c'est exactement la fenêtre de risque de l'étape 7,
  pas un défaut supplémentaire.
