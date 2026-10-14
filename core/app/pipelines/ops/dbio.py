# SPDX-License-Identifier: Apache-2.0
"""Module de voie B — bases de données & formats tabulaires.
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md.

Déclare ses ops ici (modèles `*Params` + `OperationContract`), agrégées par
app.pipelines.ops.contracts.LANE_MODULES et app.pipelines.registries — gabarit :
docs/superpowers/plans/_fme-lane-template.md. Ne jamais importer contracts/runtime/
registries au niveau module (cycle d'import)."""

from collections.abc import Callable

from app.pipelines.ops.operation_contract import OperationContract

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}
