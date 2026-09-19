# SPDX-License-Identifier: Apache-2.0
"""Échange DuckDB↔futurs moteurs natifs — Arrow zéro-copie + GeoParquet
natif en repli (design docs/superpowers/specs/
2026-09-16-ipc-echange-duckdb-arrow-design.md). Suite d'OperationContract
(docs/superpowers/specs/2026-09-16-operation-contract-design.md) : pose le
seam d'échange (champ OperationContract.exchange, app.pipelines.ops.
contracts) qu'un futur chantier "premier moteur natif" consommera — QGIS
(transform.qgis) reste explicitement hors périmètre, son échange fichier
GPKG (app.pipelines.runtime._execute_qgis_transform/_materialize_qgis_
output) n'est pas unifié avec ce module (aucun driver Parquet/Arrow dans le
GDAL 3.4.1 embarqué par l'image qgis/qgis:release-3_34, vérifié
empiriquement — design §1).

Round-trip jamais invoqué depuis app.pipelines.runtime dans ce chantier :
aucun moteur natif n'a de binding installé ici pour le consommer (design
§1/§2, hors périmètre explicite). Validé uniquement par ses propres tests
unitaires (tests/test_pipeline_exchange.py)."""

import duckdb
import pyarrow

from app.cdc.parquet_writer import write_geoparquet_from_relation
from app.pipelines.errors import PipelineRuntimeError
from app.sql_ident import quote_ident_duckdb as _qi


def _geometry_column(relation: duckdb.DuckDBPyRelation, *, fn_label: str) -> str:
    """Détection par TYPE DuckDB (GEOMETRY), jamais par nom de colonne —
    même garantie que app.pipelines.runtime._materialize_reader/
    _materialize_qgis_output. Une seule colonne géométrie attendue (même
    contrat qu'une collection) : en cas de pluralité inattendue, la
    première suffit à ne jamais perdre la géométrie silencieusement. Les
    colonnes géométrie NON sélectionnées (au-delà de la première) traversent
    malgré tout Arrow/GeoParquet comme n'importe quelle autre colonne — sans
    ST_SetCRS ni décodage WKB, elles atterrissent comme valeurs opaques
    non-géométrie (binaire brut côté Arrow, colonne non convertie côté
    GeoParquet) plutôt que d'être reconnues comme géométrie secondaire."""
    geom_cols = [d[0] for d in relation.description if d[1].id == "geometry"]
    if not geom_cols:
        raise PipelineRuntimeError(f"{fn_label} : la relation ne porte aucune colonne géométrie")
    return geom_cols[0]


def _coerce_srid(srid: object, *, fn_label: str) -> int:
    """Coercition stricte, appelée par les deux chemins publics (Arrow et
    GeoParquet) avant toute interpolation SQL ou tout calcul de CRS.

    Durcissement REV-192 : `srid` était annoté `int` mais jamais vérifié à
    l'exécution. Vérifié empiriquement avant correctif : une chaîne non
    numérique (ex. "abc") ou `None` ne levait aucune erreur — `to_arrow_stream`
    l'interpolait telle quelle dans le littéral SQL `'EPSG:{srid}'` et
    produisait silencieusement des métadonnées CRS bidon
    (`{"crs_type": "authority_code", "crs": "EPSG:abc"}`). `srid<=0` révélait
    en plus une divergence entre chemins : 0 produisait "EPSG:0" (bidon) côté
    Arrow mais `crs=None` côté GeoParquet (falsy court-circuite `if srid`
    dans build_geodataframe_from_relation) ; -1 produisait "EPSG:-1" (bidon)
    côté Arrow mais une `pyproj.exceptions.CRSError` non contrôlée côté
    GeoParquet. `int(srid)` lève un `TypeError`/`ValueError` clair pour toute
    valeur non convertible, avant que quoi que ce soit ne touche DuckDB ou
    pyproj."""
    srid_int = int(srid)  # type: ignore[call-overload]  # coercition volontaire, cf. docstring
    if srid_int <= 0:
        raise PipelineRuntimeError(f"{fn_label} : srid invalide ({srid_int}), doit être positif")
    return srid_int


def to_arrow_stream(relation: duckdb.DuckDBPyRelation, *, srid: int) -> pyarrow.RecordBatchReader:
    """Chemin 1 (design §3) : zéro-copie, pour un moteur lié in-process
    (binding Python/Rust acceptant l'interface Arrow C Data). Force
    ST_SetCRS sur la colonne géométrie avant .arrow() — sans lui, le CRS
    embarqué dans les métadonnées Arrow de la colonne reste vide ({}),
    vérifié empiriquement (design §1).

    Schéma de sortie (revue finale de branche, Important #3) : la colonne
    géométrie CONSERVE son nom d'origine mais est déplacée en dernière
    position — contrairement à to_geoparquet_file, qui la renomme
    "geometry" (convention GeoPandas/GeoParquet). Les deux chemins ne
    produisent donc PAS le même schéma pour une même relation source ; un
    futur consommateur qui bascule d'un OperationContract.exchange à
    l'autre doit s'attendre à ce nom de colonne différent."""
    srid = _coerce_srid(srid, fn_label="to_arrow_stream")
    geom_col = _geometry_column(relation, fn_label="to_arrow_stream")
    other_cols = [c for c in relation.columns if c != geom_col]
    select_list = ", ".join(
        [_qi(c) for c in other_cols]
        + [f"ST_SetCRS({_qi(geom_col)}, 'EPSG:{srid}') AS {_qi(geom_col)}"]
    )
    return relation.select(select_list).arrow()


def from_arrow_stream(
    conn: duckdb.DuckDBPyConnection, reader: pyarrow.RecordBatchReader, *, view_name: str
) -> None:
    """Symétrique de to_arrow_stream, sans jamais passer par un fichier —
    enregistre le flux Arrow comme TEMP TABLE DuckDB. Un RecordBatchReader
    ne peut être consommé qu'une seule fois : appeler cette fonction deux
    fois avec le même reader échoue ou renvoie une table vide au second
    appel, jamais garanti — aucune garde runtime ici, cohérent avec le fait
    qu'aucun code d'exécution réel n'appelle encore cette fonction dans ce
    chantier (design §4).

    IMPORTANT, vérifié empiriquement (absent du design, trouvé en écrivant
    ce plan) : `conn` doit être une connexion DuckDB DIFFÉRENTE de celle qui
    a produit la relation passée à `to_arrow_stream` pour obtenir `reader`.
    Enregistrer sur une connexion un RecordBatchReader non drainé produit
    par CETTE MÊME connexion, puis exécuter une requête dessus, deadlocke
    `conn.execute()` indéfiniment (pas une erreur, un vrai blocage,
    reproduit sous `timeout`).

    Mécanisme précis (corrigé en revue finale de branche, Minor #4 — la
    formulation précédente était trop large) : ce n'est PAS qu'une
    connexion refuse toute nouvelle requête tant qu'un flux Arrow issu
    d'elle traîne quelque part (une requête simple sur la connexion source
    pendant que `reader` reste non drainé ailleurs s'exécute normalement,
    vérifié). Le blocage est spécifique à l'auto-référence : enregistrer
    sur une connexion un flux produit par CETTE MÊME connexion, PUIS
    exécuter une requête qui lit ce flux SUR CETTE CONNEXION. Aucune garde
    runtime possible ici : un RecordBatchReader ne permet pas d'introspecter
    la connexion DuckDB qui l'a produit. Dans l'usage visé (design §3,
    chemin 1), ce n'est normalement jamais un problème : le binding du
    futur moteur consomme entièrement `reader` avant de renvoyer un NOUVEAU
    RecordBatchReader en sortie, non lié à la connexion source."""
    tmp_name = f"__exchange_arrow_src_{view_name}"
    conn.register(tmp_name, reader)
    try:
        conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT * FROM {_qi(tmp_name)}")
    except duckdb.CatalogException as exc:
        raise PipelineRuntimeError(
            f"from_arrow_stream : view_name {view_name!r} existe déjà"
        ) from exc
    finally:
        conn.unregister(tmp_name)


def to_geoparquet_file(relation: duckdb.DuckDBPyRelation, *, srid: int, path: str) -> None:
    """Chemin 2 (design §3) : repli GeoParquet, pour un moteur qui reste un
    process séparé mais comprend Parquet.

    Corrigé en revue finale de branche (Important #1) : ce chemin n'utilise
    PAS l'écriture Parquet native de DuckDB (`COPY ... TO ... (FORMAT
    PARQUET)`, qui existe et streamerait sans jamais matérialiser la
    relation côté Python — vérifié faisable, mais non retenu ici). Il
    délègue à write_geoparquet_from_relation (app.cdc.parquet_writer), qui
    fait `relation.select(...).fetchall()` puis construit un
    gpd.GeoDataFrame ligne par ligne avant `to_parquet` — la relation
    ENTIÈRE est donc matérialisée en mémoire Python, pas streamée. Ce choix
    est délibéré (cf. plan, section "Décision prise en amont") : il
    garantit la convergence sur une seule primitive d'écriture réelle
    (_write_gdf) avec le chemin CDC existant, au prix de cette limite de
    passage à l'échelle — à réévaluer par le futur chantier "premier moteur
    natif" si un besoin de très grands volumes se présente sur ce chemin
    précisément (le chemin 1, to_arrow_stream, reste un flux paresseux).
    Renomme aussi la colonne géométrie en "geometry" (cf. to_arrow_stream,
    qui garde le nom d'origine) : les deux chemins ne sont pas
    interchangeables schéma pour schéma."""
    srid = _coerce_srid(srid, fn_label="to_geoparquet_file")
    geom_col = _geometry_column(relation, fn_label="to_geoparquet_file")
    write_geoparquet_from_relation(relation, srid=srid, geometry_column=geom_col, path=path)
