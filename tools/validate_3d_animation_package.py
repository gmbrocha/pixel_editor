from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.animation_3d_package import (  # noqa: E402
    Animation3DPackageError,
    load_animation_3d_package,
    package_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Pixel Forge Blender/3D animation package."
    )
    parser.add_argument("package", type=Path, help="Package directory or manifest.json")
    args = parser.parse_args(argv)
    try:
        package = load_animation_3d_package(args.package)
    except (Animation3DPackageError, OSError) as exc:
        print(f"Invalid: {exc}", file=sys.stderr)
        return 1
    print(f"Valid: {package_summary(package)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
