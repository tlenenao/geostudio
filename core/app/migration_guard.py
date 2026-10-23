# SPDX-License-Identifier: Apache-2.0
"""Garde générale des downgrades destructifs (AUD-192, REV-381).

`alembic downgrade` supprimant une table ou une colonne porteuse de données est refusé tant que
des lignes existent, sauf `GEOSTUDIO_ALLOW_DESTRUCTIVE_DOWNGRADE=1` (le chemin normal est de
restaurer une sauvegarde, cf. deploy/backup). Appelée par `alembic/env.py` AVANT toute étape :
on refuse sans rien avoir exécuté. Les downgrades de 0039/0042 gardent en plus leur propre test.
Registre à compléter par toute migration dont le `downgrade()` détruit des données.
"""

import os

import sqlalchemy as sa

ALLOW_ENV = "GEOSTUDIO_ALLOW_DESTRUCTIVE_DOWNGRADE"

# révision -> tables supprimées par son downgrade().
DROPPED_TABLES: dict[str, tuple[str, ...]] = {
    "0001": ("config_revisions", "configs"),
    "0002": ("tenants",),
    "0003": ("users",),
    "0004": ("audit_log",),
    "0005": ("items",),
    "0006": ("item_shares", "group_members", "groups"),
    "0008": ("collection_shares", "collections"),
    "0009": ("ingestion_jobs",),
    "0013": ("extensions",),
    "0016": ("harvest_records", "harvest_sources"),
    "0018": ("pipeline_runs",),
    "0019": ("connector_secrets",),
    "0020": ("alert_evaluations",),
    "0021": ("export_jobs",),
    "0023": ("report_runs",),
    "0025": ("tileset3d_jobs",),
    "0026": ("terrain3d_jobs",),
    "0027": ("app_export_jobs",),
    "0029": ("map_icons",),
    "0030": ("roles",),
    "0031": ("notification_preferences", "notifications"),
    "0032": ("attachments",),
    "0036": ("pipeline_webhook_tokens",),
    "0040": ("share_link",),
    "0048": ("collection_export_jobs",),
    "0051": ("collection_geo_limits",),
    "0053": ("api_keys",),
    "0055": ("entity_history",),
    "0057": ("quality_reports",),
    "0058": ("submissions", "submission_tokens"),
    "0060": ("collection_relations",),
    "0062": ("group_claim_mappings",),
    "0064": ("pipeline_reader_state",),
    "0066": ("file_trigger_seen", "file_triggers", "outbox", "outbound_webhooks"),
    "0067": ("raster_assets", "raster_jobs"),
    "0080": ("tenant_basemaps",),
    "0081": ("geocode_jobs",),
    "0122": ("tenant_limits",),
    "0160": ("collect_client_ops",),
    "0163": ("submission_files",),
    "0170": ("tenant_llm_settings", "llm_usage"),
    "0172": ("saved_queries",),
}

# Tables dont la migration sème elle-même des lignes (tenant `default`, rôles prédéfinis) : seules
# les lignes hors semis comptent, sinon `downgrade base` serait refusé sur toute base neuve.
SEEDED_FILTER: dict[str, str] = {
    "tenants": "slug <> 'default'",
    "roles": "NOT is_built_in",
}

# révision -> (libellé, SQL de comptage) : colonnes saisies par un humain (valeur ≠ défaut).
DROPPED_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "0033": (
        (
            "métadonnées de collection (licence, producteur, contact, généalogie)",
            "SELECT count(*) FROM collections WHERE license <> '' OR license_uri <> '' "
            "OR producer <> '' OR contact <> '' OR lineage <> '' OR update_frequency <> '' "
            "OR version <> '' OR temporal_start IS NOT NULL OR temporal_end IS NOT NULL",
        ),
        ("licences d'item", "SELECT count(*) FROM items WHERE license <> ''"),
    ),
    "0052": (("catégories d'item", "SELECT count(*) FROM items WHERE categories::text <> '[]'"),),
    "0056": (
        (
            "domaines/sous-types de champs",
            "SELECT count(*) FROM collections WHERE field_domains::text <> '{}' "
            "OR subtypes::text <> '{}'",
        ),
    ),
    "0057": (
        (
            "règles d'attribut",
            "SELECT count(*) FROM collections WHERE attribute_rules::text <> '[]'",
        ),
    ),
    "0095": (
        (
            "mots-clés / thème INSPIRE de collection",
            "SELECT count(*) FROM collections WHERE keywords::text <> '[]' OR inspire_theme <> ''",
        ),
    ),
}


def refuse_destructive_downgrade(connection: sa.Connection, revisions: set[str]) -> None:
    """Lève RuntimeError si le downgrade des `revisions` détruirait des lignes."""
    if os.environ.get(ALLOW_ENV) == "1":
        return
    found: list[str] = []
    for rev in sorted(revisions):
        for table in DROPPED_TABLES.get(rev, ()):
            where = f" WHERE {SEEDED_FILTER[table]}" if table in SEEDED_FILTER else ""
            n = connection.execute(sa.text(f'SELECT count(*) FROM "{table}"{where}')).scalar_one()
            if n:
                found.append(f"{n} ligne(s) de {table} (migration {rev})")
        for what, sql in DROPPED_COLUMNS.get(rev, ()):
            n = connection.execute(sa.text(sql)).scalar_one()
            if n:
                found.append(f"{n} {what} (migration {rev})")
    if found:
        msg = (
            "downgrade refusé, seraient détruit(e)s : "
            + "; ".join(found)
            + ". Restaurez une sauvegarde, ou exportez ces données puis relancez avec "
            + f"{ALLOW_ENV}=1."
        )
        raise RuntimeError(msg)
