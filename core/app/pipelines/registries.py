# SPDX-License-Identifier: Apache-2.0
"""Registres readers/writers pour l'exécution de pipeline (SP-43 Étape 9).
Remplace les dispatchs if/elif inline de app.pipelines.runtime::_prepare()
(readers) et ::run_pipeline() (writers) par un dict op -> fonction — patron
repris de app.harvest.connectors.__init__ (`_REGISTRY: dict[str,
HarvestConnector]` + `get_connector(source_type)`), seul registre
préexistant du dépôt.

Les transforms non-QGIS restent dans app.pipelines.compiler (déjà un
dispatcher fonctionnel pur, testé isolément) : ce module ne couvre que les 3
readers et les 3 writers. transform.qgis (_execute_qgis_transform,
_lock_down) N'EST PAS déplacé dans un registre par cette étape (spec SP-43
§2.1) : c'est le seul transform avec un effet de bord (I/O + réseau vers le
sidecar qgis-worker) — laissé inline dans runtime.py, avec sa branche
`if node.op == "transform.qgis":` actuelle dans _execute_transform_chain().

Les fonctions référencées ci-dessous restent DÉFINIES dans
app.pipelines.runtime, jamais dupliquées ici : plusieurs tests
(tests/test_pipeline_runtime.py) font
`monkeypatch.setattr(runtime, "_table_info_for_collection", ...)` ou
`monkeypatch.setattr(runtime, "_require_readable_collection_id", ...)` —
un nom global se résout via le namespace du module où la fonction
appelante est DÉFINIE (`func.__globals__`), jamais celui d'où elle est
appelée. _read_collection/_write_collection/_write_dataset appellent ces
helpers par nom nu (pas de préfixe de module) : les déplacer dans CE
module casserait donc ces monkeypatches (le mock resterait posé sur
`runtime.X` sans jamais être vu par un appel passant par une référence
importée à plat ici). Ce module se contente d'agréger des références de
fonctions, jamais de réimplémenter leur corps.

Import de app.pipelines.runtime au niveau MODULE (pas fonction-locale) :
sûr malgré la dépendance croisée entre les deux modules, car runtime.py
n'importe CE module (`READERS`/`WRITERS`) que localement, à l'intérieur des
corps de _prepare()/run_pipeline() — jamais à son propre niveau module. Au
tout premier appel de l'une de ces deux fonctions (donc après que
app.pipelines.runtime a fini de charger, quel que soit ce qui a déclenché
ce premier import), app.pipelines.runtime est déjà entièrement défini :
_read_collection, _read_connector_rest, _read_connector_postgres,
_read_connector_snowflake, _write_collection, _write_export et
_write_dataset existent tous en tant
qu'attributs du module au moment où ce fichier-ci y accède ci-dessous."""

from collections.abc import Callable

from app.pipelines import runtime as _runtime

READERS: dict[str, Callable] = {
    "reader.collection": _runtime._read_collection,
    "reader.connector.rest": _runtime._read_connector_rest,
    "reader.connector.postgres": _runtime._read_connector_postgres,
    "reader.connector.snowflake": _runtime._read_connector_snowflake,
}

WRITERS: dict[str, Callable] = {
    "writer.collection": _runtime._write_collection,
    # Signature hétérogène (pas de session/tenant_id/user, contrairement aux
    # deux autres writers) : run_pipeline() le sait et l'appelle différemment
    # selon l'op — ce registre ne fait que remplacer la SÉLECTION if/elif par
    # un dict.get, jamais l'appel lui-même (cf. app.pipelines.runtime::
    # run_pipeline pour le detail de l'appel par op).
    "writer.export": _runtime._write_export,
    # Invariant critique SP-42 (fermé au point d'écriture unique, jamais
    # rouvert par ce découpage) : _write_dataset garde Privilege.DATA_MANAGE
    # via require_privilege() en tout premier, avant toute autre opération —
    # ce registre référence la même fonction, il n'introduit aucun second
    # chemin d'appel.
    "writer.dataset": _runtime._write_dataset,
}
