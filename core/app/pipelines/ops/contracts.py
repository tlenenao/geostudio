# SPDX-License-Identifier: Apache-2.0
"""Contrat unique par op de pipeline (schéma/moteur/licence/modèle
d'exécution/compilateur/règle de SRID de sortie) — design
docs/superpowers/specs/2026-09-16-operation-contract-design.md.

Remplace, pour les 19 op de pipeline déjà livrées, les 5 structures
parallèles indexées par nom d'op qui existaient jusqu'ici
(app.pipelines.ops.schemas::OP_PARAMS/OP_KINDS/BINARY_OPS,
app.pipelines.compiler::compile_transform_sql/transform_output_srid) : le
registre OPERATIONS (construit par une tâche ultérieure de ce même
chantier, cf. plan) devient la seule source, ces structures en deviennent
des vues dérivées, définies dans CE module (pas dans ops/schemas.py — un
import circulaire réel l'interdit, cf. Écarts au texte de la spec du plan).

Règle non négociable, vérifiée à la CONSTRUCTION de chaque contrat (donc à
chaque import de ce module, pas seulement par un test dédié) :
généralisation de la décision SP-15d déjà en vigueur pour QGIS — un moteur
copyleft (is_copyleft=True) exige un modèle d'exécution sidecar, jamais de
bindings in-process."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class OperationContract:
    op: str
    kind: Literal["reader", "transform", "writer"]
    params_schema: type[BaseModel]
    accepts_secondary_input: bool = False
    engine: str | None = None
    engine_license: str | None = None
    is_copyleft: bool = False
    execution_model: Literal["in_process", "sidecar"] = "in_process"
    compile: Callable[..., str] | None = None
    output_srid: Callable[..., int] | None = None

    def __post_init__(self) -> None:
        if self.is_copyleft and self.execution_model != "sidecar":
            raise ValueError(
                f"'{self.op}': moteur copyleft ({self.engine}) exige execution_model='sidecar'"
            )
