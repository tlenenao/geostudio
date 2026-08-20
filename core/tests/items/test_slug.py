# SPDX-License-Identifier: Apache-2.0
import pytest

from app.items.slug import (
    InvalidSlugError,
    SlugCollisionError,
    is_valid_slug,
    slugify,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Mon Portail", "mon-portail"),
        ("Été à Lyon !", "ete-a-lyon"),
        ("  double   espace  ", "double-espace"),
        ("Déjà-Tiret", "deja-tiret"),
        ("C'est / ça", "c-est-ca"),
        ("", "site"),
        ("---", "site"),
        ("!!!", "site"),
    ],
)
def test_slugify_deterministe(text, expected):
    assert slugify(text) == expected
    # idempotence : slugifier un slug déjà propre ne le change pas
    assert slugify(slugify(text)) == slugify(text)


@pytest.mark.parametrize(
    "slug,valid",
    [
        ("mon-portail", True),
        ("a", True),
        ("a1-b2", True),
        ("Mon-Portail", False),  # majuscules
        ("-lead", False),
        ("trail-", False),
        ("double--tiret", False),
        ("avec espace", False),
        ("", False),
        ("a" * 101, False),  # trop long
    ],
)
def test_is_valid_slug(slug, valid):
    assert is_valid_slug(slug) is valid


def test_exceptions_sont_des_value_errors():
    assert issubclass(InvalidSlugError, ValueError)
    assert issubclass(SlugCollisionError, ValueError)
