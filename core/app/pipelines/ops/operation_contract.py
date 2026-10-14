# SPDX-License-Identifier: Apache-2.0
"""Type `OperationContract` (contrat unique par op de pipeline), isolé du registre
`app.pipelines.ops.contracts.OPERATIONS` pour que les modules de voie
(`ops/attrs.py`, `ops/dbio.py`, … — gabarit docs/superpowers/plans/_fme-lane-template.md)
puissent construire leurs contrats sans importer contracts.py, qui les importe lui-même.

Règle non négociable, vérifiée à la CONSTRUCTION de chaque contrat : un moteur
copyleft (is_copyleft=True) exige un modèle d'exécution sidecar, jamais de bindings
in-process (généralisation de la décision SP-15d)."""

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
    # Vague 2 (design docs/superpowers/specs/2026-09-20-vague2-transformers-duckdb-design.md
    # §3.1) : quand True, compile_transform_sql résout input_columns/join_columns via un
    # DESCRIBE (app.pipelines.runtime) avant d'appeler `compile` — extension chirurgicale,
    # jamais de connexion DuckDB dans ce module lui-même.
    needs_columns: bool = False
    # Design docs/superpowers/specs/2026-09-20-vague2-transformers-duckdb-design.md §7.2 :
    # mutuellement exclusif avec `compile` — un op "transform" a l'un ou l'autre, jamais les
    # deux, jamais aucun des deux. Signature : (conn, *, input_view, view_name, params) -> None,
    # matérialise `view_name` lui-même (contrairement à `compile`, qui retourne une simple
    # chaîne SQL exécutée par l'appelant).
    execute: Callable[..., None] | None = None
    # transform.httpCall : quand True (et seulement avec `execute`), runtime.py passe en plus
    # `secret_resolver=`, `preview=` et `input_srid=` à `execute`. Les autres op `execute`
    # gardent leur signature (conn, *, input_view, view_name, params).
    needs_runtime_context: bool = False
    # Piège Python latent : un `def` nu donné ici en défaut (au lieu de `None`)
    # deviendrait un attribut de classe et serait lié comme méthode (self/le
    # contrat injecté en premier argument), pas un simple callable — inoffensif
    # aujourd'hui (défauts `None`, chaque entrée du registre passe son
    # callable en argument d'instance, jamais en défaut de classe), mais à
    # garder à l'esprit pour tout futur mainteneur de ce champ.
    compile: Callable[..., str] | None = None
    output_srid: Callable[..., int] | None = None
    # Design docs/superpowers/specs/2026-09-16-ipc-echange-duckdb-arrow-
    # design.md §2 : canal d'échange DuckDB↔futur moteur natif. None pour
    # les 19 op existantes (aucune ne l'utilise) — le champ existe pour
    # qu'un futur chantier "premier moteur natif" l'utilise sans redevoir
    # étendre ce dataclass. Jamais lu par runtime.py dans ce chantier (rien
    # à brancher, aucun moteur ne le consomme encore) ; jamais exposé par
    # ops_catalog() (même traitement que engine/engine_license/
    # execution_model, déjà invisibles côté shell).
    exchange: Literal["arrow_stream", "geoparquet_file"] | None = None
    # Design docs/superpowers/specs/2026-09-17-desktop-etl-standalone-design.md
    # §3 : capacité instance-wide optionnelle (même patron que
    # is_etl_enabled) qui gate la VISIBILITÉ de l'op dans ops_catalog() —
    # PAS le garde-fou de sécurité réel, qui vit au point d'exécution
    # (app.pipelines.runtime, jamais ici) : ce champ ne remplace aucune
    # vérification, il évite seulement de proposer une op inutilisable dans
    # la palette de l'éditeur.
    enabled_when: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        if self.is_copyleft and self.execution_model != "sidecar":
            raise ValueError(
                f"'{self.op}': moteur copyleft ({self.engine}) exige execution_model='sidecar'"
            )
        if self.compile is not None and self.execute is not None:
            raise ValueError(f"'{self.op}': compile et execute sont mutuellement exclusifs")
        if self.needs_runtime_context and self.execute is None:
            raise ValueError(f"'{self.op}': needs_runtime_context exige execute")
