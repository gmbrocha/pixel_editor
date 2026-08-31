"""Build editable, conservatively pre-cleaned sheets for fitted components."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.component_cleanup import cleanup_component_sheet


ASSET_ROOT = ROOT / "assets" / "character-forge"
DEFAULT_OUTPUT = ROOT / "animation_images_models" / "component_cleanup_v2"
OVERRIDE_SOURCE_CONFIG = (
    ROOT / "animation_images_models" / "component_override_sources.json"
)
SEQUENCES = ("idle", "walk", "run")
EXPECTED_SIZES = {"idle": (1792, 512), "walk": (1024, 512), "run": (1024, 512)}
USER_AUTHORED_DIRS = {"new_hand_authored"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registered_override_records() -> tuple[tuple[Path, dict[str, object]], ...]:
    """Return cleanup-bundle paths that are also approved edit sources.

    These files are deliberately user-owned even though they live inside the
    generated review bundle. Rebuilding the bundle must never replace them
    with the currently promoted output, since doing so changes provenance and
    can overwrite an unpromoted edit.
    """
    if not OVERRIDE_SOURCE_CONFIG.is_file():
        return ()
    config = json.loads(OVERRIDE_SOURCE_CONFIG.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported component override source configuration")
    prefix = DEFAULT_OUTPUT.relative_to(ROOT / "animation_images_models")
    records: dict[Path, dict[str, object]] = {}
    for record in config.get("overrides", []):
        source = Path(str(record["source"]))
        try:
            relative = source.relative_to(prefix)
        except ValueError:
            continue
        records[relative] = record
    return tuple(
        sorted(records.items(), key=lambda item: item[0].as_posix())
    )


def _registered_override_sources() -> tuple[Path, ...]:
    return tuple(relative for relative, _record in _registered_override_records())


def _copy_registered_override_sources(source_root: Path, target_root: Path) -> None:
    for relative in _registered_override_sources():
        source = source_root / relative
        if not source.is_file():
            raise FileNotFoundError(
                f"Registered component override source is missing: {source}"
            )
        destination = target_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _refresh_registered_override_metadata(output_root: Path) -> None:
    """Describe preserved edit sources without calling them live mirrors."""
    bundle_path = output_root / "bundle_manifest.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    variants = {
        (str(row["fit"]), str(row["family_id"])): row
        for row in bundle["variants"]
    }
    for relative, record in _registered_override_records():
        source = output_root / relative
        sequence = str(record["sequence"])
        manifest_path = (
            output_root
            / str(record["base_id"])
            / str(record["family_id"])
            / "cleanup_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_hash = _sha256(source)
        manifest["output_sha256"][sequence] = source_hash
        manifest.setdefault("registered_override_sources", {})[sequence] = {
            "source_config": OVERRIDE_SOURCE_CONFIG.relative_to(ROOT).as_posix(),
            "sha256": source_hash,
            "authoritative_directions": record["authoritative_directions"],
            "derived_directions": record["derived_directions"],
            "status": "approved_edit_source",
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        variants[(str(record["base_id"]), str(record["family_id"]))][
            "manifest_sha256"
        ] = _sha256(manifest_path)
    bundle["registered_override_source_count"] = len(
        _registered_override_records()
    )
    bundle_path.write_text(
        json.dumps(bundle, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.removeprefix("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _manifest_palette(manifest: dict[str, object]) -> tuple[tuple[int, int, int], ...]:
    ramp = manifest["colorRamp"]
    assert isinstance(ramp, dict)
    return tuple(_rgb(str(value)) for value in ramp["colors"])


def _protected_components(part: dict[str, object]) -> int:
    # A real second hand/foot remains because it is substantial or spatially
    # plausible under the shared island rule. Reserving it unconditionally lets
    # a tiny remote artifact masquerade as the second member of the pair.
    return 1


def _review_boards(
    output_root: Path,
    family_manifest: dict[str, object],
) -> dict[str, str]:
    review_root = output_root / "review"
    review_root.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    cell = 176
    for base_id in family_manifest["bases"]:
        for sequence in SEQUENCES:
            with Image.open(ASSET_ROOT / "bases" / base_id / f"{sequence}.png") as opened:
                base_frame = opened.convert("RGBA").crop((0, 0, 128, 128))
            board = Image.new("RGBA", (cell * 5, cell * 5), (27, 29, 34, 255))
            draw = ImageDraw.Draw(board)
            for index, family in enumerate(family_manifest["families"]):
                overlay_path = output_root / base_id / family["id"] / f"{sequence}.png"
                with Image.open(overlay_path) as opened:
                    overlay = opened.convert("RGBA").crop((0, 0, 128, 128))
                frame = Image.alpha_composite(base_frame, overlay)
                x = (index % 5) * cell
                y = (index // 5) * cell
                board.alpha_composite(frame, (x + 24, y + 8))
                label = str(family["name"])
                if len(label) > 23:
                    label = label[:20] + "..."
                draw.text((x + 5, y + 143), label, fill=(235, 238, 242, 255))
            output = review_root / f"{base_id}-{sequence}.png"
            board.save(output, format="PNG", optimize=False, compress_level=9)
            hashes[output.relative_to(output_root).as_posix()] = _sha256(output)
    return hashes


def _copy_base_sprites(
    output_root: Path,
    family_manifest: dict[str, object],
) -> dict[str, object]:
    """Copy exact Low-view runtime bases beside editable component sheets."""
    destination_root = output_root / "base_sprites"
    bases: dict[str, object] = {}
    for base_id, display_name in family_manifest["bases"].items():
        records: dict[str, object] = {}
        for sequence in SEQUENCES:
            source = ASSET_ROOT / "bases" / base_id / f"{sequence}.png"
            destination = destination_root / base_id / f"{sequence}.png"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            with Image.open(destination) as opened:
                dimensions = list(opened.size)
            records[sequence] = {
                "file": destination.relative_to(output_root).as_posix(),
                "sha256": _sha256(destination),
                "source": source.relative_to(ROOT).as_posix(),
                "source_sha256": _sha256(source),
                "dimensions": dimensions,
            }
        bases[base_id] = {"name": display_name, "animations": records}
    manifest = {
        "schema_version": 1,
        "kind": "component_authoring_base_sprite_references",
        "camera_height": "low",
        "direction_rows": ["front", "back", "right", "left"],
        "frame_size": [128, 128],
        "bases": bases,
    }
    manifest_path = destination_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return {
        "directory": destination_root.relative_to(output_root).as_posix(),
        "manifest": manifest_path.relative_to(output_root).as_posix(),
        "manifest_sha256": _sha256(manifest_path),
        "base_count": len(bases),
        "sheet_count": len(bases) * len(SEQUENCES),
    }


def _build(output_root: Path) -> dict[str, object]:
    family_manifest = json.loads(
        (ASSET_ROOT / "component_families_manifest.json").read_text(encoding="utf-8")
    )
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    variants: list[dict[str, object]] = []
    aggregate = {
        "removed_islands": 0,
        "removed_island_pixels": 0,
        "chamfered_outline_pixels": 0,
        "removed_spurs": 0,
        "removed_spur_pixels": 0,
        "filled_holes": 0,
        "filled_hole_pixels": 0,
    }
    for family in family_manifest["families"]:
        for variant in family["variants"]:
            manifest_path = ASSET_ROOT / variant["manifest"]
            part = json.loads(manifest_path.read_text(encoding="utf-8"))
            palette = _manifest_palette(part)
            outline = _rgb(str(part["provenance"]["outline"]["color"]))
            variant_dir = output_root / variant["fit"] / family["id"]
            variant_dir.mkdir(parents=True, exist_ok=True)
            sequence_reports: dict[str, object] = {}
            output_hashes: dict[str, str] = {}
            source_hashes: dict[str, str] = {}
            row: dict[str, object] = {
                "base_id": variant["fit"],
                "family_id": family["id"],
                "display_name": family["name"],
                "slot": family["slot"],
            }
            for sequence in SEQUENCES:
                source_path = manifest_path.parent / part["animations"][sequence]
                with Image.open(source_path) as opened:
                    source = opened.convert("RGBA")
                output_path = variant_dir / f"{sequence}.png"
                canonical_cleanup = part.get("provenance", {}).get("cleanup")
                if (
                    isinstance(canonical_cleanup, dict)
                    and canonical_cleanup.get("kind")
                    == "canonical_component_preprocessing"
                ):
                    report_data = canonical_cleanup["reports"][sequence]
                    shutil.copy2(source_path, output_path)
                    source_preprocessed = True
                else:
                    cleaned, report = cleanup_component_sheet(
                        source,
                        outline_rgb=outline,
                        palette=palette,
                        protected_components=_protected_components(part),
                    )
                    cleaned.save(
                        output_path, format="PNG", optimize=False, compress_level=9
                    )
                    report_data = report.to_dict()
                    source_preprocessed = False
                sequence_reports[sequence] = report_data
                source_hashes[sequence] = _sha256(source_path)
                output_hashes[sequence] = _sha256(output_path)
                row[sequence] = output_path.relative_to(output_root).as_posix()
                for key in aggregate:
                    aggregate[key] += int(report_data[key])
            variant_manifest = {
                "schema_version": 1,
                "kind": "editable_component_cleanup_candidate",
                "status": "editable_mirror_of_promoted_baseline",
                "component_id": part["id"],
                "family_id": family["id"],
                "display_name": family["name"],
                "fit": variant["fit"],
                "slot": family["slot"],
                "direction_rows": ["front", "back", "right", "left"],
                "frame_size": [128, 128],
                "palette": part["colorRamp"],
                "cleanup_settings": {
                    "max_island_area": 16,
                    "max_island_to_largest_ratio": 0.20,
                    "max_nearby_island_gap": 6,
                    "max_enclosed_hole_area": 2,
                    "max_terminal_spur_length": 2,
                    "protected_largest_components": _protected_components(part),
                    "outline_corner_passes": 1,
                    "source_already_preprocessed": source_preprocessed,
                },
                "source_manifest": variant["manifest"],
                "source_sha256": source_hashes,
                "output_sha256": output_hashes,
                "cleanup": sequence_reports,
            }
            variant_manifest_path = variant_dir / "cleanup_manifest.json"
            variant_manifest_path.write_text(
                json.dumps(variant_manifest, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            row["manifest"] = variant_manifest_path.relative_to(output_root).as_posix()
            rows.append(row)
            variants.append(
                {
                    "component_id": part["id"],
                    "family_id": family["id"],
                    "fit": variant["fit"],
                    "slot": family["slot"],
                    "manifest": row["manifest"],
                    "manifest_sha256": _sha256(variant_manifest_path),
                }
            )

    index_path = output_root / "index.csv"
    with index_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "base_id", "family_id", "display_name", "slot",
                "idle", "walk", "run", "manifest",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)

    review_hashes = _review_boards(output_root, family_manifest)
    base_sprites = _copy_base_sprites(output_root, family_manifest)
    manifest = {
        "schema_version": 1,
        "kind": "component_cleanup_review_bundle",
        "status": "editable_mirror_of_promoted_baseline",
        "family_count": int(family_manifest["family_count"]),
        "variant_count": len(variants),
        "sheet_count": len(variants) * len(SEQUENCES),
        "cleanup_totals": aggregate,
        "index": {"file": index_path.name, "sha256": _sha256(index_path)},
        "review_boards": review_hashes,
        "base_sprites": base_sprites,
        "variants": variants,
    }
    manifest_path = output_root / "bundle_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    readme = f"""# Component Cleanup V2 Review Bundle

This folder contains {manifest['sheet_count']} editable, component-only PNG
sprite sheets: 25 families fitted to four bases across Idle, Walk, and Run.
These files are exact editable mirrors of the preprocessed sheets currently
promoted in Character Forge, except registered approved-edit sources: those
preserve the user-authored direction rows while the live sheet may also contain
a generated mirrored direction. Later manual edits here still require promotion.

For a registered single-component edit, use
`python tools/promote_component_edit.py --component <component-id> --sequence run`.
It updates only the affected Forge variant and this bundle's related metadata;
the exhaustive family and cleanup builders remain checkpoint operations.

## Layout

- Cell size: 128 x 128 pixels.
- Rows: Front, Back, Right, Left.
- Idle: 14 columns, 1792 x 512 (sampled from authored frames 1, 3, 5, 7,
  9, 11, 13, 15, 17, 19, 21, 23, 24, and 25).
- Walk and Run: 8 columns, 1024 x 512.
- Files: `<base-id>/<family-id>/idle.png`, `walk.png`, and `run.png`.
- Exact Low-view body references: `base_sprites/<base-id>/idle.png`,
  `walk.png`, and `run.png`. These are convenient scratch-authoring bases for
  new clothing, hair, or accessories; they are not cleanup candidates.

## Canonical preprocessing applied once

1. Remove detached four-connected islands no larger than 16 pixels when they
   are either smaller than 20% of the frame's largest component or more than
   six pixels away from it. A second hand/foot must pass the same size,
   proportion, and distance checks; no disconnected piece is reserved merely
   because it is second-largest.
2. Chamfer one-pixel outline corners only when the pixel is the removable corner
   of a solid 2x2 turn. Then repeat only the detached-island sweep to catch
   specks exposed by the chamfer; the outline itself is never thinned twice.
3. Fill only fully enclosed one- or two-pixel transparent holes, using the most
   common neighboring color from the component's declared palette.
4. Remove one-pixel-wide terminal silhouette spurs up to two pixels long only
   when they attach to an edge with opaque support on both sides. This catches
   stray stems without shortening unsupported narrow straps, toes, or fingers.

The live Character Forge family builder applies this pass once. This mirror
copies those canonical results byte-for-byte and never preprocesses them again.

The pass removed {aggregate['removed_islands']} detached islands
({aggregate['removed_island_pixels']} pixels), chamfered
{aggregate['chamfered_outline_pixels']} outline pixels, and filled
{aggregate['filled_holes']} tiny holes ({aggregate['filled_hole_pixels']} pixels).
It also removed {aggregate['removed_spurs']} terminal spurs
({aggregate['removed_spur_pixels']} pixels).

Use `index.csv` to navigate the 100 variants. Every component folder contains a
`cleanup_manifest.json` with source/output hashes and per-frame changes.
The twelve PNGs under `review/` composite the first Front frame over each model
for a quick whole-catalog sanity check; edit the component-only animation sheets,
not these flattened review boards.
"""
    (output_root / "README.md").write_text(
        readme, encoding="utf-8", newline="\n"
    )
    return manifest


def _compare_trees(expected_root: Path, actual_root: Path) -> list[str]:
    expected = {
        path.relative_to(expected_root): path
        for path in expected_root.rglob("*")
        if path.is_file() and path.relative_to(expected_root).parts[0] not in USER_AUTHORED_DIRS
    }
    actual = {
        path.relative_to(actual_root): path
        for path in actual_root.rglob("*")
        if path.is_file() and path.relative_to(actual_root).parts[0] not in USER_AUTHORED_DIRS
    }
    mismatches = sorted(
        relative.as_posix()
        for relative in set(expected) | set(actual)
        if relative not in expected
        or relative not in actual
        or expected[relative].read_bytes() != actual[relative].read_bytes()
    )
    return mismatches


def refresh_component_override_source(
    output_root: Path,
    component_id: str,
    sequence: str,
) -> None:
    """Refresh one preserved edit source and its cleanup-bundle bookkeeping."""
    matches = [
        (relative, record)
        for relative, record in _registered_override_records()
        if str(record["component_id"]) == component_id
        and str(record["sequence"]) == sequence
    ]
    if len(matches) != 1:
        raise ValueError(
            f"No unique registered override source for {component_id}/{sequence}"
        )
    relative, record = matches[0]
    editable_source = output_root / relative
    if not editable_source.is_file():
        raise FileNotFoundError(editable_source)

    bundle_path = output_root / "bundle_manifest.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    variant = next(
        (
            row
            for row in bundle["variants"]
            if row["component_id"] == component_id
        ),
        None,
    )
    if variant is None:
        raise RuntimeError(f"Missing {component_id} in {bundle_path}")
    cleanup_manifest_path = output_root / str(variant["manifest"])
    cleanup_manifest = json.loads(
        cleanup_manifest_path.read_text(encoding="utf-8")
    )
    live_manifest_path = (
        ASSET_ROOT
        / "parts"
        / str(record["slot"])
        / component_id
        / "manifest.json"
    )
    live_manifest = json.loads(live_manifest_path.read_text(encoding="utf-8"))
    live_sheet = live_manifest_path.parent / str(live_manifest["animations"][sequence])
    live_report = live_manifest["provenance"]["cleanup"]["reports"][sequence]
    old_report = cleanup_manifest["cleanup"][sequence]
    for key in bundle["cleanup_totals"]:
        bundle["cleanup_totals"][key] += int(live_report[key]) - int(
            old_report[key]
        )
    cleanup_manifest["source_sha256"][sequence] = _sha256(live_sheet)
    cleanup_manifest["output_sha256"][sequence] = _sha256(editable_source)
    cleanup_manifest["cleanup"][sequence] = live_report
    cleanup_manifest_path.write_text(
        json.dumps(cleanup_manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    variant["manifest_sha256"] = _sha256(cleanup_manifest_path)

    family_manifest = json.loads(
        (ASSET_ROOT / "component_families_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    bundle["review_boards"] = _review_boards(output_root, family_manifest)
    bundle_path.write_text(
        json.dumps(bundle, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    _refresh_registered_override_metadata(output_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--target",
        metavar="COMPONENT_ID",
        help="incrementally refresh one registered override source",
    )
    parser.add_argument("--sequence", choices=SEQUENCES, default="run")
    args = parser.parse_args()
    if args.force and args.check:
        parser.error("--force and --check are mutually exclusive")
    if args.target and (args.force or args.check):
        parser.error("--target cannot be combined with --force or --check")
    output_root = args.output_root.resolve()
    if args.target:
        refresh_component_override_source(
            output_root, args.target, args.sequence
        )
        print(
            f"Refreshed cleanup source {args.target}/{args.sequence} in "
            f"{output_root}"
        )
        return 0
    if args.check:
        if not output_root.is_dir():
            raise FileNotFoundError(output_root)
        with tempfile.TemporaryDirectory(prefix="pf-component-cleanup-") as temporary:
            candidate = Path(temporary)
            _build(candidate)
            _copy_registered_override_sources(output_root, candidate)
            _refresh_registered_override_metadata(candidate)
            mismatches = _compare_trees(candidate, output_root)
        if mismatches:
            raise SystemExit(
                "Component cleanup bundle differs: " + ", ".join(mismatches[:20])
            )
        print(f"Verified component cleanup bundle in {output_root}")
        return 0

    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"{output_root} exists; use --force")
        manifest_path = output_root / "bundle_manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError(
                f"Refusing to replace unrecognized cleanup directory {output_root}"
            )
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("kind") != "component_cleanup_review_bundle":
            raise RuntimeError(
                f"Refusing to replace unrecognized cleanup directory {output_root}"
            )
        with tempfile.TemporaryDirectory(prefix="pf-user-authored-") as temporary:
            backup_root = Path(temporary)
            preserved = []
            for name in USER_AUTHORED_DIRS:
                source = output_root / name
                if source.is_dir():
                    shutil.copytree(source, backup_root / name)
                    preserved.append(name)
            _copy_registered_override_sources(output_root, backup_root)
            shutil.rmtree(output_root)
            manifest = _build(output_root)
            for name in preserved:
                shutil.copytree(backup_root / name, output_root / name)
            _copy_registered_override_sources(backup_root, output_root)
            _refresh_registered_override_metadata(output_root)
    else:
        manifest = _build(output_root)
        _refresh_registered_override_metadata(output_root)
    print(
        f"Built {manifest['variant_count']} variants and "
        f"{manifest['sheet_count']} editable sheets in {output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
