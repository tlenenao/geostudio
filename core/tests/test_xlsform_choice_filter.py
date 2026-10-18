# SPDX-License-Identifier: Apache-2.0
"""L8 T7 (Q2 : défaut « not_ported ») : `choice_filter` n'est jamais appliqué en silence.

Une cascade (`choice_filter` = `etat=${autre}`) demande des domaines conditionnels que le modèle
`FieldDomain` n'exprime pas. Plutôt que d'en porter une version fausse côté serveur, la colonne est
rapportée `not_ported` et la liste complète reste le domaine : ce test verrouille ce contrat.
"""

from app.xlsform.parser import parse_xlsform
from tests.test_xlsform_parser import _book


def _cascade_plan():
    return parse_xlsform(
        _book(
            [
                ("type", "name", "label", "choice_filter"),
                ("select_one regions", "region", "Région", None),
                ("select_one villes", "ville", "Ville", "region=${region}"),
            ],
            choices=[
                ("list_name", "name", "label", "region"),
                ("regions", "n", "Nord", None),
                ("regions", "s", "Sud", None),
                ("villes", "lille", "Lille", "n"),
                ("villes", "nice", "Nice", "s"),
            ],
        )
    )


def test_choice_filter_is_reported_not_ported_and_keeps_the_full_list():
    plan = _cascade_plan()
    items = [r for r in plan.report if r.code == "not_ported" and r.name == "ville"]
    assert len(items) == 1 and "choice_filter" in items[0].message
    # aucune règle conditionnelle inventée ; le domaine reste la liste complète des choix
    assert plan.field_domains["ville"]["values"] == ["lille", "nice"]
    assert not [r for r in plan.attribute_rules if "ville" in r["id"]]
    # la colonne de filtre de la feuille choices n'est pas une colonne de données
    assert "region" in {c["name"] for c in plan.columns} and len(plan.columns) == 2
