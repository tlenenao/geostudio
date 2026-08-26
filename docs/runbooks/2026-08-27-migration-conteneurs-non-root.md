# Runbook — passage en non-root d'un déploiement existant

Note opérationnelle courte, pas un runbook complet. Concerne uniquement une
instance **déjà en production** avec des images antérieures à SP-26 (durci
ensuite avec des utilisateurs non-root, `core/Dockerfile`/
`deploy/qgis-worker/Dockerfile`/`deploy/backup/Dockerfile`/
`deploy/appexport-runtime-builder/Dockerfile`) qui met à jour vers une image
portant ce durcissement.

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
# backup-archives -> utilisateur `backup`, uid/gid FIXÉS à 1001
# (deploy/backup/Dockerfile, `addgroup -g 1001`/`adduser -u 1001` — revue
# finale SP-26 round 2, N1). Chown NUMÉRIQUE (pas `chown backup:backup`) :
# le nom `backup` n'existe que dans /etc/passwd de l'image geostudio-backup
# elle-même, pas dans l'alpine générique utilisé ici pour le chown — une
# version antérieure de cette commande (`alpine chown -R backup:backup /v`)
# échouait en `chown: unknown user backup` (aucun compte `backup` dans
# l'alpine de base, contrairement à Debian), vérifié empiriquement. Un
# chown par uid numérique n'a besoin d'aucune résolution de nom, donc l'image
# alpine générique suffit.
docker run --rm -v backup-archives:/v alpine chown -R 1001:1001 /v

# etl-scratch -> uid/gid 1001 (core/Dockerfile `app` ET
# deploy/qgis-worker/Dockerfile `qgis`, fixés au MÊME nombre — SP-26 C1)
docker run --rm -v etl-scratch:/v alpine chown -R 1001:1001 /v

# appexport-runtime -> utilisateur `builder`, uid/gid FIXÉS à 1001
# (deploy/appexport-runtime-builder/Dockerfile — revue finale SP-26 round 2,
# N2). Volume partagé en écriture par `appexport-runtime-builder` (son CMD
# fait `cp -r dist-export/* /export-runtime/` en tant que `builder`
# non-root) et monté en lecture seule par `worker` : sans ce chown, le
# premier `cp` sur un volume préexistant root-owned échoue en Permission
# denied, exactement la même classe de panne que backup-archives/
# etl-scratch ci-dessus.
docker run --rm -v appexport-runtime:/v alpine chown -R 1001:1001 /v
```

Les trois volumes utilisent le MÊME nombre (1001) par convention de ce SP,
mais ce n'est pas une contrainte de fonctionnement entre eux — contrairement
à `etl-scratch`, qui DOIT rester au même uid des deux côtés
(`core`/`qgis-worker`) puisqu'ils écrivent tous les deux dans ce volume.
`backup-archives` et `appexport-runtime` n'ont chacun qu'un seul écrivain
non-root ; leur uid pourrait diverger de 1001 sans casser quoi que ce soit,
1001 est juste la valeur choisie pour rester documentable.

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
