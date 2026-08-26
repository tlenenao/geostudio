# Runbook — passage en non-root d'un déploiement existant

Note opérationnelle courte, pas un runbook complet. Concerne uniquement une
instance **déjà en production** avec des images antérieures à SP-26 (durci
ensuite avec des utilisateurs non-root, `core/Dockerfile`/
`deploy/qgis-worker/Dockerfile`/`deploy/backup/Dockerfile`) qui met à jour
vers une image portant ce durcissement.

## Pourquoi c'est nécessaire

Docker ne fixe la propriété d'un volume nommé qu'à sa **première** création,
à partir du contenu de l'image qui le monte à ce moment-là. Un volume déjà
peuplé par d'anciennes images tournant en root reste `root:root` : le
nouveau conteneur non-root échoue en `PermissionError` à sa première
écriture, sans rapport avec un bug de l'image elle-même.

## Volumes concernés et correctif

Pour chaque volume nommé ci-dessous, avant de redémarrer avec les nouvelles
images, re-chowner son contenu vers le uid/gid désormais utilisé :

```bash
# backup-archives -> utilisateur `backup` (deploy/backup/Dockerfile, adduser -S)
docker run --rm -v backup-archives:/v alpine chown -R backup:backup /v

# etl-scratch -> uid/gid 1001 (core/Dockerfile `app` ET
# deploy/qgis-worker/Dockerfile `qgis`, fixés au MÊME nombre — SP-26 C1)
docker run --rm -v etl-scratch:/v alpine chown -R 1001:1001 /v
```

Vérifier le uid/gid réellement utilisé par les images en place avant de
lancer ces commandes sur une instance donnée (`docker compose run --rm
<service> id`), au cas où un futur changement d'image de base ferait dériver
ces nombres.

## Ordre recommandé

1. `docker compose pull` (récupère les nouvelles images sans redémarrer).
2. Exécuter les commandes `chown` ci-dessus sur les volumes concernés,
   pendant que l'ancienne stack tourne encore (les volumes nommés existent
   déjà, ils n'ont pas besoin d'être démontés pour être chownés).
3. `docker compose up -d` pour basculer sur les nouvelles images.
