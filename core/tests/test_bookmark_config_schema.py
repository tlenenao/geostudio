# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


def _bookmark_body(**overrides) -> dict:
    body = {
        "version": 1,
        "kind": "bookmark",
        "bookmark": {
            "appId": "app-1",
            "pageId": "page-1",
            "timeRange": {"from": "2026-01-01", "to": "2026-02-01"},
            "extent": [2.0, 46.0, 3.0, 47.0],
            "crossFilter": {
                "dataset-1": {"field": "region", "value": "Nord", "originSourceId": "src-1"},
            },
        },
    }
    body["bookmark"].update(overrides)
    return body


def test_bookmark_config_valide():
    config = BuilderConfig.model_validate(_bookmark_body())
    assert config.kind == "bookmark"
    assert config.bookmark.appId == "app-1"
    assert config.bookmark.pageId == "page-1"
    assert config.bookmark.timeRange.from_ == "2026-01-01"
    assert config.bookmark.timeRange.to == "2026-02-01"
    assert config.bookmark.extent == (2.0, 46.0, 3.0, 47.0)
    assert config.bookmark.crossFilter["dataset-1"].field == "region"
    assert config.bookmark.crossFilter["dataset-1"].originSourceId == "src-1"


def test_bookmark_config_sans_payload_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"version": 1, "kind": "bookmark"})


def test_bookmark_config_time_range_extent_cross_filter_optionnels():
    body = _bookmark_body()
    del body["bookmark"]["timeRange"]
    del body["bookmark"]["extent"]
    del body["bookmark"]["crossFilter"]
    config = BuilderConfig.model_validate(body)
    assert config.bookmark.timeRange is None
    assert config.bookmark.extent is None
    assert config.bookmark.crossFilter == {}


def test_bookmark_config_page_id_vide_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_bookmark_body(pageId=""))


def test_bookmark_config_page_id_blanc_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_bookmark_body(pageId="   "))


def test_bookmark_config_round_trips_through_dump_and_validate():
    # by_alias=True is what configs_repo.create_config persists with — this
    # is the exact round trip a saved-then-reloaded bookmark goes through.
    config = BuilderConfig.model_validate(_bookmark_body())
    dumped = config.model_dump(by_alias=True)
    assert dumped["bookmark"]["timeRange"]["from"] == "2026-01-01"
    reloaded = BuilderConfig.model_validate(dumped)
    assert reloaded.bookmark.timeRange.from_ == "2026-01-01"
