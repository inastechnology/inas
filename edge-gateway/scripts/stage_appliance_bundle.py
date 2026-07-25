#!/usr/bin/env python3
import argparse
import hashlib
import shutil
from pathlib import Path

EXCLUDED_NAMES = {
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage a non-destructive INAS Edge Gateway source bundle")
    parser.add_argument("--output", required=True, help="new, non-existent directory outside the repository")
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[2]
    output = Path(args.output).expanduser().resolve()
    _validate_output(output, repository_root)
    output.mkdir(parents=True)

    shutil.copytree(
        repository_root / "edge-gateway",
        output / "edge-gateway",
        ignore=shutil.ignore_patterns(*EXCLUDED_NAMES, "*.pyc"),
    )
    shutil.copytree(
        repository_root / "shared" / "edge-runtime",
        output / "shared" / "edge-runtime",
        ignore=shutil.ignore_patterns(*EXCLUDED_NAMES, "*.pyc"),
    )
    _write_manifest(output)
    print(output)
    return 0


def _validate_output(output: Path, repository_root: Path) -> None:
    if output == Path("/") or output == Path.home().resolve():
        raise ValueError("output must not be the filesystem root or home directory")
    if output == repository_root or output.is_relative_to(repository_root):
        raise ValueError("output must be outside the source repository")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")


def _write_manifest(root: Path) -> None:
    lines = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
