# 0018 — OWS (WFS 2.0, OGC API Tiles) servis par le cœur, sans sidecar GPL

Statut: acceptée
Source : ARC-11 (comparatif FME/ArcGIS Enterprise 2026-10-11 §6.1.2) ; A3 (RLS), A4/ADR 0004 (OGC API Features), A12, ADR 0012 ; précédent : retrait de `transform.qgis` (GPL-2.0).

## Contexte

QGIS Desktop et ArcGIS Pro consomment WFS. GeoStudio moissonne déjà WFS (ADR 0012) mais ne l'expose pas. Les serveurs OWS usuels (GeoServer, GPL-2.0) lisent PostGIS directement, hors `rls_scope`, et ont déjà posé un problème de licence avec QGIS.

## Décision

- Module `core/app/ows/` (couche `features` → `ows`, entrée `lint-imports`) : WFS 2.0 lecture (GetCapabilities, DescribeFeatureType, GetFeature en GML 3.2 et GeoJSON) sous `/v1/ows/wfs`, et OGC API Tiles (MVT) sous `/v1/collections/{id}/tiles/{tms}/{z}/{x}/{y}`.
- **Mêmes `rls_scope` et `can()`** que l'API Features, **même masquage de champs sensibles** (GAP-22) : aucun accès SQL direct hors de la portée de lecture existante.
- Activation **par collection**, désactivée par défaut ; le flag d'instance est câblé dans le compose par valeur (piège n°2) et la capacité est absente quand il est éteint.
- WMS/WMTS (ARC-20, Vague 3) relèvent d'une décision séparée : renderer interne recommandé, MapServer (MIT) derrière proxy authentifié sans accès base en alternative ; aucun GeoServer.

## Conséquences

- Pas de nouvelle dépendance GPL ; une seule porte d'autorisation.
- Sous-ensemble WFS assumé (lecture seule, pas de WFS-T) ; validation par fixtures XML contre les schémas OGC et chargement réel dans QGIS.
