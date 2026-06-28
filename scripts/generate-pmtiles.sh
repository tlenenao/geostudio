#!/bin/bash
# Génère des fichiers PMTiles depuis PostGIS et les upload vers MinIO
set -euo pipefail

: "${PG_PASSWORD:?Variable PG_PASSWORD non définie}"
: "${MINIO_USER:?Variable MINIO_USER non définie}"
: "${MINIO_PASSWORD:?Variable MINIO_PASSWORD non définie}"

PGCONN="postgresql://gis:${PG_PASSWORD}@localhost:5432/gis"
OUTPUT_DIR="/tmp/pmtiles"
MINIO_ALIAS="local"
MINIO_BUCKET="tiles"

mkdir -p "$OUTPUT_DIR"

# Configurer le client MinIO
mc alias set "$MINIO_ALIAS" http://localhost:9000 "$MINIO_USER" "$MINIO_PASSWORD"
mc mb --ignore-existing "$MINIO_ALIAS/$MINIO_BUCKET"

generate_layer() {
    local layer=$1
    local sql=$2
    local minzoom=$3
    local maxzoom=$4

    echo "Génération : ${layer}..."

    ogr2ogr \
        -f GeoJSON /vsistdout/ \
        "$PGCONN" \
        -sql "$sql" | \
    tippecanoe \
        --output="${OUTPUT_DIR}/${layer}.pmtiles" \
        --layer="$layer" \
        --minimum-zoom="$minzoom" \
        --maximum-zoom="$maxzoom" \
        --drop-densest-as-needed \
        --extend-zooms-if-still-dropping \
        --force \
        /dev/stdin

    mc cp "${OUTPUT_DIR}/${layer}.pmtiles" "${MINIO_ALIAS}/${MINIO_BUCKET}/${layer}.pmtiles"
    mc anonymous set download "${MINIO_ALIAS}/${MINIO_BUCKET}"

    echo "Publié : http://localhost:9000/${MINIO_BUCKET}/${layer}.pmtiles"
}

generate_layer "communes" \
    "SELECT code_insee, nom, population, surface_ha, geom FROM communes" \
    4 14

generate_layer "points_interet" \
    "SELECT id, categorie, nom, score, geom FROM points_interet" \
    10 20

echo "Génération terminée."
