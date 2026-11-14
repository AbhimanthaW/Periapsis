"""Versioned, checked, memory-mapped ranking pack."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(directory: Path, arrays: dict[str, np.ndarray], metadata: dict, extras: dict[str, Path] | None = None) -> dict:
    for name, array in sorted(arrays.items()):
        np.save(directory / f"{name}.npy", array, allow_pickle=False)
    files = {f"{name}.npy": digest(directory / f"{name}.npy") for name in sorted(arrays)}
    for name in ("concepts.json", "lexicon.json"):
        source = Path(__file__).with_name(name)
        shutil.copyfile(source, directory / name)
        files[name] = digest(directory / name)
    for name, source in sorted((extras or {}).items()):
        shutil.copyfile(source, directory / name)
        files[name] = digest(directory / name)
    files["cells.sqlite"] = digest(directory / "cells.sqlite")
    payload = {**metadata, "files": files}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    (directory / "manifest.json").write_bytes(encoded)
    return payload


class Pack:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        encoded = (self.directory / "manifest.json").read_bytes()
        self.manifest = json.loads(encoded)
        if self.manifest["version"] != "cell-ranking-v2" or "cells.sqlite" not in self.manifest["files"]:
            raise ValueError("unsupported ranking pack; rebuild the pack")
        for name, expected in self.manifest["files"].items():
            if digest(self.directory / name) != expected:
                raise ValueError(f"pack file {name} failed SHA-256")
        self.sha256 = hashlib.sha256(encoded).hexdigest()
        self.arrays = {name.removesuffix(".npy"): np.load(self.directory / name, mmap_mode="r", allow_pickle=False)
                       for name in self.manifest["files"] if name.endswith(".npy")}

    def __getitem__(self, name: str):
        return self.arrays[name]
