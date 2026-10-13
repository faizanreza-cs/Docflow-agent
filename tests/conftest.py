import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def samples() -> Path:
    if not (ROOT / "samples" / "docs" / "invoice_01.pdf").exists():
        subprocess.run([sys.executable, str(ROOT / "samples" / "generate.py")], check=True)
    return ROOT / "samples"
