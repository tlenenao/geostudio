# 0025 — Routage et isochrones : Valhalla en service externe sous egress

Statut: acceptée
Source : ARC-34 (comparatif FME/ArcGIS Enterprise 2026-10-11 §6.1.2, §3.5) ; précédent `transform.qgis` (GPL) ; garde d'egress SSRF.

## Contexte

L'analyse de réseau (itinéraires, isochrones, zones de service) est absente. pgRouting est GPL-2 (précédent QGIS : exclu). Les données de réseau (OSM) ne sont pas fournies par le produit.

## Décision

- **Valhalla (MIT)** en service externe, profil compose optionnel `routing` (+ sous-chart Helm optionnel) ; l'opérateur fournit les tuiles de routage.
- Module `app/routing/` : `route`, `isochrone`, `service-area`, `matrix` ; appels sous la garde d'egress, timeout et plafonds (points, durée), privilège `analytics.view`, audit de chaque appel.
- Service absent = 503 RFC 7807 lisible, jamais de crash ; rate limit dédié.
- Ops de pipeline et widget « Directions » consomment l'API du cœur, jamais Valhalla directement.

## Conséquences

- Aucune dépendance GPL embarquée ; la qualité du routage dépend des données OSM de l'opérateur.
