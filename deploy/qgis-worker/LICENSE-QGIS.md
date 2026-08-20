# Licences des composants de cette image

Cette image est publiée par le projet GeoStudio (Apache-2.0) et **contient
des logiciels sous GNU GPL** :

- **QGIS** (`qgis/qgis:release-3_34`, QGIS 3.34.5 « Prizren », LTR) —
  GPL-2.0-or-later. Sources amont : <https://github.com/qgis/QGIS>, tag
  correspondant à QGIS 3.34.5.
- **GRASS GIS** (fourni par l'image amont, plugin `grassprovider` activé) —
  GPL-2.0-or-later. Sources amont : <https://github.com/OSGeo/grass>.

GeoStudio ne modifie pas les sources de QGIS ni de GRASS. La seule opération
appliquée par-dessus l'image amont sur ces logiciels est l'activation du
plugin QGIS `grassprovider` (`qgis_process plugins enable grassprovider`),
livré avec l'image amont mais désactivé par défaut — un réglage de
configuration, pas une modification de code. Les seuls fichiers ajoutés par
GeoStudio par-dessus l'image amont sont `server.py` et `allowlist.txt`,
publiés sous Apache-2.0 dans le dépôt GeoStudio
(<https://github.com/tlenenao/geostudio>, `deploy/qgis-worker/`).

Les termes GPL s'appliquent à QGIS et GRASS tels que distribués ici. Le
cœur de GeoStudio (`core/`) reste sous Apache-2.0 : il n'est pas lié à QGIS,
il dialogue avec ce conteneur par HTTP, en sous-processus isolé et sans
credential (arbitrage A39).
