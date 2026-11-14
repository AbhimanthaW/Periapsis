"""Shared location for archives and generated cell map artifacts."""
import os
from pathlib import Path


def build_workspace():
    """Use a caller-selected workspace or the repository's ignored data directory."""
    default = Path(__file__).resolve().parents[2] / "data" / "cell-map"
    return Path(os.environ.get("RW_CELL_MAP_WORKSPACE", default)).expanduser().resolve()
