# SPDX-License-Identifier: Apache-2.0
"""Quoting d'identifiants SQL (GAP-15, premier volet) — module bas niveau,
sans dépendance vers aucun module `app.*` métier, donc importable depuis
n'importe quelle couche du contrat `lint-imports` sans exemption nommée
(même statut qu'`app.db` : fichier top-level hors de la liste `layers`).

Deux implémentations distinctes cohabitaient dans le dépôt avant ce module,
pour deux backends réellement différents — regroupées ici sans être
fusionnées en une seule fonction, le comportement de chacune étant
volontairement conservé à l'identique :

- `quote_ident` : backend PostgreSQL réel via une `Session` SQLAlchemy —
  délègue au preparer du dialecte (`identifier_preparer.quote`), qui ne
  quote un identifiant que si nécessaire (mot réservé, casse mixte,
  caractères spéciaux). C'est la version historiquement définie dans
  `app.collections.ddl` (SP-3), dupliquée telle quelle dans
  `app.collections.publication` (SP-11a) pour une raison structurelle :
  `app.collections.ddl` importe déjà `app.collections.publication`
  (`add_table_to_publication`), un import dans l'autre sens aurait créé un
  cycle. Ce module, indépendant des deux, lève cette contrainte à la
  racine.
- `quote_ident_duckdb` : backend DuckDB (pas de `Session` SQLAlchemy, pas
  de dialecte) — quote systématiquement l'identifiant entre guillemets
  doubles et double les guillemets internes. Utilisé par le module
  analytique (`app.analytics.aggregate`, SP-11b) et par le mini-serveur
  d'export autoporté (`app.appexport.miniserver.items`, SP-18c), qui lit
  le même GeoParquet via DuckDB mais ne peut pas dépendre d'une Session
  Postgres (pas de driver Postgres dans cette image).
"""

from sqlalchemy.orm import Session


def quote_ident(session: Session, identifier: str) -> str:
    """Quote un identifiant pour le dialecte réel de `session` (PostgreSQL en
    production, SQLite en test) via le preparer SQLAlchemy — ne quote que si
    le dialecte l'exige."""
    return session.get_bind().dialect.identifier_preparer.quote(identifier)


def quote_ident_duckdb(identifier: str) -> str:
    """Quote systématiquement un identifiant pour DuckDB (guillemets doubles
    SQL standard, guillemets internes doublés) — aucune Session, aucun
    dialecte : DuckDB n'a pas de notion de dialecte SQLAlchemy ici."""
    return '"' + identifier.replace('"', '""') + '"'
