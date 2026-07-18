"""pylzt code generation.

Scrape the official readme.io OpenAPI reference, generate typed BaseMethod[T]
methods + response models + enums + Client facades into the `generated/`
subpackages under `src/pylzt/`, and install them only behind a ruff + mypy gate.

Entrypoint: `python -m dev.codegen build`. See `pipeline.build`.
"""

from .pipeline import build, generate, install, scrape, validate

__all__ = ["build", "generate", "install", "scrape", "validate"]
