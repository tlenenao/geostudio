# 0003 — RLS PostGIS différée à SP-3, sur les données métier seulement

Statut: acceptée
Source : `docs/vision/2026-07-04-feuille-de-route-geostudio.md` §7, A3 —
Row-Level Security PostGIS : quand ? (SP-1 vs SP-3)

## Contexte

La Row-Level Security PostGIS pourrait protéger soit les tables internes du
cœur dès SP-1, soit seulement les données métier (tables de collections)
plus tard, quand d'autres clients que le cœur (Martin, DuckDB) commencent à
les lire directement.

## Décision

Pas de RLS en SP-1 ; RLS générée par collection à partir de SP-3, sur les
données métier seulement — jamais sur les tables internes du cœur (users,
items, shares…), qui restent protégées par `can()` (ADR-0001).

## Conséquences

- Fenêtre en SP-1/SP-2 où l'enforcement sur les données métier est purement
  applicatif (le cœur est alors l'unique client de sa base).
- À partir de SP-3, deux logiques de contrôle d'accès coexistent (`can()` +
  politiques RLS générées) — à garder cohérentes à chaque évolution du
  modèle de partage.
- Martin (tuiles) doit à terme passer par des vues ou un rôle par tenant pour
  que la RLS serve aussi les tuiles — non résolu par cet ADR seul (traité
  par SP-24, tuiles vectorielles servies par le cœur sous `rls_scope`).
