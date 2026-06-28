-- Extensions spatiales
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_raster;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Table exemple : communes
CREATE TABLE IF NOT EXISTS communes (
    id          SERIAL PRIMARY KEY,
    code_insee  VARCHAR(10) UNIQUE NOT NULL,
    nom         VARCHAR(255) NOT NULL,
    population  INTEGER,
    surface_ha  NUMERIC(12, 2),
    geom        GEOMETRY(MULTIPOLYGON, 4326)
);

CREATE INDEX IF NOT EXISTS idx_communes_geom
    ON communes USING GIST(geom);

-- Table exemple : points d'intérêt
CREATE TABLE IF NOT EXISTS points_interet (
    id         SERIAL PRIMARY KEY,
    categorie  VARCHAR(100),
    nom        VARCHAR(255),
    score      NUMERIC(3, 1),
    geom       GEOMETRY(POINT, 4326)
);

CREATE INDEX IF NOT EXISTS idx_poi_geom
    ON points_interet USING GIST(geom);

-- Table exemple : incidents (avec dimension temporelle)
CREATE TABLE IF NOT EXISTS incidents (
    id             SERIAL PRIMARY KEY,
    categorie      VARCHAR(100),
    severite       INTEGER CHECK (severite BETWEEN 1 AND 5),
    date_incident  TIMESTAMPTZ DEFAULT NOW(),
    geom           GEOMETRY(POINT, 4326)
);

CREATE INDEX IF NOT EXISTS idx_incidents_geom
    ON incidents USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_incidents_date
    ON incidents(date_incident DESC);

-- Vues matérialisées pour performance MVT (tuiles par niveau de zoom)
CREATE MATERIALIZED VIEW IF NOT EXISTS communes_z8 AS
SELECT code_insee, nom, population,
       ST_Simplify(geom, 0.01) AS geom
FROM communes
WHERE geom IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_communes_z8_geom
    ON communes_z8 USING GIST(geom);

CREATE MATERIALIZED VIEW IF NOT EXISTS communes_z12 AS
SELECT code_insee, nom, population,
       ST_Simplify(geom, 0.001) AS geom
FROM communes
WHERE geom IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_communes_z12_geom
    ON communes_z12 USING GIST(geom);

-- Fonction MVT optimisée pour Martin
CREATE OR REPLACE FUNCTION get_communes_tiles(z INT, x INT, y INT)
RETURNS bytea AS $$
DECLARE
    bounds    geometry := ST_TileEnvelope(z, x, y);
    tolerance float    := CASE
        WHEN z < 8  THEN 0.01
        WHEN z < 12 THEN 0.001
        ELSE 0.0001
    END;
BEGIN
    RETURN (
        SELECT ST_AsMVT(tile, 'communes', 4096, 'geom')
        FROM (
            SELECT code_insee, nom, population,
                   ST_AsMVTGeom(
                       ST_Simplify(geom, tolerance),
                       bounds, 4096, 256, true
                   ) AS geom
            FROM communes
            WHERE geom && bounds
        ) tile
        WHERE geom IS NOT NULL
    );
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

-- Fonction MVT incidents (90 derniers jours)
CREATE OR REPLACE FUNCTION get_incidents_tiles(z INT, x INT, y INT)
RETURNS bytea AS $$
DECLARE
    bounds geometry := ST_TileEnvelope(z, x, y);
BEGIN
    RETURN (
        SELECT ST_AsMVT(tile, 'incidents', 4096, 'geom')
        FROM (
            SELECT id, categorie, severite,
                   date_trunc('day', date_incident) AS date_jour,
                   ST_AsMVTGeom(geom, bounds, 4096, 256, true) AS geom
            FROM incidents
            WHERE geom && bounds
              AND date_incident > NOW() - INTERVAL '90 days'
        ) tile
        WHERE geom IS NOT NULL
    );
END;
$$ LANGUAGE plpgsql STABLE PARALLEL SAFE;
