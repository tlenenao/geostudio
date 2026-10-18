# SPDX-License-Identifier: Apache-2.0
"""Évaluation rejouable des garde-fous du copilote (AUD-104, D23-04/D23-12).

  PYTHONPATH=. uv run python scripts/copilot_eval.py            # hors ligne, seuil 100 %
  PYTHONPATH=. uv run python scripts/copilot_eval.py --live     # vrai LLM (CORE_LLM_*)

Hors ligne : chaque réponse scriptée de `evals/copilot/cases.jsonl` passe par les mêmes
validateurs que `generate_sql_query` / `generate_cel_expression` ; le verdict doit égaler
`expect`. `--live` : la question est posée au fournisseur configuré (cas `accept`) et sa
réponse réelle doit passer les validateurs — mesure de qualité, non bloquante en CI."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.analytics.sql_draft import validate_draft_sql
from app.analytics.sql_sandbox import SqlSandboxError
from app.configs.document_validation import _cel_syntax_error
from app.mcp.tools.query_generation import _cel_refs, _prompt_messages, _strip_code_fence

CASES = Path(__file__).resolve().parents[1] / "evals" / "copilot" / "cases.jsonl"


def load_cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]


def check(case: dict[str, Any], reply: str) -> str | None:
    """None si la réponse passe les garde-fous, sinon le message de refus."""
    text = _strip_code_fence(reply)
    if not text:
        return "réponse vide"
    if case["kind"] == "sql":
        try:
            validate_draft_sql(
                text,
                table=case["table"],
                fields=case["fields"],
                extra_columns=tuple(case.get("extra", ())),
            )
        except SqlSandboxError as exc:
            return str(exc)
        return None
    if error := _cel_syntax_error(text):
        return error
    unknown = sorted(_cel_refs(text) - set(case["available"]))
    return f"champs inconnus : {', '.join(unknown)}" if unknown else None


def run_offline(cases: list[dict[str, Any]]) -> list[tuple[str, bool, str]]:
    results = []
    for case in cases:
        error = check(case, case["reply"])
        ok = (error is None) == (case["expect"] == "accept")
        if ok and error is not None and case.get("match"):
            ok = case["match"].lower() in error.lower()
        results.append((case["id"], ok, error or "accepté"))
    return results


async def _live_one(case: dict[str, Any], provider: Any) -> tuple[str, bool, str]:
    if case["kind"] == "sql":
        instructions = (
            f'Écris une unique requête SQL SELECT (DuckDB) sur la table "{case["table"]}". '
            "Réponds uniquement par le SQL."
        )
        data = {"SCHEMA": json.dumps({"fields": case["fields"]})}
    else:
        instructions = "Écris une expression CEL. Réponds uniquement par l'expression."
        data = {"REFERENCES": json.dumps(case["available"])}
    turn = await provider.chat(
        messages=_prompt_messages(instructions, data, case["question"]), tools=[]
    )
    error = check(case, turn.text)
    return case["id"], error is None, error or "accepté"


def run_live(cases: list[dict[str, Any]]) -> list[tuple[str, bool, str]]:
    from app.copilot.llm_provider import get_llm_provider

    provider = get_llm_provider()

    async def go() -> list[tuple[str, bool, str]]:
        return [await _live_one(c, provider) for c in cases if c["expect"] == "accept"]

    return asyncio.run(go())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--floor", type=float, default=1.0 if "--live" not in (argv or sys.argv) else 0.0
    )
    args = parser.parse_args(argv)
    cases = load_cases()
    results = run_live(cases) if args.live else run_offline(cases)
    for cid, ok, detail in results:
        print(f"{'OK  ' if ok else 'FAIL'} {cid}: {detail}")
    rate = sum(ok for _, ok, _ in results) / max(len(results), 1)
    print(f"{sum(ok for _, ok, _ in results)}/{len(results)} ({rate:.0%}), seuil {args.floor:.0%}")
    return 0 if rate >= args.floor else 1


if __name__ == "__main__":
    sys.exit(main())
