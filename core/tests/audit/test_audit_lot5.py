# SPDX-License-Identifier: Apache-2.0
from app.configs.schemas import PipelineCanvasNote, PipelineNode


def test_pipeline_node_accepts_fractional_position():
    PipelineNode(id="n", kind="reader", op="reader.x", x=12.5, y=3.25)


def test_pipeline_canvas_note_accepts_fractional_geometry():
    PipelineCanvasNote(id="z", label="z", x=1.5, y=2.5, width=200.5, height=120.5)
