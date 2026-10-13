# SPDX-License-Identifier: Apache-2.0
"""Lecture incrémentale des readers connecteurs (ARC-K2/F4).

Le curseur (valeur max d'une colonne, sérialisée en texte) est persisté par
(pipeline, nœud) dans `pipeline_reader_state` — mais UNIQUEMENT après un run
réussi : pendant le run il n'est que « en attente » (`ReaderState.pending`),
si bien qu'un échec laisse le curseur où il était.

Le filtrage se fait côté DuckDB sur la table matérialisée par le connecteur
(dlt écrit un scratch par appel, sans état partagé : nous ne nous appuyons pas
sur `dlt.sources.incremental`, dont l'état vit dans ce scratch jetable).
# ponytail: la source est quand même lue en entier (filtrage client) — un
# pushdown dans la requête source (`WHERE col > {{cursor}}`) réduirait le
# transfert ; non fait. Comparaison stricte (>) : une ligne ajoutée plus tard
# avec exactement la valeur du curseur est perdue (dédup de frontière dlt non
# reproduite) — choisir un curseur strictement croissant."""

from app.pipelines.errors import PipelineRuntimeError
from app.sql_ident import quote_ident_duckdb as _qi


class ReaderState:
    """Curseurs lus au départ du run + curseurs en attente de validation."""

    def __init__(self, stored: dict[str, str] | None = None) -> None:
        self.stored: dict[str, str] = dict(stored or {})
        self.pending: dict[str, str] = {}

    def get(self, node_id: str) -> str | None:
        return self.stored.get(node_id)

    def stage(self, node_id: str, value: str) -> None:
        self.pending[node_id] = value


def apply_incremental(conn, table: str, cursor_field: str, stored: str | None) -> str | None:
    """Filtre `table` (TEMP TABLE d'un reader connecteur) aux lignes plus
    récentes que `stored` ; retourne le nouveau curseur (max, texte) ou None
    si ni curseur ni ligne. Les lignes à curseur NULL sont conservées."""
    cols = {d[0]: d[1] for d in conn.execute(f"DESCRIBE {_qi(table)}").fetchall()}
    if cursor_field not in cols:
        raise PipelineRuntimeError(
            f"lecture incrémentale : colonne curseur '{cursor_field}' absente de la source"
        )
    col, ctype = _qi(cursor_field), cols[cursor_field]
    try:
        if stored is None:
            new = conn.execute(f"SELECT max({col})::VARCHAR FROM {_qi(table)}").fetchone()[0]
        else:
            # greatest ignore les NULL ; `stored` est lié, jamais interpolé.
            new = conn.execute(
                f"SELECT greatest(max({col}), CAST(? AS {ctype}))::VARCHAR FROM {_qi(table)}",
                [stored],
            ).fetchone()[0]
            conn.execute(f"DELETE FROM {_qi(table)} WHERE {col} <= CAST(? AS {ctype})", [stored])
    except Exception as exc:  # type non ordonnable, curseur stocké incompatible…
        raise PipelineRuntimeError(
            f"lecture incrémentale : colonne '{cursor_field}' inutilisable comme curseur ({exc})"
        ) from exc
    return new
