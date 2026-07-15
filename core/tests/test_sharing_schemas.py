# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.sharing.schemas import GroupShare, Sharing


def test_duplicate_group_ids_rejected():
    with pytest.raises(ValidationError):
        Sharing(public=False, groups=[
            GroupShare(groupId="g1", role="viewer"),
            GroupShare(groupId="g1", role="editor"),
        ])


def test_distinct_groups_ok():
    s = Sharing(public=True, groups=[
        GroupShare(groupId="g1", role="viewer"),
        GroupShare(groupId="g2", role="editor"),
    ])
    assert len(s.groups) == 2
