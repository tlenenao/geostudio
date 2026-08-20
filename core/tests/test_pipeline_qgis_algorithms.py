# SPDX-License-Identifier: Apache-2.0
from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS

EXPECTED_IDS = {
    "native:dissolve",
    "native:simplifygeometries",
    "native:smoothgeometry",
    "native:centroids",
    "native:convexhull",
    "native:multiparttosingleparts",
    "native:fixgeometries",
    "native:deleteholes",
    "native:extractvertices",
    "native:pointsalonglines",
    "native:densifygeometriesgivenaninterval",
    "native:snapgeometries",
    "qgis:minimumboundinggeometry",
    "native:voronoipolygons",
    "native:delaunaytriangulation",
    "native:union",
    "native:difference",
    "native:symmetricaldifference",
    "native:clip",
    "native:mergevectorlayers",
    "native:splitvectorlayer",
    "native:multiringconstantbuffer",
    "native:joinattributesbylocation",
    "native:extractbylocation",
    "native:extractbyattribute",
    "native:polygonstolines",
    "native:nearestneighbouranalysis",
    "native:zonalstatisticsfb",
    "native:rasterlayerzonalstats",
    "qgis:heatmapkerneldensityestimation",
    "native:creategrid",
    "native:fieldcalculator",
    "qgis:tininterpolation",
    "qgis:idwinterpolation",
    "native:shortestpathpointtopoint",
    "native:serviceareafrompoint",
    "native:hillshade",
    "native:slope",
    "native:aspect",
    "gdal:contour",
    "gdal:polygonize",
    "gdal:rasterize",
    "gdal:sieve",
    "gdal:proximity",
    "gdal:warpreproject",
    "gdal:viewshed",
    "grass7:r.watershed",
    "grass7:r.slope.aspect",
    "grass7:r.fill.dir",
    "grass7:r.flow",
}


def test_allowlist_has_exactly_fifty_algorithms():
    assert len(QGIS_ALGORITHMS) == 50


def test_allowlist_matches_expected_ids():
    assert set(QGIS_ALGORITHMS) == EXPECTED_IDS


def test_each_entry_has_name_and_nonempty_parameters():
    for algo_id, schema in QGIS_ALGORITHMS.items():
        assert isinstance(schema["name"], str) and schema["name"], algo_id
        assert isinstance(schema["parameters"], dict) and schema["parameters"], algo_id
        for param_name, param in schema["parameters"].items():
            assert isinstance(param["optional"], bool), (algo_id, param_name)
            assert isinstance(param["type"], str), (algo_id, param_name)


def test_simplify_required_params_match_spike_findings():
    required = {
        n
        for n, p in QGIS_ALGORITHMS["native:simplifygeometries"]["parameters"].items()
        if not p["optional"]
    }
    assert required == {"INPUT", "METHOD", "OUTPUT", "TOLERANCE"}


def test_centroids_required_params_match_spike_findings():
    required = {
        n for n, p in QGIS_ALGORITHMS["native:centroids"]["parameters"].items() if not p["optional"]
    }
    assert required == {"ALL_PARTS", "INPUT", "OUTPUT"}


def test_dissolve_field_param_is_optional():
    assert QGIS_ALGORITHMS["native:dissolve"]["parameters"]["FIELD"]["optional"] is True
