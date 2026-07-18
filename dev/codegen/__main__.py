"""CLI for the pylzt codegen pipeline. Run from the repo root:

    python -m dev.codegen generate              # render into the staging tree only
    python -m dev.codegen install               # promote staging -> library (gated)
    python -m dev.codegen build                 # generate + install in one shot
    python -m dev.codegen build --scrape        # re-scrape the OpenAPI spec first
    python -m dev.codegen scrape                 # scrape + merge the spec only
    python -m dev.codegen check                  # ruff + mypy gate, no regen

Two-phase by design: `generate` writes flat files into `dev/codegen/generated/` without
touching the library; `install` promotes them flat into `src/pylzt/` behind the gate and
refuses to overwrite hand-written modules.
"""

from __future__ import annotations

import argparse

from . import diff as diff_mod
from . import pipeline
from .generator import ModelBackend


def _add_api(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--api",
        choices=list(pipeline.APIS),
        action="append",
        help="restrict to one API (repeatable); default: all",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dev.codegen",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("generate", help="render the SDK into the staging tree (no install)")
    _add_api(gen)
    gen.add_argument("--model-backend", choices=[b.value for b in ModelBackend], default="pydantic")
    gen.add_argument("--scrape", action="store_true", help="re-scrape the OpenAPI spec first")
    gen.add_argument("--refresh", action="store_true", help="with --scrape: ignore the page cache")

    inst = sub.add_parser("install", help="promote the staging tree into the library (gated)")
    inst.add_argument(
        "--no-validate", action="store_true", help="install without the ruff+mypy gate (danger)"
    )

    bld = sub.add_parser("build", help="generate + install in one shot")
    _add_api(bld)
    bld.add_argument("--model-backend", choices=[b.value for b in ModelBackend], default="pydantic")
    bld.add_argument("--scrape", action="store_true", help="re-scrape the OpenAPI spec first")
    bld.add_argument("--refresh", action="store_true", help="with --scrape: ignore the page cache")
    bld.add_argument("--no-validate", action="store_true", help="install without the gate (danger)")

    scr = sub.add_parser("scrape", help="scrape + merge the OpenAPI spec only")
    scr.add_argument(
        "--site",
        choices=list(pipeline.APIS),
        action="append",
        help="restrict to one site (repeatable); default: all",
    )
    scr.add_argument("--refresh", action="store_true", help="ignore the page cache and refetch")

    sub.add_parser("check", help="run the ruff+mypy+import gate over src/pylzt")

    diff_p = sub.add_parser(
        "diff", help="scrape fresh spec(s) and diff against the committed baseline"
    )
    _add_api(diff_p)
    diff_p.add_argument("--refresh", action="store_true", help="ignore the page cache and refetch")

    args = parser.parse_args()

    if args.cmd == "generate":
        pipeline.generate(
            args.api,
            backend=ModelBackend(args.model_backend),
            do_scrape=args.scrape,
            refresh=args.refresh,
        )
        return 0
    if args.cmd == "install":
        return pipeline.install(do_validate=not args.no_validate)
    if args.cmd == "build":
        return pipeline.build(
            args.api,
            backend=ModelBackend(args.model_backend),
            do_scrape=args.scrape,
            do_validate=not args.no_validate,
            refresh=args.refresh,
        )
    if args.cmd == "scrape":
        pipeline.scrape(args.site or list(pipeline.APIS), refresh=args.refresh)
        return 0
    if args.cmd == "diff":
        # antipublic has no committed baseline (dev/generated/openapi/lzt_antipublic.json
        # doesn't exist) — default run skips it, an explicit --api antipublic still raises.
        sites = args.api or [s for s in pipeline.APIS if s != "antipublic"]
        all_drift: list[diff_mod.SpecDrift] = []
        for site in sites:
            all_drift.extend(diff_mod.diff_site(site, refresh=args.refresh))
        for d in all_drift:
            print(f"{d.kind.value}: {d.path} {d.detail}".rstrip())
        return 1 if all_drift else 0

    result = pipeline.validate()
    print(result.report)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
