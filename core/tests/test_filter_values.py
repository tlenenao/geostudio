# SPDX-License-Identifier: Apache-2.0
"""REV-313 : le filtre `__in` ne casse plus une valeur contenant une virgule."""

from app.filter_values import fold_query_filters, normalize_filters, split_in_values


def test_legacy_comma_list_is_kept_as_alias():
    assert split_in_values("a,b,c") == ["a", "b", "c"]
    assert split_in_values("solo") == ["solo"]


def test_escaped_comma_and_backslash_are_literal():
    assert split_in_values("Paris\\, France,Lyon") == ["Paris, France", "Lyon"]
    assert split_in_values("a\\\\,b") == ["a\\", "b"]


def test_repeated_param_values_are_literal_even_with_commas():
    folded = fold_query_filters([("note__in", "Paris, France"), ("note__in", "Lyon"), ("x", "1")])
    assert split_in_values(folded["note__in"]) == ["Paris, France", "Lyon"]
    assert folded["x"] == "1"


def test_single_occurrence_stays_legacy_and_reserved_are_dropped():
    folded = fold_query_filters([("note__in", "a,b"), ("limit", "5")], reserved={"limit"})
    assert folded == {"note__in": "a,b"}
    assert split_in_values(folded["note__in"]) == ["a", "b"]


def test_normalize_filters_turns_lists_into_literal_in_values():
    out = normalize_filters({"note__in": ["Paris, France", "a\\b"], "k": "v"})
    assert out is not None
    assert split_in_values(out["note__in"]) == ["Paris, France", "a\\b"]
    assert out["k"] == "v"
    assert normalize_filters(None) is None
