# SPDX-License-Identifier: Apache-2.0
"""Validation directe du kind="tileset3d" pour app.configs : ce kind n'a
aucune voie de création/mise à jour légitime via les routes publiques —
seule finalize_tileset3d_task (app.tileset3d.jobs) le produit, via un appel
direct à app.configs.repository.create_config qui ne passe jamais par ces
routes REST. Un POST/PUT/PATCH authentifié quelconque avec kind="tileset3d"
serait sinon un moyen de s'approprier un sourceKey S3 arbitraire (item créé
par l'appelant, mais pointant vers les octets d'un autre tileset) et de le
lire via le proxy authentifié GET /tileset3d/{item_id}/{path} — le proxy
vérifie can() sur l'item appelant, jamais sur la provenance du sourceKey
qu'il désigne.

`_session`/`user` sont inutilisés (le refus est inconditionnel, rien à
rechercher en base) mais conservés : les cinq autres validateurs de ce
paquet partagent la même signature et les trois points d'appel de
app.configs.routes les invoquent uniformément.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.users.models import User


def validate_tileset3d_payload(_session: Session, config: BuilderConfig, *, user: User) -> None:  # noqa: ARG001
    if config.kind != "tileset3d":
        return
    raise HTTPException(
        status_code=422,
        detail="tileset3d configs can only be created by the finalize task",
    )
