# SPDX-License-Identifier: Apache-2.0
import re
import unicodedata

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_LEN = 100
_FALLBACK = "site"


class InvalidSlugError(ValueError):
    """Slug dont le format est invalide."""


class SlugCollisionError(ValueError):
    """Slug déjà utilisé par un autre item du même tenant."""


def slugify(text: str) -> str:
    """Slug déterministe : ASCII, minuscules, tirets simples, borné. Repli
    sur `site` si le résultat est vide."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    dashed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    result = dashed[:_MAX_LEN].strip("-")
    return result or _FALLBACK


def is_valid_slug(slug: str) -> bool:
    return len(slug) <= _MAX_LEN and bool(_SLUG_RE.match(slug))
