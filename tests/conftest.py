"""Refuse to run against anyone else's checkout.

`uv run pytest` falls back to the pytest on PATH when the project venv has none, and a global
interpreter carries `.pth` files for every other project on the machine. This suite then imported
`pylzt` from a sibling clone and reported green for code that is not in this repository — the
symptom was a fix that "did not work" while its own standalone reproduction did.
"""

from __future__ import annotations

from pathlib import Path

import pylzt

_SRC = Path(__file__).resolve().parents[1] / "src"

if not Path(pylzt.__file__).resolve().is_relative_to(_SRC):
    raise RuntimeError(
        f"pylzt resolved to {pylzt.__file__}, not this repo's {_SRC}. "
        "Run the suite with the project interpreter: .venv/Scripts/python.exe -m pytest "
        "(or `uv sync --extra dev` first, so `uv run` has a pytest of its own)."
    )
