# SPDX-License-Identifier: Apache-2.0
"""Produit shell/e2e/fixtures/world-tile.mvt : une tuile MVT à une entité
polygonale couvrant presque toute la tuile 0/0/0, portant les propriétés que la
spec E2E attend. À exécuter UNE FOIS contre un PostGIS réel ; le résultat est
committé et n'a pas à être régénéré.

    CORE_TEST_DATABASE_URL=postgresql+psycopg://... uv run python scripts/dump_mvt_fixture.py

Le nom de la couche ("communes") doit rester égal au `sourceLayer` de la couche
de test dans shell/e2e/mocks.ts, et au :layer que la route passe à ST_AsMVT."""

import os
import pathlib
import sys

from sqlalchemy import create_engine, text

SQL = """
SELECT ST_AsMVT(tile, 'communes', 4096, 'geom', 'id') FROM (
  SELECT ST_AsMVTGeom(
           ST_Transform(ST_SetSRID(ST_MakeEnvelope(-170, -80, 170, 80), 4326), 3857),
           ST_TileEnvelope(0, 0, 0), 4096, 64, true) AS geom,
         1 AS id, 'Tulle' AS nom, 14000 AS population
) AS tile WHERE tile.geom IS NOT NULL
"""

OUT = pathlib.Path(__file__).parent.parent.parent / "shell" / "e2e" / "fixtures" / "world-tile.mvt"


def main() -> int:
    url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not url:
        print("CORE_TEST_DATABASE_URL est requis (PostGIS réel)", file=sys.stderr)
        return 1
    with create_engine(url).connect() as conn:
        tile = conn.execute(text(SQL)).scalar()
    if not tile:
        print("la requête n'a produit aucune tuile", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(bytes(tile))
    print(f"{OUT} — {len(bytes(tile))} octets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
