#!/usr/bin/env python3
"""Inventory regular files in the public model cache as deterministic JSONL."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import NoReturn

ALLOWED_TOP_LEVEL = {"ckpts", "loras", "huggingface", "torch", "compute-cache"}


def fail(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    configured = os.environ.get("PUBLIC_MODEL_ROOT", "/workspace/wangp-public-models")
    root = Path(configured)
    if not root.is_absolute() or not root.is_dir():
        fail("PUBLIC_MODEL_ROOT must be an existing absolute directory")
    if root.is_symlink():
        fail("PUBLIC_MODEL_ROOT may not be a symlink")
    root = root.resolve(strict=True)

    files: list[Path] = []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in dirnames:
            path = current_path / name
            relative = path.relative_to(root)
            if len(relative.parts) == 1 and name not in ALLOWED_TOP_LEVEL:
                fail(f"unexpected top-level public cache path: {name}")
            if path.is_symlink():
                fail(f"symlinked directory is not allowed: {relative}")
        for name in filenames:
            path = current_path / name
            relative = path.relative_to(root)
            if len(relative.parts) == 1 or relative.parts[0] not in ALLOWED_TOP_LEVEL:
                fail(f"file is outside an allowed public cache directory: {relative}")
            if path.is_symlink() or not path.is_file():
                fail(f"non-regular file is not allowed: {relative}")
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                fail(f"file escaped PUBLIC_MODEL_ROOT: {relative}")
            files.append(path)

    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        record = {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": digest.hexdigest(),
        }
        print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())