# Redistribution des images publiées

GeoStudio publie 8 images sur `ghcr.io/tlenenao/` à chaque tag `v*`
(cf. `.github/workflows/release.yml`) : `geostudio-core`, `geostudio-shell`,
`geostudio-postgis`, `geostudio-appexport-standalone`,
`geostudio-export-worker`, `geostudio-qgis-worker`,
`geostudio-appexport-runtime-builder`, `geostudio-backup`. Sept d'entre
elles ne contiennent que du code GeoStudio (Apache-2.0) et des dépendances
permissives.

## `geostudio-qgis-worker` — contient du GPL

Cette image dérive de `qgis/qgis:release-3_34` (QGIS 3.34.5 « Prizren »,
LTR) et contient **QGIS** et **GRASS GIS**, sous GPL-2.0-or-later. La
publier est un acte de distribution : l'image embarque `/LICENSE-QGIS.md`
(notice + pointeurs vers les sources amont) et porte les labels OCI
correspondants.

GeoStudio ne modifie pas les sources de QGIS ni de GRASS ; la seule
opération appliquée par-dessus l'image amont est l'activation du plugin
`grassprovider` (réglage de configuration, livré désactivé par défaut dans
l'image amont). Les deux seuls fichiers ajoutés (`server.py`,
`allowlist.txt`) sont publics dans ce dépôt sous Apache-2.0 : l'offre de
source est donc satisfaite par référence, forme usuelle pour une image
dérivée sans modification de l'amont.

**Ce que cela ne change pas** : le cœur GeoStudio (`core/`) reste
Apache-2.0. Il n'est pas lié à QGIS — il appelle ce conteneur en HTTP, isolé,
sans credential de base de données ni accès réseau externe (arbitrage A39).
La capacité est de surcroît éteinte par défaut (`CORE_ETL_ENABLED=false`,
profil compose `etl`).

## Avant d'ajouter une image à la matrice de release

Vérifier la licence de l'image de base. Si elle est copyleft, ajouter ici sa
section et embarquer une notice dans l'image, comme ci-dessus.
