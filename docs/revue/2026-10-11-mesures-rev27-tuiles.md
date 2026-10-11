# Mesures REV-283 — agrégation de tuiles z5 (voie E-bis-1), 2026-10-11

Collection : 500 000 points WGS84 aléatoires sur la France (`query_711aa0877d9a`, index GiST), tuile z5/16/11 :
237 035 points dans l'enveloppe, 180 cellules. Machine chargée (load average 13 à 18 pendant les mesures,
autres voies actives) : les valeurs absolues sont gonflées, seuls les rapports comptent.

## Où va le temps (EXPLAIN ANALYZE de `build_agg_mvt_sql`)

- Sonde bornée et GiST : pas en cause (index scan bitmap ~290 ms à froid, 85 ms en `count(*)` chaud).
- Coût par ligne : `ST_Transform` par point (~130 ms de l'exécution) + tri/regroupement ; `ST_PointOnSurface` ~ 40 ms.
- **JIT** : le coût planifié (~1,1e7, gonflé par `ST_Transform`) dépasse `jit_above_cost` : PostgreSQL compile
  (inlining + optimisation + émission) 600-700 ms pour une exécution de ~250-500 ms. Le JIT ne sert à rien sur une tuile.
- RLS / `can()` : pas mesurés comme dominants (tuile vide ~165 ms = surcoût fixe auth + introspection).

## Correctif

`apply_tile_statement_timeout` pose aussi `set_config('jit','off',true)` (transaction-locale, même requête,
aucun aller-retour de plus). Couvre les deux requêtes (tuile brute et agrégée).

## Avant / après (même requête, EXPLAIN ANALYZE, alternés, charge ~17)

| jit | exécutions (ms) | JIT inclus |
|---|---|---|
| on (avant) | 703, 1012, 696, 710 | 608-676 ms |
| off (après) | 457, 464, 515, 509 | 0 |

Médiane 710 -> 487 ms (-31 %). Premier passage à froid : 1015 -> 244 ms mesuré lors de l'investigation.
En `\timing` sans EXPLAIN la différence est noyée par la charge (615-830 ms de part et d'autre) : gain réel
mais modeste ; **il ne suffit pas à lui seul à garantir t03 < 2 s**.

## Levier restant (non fait, un seul correctif demandé)

Grouper sans `ST_Transform` par ligne quand `srid = 4326` et géométrie ponctuelle (x de Mercator linéaire en lon,
y = R·ln tan(π/4+φ/2)) : mesuré 131-145 ms contre ~245 ms (jit off), soit encore ~-45 %. Non fait : demande un chemin
SQL distinct (points 4326) à tester contre la variante polygones.

## Garde de non-régression

`test_a_tile_request_disables_jit_transaction_locally` (`core/tests/test_features_tiles_postgis.py`) : `SHOW jit == off`
pendant la requête, absent après la transaction. Falsifié (jit `on` dans le code : test rouge). Propriété de
configuration, pas une durée (piège n°7). Base dédiée `rev27_ebis`.

## Rejeu t03

Stack levée mais l'image `core` tourne l'ancien code : t03 à rejouer en Z après reconstruction, seuil de 2 s inchangé.

## E-bis-3 — chemin « points WGS84 » sans ST_Transform par ligne (2026-10-11)

`build_agg_mvt_sql` : si `info.srid == 4326` ET `info.geometry_type == "Point"`, la cellule de grille se calcule
directement en Mercator par formule (`x = lon·20037508.34/180`, `y = R·ln tan(π/4+φ/2)`) ; plus de `ST_Transform` ni
`ST_PointOnSurface` par ligne (les centres de cellule sont déjà en 3857, aucune transformation à faire). Le filtre
d'enveloppe (`&&` indexable, transformé une seule fois) est inchangé. Polygones, lignes, multipoints et autres SRID
gardent l'ancien chemin.

Mesure : 500 000 points aléatoires 4326 (France), index GiST, tuile z5/16/11, `EXPLAIN (ANALYZE)` alternés ancien/nouveau,
5 passes, jit off, machine très chargée (load ~19) : valeurs absolues gonflées.

| chemin | exécutions (ms) | médiane |
|---|---|---|
| ancien (ST_Transform par ligne) | 1357, 1229, 1260, 2664, 1733 | 1357 |
| nouveau (formule Mercator) | 537, 438, 831, 578, 692 | 578 |

Rapport ~2,3x (-57 %). Équivalence : `test_features_tiles_agg_points_postgis.py` compare les cellules (comptes
identiques, centres à <= 1 px de tuile) entre les deux chemins sur 3000 points fixes ; falsifié (facteur lon/170 : rouge).
