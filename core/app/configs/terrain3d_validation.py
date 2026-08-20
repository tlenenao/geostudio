# SPDX-License-Identifier: Apache-2.0
"""Validation directe du kind="terrain3d" pour app.configs : ce kind n'a
aucune voie de création/mise à jour légitime via les routes publiques —
seule convert_terrain3d_task (app.terrain3d.jobs) le produit, via un appel
direct à app.configs.repository.create_config qui ne passe jamais par ces
routes REST. Un POST/PUT/PATCH authentifié quelconque avec kind="terrain3d"
serait sinon un moyen de s'approprier un sourceKey S3 arbitraire (item créé
par l'appelant, mais pointant vers les octets d'un autre DEM converti) et de
le lire via le proxy authentifié GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png
— le proxy vérifie can() sur l'item appelant, jamais sur la provenance du
sourceKey qu'il désigne. Même raisonnement que app.configs.tileset3d_validation,
copié verbatim pour ce second kind à source S3 opaque.

`_session`/`user` sont inutilisés (le refus est inconditionnel) mais
conservés : les autres validateurs de ce paquet partagent la même signature
et les trois points d'appel de app.configs.routes les invoquent uniformément.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.users.models import User


def validate_terrain3d_payload(_session: Session, config: BuilderConfig, *, user: User) -> None:  # noqa: ARG001
    if config.kind != "terrain3d":
        return
    raise HTTPException(
        status_code=422,
        detail="terrain3d configs can only be created by the conversion task",
    )
