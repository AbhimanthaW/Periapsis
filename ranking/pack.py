"""Versioned, checked, memory-mapped ranking pack."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import zlib
from pathlib import Path

import numpy as np


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(directory: Path, arrays: dict[str, np.ndarray], metadata: dict, extras: dict[str, Path] | None = None) -> dict:
    decoded = {}
    files = {}
    for name, array in sorted(arrays.items()):
        buffer = io.BytesIO()
        np.save(buffer, array, allow_pickle=False)
        raw = buffer.getvalue()
        filename = f"{name}.npy.zlib"
        (directory / filename).write_bytes(zlib.compress(raw, level=9))
        files[filename] = digest(directory / filename)
        decoded[name] = hashlib.sha256(raw).hexdigest()
    for name in ("concepts.json", "lexicon.json"):
        source = Path(__file__).with_name(name)
        shutil.copyfile(source, directory / name)
        files[name] = digest(directory / name)
    for name, source in sorted((extras or {}).items()):
        shutil.copyfile(source, directory / name)
        files[name] = digest(directory / name)
    files["cells.sqlite"] = digest(directory / "cells.sqlite")
    files["catalogue-context.json.gz"] = digest(directory / "catalogue-context.json.gz")
    payload = {**metadata, "files": files, "decoded_sha256": decoded}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    (directory / "manifest.json").write_bytes(encoded)
    return payload


class Pack:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        encoded = (self.directory / "manifest.json").read_bytes()
        self.manifest = json.loads(encoded)
        if (self.manifest["version"] != "cell-ranking-v3" or
                not {"cells.sqlite", "catalogue-context.json.gz"} <= self.manifest["files"].keys()):
            raise ValueError("unsupported ranking pack; rebuild the pack")
        for name, expected in self.manifest["files"].items():
            if digest(self.directory / name) != expected:
                raise ValueError(f"pack file {name} failed SHA-256")
        self.sha256 = hashlib.sha256(encoded).hexdigest()
        cache = Path(tempfile.gettempdir()) / "periapsis-ranking-mmap" / self.sha256
        cache.mkdir(parents=True, exist_ok=True)
        self.arrays = {}
        for filename in self.manifest["files"]:
            if not filename.endswith(".npy.zlib"):
                continue
            name = filename.removesuffix(".npy.zlib")
            expected = self.manifest["decoded_sha256"][name]
            target = cache / f"{name}.npy"
            if not target.exists():
                raw = zlib.decompress((self.directory / filename).read_bytes())
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise ValueError(f"decoded pack array {name} failed SHA-256")
                with tempfile.NamedTemporaryFile(dir=cache, suffix=".npy", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(raw)
                try:
                    os.replace(temporary, target)
                except PermissionError:
                    temporary.unlink(missing_ok=True)
                    if not target.exists() or digest(target) != expected:
                        raise
            if digest(target) != expected:
                raise ValueError(f"cached pack array {name} failed SHA-256")
            self.arrays[name] = np.load(target, mmap_mode="r", allow_pickle=False)

    def __getitem__(self, name: str):
        return self.arrays[name]
