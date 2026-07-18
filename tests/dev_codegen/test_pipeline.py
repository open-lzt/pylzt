"""`_guard_no_clobber` per-file skip — a hand-patched clash no longer aborts the install."""

from __future__ import annotations

from pathlib import Path

import pytest
from dev.codegen import pipeline


def _write(path: Path, marker: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f'"""{marker}"""\n' if marker else '"""hand-written, not generated."""\n'
    path.write_text(header + "X = 1\n", encoding="utf-8")


def test_guard_no_clobber_skips_hand_patched_clash_without_raising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    staging = tmp_path / "staging"
    pkg = tmp_path / "pkg"
    monkeypatch.setattr(pipeline, "STAGING_ROOT", staging)
    monkeypatch.setattr(pipeline, "PKG_ROOT", pkg)

    clean_staged = staging / "models" / "clean.py"
    clash_staged = staging / "models" / "hand_patched.py"
    _write(clean_staged, pipeline.generator.GEN_MARKER)
    _write(clash_staged, pipeline.generator.GEN_MARKER)
    _write(pkg / "models" / "hand_patched.py", None)  # hand-written target, no marker

    safe = pipeline._guard_no_clobber([clean_staged, clash_staged])

    assert safe == [clean_staged]


def test_install_skips_clash_and_installs_the_rest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    staging = tmp_path / "staging"
    pkg = tmp_path / "pkg"
    monkeypatch.setattr(pipeline, "STAGING_ROOT", staging)
    monkeypatch.setattr(pipeline, "PKG_ROOT", pkg)
    monkeypatch.setattr(pipeline, "validate", lambda: pipeline.ValidationResult(ok=True, report=""))
    monkeypatch.setattr(pipeline, "_ruff_fix_format", lambda files: None)

    marker = pipeline.generator.GEN_MARKER
    _write(staging / "models" / "clean.py", marker)
    _write(staging / "models" / "hand_patched.py", marker)
    hand_patched_target = pkg / "models" / "hand_patched.py"
    _write(hand_patched_target, None)
    original_hand_patched = hand_patched_target.read_text(encoding="utf-8")

    exit_code = pipeline.install()

    assert exit_code == 0
    assert (pkg / "models" / "clean.py").exists()
    # the clash target is untouched — not overwritten, not deleted
    assert hand_patched_target.read_text(encoding="utf-8") == original_hand_patched
    assert "skipped 1 hand-patched file(s)" in capsys.readouterr().out
