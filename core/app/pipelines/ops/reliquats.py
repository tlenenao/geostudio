# SPDX-License-Identifier: Apache-2.0
"""Module de voie S — reliquats FME qui dépendent du modèle de pipeline.
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md.

- `transform.removeSrid` (CoordinateSystemRemover) et `transform.localCoordinateSystem`
  (LocalCoordinateSystemSetter) : introduisent le SRID 0 = « non défini » (convention PostGIS)
  dans le modèle de pipeline. Garde-fous (voie S) : toute reprojection depuis/vers EPSG:0 échoue
  (PROJ refuse « EPSG:0 ») ; les ops qui repliaient un SRID faux sur 4326 (`input_srid or 4326`)
  refusent explicitement 0 ; writer.collection/writer.dataset refusent un SRID 0 (runtime) ;
  writer.file écrit sans SRS. Deux entrées à SRID 0 sont considérées compatibles par les ops
  binaires (même convention que PostGIS : 0 = 0, à l'auteur du pipeline d'en répondre).
- `transform.databaseJoin` (DatabaseJoiner) : jointure d'une table Postgres externe (secret
  `postgres_dsn`) à l'entrée, lecture distante bornée DANS l'op (clés poussées en `IN (...)`
  paramétré, plafonds de clés et de lignes, garde d'egress + épinglage DNS, délais).
- `writer.topojson` (TopoJSON) : écriture fichier local en Python pur, derrière
  CORE_PIPELINE_FILE_IO_ENABLED (patron writer.file).

Ne jamais importer contracts/runtime/registries au niveau module (cycle d'import)."""

import decimal
import json
import math
import os
import re
import uuid
from collections.abc import Callable
from typing import Literal

import pandas as pd
import shapely
import shapely.wkb
from pydantic import BaseModel, Field, model_validator

from app.auth.dependency import is_pipeline_file_io_enabled
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.operation_contract import OperationContract
from app.sql_ident import quote_ident_duckdb as _qi

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}

_DUCKDB = "MIT (DuckDB)"
UNDEFINED_SRID = 0


def _columns(conn, view: str) -> dict[str, str]:
    return {d[0]: d[1] for d in conn.execute(f"DESCRIBE {_qi(view)}").fetchall()}


# --------------------------------------------------------------------------- SRID 0


class TransformRemoveSridParams(BaseModel):
    """Retire le système de coordonnées du flux SANS toucher aux coordonnées : le SRID devient
    0 (« non défini »). Toute reprojection ultérieure est refusée tant qu'un SRID n'est pas
    réassigné (transform.setSrid ou transform.localCoordinateSystem) ; l'écriture dans une
    collection est refusée, writer.file écrit le fichier sans système de coordonnées."""


def _compile_passthrough(params: dict, *, input_view: str, join_view=None, input_srid=None) -> str:
    return f"SELECT * FROM {_qi(input_view)}"


def _srid_zero(params: dict, *, op: str, input_srid: int, join_srid: int | None = None) -> int:
    return UNDEFINED_SRID


class TransformLocalCoordinateSystemParams(BaseModel):
    """Système de coordonnées local (plan de chantier, DAO) défini par une origine géographique
    (longitude/latitude WGS84), une rotation et une échelle. `fromLocal` : les coordonnées
    d'entrée sont lues comme locales et converties dans le SRID `targetSrid` ; `toLocal` : des
    coordonnées géoréférencées sont exprimées dans le repère local (SRID 0 en sortie).

    Repère local : axe Y orienté selon l'azimut `rotation` (degrés depuis le nord, sens horaire),
    axe X à sa droite ; une unité locale vaut `scale` mètres. La projection intermédiaire est
    azimutale équidistante centrée sur l'origine (PROJ `aeqd`) : exacte à l'origine, distorsion
    croissante avec la distance (< 0,1 % jusqu'à ~100 km)."""

    direction: Literal["fromLocal", "toLocal"] = "fromLocal"
    originLon: float = Field(..., ge=-180, le=180)
    originLat: float = Field(..., ge=-90, le=90)
    rotation: float = Field(0.0, ge=-360, le=360)
    scale: float = Field(1.0, gt=0, le=1e6)
    targetSrid: int | None = Field(None, gt=0)

    @model_validator(mode="after")
    def _check(self):
        if self.direction == "fromLocal" and self.targetSrid is None:
            raise ValueError("targetSrid requis pour direction=fromLocal")
        if self.direction == "toLocal" and self.targetSrid is not None:
            raise ValueError("targetSrid sans objet pour direction=toLocal (sortie SRID 0)")
        return self


def _aeqd(p: TransformLocalCoordinateSystemParams) -> str:
    # Flottants validés par Pydantic, rendus par repr : aucune injection possible.
    return f"+proj=aeqd +lat_0={p.originLat!r} +lon_0={p.originLon!r} +x_0=0 +y_0=0 +units=m"


def _compile_local_cs(params: dict, *, input_view: str, join_view=None, input_srid=None) -> str:
    p = TransformLocalCoordinateSystemParams.model_validate(params)
    t, s = math.radians(p.rotation), p.scale
    c, n = math.cos(t), math.sin(t)
    if p.direction == "fromLocal":
        # (x, y) locaux -> (E, N) mètres autour de l'origine -> SRID cible
        g = f"ST_Affine(geometry, {s * c!r}, {s * n!r}, {-s * n!r}, {s * c!r}, 0.0, 0.0)"
        g = f"ST_Transform({g}, '{_aeqd(p)}', 'EPSG:{p.targetSrid}', true)"
    else:
        if input_srid == UNDEFINED_SRID:
            raise PipelineRuntimeError(
                "transform.localCoordinateSystem: toLocal exige un SRID défini en entrée (reçu 0)"
            )
        g = f"ST_Transform(geometry, 'EPSG:{int(input_srid or 4326)}', '{_aeqd(p)}', true)"
        g = f"ST_Affine({g}, {c / s!r}, {-n / s!r}, {n / s!r}, {c / s!r}, 0.0, 0.0)"
    return f"SELECT * REPLACE ({g} AS geometry) FROM {_qi(input_view)}"


def _local_cs_srid(params: dict, *, op: str, input_srid: int, join_srid: int | None = None) -> int:
    p = TransformLocalCoordinateSystemParams.model_validate(params)
    return p.targetSrid if p.direction == "fromLocal" else UNDEFINED_SRID  # type: ignore[return-value]


# --------------------------------------------------------------------------- DatabaseJoiner

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_TABLE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_$]*\.)?[A-Za-z_][A-Za-z0-9_$]*$")
MAX_JOIN_KEYS = 10_000
_KEY_CHUNK = 1_000


class TransformDatabaseJoinParams(BaseModel):
    """Joint à chaque ligne les lignes d'une table d'une base Postgres externe (secret de
    connexion) dont les colonnes clés valent celles de la ligne. Seules les valeurs de clé
    présentes en entrée sont demandées à la base (au plus 10 000 clés distinctes) ; le nombre
    de lignes distantes est plafonné. `left` garde les lignes sans correspondance (colonnes
    jointes à NULL), `inner` les écarte ; plusieurs correspondances donnent plusieurs lignes.

    Lecture seule (autorisée en aperçu, mêmes plafonds) ; garde d'egress et épinglage DNS sur
    l'hôte du DSN, délais de connexion/requête du connecteur ; identifiants vérifiés contre la
    table distante réfléchie, valeurs de clé toujours paramétrées. Les colonnes géométriques
    distantes arrivent telles que le pilote les rend (EWKB hexadécimal) : utiliser
    reader.connector.postgres + ST_AsText côté requête pour une vraie géométrie."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    table: str = Field(..., max_length=200, description="`table` ou `schema.table`")
    inputKeys: list[str] = Field(..., min_length=1, max_length=4)
    tableKeys: list[str] | None = Field(None, min_length=1, max_length=4)
    columns: list[str] | None = Field(None, min_length=1, max_length=100)
    joinType: Literal["left", "inner"] = "left"
    prefix: str = Field("", max_length=32, pattern=r"^[A-Za-z0-9_]*$")
    maxRows: int = Field(50_000, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def _check(self):
        if not _TABLE_RE.match(self.table):
            raise ValueError("table: forme attendue `table` ou `schema.table`")
        keys = self.tableKeys or self.inputKeys
        if len(keys) != len(self.inputKeys):
            raise ValueError("tableKeys et inputKeys doivent avoir la même longueur")
        for name in [*keys, *(self.columns or [])]:
            if not _IDENT_RE.match(name):
                raise ValueError(f"identifiant invalide : {name!r}")
        if len(set(self.inputKeys)) != len(self.inputKeys) or len(set(keys)) != len(keys):
            raise ValueError("colonnes clés dupliquées")
        return self


def _plain(v):
    """Valeur distante -> type que DuckDB sait typer depuis un DataFrame `object`."""
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, dict | list):
        return json.dumps(v, default=str)
    if isinstance(v, memoryview):
        return bytes(v)
    return v


def _remote_engine(op: str, dsn: str):
    import sqlalchemy as sa

    from app.pipelines import connector_runtime as cr
    from app.pipelines.egress import assert_dsn_egress_allowed, dsn_pin_connect_args

    url = sa.engine.make_url(dsn)
    if not url.get_backend_name().startswith("postgresql"):
        raise PipelineRuntimeError(f"{op}: DSN non PostgreSQL")
    assert_dsn_egress_allowed(dsn)
    args = {**cr._timeout_connect_args("postgresql", url.host), **dsn_pin_connect_args(dsn)}
    return sa.create_engine(dsn, connect_args=args)


def execute_database_join(
    conn, *, input_view, view_name, params, secret_resolver=None, preview=False, input_srid=None
):
    import sqlalchemy as sa

    from app.pipelines.egress import EgressBlockedError

    op = "transform.databaseJoin"
    p = TransformDatabaseJoinParams.model_validate(params)
    tkeys = p.tableKeys or p.inputKeys
    in_cols = _columns(conn, input_view)
    if missing := [k for k in p.inputKeys if k not in in_cols]:
        raise PipelineRuntimeError(f"{op}: colonne(s) clé absente(s) de l'entrée : {missing}")
    if any(in_cols[k] == "GEOMETRY" for k in p.inputKeys):
        raise PipelineRuntimeError(f"{op}: une géométrie ne peut pas servir de clé")
    keys_sql = ", ".join(_qi(k) for k in p.inputKeys)
    nonnull = " AND ".join(f"{_qi(k)} IS NOT NULL" for k in p.inputKeys)
    key_rows = conn.execute(
        f"SELECT DISTINCT {keys_sql} FROM {_qi(input_view)} WHERE {nonnull} "
        f"LIMIT {MAX_JOIN_KEYS + 1}"
    ).fetchall()
    if len(key_rows) > MAX_JOIN_KEYS:
        raise PipelineRuntimeError(f"{op}: plus de {MAX_JOIN_KEYS} clés distinctes en entrée")
    if secret_resolver is None:
        raise PipelineRuntimeError(f"{op}: aucun coffre de secrets disponible")
    try:
        payload = secret_resolver.get(p.secretName)
    except KeyError:
        raise PipelineRuntimeError(f"{op}: secret '{p.secretName}' not found") from None
    if payload.kind != "postgres_dsn":
        raise PipelineRuntimeError(f"{op}: secret has kind '{payload.kind}', expected postgres_dsn")

    schema, _, name = p.table.rpartition(".")
    fetched: list[tuple] = []
    try:
        engine = _remote_engine(op, payload.dsn)
        try:
            remote = sa.Table(name, sa.MetaData(), schema=schema or None, autoload_with=engine)
            want = p.columns or [c.name for c in remote.c if c.name not in tkeys]
            if missing := [c for c in [*tkeys, *want] if c not in remote.c]:
                raise PipelineRuntimeError(f"{op}: colonne(s) absente(s) de '{p.table}': {missing}")
            out_names = [p.prefix + c for c in want]
            if clash := [c for c in out_names if c in in_cols]:
                raise PipelineRuntimeError(f"{op}: colonne(s) déjà présente(s) en entrée : {clash}")
            sel = [remote.c[k] for k in tkeys] + [remote.c[c] for c in want]
            key_expr = (
                remote.c[tkeys[0]] if len(tkeys) == 1 else sa.tuple_(*(remote.c[k] for k in tkeys))
            )
            with engine.connect() as db:
                for i in range(0, len(key_rows), _KEY_CHUNK):
                    chunk = key_rows[i : i + _KEY_CHUNK]
                    values = [r[0] for r in chunk] if len(tkeys) == 1 else [tuple(r) for r in chunk]
                    stmt = sa.select(*sel).where(key_expr.in_(values))
                    stmt = stmt.limit(p.maxRows - len(fetched) + 1)
                    fetched += db.execute(stmt).fetchall()
                    if len(fetched) > p.maxRows:
                        raise PipelineRuntimeError(
                            f"{op}: plafond de {p.maxRows} lignes distantes dépassé"
                        )
        finally:
            engine.dispose()
    except EgressBlockedError as exc:
        raise PipelineRuntimeError(f"{op}: egress blocked: {exc}") from exc
    except sa.exc.NoSuchTableError:
        raise PipelineRuntimeError(f"{op}: table '{p.table}' introuvable") from None
    except sa.exc.SQLAlchemyError as exc:
        # Message borné : le pilote n'inclut jamais le mot de passe du DSN (cf. connector_runtime)
        raise PipelineRuntimeError(
            f"{op}: lecture distante en échec ({exc.__class__.__name__}: "
            f"{str(exc.orig if hasattr(exc, 'orig') else exc)[:300]})"
        ) from exc

    rkeys = [f"__gs_k{i}" for i in range(len(tkeys))]
    frame = pd.DataFrame(
        [[_plain(v) for v in r] for r in fetched], columns=[*rkeys, *out_names], dtype=object
    )
    conn.register("_gs_dbjoin", frame)
    try:
        if fetched:
            rsrc = "_gs_dbjoin"
        else:  # aucun résultat : types de clé alignés sur l'entrée (pas de jointure VARCHAR=INT)
            casts = [
                f"CAST(NULL AS {in_cols[k]}) AS {_qi(rk)}"
                for k, rk in zip(p.inputKeys, rkeys, strict=True)
            ]
            casts += [f"CAST(NULL AS VARCHAR) AS {_qi(c)}" for c in out_names]
            rsrc = f"(SELECT {', '.join(casts)} WHERE false)"
        on = " AND ".join(
            f"i.{_qi(k)} = r.{_qi(rk)}" for k, rk in zip(p.inputKeys, rkeys, strict=True)
        )
        extra = "".join(f", r.{_qi(c)}" for c in out_names)
        join = "LEFT JOIN" if p.joinType == "left" else "JOIN"
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT i.*{extra} "
            f"FROM {_qi(input_view)} i {join} {rsrc} r ON {on}"
        )
    finally:
        conn.unregister("_gs_dbjoin")


# --------------------------------------------------------------------------- TopoJSON writer

MAX_TOPOJSON_FEATURES = 100_000
MAX_TOPOJSON_VERTICES = 5_000_000


class WriterTopojsonParams(BaseModel):
    """Écrit l'entrée dans un fichier TopoJSON local (une couche `objects.<objectName>`, arcs
    partagés entre géométries voisines, propriétés = colonnes non géométriques). Coordonnées
    écrites dans le système du pipeline (TopoJSON ne porte pas de CRS : reprojeter en
    EPSG:4326 avant pour un usage web). Fichier local, mêmes conditions que writer.file
    (CORE_PIPELINE_FILE_IO_ENABLED) ; au plus 100 000 entités et 5 millions de sommets.

    Arcs : chaque segment de ligne/anneau est découpé aux sommets partagés par plusieurs
    géométries ; un arc identique (ou inversé) n'est stocké qu'une fois. Pas de quantification
    (`transform` absent : coordonnées exactes)."""

    path: str = Field(..., min_length=1)
    objectName: str = Field("data", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


class _Topology:
    """Construction d'arcs partagés : une géométrie est découpée aux « jonctions » (sommets
    présents dans plus d'une ligne/anneau ou extrémités) ; chaque arc est dédoublonné par sa
    séquence de coordonnées, dans un sens ou dans l'autre (index négatif = arc inversé, ~i)."""

    def __init__(self) -> None:
        self.arcs: list[list[list[float]]] = []
        self._index: dict[tuple, int] = {}

    def arc(self, coords: list[tuple]) -> int:
        key = tuple(coords)
        if key in self._index:
            return self._index[key]
        rev = key[::-1]
        if rev in self._index:
            return ~self._index[rev]
        self._index[key] = len(self.arcs)
        self.arcs.append([list(c) for c in coords])
        return self._index[key]

    def line(self, coords: list[tuple], junctions: set) -> list[int]:
        out, start = [], 0
        for i in range(1, len(coords)):
            if i == len(coords) - 1 or coords[i] in junctions:
                out.append(self.arc(coords[start : i + 1]))
                start = i
        return out


def _lines_of(g) -> list[list[tuple]]:
    """Toutes les polylignes (lignes + anneaux) d'une géométrie, pour le comptage des jonctions."""
    if g.geom_type in ("LineString", "LinearRing"):
        return [list(g.coords)]
    if g.geom_type == "Polygon":
        return [list(g.exterior.coords)] + [list(r.coords) for r in g.interiors]
    if hasattr(g, "geoms"):
        return [line for part in g.geoms for line in _lines_of(part)]
    return []


def _junctions(geoms) -> set:
    seen: dict[tuple, int] = {}
    ends: set = set()
    neighbours: dict[tuple, set] = {}
    for line_no, line in enumerate(line for g in geoms for line in _lines_of(g)):
        ends.add(line[0])
        ends.add(line[-1])
        for i, c in enumerate(line):
            seen[c] = seen.get(c, 0) + 1
            nb = neighbours.setdefault(c, set())
            if i > 0:
                nb.add((line_no, line[i - 1]))
            if i < len(line) - 1:
                nb.add((line_no, line[i + 1]))
    # jonction = extrémité, ou sommet partagé dont les voisins diffèrent d'une ligne à l'autre
    out = set(ends)
    for c, n in seen.items():
        if n > 1 and len({v for _, v in neighbours[c]}) > 2:
            out.add(c)
    return out


def _topo_geom(g, topo: _Topology, junctions: set) -> dict:
    t = g.geom_type
    if t == "Point":
        return {"type": "Point", "coordinates": list(g.coords[0])}
    if t == "MultiPoint":
        return {"type": "MultiPoint", "coordinates": [list(p.coords[0]) for p in g.geoms]}
    if t == "LineString":
        return {"type": "LineString", "arcs": topo.line(list(g.coords), junctions)}
    if t == "MultiLineString":
        return {
            "type": "MultiLineString",
            "arcs": [topo.line(list(x.coords), junctions) for x in g.geoms],
        }
    if t == "Polygon":
        return {"type": "Polygon", "arcs": [topo.line(r, junctions) for r in _lines_of(g)]}
    if t == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "arcs": [[topo.line(r, junctions) for r in _lines_of(p)] for p in g.geoms],
        }
    if t == "GeometryCollection":
        return {
            "type": "GeometryCollection",
            "geometries": [_topo_geom(x, topo, junctions) for x in g.geoms],
        }
    raise ValueError(f"type de géométrie non pris en charge : {t}")


def write_topojson(session, conn, *, node, view_by_node, tenant_id, user, **_extra):
    from app.pipelines.ops.readers2 import _check_path
    from app.pipelines.runtime import NodeStat

    op = "writer.topojson"
    if not is_pipeline_file_io_enabled():
        raise PipelineRuntimeError(f"{op} requires CORE_PIPELINE_FILE_IO_ENABLED=true")
    p = WriterTopojsonParams.model_validate(node.params)
    real = _check_path(op, p.path)
    view = view_by_node[node.id]
    cols = _columns(conn, view)
    if "geometry" not in cols:
        raise PipelineRuntimeError(f"{op}: input has no 'geometry' column")
    props = [c for c in cols if c != "geometry" and cols[c] != "GEOMETRY"]
    sel = ", ".join(["ST_AsWKB(geometry)", *(_qi(c) for c in props)])
    rows = conn.execute(
        f"SELECT {sel} FROM {_qi(view)} LIMIT {MAX_TOPOJSON_FEATURES + 1}"
    ).fetchall()
    if len(rows) > MAX_TOPOJSON_FEATURES:
        raise PipelineRuntimeError(f"{op}: plus de {MAX_TOPOJSON_FEATURES} entités")
    geoms = []
    vertices = 0
    for r in rows:
        g = None if r[0] is None else shapely.wkb.loads(bytes(r[0]))
        if g is not None and g.is_empty:
            g = None
        if g is not None:
            vertices += shapely.get_num_coordinates(g)
            if vertices > MAX_TOPOJSON_VERTICES:
                raise PipelineRuntimeError(f"{op}: plus de {MAX_TOPOJSON_VERTICES} sommets")
        geoms.append(g)
    topo = _Topology()
    junctions = _junctions([g for g in geoms if g is not None])
    out_geoms = []
    for g, r in zip(geoms, rows, strict=True):
        properties = {c: v for c, v in zip(props, r[1:], strict=True)}
        geom = {"type": None} if g is None else _topo_geom(g, topo, junctions)
        out_geoms.append({**geom, "properties": properties})
    doc = {
        "type": "Topology",
        "objects": {p.objectName: {"type": "GeometryCollection", "geometries": out_geoms}},
        "arcs": topo.arcs,
    }
    if parent := os.path.dirname(real):
        os.makedirs(parent, exist_ok=True)
    tmp = f"{real}.tmp-{uuid.uuid4().hex}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, default=str, allow_nan=False)
        os.replace(tmp, real)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return NodeStat(node.id, node.op, len(rows))


WRITERS["writer.topojson"] = write_topojson


# --------------------------------------------------------------------------- contrats

CONTRACTS.extend(
    [
        OperationContract(
            op="transform.removeSrid", kind="transform", params_schema=TransformRemoveSridParams,
            engine="duckdb", engine_license=_DUCKDB, compile=_compile_passthrough,
            output_srid=_srid_zero,
        ),
        OperationContract(
            op="transform.localCoordinateSystem", kind="transform",
            params_schema=TransformLocalCoordinateSystemParams, engine="duckdb",
            engine_license=_DUCKDB + " ; PROJ (MIT) via DuckDB spatial",
            compile=_compile_local_cs, output_srid=_local_cs_srid,
        ),
        OperationContract(
            op="transform.databaseJoin", kind="transform",
            params_schema=TransformDatabaseJoinParams, engine="python",
            engine_license="MIT (SQLAlchemy) ; " + _DUCKDB,
            execute=execute_database_join, needs_runtime_context=True,
        ),
        OperationContract(
            op="writer.topojson", kind="writer", params_schema=WriterTopojsonParams,
            engine="python", engine_license="stdlib json ; Shapely (BSD-3-Clause)",
            enabled_when=is_pipeline_file_io_enabled,
        ),
    ]
)  # fmt: skip
