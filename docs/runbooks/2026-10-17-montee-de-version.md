# Runbook — monter de version une instance compose (production)

Cible : une instance installée par `scripts/install.sh` (overlay
`docker-compose.prod.yml`, images `ghcr.io/tlenenao/geostudio-*` épinglées
par `GEOSTUDIO_VERSION` dans `.env`). Pour Kubernetes, voir
[`2026-10-12-deploiement-kubernetes-helm.md`](2026-10-12-deploiement-kubernetes-helm.md)
(migrations en hook `pre-upgrade`).

La montée de version **coupe le service** quelques dizaines de secondes à
quelques minutes : le conteneur `core` applique `alembic upgrade head` avant
de servir. Une mise à jour sans interruption n'est pas outillée (AUD-033).

```bash
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
```

## 1. Avant

1. Lire `CHANGELOG.md` entre la version en place et la cible : ruptures,
   variables d'environnement nouvelles (à reporter dans `.env` depuis
   `.env.example`), migrations longues annoncées.
2. Noter la version en place : `grep ^GEOSTUDIO_VERSION= .env` (aussi
   affichée dans le pied de page du shell et dans `GET /api/v1/me`).
3. **Sauvegarde fraîche**, et vérifier qu'elle est complète :

   ```bash
   $COMPOSE run --rm --entrypoint /usr/local/bin/backup.sh backup
   $COMPOSE run --rm --entrypoint sh backup -c 'ls -l /backup/archives | tail -n 3'
   ```

   Code de sortie 0 attendu (75 = archive locale écrite mais envoi hors-site
   en échec : acceptable pour une montée de version, à corriger ensuite).

## 2. Monter

```bash
sed -i 's/^GEOSTUDIO_VERSION=.*/GEOSTUDIO_VERSION=vX.Y.Z/' .env
$COMPOSE pull
$COMPOSE up -d
```

Relancer ensuite `./scripts/install.sh` (idempotent) si la version cible
modifie le realm Keycloak : Keycloak n'importe le fichier realm qu'au tout
premier démarrage, l'installeur resynchronise les réglages qui comptent
(URLs de redirection, comptes de démonstration désactivés, flux mot de passe
fermé sur le client du shell).

## 3. Vérifier

```bash
$COMPOSE ps                                   # tout `healthy`
$COMPOSE exec core alembic current            # = tête annoncée par la version cible
$COMPOSE logs --since 10m core worker | grep -iE 'error|traceback' || true
```

Puis dans le navigateur : connexion, catalogue, ouverture d'une carte et
d'une app ; le pied de page affiche la nouvelle version.

## 4. Revenir en arrière

Les images se rétrogradent, **le schéma de base non** : `core` a déjà appliqué
les migrations de la version cible et l'ancienne image ne connaît pas ces
révisions.

- **Chemin sûr** : remettre l'ancien `GEOSTUDIO_VERSION` dans `.env`, puis
  restaurer la sauvegarde de l'étape 1 selon
  [`2026-07-24-restauration-sauvegardes.md`](2026-07-24-restauration-sauvegardes.md)
  (perte des écritures faites depuis la montée).
- **Sans restauration** (seulement si toutes les migrations ajoutées ont un
  `downgrade()` et qu'aucune donnée n'a été écrite dans les nouvelles
  colonnes) : avant de changer l'image, avec la NOUVELLE image encore en place,
  `$COMPOSE exec core alembic downgrade <révision de l'ancienne version>`,
  puis remettre l'ancien tag et `$COMPOSE up -d`.
