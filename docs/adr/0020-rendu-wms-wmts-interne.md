# 0020 — WMS 1.3.0 / WMTS 1.0.0 : renderer interne du cœur, sans sidecar GPL

Statut: acceptée
Source : ARC-20 (comparatif FME/ArcGIS Enterprise 2026-10-11 §6.1.2) ; ADR 0018 (OWS), A3 (RLS), A12 ; précédent : retrait de `transform.qgis` (GPL-2.0).

## Contexte

QGIS et ArcGIS Pro consomment WMS/WMTS. Les serveurs usuels (GeoServer, GPL-2.0) lisent PostGIS hors `rls_scope` et posent un problème de licence.

## Décision

- Les couches WMS/WMTS sont **rendues par le cœur** (module `app/ows/`, extension de l'ADR 0018), à partir de la symbologie déclarative (export de style d'ARC-28 comme représentation intermédiaire) et des données lues **par `select_features`/`rls_scope`** : mêmes `can()`, limites géographiques et masquage de champs que l'API Features.
- Renderer Python interne (pas de sidecar GPL, pas d'accès direct à PostGIS hors portée de lecture). Plafond d'entités par tuile/requête, délai borné, rendu raster 256×256 < 300 ms p95 pour les couches nominales.
- Activation par collection et par flag d'instance (même mécanisme que WFS). WMTS raster dérivé du même renderer, pas des tuiles MVT.
- Alternative écartée : MapServer (MIT) derrière proxy authentifié — à rouvrir seulement si le renderer interne n'atteint pas la perf cible, et sans accès base direct.

## Conséquences

- Sous-ensemble assumé : couches vectorielles, styles issus de la symbologie déclarative ; pas de SLD arbitraire en entrée.
