# SPDX-License-Identifier: Apache-2.0
"""Garde-fou de déployabilité (SP-21, vague 1 du plan d'action 2026-08-20).

Ces tests ne testent pas `core/app/` : ils testent le **dépôt** —
`docker-compose.yml`, l'overlay de production, `release.yml`, `.env.example`
et `deploy/backup/backup.sh`. Entorse assumée au découpage : `core/` est le
seul répertoire du dépôt qui possède déjà un runner Python et une place dans
la CI (`uv run pytest` du job `core`), et la propriété vérifiée ici —
« toute capacité livrée est déployable » — n'a pas d'autre foyer.

Raison d'être : quatre capacités livrées, testées et mergées se sont révélées
non câblées dans la stack packagée (SP-17a, SP-17b, tileset3d, et
`CORE_ETL_ENABLED` trouvée en écrivant ces tests). Chaque règle ci-dessous
correspond à une de ces découvertes, et échoue sur le dépôt tel qu'il était
avant SP-21.
"""
import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
BASE = REPO / "docker-compose.yml"
PROD = REPO / "docker-compose.prod.yml"
RELEASE = REPO / ".github/workflows/release.yml"
ENV_EXAMPLE = REPO / ".env.example"
BACKUP_SH = REPO / "deploy/backup/backup.sh"
CORE_APP = REPO / "core/app"

# Préfixe des images que nous publions nous-mêmes.
OWN_IMAGE_RE = re.compile(r"ghcr\.io/[^/]+/(geostudio-[a-z0-9-]+)")


class ComposeLoader(yaml.SafeLoader):
    """`docker-compose.prod.yml` utilise les tags de fusion propres à Compose
    (`ports: !reset []`) — `yaml.safe_load` lève un ConstructorError dessus.
    Ces tags disent *comment* fusionner, pas *quoi* : on les résout à leur
    valeur nue, aucune règle d'ici n'en dépend."""


def _drop_tag(loader, suffix, node):
    if isinstance(node, yaml.nodes.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.nodes.MappingNode):
        return loader.construct_mapping(node)
    return node.value


ComposeLoader.add_multi_constructor("!", _drop_tag)


def load_yaml(path: pathlib.Path) -> dict:
    return yaml.load(path.read_text(), Loader=ComposeLoader) or {}


def services(path: pathlib.Path) -> dict:
    return load_yaml(path).get("services") or {}


def build_target(service: dict) -> tuple[str, str] | None:
    """(contexte, dockerfile) normalisé, ou None si le service n'a pas de
    `build:`. La forme courte (`build: ./core`) et la forme longue
    (`build: {context, dockerfile}`) donnent le même couple."""
    build = service.get("build")
    if build is None:
        return None
    if isinstance(build, str):
        return (build, "Dockerfile")
    return (build.get("context", "."), build.get("dockerfile", "Dockerfile"))


def release_matrix() -> list[dict]:
    return load_yaml(RELEASE)["jobs"]["build-and-push"]["strategy"]["matrix"]["include"]


def test_every_build_service_has_a_released_image():
    """Tout service construit depuis les sources doit avoir une image
    publiée par la CI de release. Sinon, déployer la capacité exige de
    cloner le dépôt sur l'hôte de production et d'y compiler Chromium ou
    QGIS — ce que l'en-tête de l'overlay prod prétend justement éviter."""
    published = {(e["context"], e["dockerfile"]) for e in release_matrix()}
    missing = {}
    for path in (BASE, PROD):
        for name, service in services(path).items():
            target = build_target(service)
            if target and target not in published:
                missing[f"{path.name}:{name}"] = target
    assert not missing, (
        "services construits depuis les sources sans image publiée dans "
        f"release.yml : {missing}. Ajouter une entrée à la matrice "
        "build-and-push avec exactement ce couple (context, dockerfile)."
    )


def test_every_referenced_ghcr_image_is_released():
    """Miroir de la règle précédente, dans l'autre sens : un service qui
    référence une de nos images GHCR doit la trouver publiée. Sans cette
    règle, remplacer un `build:` par un `image:` (tâche 2) supprimerait le
    contrôle au lieu de le satisfaire."""
    published = {e["image"] for e in release_matrix()}
    missing = {}
    for path in (BASE, PROD):
        for name, service in services(path).items():
            match = OWN_IMAGE_RE.match(service.get("image") or "")
            if match and match.group(1) not in published:
                missing[f"{path.name}:{name}"] = match.group(1)
    assert not missing, (
        f"images GHCR référencées mais jamais publiées : {missing}."
    )


def test_prod_overlay_substitutes_every_build_with_an_image():
    """L'overlay de production annonce en en-tête servir des « images depuis
    GHCR (au lieu de build:) ». Tout service construit dans le fichier de
    base doit donc y être substitué par un `image:`, et l'overlay ne doit
    pas introduire de `build:` de son cru."""
    prod = services(PROD)
    not_substituted = [
        name for name, service in services(BASE).items()
        if build_target(service) and not (prod.get(name) or {}).get("image")
    ]
    introduced = [name for name, service in prod.items() if build_target(service)]
    assert not not_substituted, (
        "services encore construits depuis les sources en production : "
        f"{not_substituted}. Ajouter `image: ghcr.io/tlenenao/geostudio-"
        "<nom>:${GEOSTUDIO_VERSION:-latest}` dans docker-compose.prod.yml."
    )
    assert not introduced, (
        f"l'overlay de production introduit lui-même un build: {introduced}."
    )
