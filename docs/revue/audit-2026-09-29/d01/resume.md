# d01 — Benchmark produit

Périmètre couvert : Felt, ArcGIS Experience Builder/Online, QGIS Server, CARTO/Kepler, FME ; recoupé avec docs/vision, l'audit pré-release, GAP/REV déjà connus (gaps connus référencés via related_gap, non dupliqués).
Non couvert : essais utilisateur des concurrents (sources publiques uniquement), Kepler.gl seul (recherche sans résultat spécifique), chiffrage précis.
Méthode : lecture des docs du dépôt, 6 WebSearch (2026), greps de vérification (pas d'op MCP, pas de géocodage, pas de WMS servi côté cœur). Tous les findings sont doc-read, probable/hypothesis, sans location.
Positionnement respecté : aucune proposition ne contredit les arbitrages §8 (A4, A20, A32 explicitement préservés).
Commandes : grep sur core/app et shell/src ; validateur audit_findings.py.
