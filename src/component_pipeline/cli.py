from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import (
    PILOT_COMPONENT_IDS,
    PipelineError,
    generate_job,
    normalize_job,
    extract_job,
    openai_api_available,
    prepare_pipeline,
    promote_candidate,
    qa_job,
    queue_bootstrap_jobs,
    queue_component_jobs,
    rebaseline_canonical,
    validate_pipeline,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="component-pipeline",
        description="Pip & Pyre modular character-component production pipeline",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="Validate canonical art, catalog, and production manifests")
    commands.add_parser("prepare", help="Build deterministic generation masters and masks")

    generate = commands.add_parser("generate", help="Queue, resume, and process component generation")
    target = generate.add_mutually_exclusive_group(required=True)
    target.add_argument("--component")
    target.add_argument("--bootstrap", action="store_true")
    generate.add_argument("--animation", choices=("idle", "walk", "run"))
    generate.add_argument("--candidates", type=int, default=3)
    generate.add_argument("--new", action="store_true", help="Create new jobs instead of resuming")
    generate.add_argument("--remaining", action="store_true", help="Run the non-pilot bootstrap queue")
    generate.add_argument("--design-reference")

    for name in ("normalize", "extract", "qa"):
        command = commands.add_parser(name)
        command.add_argument("--job", required=True)

    review = commands.add_parser("review", help="Open the local candidate review conveyor")
    review.add_argument("--job")

    promote = commands.add_parser("promote", help="Promote one approved candidate into production")
    promote.add_argument("--job", required=True)
    promote.add_argument("--candidate", required=True)
    promote.add_argument("--replace", action="store_true")

    rebaseline = commands.add_parser("rebaseline", help="Accept intentional same-geometry master changes")
    rebaseline.add_argument("--confirm", metavar="BASE_ID", required=True)

    smoke = commands.add_parser("smoke-api", help="Run one isolated real OpenAI edit smoke test")
    smoke.add_argument("--component", default="weathered_captains_cap_01")
    smoke.add_argument("--animation", choices=("idle", "walk", "run"), default="idle")
    return parser


def _run_jobs(paths: tuple[Path, ...]) -> None:
    for path in paths:
        print(f"Processing {path.name}")
        metadata = generate_job(path)
        print(f"  {metadata['status']}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            summary = validate_pipeline()
            print(
                f"Valid: {summary['animations']} animations, "
                f"{summary['component_ideas']} ideas, "
                f"{summary['production_components']} production component(s)"
            )
        elif args.command == "prepare":
            outputs = prepare_pipeline()
            print(
                f"Prepared {len(outputs['masters'])} blue-mannequin masters, "
                f"{len(outputs['ramps'])} reversible ramps, and "
                f"{len(outputs['masks'])} slot masks under art_pipeline"
            )
        elif args.command == "generate":
            if args.bootstrap:
                jobs = queue_bootstrap_jobs(candidates=args.candidates)
                print(f"Queued/resumed {len(jobs)} bootstrap animation jobs")
                if not openai_api_available():
                    print(
                        "OPENAI_API_KEY is not configured; no API calls or fake assets were created.\n"
                        "Resume with: python component_pipeline.py generate --bootstrap"
                    )
                    return 2
                selected = tuple(
                    path
                    for path in jobs
                    if ((path.name.split("-idle-")[0].split("-walk-")[0].split("-run-")[0] in PILOT_COMPONENT_IDS) != args.remaining)
                )
                _run_jobs(selected)
            else:
                jobs = queue_component_jobs(
                    args.component,
                    animation_id=args.animation,
                    candidates=args.candidates,
                    force_new=args.new,
                    design_reference=args.design_reference,
                )
                print(f"Queued/resumed {len(jobs)} job(s)")
                if not openai_api_available():
                    animation_option = f" --animation {args.animation}" if args.animation else ""
                    print(
                        "OPENAI_API_KEY is not configured; no API calls or fake assets were created.\n"
                        f"Resume with: python component_pipeline.py generate --component {args.component}{animation_option}"
                    )
                    return 2
                _run_jobs(jobs)
        elif args.command == "normalize":
            print(normalize_job(args.job)["status"])
        elif args.command == "extract":
            print(extract_job(args.job)["status"])
        elif args.command == "qa":
            print(qa_job(args.job)["status"])
        elif args.command == "review":
            from src.ui.component_review_window import run_component_review

            return run_component_review(args.job)
        elif args.command == "promote":
            path = promote_candidate(args.job, args.candidate, replace=args.replace)
            print(f"Promoted {path}")
        elif args.command == "rebaseline":
            hashes = rebaseline_canonical(args.confirm, confirmed=True)
            print(f"Rebaselined {len(hashes)} canonical animations")
        elif args.command == "smoke-api":
            if not openai_api_available():
                raise PipelineError("OPENAI_API_KEY is required for smoke-api")
            jobs = queue_component_jobs(
                args.component,
                animation_id=args.animation,
                candidates=1,
                force_new=True,
            )
            _run_jobs(jobs)
        return 0
    except PipelineError as exc:
        print(f"component-pipeline: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
