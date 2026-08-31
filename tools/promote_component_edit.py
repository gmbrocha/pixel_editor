"""Incrementally promote one approved component edit into Character Forge."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from build_character_component_families import (
    ASSET_ROOT,
    build_variant_incremental,
)
from build_component_cleanup_bundle import (
    DEFAULT_OUTPUT as CLEANUP_ROOT,
    refresh_component_override_source,
)
from promote_component_overrides import OUTPUT_ROOT, promote_target


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def promote_component_edit(component_id: str, sequence: str) -> float:
    started = time.perf_counter()
    override_manifest = promote_target(component_id, sequence)
    record = next(
        (
            item
            for item in override_manifest["overrides"]
            if item["component_id"] == component_id
            and item["sequence"] == sequence
        ),
        None,
    )
    if record is None:
        raise RuntimeError(f"Promoted override record is missing: {component_id}/{sequence}")

    variant = build_variant_incremental(ASSET_ROOT, component_id)
    refresh_component_override_source(CLEANUP_ROOT, component_id, sequence)

    source = ROOT / str(record["source"])
    override = OUTPUT_ROOT / str(record["file"])
    part_manifest_path = ASSET_ROOT / str(variant["manifest"])
    part_manifest = json.loads(part_manifest_path.read_text(encoding="utf-8"))
    live_sheet = part_manifest_path.parent / str(part_manifest["animations"][sequence])
    if _sha256(source) != record["source_sha256"]:
        raise RuntimeError(f"Source hash drifted during promotion: {source}")
    if _sha256(override) != record["output_sha256"]:
        raise RuntimeError(f"Override hash mismatch: {override}")
    if live_sheet.read_bytes() != override.read_bytes():
        raise RuntimeError(f"Live Character Forge sheet differs: {live_sheet}")
    approved = part_manifest["provenance"]["approvedOverrides"][sequence]
    if approved["sha256"] != record["output_sha256"]:
        raise RuntimeError(f"Live Character Forge manifest is stale: {part_manifest_path}")
    return time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", required=True, metavar="COMPONENT_ID")
    parser.add_argument("--sequence", default="run")
    args = parser.parse_args()
    elapsed = promote_component_edit(args.component, args.sequence)
    print(
        f"Promoted {args.component}/{args.sequence} incrementally in "
        f"{elapsed:.2f} seconds"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
