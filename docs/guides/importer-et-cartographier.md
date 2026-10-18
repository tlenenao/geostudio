# Importer des données et en faire une carte

## Importer un fichier

1. Dans le **Catalogue**, bouton **Importer un fichier** (ou glisser-déposer).
2. Formats acceptés : GeoJSON, CSV (colonnes lat/lon ou WKT), GeoPackage,
   Shapefile zippé, KML/KMZ, GeoParquet, XLSX, GML/INSPIRE, JSON Lines, ainsi que
   FileGDB/DXF/DGN/MapInfo via GDAL. Les formats exacts de votre version sont
   listés dans le sélecteur de fichier.
3. Donnez un **titre de collection**, lancez l'import. Il s'exécute en tâche de
   fond (barre de progression, bouton **Annuler l'import**) ; la cloche de
   notifications prévient à la fin.

Le résultat est une **collection** : une table PostGIS cloisonnée par tenant
(RLS), avec un schéma détecté (types, clé primaire, géométrie, SRID). Les
coordonnées hors bornes et les géométries invalides sont signalées, pas
silencieusement corrigées. Les quotas de stockage et de collections du tenant
s'appliquent dès l'envoi.

> Une table PostGIS déjà présente peut aussi être **enregistrée** comme
> collection (Administration → Collections), sans copie.

## Ouvrir la collection sur une carte

1. **Nouveau → Carte**, puis **Ajouter une couche** et choisissez la collection.
   Les tuiles vectorielles sont servies par le cœur, sous vos droits.
2. **Symbologie** : couleur unique, catégorielle, continue ou classée
   (quantiles, intervalles égaux, Jenks) ; contour, opacité et icônes pilotés
   par une colonne ; étiquettes multi-champs.
3. **Popup** : gabarit Markdown avec expressions (`{{ properties.nom }}`),
   pièces jointes de l'entité.
4. **Enregistrer** : la carte devient un objet du catalogue, versionné (historique
   et retour arrière dans *Historique*).

## Partager

Depuis la fiche d'un objet : partager avec un **groupe**, ou **publier** pour une
URL publique anonyme. Les droits (lire, écrire, supprimer, partager) sont calculés
par le cœur pour chaque utilisateur ; un lien de partage peut avoir une échéance.
Voir [administration et rôles](administration-et-roles.md).

## Aller plus loin

- Interroger la collection : OGC API Features sur `/v1/collections/{id}/items`
  (filtres `bbox`, `datetime`, `sortby`, `crs`).
- Agréger sans SQL : requête visuelle *Filtrer → Joindre → Résumer*.
- Mettre la donnée à jour automatiquement : [pipelines](pipelines.md).
