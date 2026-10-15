# SPDX-License-Identifier: Apache-2.0
"""Revue finale de branche FME : gardes transverses parcourant tout le registre `OPERATIONS`
(I1 : classement de rejeu des writers)."""

from app.configs.schemas import EXTERNAL_EFFECT_WRITER_OPS
from app.pipelines.ops.contracts import OPERATIONS

# --- I1 ---------------------------------------------------------------------------------

# Writers rejouables par retry/reprise, avec la raison (tout writer absent d'ici doit être
# dans EXTERNAL_EFFECT_WRITER_OPS — un nouveau writer force donc une décision explicite).
REPLAY_SAFE_WRITERS = {
    "writer.collection": "transaction du run (mode append refusé par append_writers)",
    "writer.dataset": "transaction du run (mode append refusé par append_writers)",
    "writer.export": "objet d'export régénéré",
    "writer.file": "écrase le même fichier local",
    "writer.topojson": "écrase le même fichier local",
    "writer.ftp": "écrase le même chemin distant (fichier .part puis renommage)",
    "writer.connector.postgres.update": "UPDATE borné aux clés : idempotent",
    "writer.connector.postgres.delete": "DELETE borné aux clés : idempotent",
}


def test_every_writer_is_classified_for_replay():
    writers = {k for k, c in OPERATIONS.items() if c.kind == "writer"}
    assert not (EXTERNAL_EFFECT_WRITER_OPS & set(REPLAY_SAFE_WRITERS))
    assert writers == EXTERNAL_EFFECT_WRITER_OPS | set(REPLAY_SAFE_WRITERS)
