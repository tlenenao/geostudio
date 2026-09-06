# SPDX-License-Identifier: Apache-2.0
"""Tests du module de quoting d'identifiants partagé (GAP-15, premier volet,
cf. app.sql_ident). Aucune dépendance Postgres : `quote_ident_duckdb` est une
fonction pure, et `quote_ident` est vérifié via une Session SQLite en
mémoire — le comportement (conditionnel au dialecte) est le même sur
PostgreSQL, déjà exercé par les tests DDL existants (test_collections_ddl.py,
marqués `postgis`)."""

from sqlalchemy import text

from app.db import make_engine, make_session_factory
from app.sql_ident import quote_ident, quote_ident_duckdb


def test_quote_ident_duckdb_always_wraps_a_simple_identifier():
    assert quote_ident_duckdb("simple") == '"simple"'


def test_quote_ident_duckdb_doubles_internal_double_quotes():
    assert quote_ident_duckdb('has"quote') == '"has""quote"'


def test_quote_ident_only_quotes_when_the_dialect_requires_it():
    """Contrairement à quote_ident_duckdb, quote_ident délègue au preparer du
    dialecte : un identifiant simple, tout en minuscules, sans caractère
    spécial ni mot réservé, ressort NON quoté — écart de comportement
    assumé entre les deux fonctions (cf. docstring du module)."""
    engine = make_engine("sqlite+pysqlite:///:memory:")
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        assert quote_ident(session, "simple") == "simple"


def test_quote_ident_quotes_a_reserved_word():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        assert quote_ident(session, "select") == '"select"'


def test_quote_ident_quotes_and_escapes_special_characters():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        assert quote_ident(session, "weird name") == '"weird name"'
        assert quote_ident(session, 'has"quote') == '"has""quote"'


def test_quote_ident_round_trips_a_reserved_word_column():
    """Test caractéristique (pas seulement unitaire) : l'identifiant quoté est
    réellement utilisable dans une requête SQL contre la colonne qu'il
    désigne."""
    engine = make_engine("sqlite+pysqlite:///:memory:")
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        session.execute(text('CREATE TABLE t ("select" text)'))
        session.execute(text('INSERT INTO t ("select") VALUES (:v)'), {"v": "ok"})
        col = quote_ident(session, "select")
        value = session.execute(text(f"SELECT {col} FROM t")).scalar_one()
        assert value == "ok"
