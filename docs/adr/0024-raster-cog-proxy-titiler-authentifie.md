# 0024 — Raster : COG seul en entrée, TiTiler derrière un proxy authentifié par `can()`

Statut: acceptée
Source : ARC-33 (comparatif FME/ArcGIS Enterprise 2026-10-11 §6.1.2, §3.1/§3.5) ; Q2 (produit horizontal) ; ADR 0001 (`can()`), SP-32 (passerelle admin), SP-40 (S3 présigné), SP-58 (quotas).

## Contexte

GeoStudio n'a aucun support raster : TiTiler existe en compose mais n'est pas exposé. Esri propose Image Server et l'analyse raster. Le produit horizontal (Q2) justifie un minimum utile : servir des rasters et en tirer des statistiques de zone.

## Décision

- **Entrée : COG uniquement** (GeoTIFF Cloud Optimized). Un TIFF non COG est converti par un job de validation/conversion ; les autres formats raster restent hors périmètre.
- Stockage S3 (bucket dédié, quotas SP-58) ; emprise, SRID, bandes et statistiques persistés sur l'item.
- **TiTiler n'est jamais exposé** : réseau interne seulement. Le cœur sert `GET /v1/raster/{item}/tiles/...` en proxy, sous `can()` + limites géographiques ; aucune URL S3 présignée n'est transmise au client pour les tuiles.
- Statistiques par zone (`zonal-stats`) calculées par le cœur (rasterio, BSD) avec plafond de polygones ; outil dans le widget Analyse (ARC-25) et MCP.
- Licences : rasterio/GDAL (BSD/MIT) ; aucune dépendance GPL/AGPL.

## Conséquences

- Une seule porte d'accès aux pixels. Le raster n'est pas couvert par le RLS PostGIS : l'autorisation est celle de l'item (`can()`).
- Pas de mosaïque, pas de raster analytics complet (hors périmètre).
