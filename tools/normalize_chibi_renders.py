"""Center paired chibi renders with one fixed translation per direction."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile

from PIL import Image


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (manifest_path.parent / path).resolve()


def _paths_for_direction(
    manifest_path: Path,
    data: dict[str, object],
    direction: str,
    field: str,
) -> list[Path]:
    return [
        _resolve(manifest_path, value)
        for sequence in data["sequences"].values()
        for value in sequence[field][direction]
    ]


def _union_bbox(paths: list[Path]) -> tuple[int, int, int, int]:
    union: tuple[int, int, int, int] | None = None
    size = None
    for path in paths:
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
        size = image.size if size is None else size
        if image.size != size:
            raise ValueError("Chibi render sizes differ")
        bbox = image.getchannel("A").getbbox()
        if bbox is None:
            raise ValueError(f"Chibi render is empty: {path}")
        union = bbox if union is None else (
            min(union[0], bbox[0]),
            min(union[1], bbox[1]),
            max(union[2], bbox[2]),
            max(union[3], bbox[3]),
        )
    if union is None:
        raise ValueError("No chibi renders were supplied")
    return union


def _shift(source: Path, destination: Path, offset: tuple[int, int]) -> None:
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    output = Image.new("RGBA", image.size, (0, 0, 0, 0))
    output.alpha_composite(image, offset)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.save(destination, format="PNG", optimize=False, compress_level=9)


def _build(manifest_path: Path, output_dir: Path) -> dict[str, object]:
    source = json.loads(manifest_path.read_text(encoding="utf-8"))
    if source.get("kind") != "paired_chibi_sprite_render":
        raise ValueError("Expected a paired chibi render manifest")
    directions = [str(value) for value in source["direction_order"]]
    render_size = int(source["render_size"])
    transforms = {}
    for direction in directions:
        paths = _paths_for_direction(manifest_path, source, direction, "directions")
        left, top, right, bottom = _union_bbox(paths)
        if min(left, top, render_size - right, render_size - bottom) < 2:
            raise RuntimeError(
                f"{direction} source rendering is clipped or lacks a two-pixel guard margin"
            )
        offset = (
            round(render_size * 0.5 - (left + right) * 0.5),
            round(render_size * 0.5 - (top + bottom) * 0.5),
        )
        transforms[direction] = {
            "source_union_bbox": [left, top, right, bottom],
            "translation": list(offset),
        }

    normalized = copy.deepcopy(source)
    source_hashes = {}
    output_hashes = {}
    for sequence_name, sequence in normalized["sequences"].items():
        for field, pass_name in (
            ("directions", "beauty"),
            ("semantic_directions", "semantic"),
        ):
            for direction in directions:
                outputs = []
                raw_values = source["sequences"][sequence_name][field][direction]
                for frame_index, raw_value in enumerate(raw_values):
                    source_path = _resolve(manifest_path, raw_value)
                    destination = (
                        output_dir
                        / pass_name
                        / sequence_name
                        / direction
                        / f"frame_{frame_index:02d}.png"
                    )
                    _shift(
                        source_path,
                        destination,
                        tuple(transforms[direction]["translation"]),
                    )
                    outputs.append(destination.relative_to(output_dir).as_posix())
                    source_hashes[str(source_path.resolve())] = _sha256(source_path)
                    output_hashes[
                        destination.relative_to(output_dir).as_posix()
                    ] = _sha256(destination)
                sequence[field][direction] = outputs
    normalized["kind"] = "normalized_paired_chibi_sprite_render"
    normalized["normalization"] = {
        "kind": "fixed_direction_translation",
        "source_manifest": str(manifest_path.resolve()),
        "source_manifest_sha256": _sha256(manifest_path),
        "transforms": transforms,
        "source_sha256": source_hashes,
        "output_sha256": output_hashes,
    }
    output = output_dir / "sprite_render_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(normalized, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return normalized


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="pf-chibi-normalize-") as temporary:
            candidate = Path(temporary)
            _build(args.manifest, candidate)
            if not args.output_dir.is_dir() or _tree(candidate) != _tree(args.output_dir):
                raise SystemExit("Normalized chibi renders differ")
        print(f"Verified normalized chibi renders in {args.output_dir.resolve()}")
        return 0
    _build(args.manifest, args.output_dir)
    print(f"Normalized chibi renders in {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
