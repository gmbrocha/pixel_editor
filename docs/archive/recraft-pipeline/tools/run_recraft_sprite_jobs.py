"""Guarded Recraft API submission, validation, resumption, and promotion CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.recraft_sprite_pipeline import (
    RecraftClient,
    RecraftPipelineError,
    check_candidate,
    load_job,
    load_pipeline_config,
    process_candidate,
    promote_recraft_component,
    submit_job_candidates,
)


def _float_csv(value: str) -> list[float]:
    try:
        return [float(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected comma-separated numbers") from exc


def _int_csv(value: str) -> list[int]:
    try:
        return [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected comma-separated integers") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check token identity and API-unit balance")

    submit = subparsers.add_parser("submit", help="Spend API units for job candidates")
    submit.add_argument("--job", required=True, type=Path)
    submit.add_argument("--submit", action="store_true", help="Required paid-action acknowledgement")
    submit.add_argument("--calibration", action="store_true")
    submit.add_argument("--strengths", type=_float_csv)
    submit.add_argument("--seeds", type=_int_csv)
    submit.add_argument("--max-outputs", type=int)

    validate = subparsers.add_parser("validate", help="Process one or all received candidates")
    validate.add_argument("--job", required=True, type=Path)
    validate.add_argument("--candidate")
    validate.add_argument("--check", action="store_true")

    resume = subparsers.add_parser("resume", help="Resume safe local processing without new spend")
    resume.add_argument("--job", required=True, type=Path)

    check = subparsers.add_parser("check", help="Deterministically verify candidate outputs")
    check.add_argument("--job", required=True, type=Path)
    check.add_argument("--candidate", required=True)

    promote = subparsers.add_parser("promote", help="Promote a complete approved Heroic matrix")
    promote.add_argument("--job", action="append", required=True, type=Path)
    return parser


def _candidate_ids(job_root: Path, requested: str | None = None) -> list[str]:
    job = load_job(job_root)
    ids = [str(record["id"]) for record in job["candidates"]]
    if requested is not None:
        if requested not in ids:
            raise RecraftPipelineError(f"Unknown candidate {requested!r}")
        return [requested]
    return ids


def main() -> int:
    args = _parser().parse_args()
    if args.command == "doctor":
        with RecraftClient() as client:
            print(json.dumps(client.doctor(), indent=2))
        return 0
    if args.command == "submit":
        config = load_pipeline_config()
        if args.calibration:
            strengths = [float(value) for value in config["calibration_strengths"]]
            seeds = [int(value) for value in config["calibration_seeds"]]
            maximum = int(args.max_outputs or config["calibration_max_outputs"])
        else:
            job = load_job(args.job)
            strengths = args.strengths or [float(job["provider"]["strength"])]
            seeds = args.seeds or [int(config["calibration_seeds"][0])]
            maximum = int(args.max_outputs or len(strengths) * len(seeds))
        candidates = submit_job_candidates(
            args.job,
            strengths=strengths,
            seeds=seeds,
            max_outputs=maximum,
            submit=args.submit,
        )
        print(f"Received and validated {len(candidates)} candidates")
        for candidate in candidates:
            print(candidate)
        return 0
    if args.command in ("validate", "resume"):
        job = load_job(args.job)
        unknown = [
            str(record["id"])
            for record in job["candidates"]
            if record.get("state") == "unknown_submission"
        ]
        if unknown:
            print(
                "Unresolved ambiguous submissions were not retried: "
                + ", ".join(unknown),
                file=sys.stderr,
            )
        requested = args.candidate if args.command == "validate" else None
        for candidate in _candidate_ids(args.job, requested):
            raw = args.job / "candidates" / candidate / "raw" / "output.png"
            if not raw.is_file():
                continue
            if args.command == "validate" and args.check:
                mismatches = check_candidate(args.job, candidate)
                if mismatches:
                    raise SystemExit("Candidate outputs differ: " + ", ".join(mismatches))
                print(f"Verified {candidate}")
            else:
                validation = process_candidate(args.job, candidate)
                print(f"{candidate}: {validation['status']}")
        return 0
    if args.command == "check":
        mismatches = check_candidate(args.job, args.candidate)
        if mismatches:
            raise SystemExit("Candidate outputs differ: " + ", ".join(mismatches))
        print(f"Verified deterministic Recraft outputs for {args.candidate}")
        return 0
    manifest = promote_recraft_component(args.job)
    print(f"Promoted approved Heroic component: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
