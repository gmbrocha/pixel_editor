"""Offline preparation, ingestion, review, and calibration for Recraft sprites."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.character_forge import CHARACTER_LAYER_ORDER, CHARACTER_SLOTS
from src.core.recraft_sprite_pipeline import (
    DEFAULT_WORK_ROOT,
    VALIDATION_PROFILE,
    calibrate_validation_profile,
    ingest_candidate,
    prepare_job,
    record_review,
    serve_review,
)


def _csv_ints(value: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected comma-separated frame numbers") from exc
    if not values or any(value < 1 for value in values):
        raise argparse.ArgumentTypeError("Frames are one-based positive integers")
    return [value - 1 for value in values]


def _component(args: argparse.Namespace) -> dict[str, object] | None:
    if args.mode != "component":
        return None
    if args.component_file:
        data = json.loads(args.component_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SystemExit("Component JSON must contain an object")
        return data
    missing = [
        name
        for name in ("component_id", "component_name", "description", "slot")
        if not getattr(args, name)
    ]
    if missing:
        raise SystemExit(
            "Component mode requires --component-file or: "
            + ", ".join("--" + name.replace("_", "-") for name in missing)
        )
    occupies = args.occupies_slots or [args.slot]
    render_layers = {args.layer or "": []} if args.layer else None
    result: dict[str, object] = {
        "id": args.component_id,
        "display_name": args.component_name,
        "description": args.description,
        "slot": args.slot,
        "occupies_slots": occupies,
        "material": args.material,
        "colors": args.color,
        "mirror_safe": not args.explicit_left,
        "expected_pieces": args.expected_pieces,
        "hair_occlusion": args.hair_occlusion,
    }
    if args.layer:
        result["layer"] = args.layer
        result["render_layers"] = render_layers
    if args.envelope_px is not None:
        result["envelope_px"] = args.envelope_px
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Build a request package offline")
    prepare.add_argument("--base", required=True)
    prepare.add_argument("--camera", required=True, choices=("top_down", "three_quarter", "low"))
    prepare.add_argument("--animation", required=True, choices=("idle", "walk", "run"))
    prepare.add_argument("--direction", required=True, choices=("front", "back", "right", "left"))
    prepare.add_argument("--mode", choices=("component", "full_style_experiment"), default="component")
    prepare.add_argument("--model", choices=("recraftv4_1", "recraftv4_1_pro"))
    prepare.add_argument("--frames", type=_csv_ints, help="Optional one-based frame subset")
    prepare.add_argument("--job-id")
    prepare.add_argument("--component-file", type=Path)
    prepare.add_argument("--component-id")
    prepare.add_argument("--component-name")
    prepare.add_argument("--description")
    prepare.add_argument("--slot", choices=CHARACTER_SLOTS)
    prepare.add_argument("--occupies-slots", nargs="+", choices=CHARACTER_SLOTS)
    prepare.add_argument("--layer", choices=CHARACTER_LAYER_ORDER)
    prepare.add_argument("--material", default="unspecified")
    prepare.add_argument("--color", action="append", default=[])
    prepare.add_argument("--expected-pieces", type=int, default=1)
    prepare.add_argument("--envelope-px", type=int)
    prepare.add_argument("--explicit-left", action="store_true")
    prepare.add_argument("--hair-occlusion", choices=("show", "clip", "hide"), default="show")

    ingest = subparsers.add_parser("ingest", help="Import a downloaded Recraft output")
    ingest.add_argument("--job", required=True, type=Path)
    ingest.add_argument("--input", required=True, type=Path)
    ingest.add_argument("--layout", required=True, help="COLSxROWS, for example 4x2 or 2x2")
    ingest.add_argument("--candidate-id")
    ingest.add_argument("--strict-layout", action="store_true")

    review = subparsers.add_parser("review", help="Open the local HTML reviewer")
    review.add_argument("--job", required=True, type=Path)
    review.add_argument("--candidate", required=True)
    review.add_argument("--port", type=int, default=0)
    review.add_argument("--no-browser", action="store_true")

    decide = subparsers.add_parser("decide", help="Record a manual decision without the browser")
    decide.add_argument("--job", required=True, type=Path)
    decide.add_argument("--candidate", required=True)
    decide.add_argument("--status", required=True, choices=("approved", "rejected"))
    decide.add_argument("--notes", default="")

    calibrate = subparsers.add_parser("calibrate", help="Learn gates from reviewed candidates")
    calibrate.add_argument("--job", required=True, action="append", type=Path)
    calibrate.add_argument("--output", type=Path, default=VALIDATION_PROFILE)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "prepare":
        root = prepare_job(
            base=args.base,
            camera=args.camera,
            animation=args.animation,
            direction=args.direction,
            mode=args.mode,
            component=_component(args),
            selected_frames=args.frames,
            model=args.model,
            job_id=args.job_id,
            work_root=args.work_root,
        )
        print(f"Prepared Recraft job: {root}")
        print(f"Request board: {root / 'source' / 'request_board.png'}")
        return 0
    if args.command == "ingest":
        candidate = ingest_candidate(
            args.job,
            args.input,
            layout=args.layout,
            candidate_id=args.candidate_id,
            strict_layout=args.strict_layout,
        )
        print(f"Ingested and validated candidate {candidate}")
        print(args.job.resolve() / "candidates" / candidate / "review" / "index.html")
        return 0
    if args.command == "review":
        serve_review(
            args.job,
            args.candidate,
            port=args.port,
            open_browser=not args.no_browser,
        )
        return 0
    if args.command == "decide":
        decision = record_review(
            args.job, args.candidate, status=args.status, notes=args.notes
        )
        print(json.dumps(decision, indent=2))
        return 0
    profile = calibrate_validation_profile(args.job, output_path=args.output)
    print(
        f"Wrote {args.output.resolve()} with {len(profile['hard_metrics'])} "
        "perfectly separating hard metrics"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
