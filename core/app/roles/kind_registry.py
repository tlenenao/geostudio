# SPDX-License-Identifier: Apache-2.0
"""Registre unique kind -> privilège requis pour créer/modifier une config.

Source de vérité unique, consommée par app.configs.routes, app.mcp.tools,
app.tileset3d.routes, app.terrain3d.routes et app.pipelines.routes — remplace
plusieurs formes de couplage distinctes (import de nom privé, import de dict
privé, recopie de valeur en dur) qui ont laissé rouvrir 3 fois le même défaut
d'autorisation (cf. spec SP-43 §1.1). app.terrain3d.routes couplait par le
même import de dict privé que app.tileset3d.routes ; non listé explicitement
par le brief de cette tâche — trouvé par le grep de clôture (Step 12), corrigé
au même titre que les 4 sites nommément prévus.

SP-42/F-securite-autorisation-01 : avant la garde d'origine (app.configs.routes,
commit eafb02cc), aucune route de création/mise à jour de config ne consultait
le catalogue de privilèges — un rôle « Lecteur » (0 privilège) obtenait 201 sur
POST /configs pour n'importe quel kind. Mapping calé sur le domaine shell
(capabilities.ts) : dashboard/site partagent le domaine "apps" avec app (même
runtime AppRenderer, cf. CLAUDE.md règle d'architecture n°3) ; tileset3d/
terrain3d n'ont pas de domaine dédié et retombent sur catalog.manage.

bookmark -> analytics.view (décision Tanguy, revue du lot de correctifs 1,
SP-42) : un bookmark est une « vue analytique enregistrée » (spec
docs/superpowers/specs/2026-08-05-sp14m-bookmarks-vues-design.md), portée
par le domaine Analytique de la matrice de la refonte UI — PAS
catalog.manage, qui aurait bloqué l'Analyste (qui porte analytics.view
mais pas catalog.manage) tout en laissant passer un Lecteur si jamais un
rôle sur mesure portait catalog.manage sans analytics.view."""

from app.roles.privileges import Privilege

_KIND_PRIVILEGE: dict[str, str] = {
    "app": Privilege.APPS_MANAGE.value,
    "dashboard": Privilege.APPS_MANAGE.value,
    "site": Privilege.APPS_MANAGE.value,
    "map": Privilege.MAPS_MANAGE.value,
    "dataset": Privilege.DATA_MANAGE.value,
    "pipeline": Privilege.AUTOMATION_MANAGE.value,
    "alert": Privilege.AUTOMATION_MANAGE.value,
    "report": Privilege.AUTOMATION_MANAGE.value,
    "bookmark": Privilege.ANALYTICS_VIEW.value,
    "tileset3d": Privilege.CATALOG_MANAGE.value,
    "terrain3d": Privilege.CATALOG_MANAGE.value,
}


def privilege_for_kind(kind: str) -> str:
    """Privilège requis pour créer/modifier une config du kind donné.

    Repli sur catalog.manage pour tout kind inconnu de ce registre (nouveau
    kind pas encore explicitement mappé) — mieux vaut sur-restreindre qu'ouvrir
    par défaut."""
    return _KIND_PRIVILEGE.get(kind, Privilege.CATALOG_MANAGE.value)
