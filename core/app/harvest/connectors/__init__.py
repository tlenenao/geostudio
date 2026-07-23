# SPDX-License-Identifier: Apache-2.0
from app.harvest.connectors.arcgis import ArcgisConnector
from app.harvest.connectors.base import HarvestConnector
from app.harvest.connectors.stac import StacConnector
from app.harvest.connectors.wms import WmsConnector

_REGISTRY: dict[str, HarvestConnector] = {
    "stac": StacConnector(),
    "arcgis": ArcgisConnector(),
    "wms": WmsConnector(),
}


def get_connector(source_type: str) -> HarvestConnector:
    connector = _REGISTRY.get(source_type)
    if connector is None:
        raise ValueError(f"unknown harvest connector type: {source_type!r}")
    return connector
