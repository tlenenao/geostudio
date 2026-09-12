# SPDX-License-Identifier: Apache-2.0
"""Tests directs de `_strip_code_fence` (GAP-17, revue Tâche 2 — Important
#4) : le brief de tâche ("module-privée, testée directement") n'était pas
honoré par les tests livrés, qui ne l'exerçaient qu'indirectement via des
tests @pytest.mark.postgis. Ce module ne dépend d'aucune base ni du fixture
app_client — pure fonction, pur test."""

from app.mcp.tools.query_generation import _strip_code_fence


def test_passthrough_when_there_is_no_fence():
    assert _strip_code_fence("  SELECT 1  ") == "SELECT 1"


def test_strips_multiline_fence_with_language_tag():
    assert _strip_code_fence('```sql\nSELECT titre FROM "t"\n```') == 'SELECT titre FROM "t"'


def test_strips_multiline_fence_without_language_tag():
    assert _strip_code_fence('```\nSELECT titre FROM "t"\n```') == 'SELECT titre FROM "t"'


def test_extracts_sql_from_fenced_block_preceded_by_prose():
    text = "Here is the SQL:\n```sql\nSELECT 1\n```"
    assert _strip_code_fence(text) == "SELECT 1"


def test_strips_single_line_fence():
    assert _strip_code_fence("```SELECT 1```") == "SELECT 1"
