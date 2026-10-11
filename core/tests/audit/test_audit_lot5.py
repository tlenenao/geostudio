# SPDX-License-Identifier: Apache-2.0
import pytest

from app.configs.schemas import PipelineCanvasNote, PipelineNode


@pytest.mark.xfail(
    strict=True,
    reason="REV-audit: PipelineNode.x/y int rejette les flottants du canvas (schemas.py:248)",
)
def test_pipeline_node_accepts_fractional_position():
    PipelineNode(id="n", kind="reader", op="reader.x", x=12.5, y=3.25)


@pytest.mark.xfail(
    strict=True, reason="REV-audit: PipelineCanvasNote int rejette les flottants (schemas.py:273)"
)
def test_pipeline_canvas_note_accepts_fractional_geometry():
    PipelineCanvasNote(id="z", label="z", x=1.5, y=2.5, width=200.5, height=120.5)
