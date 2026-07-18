"""Two-phase pylzt codegen pipeline.

`generate` renders the SDK into a flat STAGING tree (`dev/codegen/generated/`) — it reads
the library to dedup against hand-written methods, but never writes to it. `install` then
promotes the staged files FLAT into `src/pylzt/{methods,models,enums,facades}/` behind the
real quality gate (ruff + mypy strict + import smoke), atomically:

  * it SKIPS (warns, does not overwrite) any hand-written module (a file lacking the
    auto-gen marker) — one clash no longer aborts the rest of the install,
  * it snapshots the currently-installed generated files, wipes them (so files for a
    removed domain disappear), copies the staged set in, then runs the gate,
  * on any gate failure it restores the snapshot — the library is never left broken.

`build` runs both. Generated and hand-written modules coexist flat in the same package;
they're told apart by the auto-gen marker in the file header, and by the naming invariant
(hand-written are unprefixed, generated always carry an `{api}_` prefix or an `{api}` name).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import generator, scraper
from .generator import GEN_MARKERS_ALL, STAGING_ROOT, ModelBackend

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG_ROOT = REPO_ROOT / "src" / "pylzt"
SPEC_DIR = REPO_ROOT / "dev" / "generated" / "openapi"
AREAS = ("methods", "models", "enums", "facades")
APIS = ("market", "forum", "antipublic")


class CodegenError(RuntimeError):
    """A codegen pipeline step failed (missing spec, scrape/generate error, name clash)."""


@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    report: str


def _is_generated(path: Path) -> bool:
    """True if a file carries the auto-gen marker — i.e. it's ours to overwrite/wipe."""
    if not path.is_file():
        return False
    head = path.read_text(encoding="utf-8")[:200]
    return any(marker in head for marker in GEN_MARKERS_ALL)


def _lib_generated_files() -> list[Path]:
    """Every marker-carrying (generated) file currently installed in the library (recursive —
    some areas nest, e.g. models/<api>/<snake>.py)."""
    files: list[Path] = []
    for area in AREAS:
        d = PKG_ROOT / area
        if d.exists():
            files += [p for p in sorted(d.rglob("*.py")) if _is_generated(p)]
    return files


def _staged_files() -> list[Path]:
    files: list[Path] = []
    for area in AREAS:
        d = STAGING_ROOT / area
        if d.exists():
            files += sorted(d.rglob("*.py"))
    return files


def _prune_empty_dirs() -> None:
    """Drop empty generated subdirs left when a domain disappears (deepest first)."""
    for area in AREAS:
        root = PKG_ROOT / area
        if not root.exists():
            continue
        for d in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()


def _run(name: str, cmd: list[str]) -> tuple[bool, str]:
    # Docstrings/comments carry non-ASCII (→, —, …); the OS locale encoding (cp1252 on
    # Windows) can't decode them back from the subprocess's UTF-8 pipe, so pin it explicitly
    # rather than inheriting whatever `subprocess` picks by default.
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    body = f"{proc.stdout}{proc.stderr}".rstrip()
    return proc.returncode == 0, f"$ {name}\n{body}".rstrip()


_SMOKE_IMPORT_ALL_SCRIPT = (
    "import importlib, pkgutil\n"
    "n = 0\n"
    "for area in ('methods', 'models', 'enums', 'facades'):\n"
    "    pkg = importlib.import_module(f'pylzt.{area}')\n"
    "    for info in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + '.'):\n"
    "        importlib.import_module(info.name)\n"
    "        n += 1\n"
    "print(f'imported {n} generated modules')\n"
)


def validate() -> ValidationResult:
    """The real quality gate over the installed package: ruff, mypy strict, then two import
    smokes and a test run.

    `import pylzt.client` alone only forces the models/methods that client.py's own
    import graph happens to reach — a broken field (e.g. a name only available under
    `TYPE_CHECKING` used in a real Pydantic field position, see docs/codegen-runbook.md)
    on a model nothing else imports would slip through undetected. `smoke-import-all`
    walks every module under the four generated areas directly, so Pydantic actually
    builds each model at least once. `pytest` catches the other documented recurrence
    (runbook: a BaseMethod dataclass->Pydantic migration once left 6 tests asserting the
    old construction style, undetected by ruff/mypy/import alone) — the full suite, not a
    narrowed subset, since the historical failure lived in tests/pylzt/, not
    tests/dev_codegen/.
    """
    steps = (
        ("ruff", [sys.executable, "-m", "ruff", "check", "src/pylzt"]),
        ("mypy", [sys.executable, "-m", "mypy", "src/pylzt"]),
        ("import", [sys.executable, "-c", "import pylzt.client"]),
        ("smoke-import-all", [sys.executable, "-c", _SMOKE_IMPORT_ALL_SCRIPT]),
        ("pytest", [sys.executable, "-m", "pytest", "tests", "-q"]),
    )
    ok = True
    chunks: list[str] = []
    for name, cmd in steps:
        step_ok, report = _run(name, cmd)
        ok = ok and step_ok
        chunks.append(report)
    return ValidationResult(ok=ok, report="\n\n".join(chunks))


def scrape(sites: list[str], refresh: bool = False) -> None:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    for site in sites:
        out = SPEC_DIR / f"lzt_{site}.json"
        stats = scraper.scrape_site(site, out, refresh=refresh)
        print(f"scraped {site} -> {out.name}: {stats}")


def generate(
    apis: list[str] | None = None,
    *,
    backend: ModelBackend = ModelBackend.PYDANTIC,
    do_scrape: bool = False,
    refresh: bool = False,
) -> None:
    """Render the SDK into the flat STAGING tree; the library is left untouched."""
    selected = list(apis or APIS)
    if do_scrape:
        scrape(selected, refresh=refresh)
    for api in selected:
        spec_path = SPEC_DIR / f"lzt_{api}.json"
        if not spec_path.exists():
            raise CodegenError(f"spec not found: {spec_path} — run `scrape` first")
    if STAGING_ROOT.exists():
        shutil.rmtree(STAGING_ROOT)
    for api in selected:
        spec = json.loads((SPEC_DIR / f"lzt_{api}.json").read_text(encoding="utf-8"))
        generator.generate_all(spec, api, backend)
    staged = _staged_files()
    _ruff_fix_format(staged)
    print(f"staged {len(staged)} files under {STAGING_ROOT.relative_to(REPO_ROOT)}")


def _guard_no_clobber(staged: list[Path]) -> list[Path]:
    """Drop every staged file whose library target is a HAND-WRITTEN module.

    This is the 'builder works always' guarantee: a generated file can never destroy
    curated code. A clash means a generated domain collided with a hand-written module —
    that file is warned about and excluded from the returned set, but the rest of the
    install proceeds (one hand-patched clash no longer aborts the whole batch); the
    auto-gen marker in the file header stays the sole source of truth for what counts
    as a clash, same as before."""
    safe: list[Path] = []
    skipped: list[str] = []
    for s in staged:
        rel = s.relative_to(STAGING_ROOT)
        target = PKG_ROOT / rel
        if target.exists() and not _is_generated(target):
            skipped.append(str(rel))
        else:
            safe.append(s)
    if skipped:
        print(
            f"WARN skipped {len(skipped)} hand-patched file(s), not overwritten: "
            + ", ".join(skipped)
            + " — see docs/codegen-runbook.md"
        )
    return safe


def _ruff_fix_format(files: list[Path]) -> None:
    """ruff --fix (import order) then ruff format (PEP 8 line wrapping) a batch of files —
    run once over the STAGING tree at the end of `generate` (so a reviewer reading staged
    output before install already sees normalized code) and again over the just-installed
    files in `install` (so long facade signatures wrap instead of one-lining)."""
    paths = [str(p) for p in files if p.exists()]
    if paths:
        _run("ruff-fix", [sys.executable, "-m", "ruff", "check", "--fix", "--quiet", *paths])
        _run("ruff-format", [sys.executable, "-m", "ruff", "format", "--quiet", *paths])


def install(*, do_validate: bool = True) -> int:
    """Promote the staged tree into the flat library behind the gate, atomically."""
    staged_all = _staged_files()
    if not staged_all:
        raise CodegenError(f"nothing staged under {STAGING_ROOT} — run `generate` first")
    staged = _guard_no_clobber(staged_all)
    skipped_count = len(staged_all) - len(staged)

    backup = Path(tempfile.mkdtemp(prefix="pylzt-codegen-backup-"))
    installed: list[Path] = []
    try:
        for f in _lib_generated_files():
            dest = backup / f.relative_to(PKG_ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            f.unlink()
        for s in staged:
            target = PKG_ROOT / s.relative_to(STAGING_ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, target)
            installed.append(target)
        for area in AREAS:
            area_dir = PKG_ROOT / area
            init = area_dir / "__init__.py"
            if area_dir.exists() and not init.exists():
                init.write_text("", encoding="utf-8")
        _prune_empty_dirs()

        _ruff_fix_format(installed)

        if not do_validate:
            print(
                f"WARN validation skipped; installed {len(installed)} files unchecked"
                f" ({skipped_count} hand-patched skipped)"
            )
            return 0

        result = validate()
        print(result.report)
        if result.ok:
            print(
                f"\nOK   installed + validated {len(installed)} generated files"
                f" ({skipped_count} hand-patched skipped)"
            )
            return 0

        for p in installed:
            p.unlink(missing_ok=True)
        for f in backup.rglob("*.py"):
            dest = PKG_ROOT / f.relative_to(backup)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
        print("\nFAIL validation failed — install rolled back, library untouched")
        return 1
    finally:
        shutil.rmtree(backup, ignore_errors=True)


def build(
    apis: list[str] | None = None,
    *,
    backend: ModelBackend = ModelBackend.PYDANTIC,
    do_scrape: bool = False,
    do_validate: bool = True,
    refresh: bool = False,
) -> int:
    """`generate` -> `install` in one shot."""
    generate(apis, backend=backend, do_scrape=do_scrape, refresh=refresh)
    return install(do_validate=do_validate)
