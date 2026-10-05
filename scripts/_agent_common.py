from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


TOOL = Path(__file__).resolve().parents[1]
SRC = TOOL / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def fail(message: str, code: int = 1) -> None:
    print_json({"ok": False, "error": message})
    raise SystemExit(code)


from autobookkeeping.workspace import data_root
ROOT = TOOL / "daten"
