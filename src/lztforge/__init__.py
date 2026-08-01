"""``lztforge`` re-exports :mod:`pylzt`.

Aliases every ``lztforge.*`` module onto the corresponding ``pylzt.*`` module object (same
instance — ``isinstance`` stays correct across the boundary).
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from types import ModuleType

_SHIM = "lztforge"
_REAL = "pylzt"


class _ForgeAliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(
        self,
        name: str,
        path: object = None,
        target: object = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if name == _SHIM or name.startswith(_SHIM + "."):
            return importlib.util.spec_from_loader(name, self)
        return None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        real_name = _REAL + spec.name[len(_SHIM) :]
        module = importlib.import_module(real_name)
        sys.modules[spec.name] = module
        return module

    def exec_module(self, module: ModuleType) -> None:
        pass


if not any(isinstance(f, _ForgeAliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _ForgeAliasFinder())

_pylzt = importlib.import_module(_REAL)
sys.modules[_SHIM] = _pylzt
