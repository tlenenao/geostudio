# SPDX-License-Identifier: Apache-2.0
"""DDL par collection (spec SP-3 §2/§5, arbitrage A3) : tenant_id + RLS +
GRANTs au rôle non-propriétaire gis_rls. Idempotent — ré-enregistrer une table
ou rejouer un seed ne casse rien. Les identifiants sont quotés via le preparer
SQLAlchemy (le nom vient du registre, mais la défense vaut pour tout appelant).

`quote_ident` vit désormais dans `app.sql_ident` (GAP-15, premier volet) —
réexporté ici pour compatibilité avec les appelants existants
(`from app.collections.ddl import quote_ident`)."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.publication import add_table_to_publication
from app.sql_ident import quote_ident
from app.tenants.repository import DEFAULT_TENANT_SLUG

__all__ = [
    "TenantColumnMismatch",
    "quote_ident",
    "spatial_index_name",
    "apply_collection_ddl",
    "sync_masked_role_grants",
    "ensure_geo_limit_policy",
    "alter_geometry_column",
]


class TenantColumnMismatch(Exception):
    """La table à enregistrer porte déjà une colonne `tenant_id` dont au moins
    une valeur ne correspond pas au tenant de l'appelant. Poser la policy RLS
    dans ce cas rendrait ces lignes invisibles sous RLS (ou visibles à un
    tenant qui n'est pas le leur) alors qu'un COUNT(*) hors RLS les compterait
    quand même — cf. SP-42/F-securite-tenant-rls-01."""


def _quote_literal(value: str) -> str:
    # SP-42, revue de la dernière passe de correctifs (point 4, Important) :
    # `ALTER TABLE ... ADD COLUMN ... DEFAULT` est une instruction DDL — un
    # paramètre lié (`:tenant_id`) y échoue systématiquement avec
    # `IndeterminateDatatype` (vérifié empiriquement contre Postgres réel,
    # psycopg 3) : Postgres n'accepte de paramètres que dans les
    # instructions DML. Le littéral doit donc être interpolé, correctement
    # échappé — un tenant_id vient de app.tenants (jamais saisi librement
    # dans ce module), mais l'échappement est appliqué par défense en
    # profondeur plutôt que par confiance dans l'appelant.
    return "'" + value.replace("'", "''") + "'"


_qi = quote_ident


def spatial_index_name(table_name: str) -> str:
    """Nom de l'index GiST d'une collection. Partagé avec la migration 0028 —
    une seule définition, jamais deux conventions de nommage."""
    return f"ix_{table_name}_geom_gist"


def _all_real_columns(session: Session, table_name: str) -> list[str]:
    return list(
        session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table_name},
        ).scalars()
    )


def sync_masked_role_grants(session: Session, table_name: str, sensitive_fields: list[str]) -> None:
    """(Re)calcule en entier les GRANT/REVOKE SELECT par colonne pour
    gis_rls_masked (GAP-22) — jamais un GRANT SELECT au niveau table (un
    REVOKE(colonne) ultérieur serait alors sans effet, cf. spec §1.2).
    Idempotent : recalcule l'état complet à partir de `sensitive_fields`, ne
    diffuse pas un delta contre un état précédent inconnu de l'appelant.
    No-op hors Postgres (appelée depuis patch_collection, qui n'a pas
    l'override de test que register_collection a via get_ddl_applier)."""
    if session.get_bind().dialect.name != "postgresql":
        return
    t = _qi(session, table_name)
    all_cols = _all_real_columns(session, table_name)
    sensitive = set(sensitive_fields) & set(all_cols)
    visible = [c for c in all_cols if c not in sensitive]
    if visible:
        cols_sql = ", ".join(_qi(session, c) for c in visible)
        session.execute(text(f"GRANT SELECT ({cols_sql}) ON public.{t} TO gis_rls_masked"))
    if sensitive:
        cols_sql = ", ".join(_qi(session, c) for c in sorted(sensitive))
        session.execute(text(f"REVOKE SELECT ({cols_sql}) ON public.{t} FROM gis_rls_masked"))


_GEO_LIMIT_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION public.app_geo_limit(tbl text) RETURNS geometry
LANGUAGE sql STABLE AS $fn$
SELECT CASE
  WHEN m.v IS NULL THEN NULL::geometry
  WHEN jsonb_array_length(m.v) = 0 THEN ST_GeomFromText('GEOMETRYCOLLECTION EMPTY', 4326)
  ELSE (SELECT ST_Union(ST_SetSRID(ST_GeomFromGeoJSON(e::text), 4326))
        FROM jsonb_array_elements(m.v) e)
END
FROM (SELECT (NULLIF(current_setting('app.geo_limits', true), '')::jsonb -> tbl) AS v) m
$fn$
"""


_GEO_POLICIES = ("geo_limit_select", "geo_limit_insert", "geo_limit_update", "geo_limit_delete")


def _geometry_column(session: Session, table_name: str):
    return session.execute(
        text(
            "SELECT f_geometry_column, srid FROM geometry_columns "
            "WHERE f_table_schema = 'public' AND f_table_name = :t"
        ),
        {"t": table_name},
    ).first()


def _drop_geo_limit_policies(session: Session, table_name: str) -> None:
    t = _qi(session, table_name)
    for name in ("geo_limit", *_GEO_POLICIES):  # `geo_limit` : policy unique de la v1
        session.execute(text(f"DROP POLICY IF EXISTS {name} ON public.{t}"))


def ensure_geo_limit_policy(session: Session, table_name: str) -> bool:
    """Pose (idempotent) les policies RLS RESTRICTIVES `geo_limit_*` d'une collection
    à colonne géométrique (GAP-27, REV-121, v2 découpage). Limite portée par le GUC
    `app.geo_limits` (cf. app.sharing.geo_limits) ; sans limite, rien n'est restreint.

    - lecture (SELECT) et UPDATE (USING + WITH CHECK) : géométrie ENTIÈREMENT contenue
      (ST_CoveredBy), ou — seulement quand `app.geo_partial` est levé par
      `geo_source`/la mise à jour d'attributs — intersectant la limite (entité à
      cheval : visible, mais la lecture passe par la géométrie découpée) ;
    - INSERT : WITH CHECK entièrement contenue ; DELETE : entièrement contenue (une
      entité à cheval ne se supprime pas : sa partie cachée serait détruite) ;
    - un lecteur qui ignore `geo_source` ne voit donc que des entités entièrement
      contenues : jamais de géométrie complète au-delà de la limite.

    Renvoie False (rien posé) hors Postgres ou sans géométrie. RESTRICTIVE = ET avec
    tenant_isolation ; vaut pour gis_rls ET gis_rls_masked. Le SRID est figé ici :
    tout changement de type/SRID de la colonne passe par `alter_geometry_column`."""
    if session.get_bind().dialect.name != "postgresql":
        return False
    row = _geometry_column(session, table_name)
    if row is None:
        return False
    # CREATE OR REPLACE FUNCTION concurrent sur la même signature : UniqueViolation sur
    # pg_proc / « tuple concurrently updated » (500 à deux créations simultanées).
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext('app_geo_limit_fn'))"))
    session.execute(text(_GEO_LIMIT_FUNCTION_SQL))
    t = _qi(session, table_name)
    g = _qi(session, row[0])
    lit = _quote_literal(table_name)
    srid = int(row[1] or 4326)
    lim = f"(SELECT app_geo_limit({lit}))"
    lim_t = f"(SELECT ST_Transform(app_geo_limit({lit}), {srid}))"
    strict = f"({lim} IS NULL OR ST_CoveredBy({g}, {lim_t}))"
    partial = (
        f"({lim} IS NULL OR ST_CoveredBy({g}, {lim_t}) OR "
        f"(coalesce(current_setting('app.geo_partial', true), '') = '1' "
        f"AND ST_Intersects({g}, {lim_t})))"
    )
    _drop_geo_limit_policies(session, table_name)
    for name, command, using, check in (
        ("geo_limit_select", "SELECT", partial, None),
        ("geo_limit_insert", "INSERT", None, strict),
        ("geo_limit_update", "UPDATE", partial, partial),
        ("geo_limit_delete", "DELETE", strict, None),
    ):
        clause = (f" USING ({using})" if using else "") + (
            f" WITH CHECK ({check})" if check else ""
        )
        session.execute(
            text(f"CREATE POLICY {name} ON public.{t} AS RESTRICTIVE FOR {command}{clause}")
        )
    return True


def alter_geometry_column(
    session: Session, table_name: str, *, geometry_type: str, srid: int, using: str | None = None
) -> None:
    """SEUL chemin de changement de type/SRID de la colonne géométrie d'une collection
    (test AST `test_geo_limits_coverage`). Postgres refuse d'altérer le type d'une
    colonne citée par une policy : on retire les policies `geo_limit_*`, on altère, puis
    `ensure_geo_limit_policy` les recrée (SRID et colonne relus). Sans cela la policy
    resterait absente (donc la limite ne s'appliquerait plus) ou figée sur l'ancien SRID.
    `using` : expression de conversion (défaut ST_Transform vers le nouveau SRID)."""
    row = _geometry_column(session, table_name)
    if row is None:
        raise ValueError(f"{table_name!r} has no geometry column")
    t = _qi(session, table_name)
    g = _qi(session, row[0])
    gtype = geometry_type.strip()
    if not gtype.replace("_", "").isalnum():
        raise ValueError(f"invalid geometry type {geometry_type!r}")
    conv = using or f"ST_Transform({g}, {int(srid)})"
    _drop_geo_limit_policies(session, table_name)
    session.execute(
        text(
            f"ALTER TABLE public.{t} ALTER COLUMN {g} "
            f"TYPE geometry({gtype}, {int(srid)}) USING {conv}"
        )
    )
    ensure_geo_limit_policy(session, table_name)


def _reject_preexisting_mismatched_tenant_column(
    session: Session, table_name: str, tenant_id: str
) -> None:
    # ADD COLUMN IF NOT EXISTS (plus bas) est un no-op silencieux si la
    # colonne existe déjà (cas d'une table PostGIS préexistante important
    # déjà un identifiant "tenant_id" d'un autre système) : aucune valeur
    # n'est alors réécrite, et la policy RLS posée juste après comparerait
    # les valeurs préexistantes au tenant réel de l'appelant. Refuser ce cas
    # plutôt que réécrire silencieusement : une réécriture aveugle
    # corromprait un usage légitime où plusieurs tenants partagent déjà la
    # même table physique (RLS par ligne, cf. UniqueConstraint
    # tenant_id+table_name sur Collection).
    has_column = session.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t AND column_name = 'tenant_id'"
        ),
        {"t": table_name},
    ).first()
    if has_column is None:
        return
    t = _qi(session, table_name)
    mismatched = session.execute(
        text(f"SELECT 1 FROM public.{t} WHERE tenant_id IS DISTINCT FROM :tenant_id LIMIT 1"),
        {"tenant_id": tenant_id},
    ).first()
    if mismatched is not None:
        raise TenantColumnMismatch(
            f"la table {table_name!r} porte déjà une colonne tenant_id avec des "
            "valeurs qui ne correspondent pas au tenant de l'appelant"
        )


def apply_collection_ddl(
    session: Session,
    table_name: str,
    *,
    tenant_id: str = DEFAULT_TENANT_SLUG,
    sensitive_fields: list[str] | None = None,
) -> None:
    _reject_preexisting_mismatched_tenant_column(session, table_name, tenant_id)
    t = _qi(session, table_name)
    stmts = [
        f"ALTER TABLE public.{t} ADD COLUMN IF NOT EXISTS tenant_id text "
        f"NOT NULL DEFAULT {_quote_literal(tenant_id)}",
        f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS tenant_isolation ON public.{t}",
        f"CREATE POLICY tenant_isolation ON public.{t} "
        "USING (tenant_id = current_setting('app.tenant_id')) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id'))",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{t} TO gis_rls",
        # L'index sert toutes les requêtes RLS — current_setting est comparé à
        # chaque ligne sinon ; nom ≤ 63 octets garanti : tableName est borné à
        # 50 par CollectionCreate (schemas.py).
        f"CREATE INDEX IF NOT EXISTS "
        f"{quote_ident(session, 'ix_' + table_name + '_tenant_id')} "
        f"ON public.{t} (tenant_id)",
    ]
    for stmt in stmts:
        session.execute(text(stmt))
    # REV-186 : jamais `[]` en dur — une ré-application sur une collection
    # sensible rouvrirait la colonne à gis_rls_masked (GAP-22).
    sync_masked_role_grants(session, table_name, sensitive_fields or [])
    # Index spatial : sans lui, tout filtre bbox (OGC Features, geom_intersects
    # du cross-filter SP-14n, tuiles MVT SP-24) est un scan complet de table.
    # Le nom de la colonne de géométrie vient de geometry_columns, jamais de
    # l'appelant.
    geom_col = session.execute(
        text(
            "SELECT f_geometry_column FROM geometry_columns "
            "WHERE f_table_schema = 'public' AND f_table_name = :t"
        ),
        {"t": table_name},
    ).scalar()
    if geom_col:
        session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {_qi(session, spatial_index_name(table_name))} "
                f"ON public.{t} USING GIST ({_qi(session, geom_col)})"
            )
        )
    # Les INSERT sous gis_rls doivent pouvoir tirer la séquence de la PK (serial).
    seq = session.execute(
        text(
            "SELECT pg_get_serial_sequence('public.' || quote_ident(:t), a.attname) "
            "FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = ('public.' || quote_ident(:t))::regclass "
            "AND i.indisprimary"
        ),
        {"t": table_name},
    ).scalar()
    if seq:
        session.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO gis_rls"))
    # GAP-27 : policy de limite géographique sur toute collection géométrique.
    ensure_geo_limit_policy(session, table_name)
    add_table_to_publication(session, table_name)
