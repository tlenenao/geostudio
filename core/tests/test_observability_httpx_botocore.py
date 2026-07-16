# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
from pathlib import Path


def test_setup_instruments_httpx_and_botocore_globally():
    core_dir = Path(__file__).resolve().parents[1]
    script = (
        "from app import observability\n"
        "observability.setup()\n"
        "from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor\n"
        "from opentelemetry.instrumentation.botocore import BotocoreInstrumentor\n"
        "print(HTTPXClientInstrumentor().is_instrumented_by_opentelemetry)\n"
        "print(BotocoreInstrumentor().is_instrumented_by_opentelemetry)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=core_dir, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"sous-process a échoué : {result.stderr}"
    assert result.stdout.strip().splitlines() == ["True", "True"]
