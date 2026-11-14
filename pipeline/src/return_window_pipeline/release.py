"""Create and verify versioned offline atlas candidates in a local registry."""

from hashlib import sha256 as hash_bytes
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
from tempfile import TemporaryDirectory

import pyproj
import rasterio

from . import __version__
from .atlas import MANIFEST as ATLAS_MANIFEST, build_global_atlas, validate_global_atlas
from .errors import ConfigurationError, IntegrityError
from .ingestion import sha256, write_json
from .models import SourceSpec, canonical, keys, safe_name, text


RELEASE_MANIFEST = "release-manifest.json"
ATLAS_ID = "mars-mola-meg004"
SOURCE_CONFIG = "source-config.json"
REGION_CATALOG = "region-catalog.json"


def _destination(registry: Path, release_version: str) -> Path:
    atlas_root = registry / ATLAS_ID
    destination = atlas_root / safe_name(release_version, "atlas release version")
    if atlas_root.is_symlink() or destination.is_symlink():
        raise IntegrityError("Atlas registry and release entries must be ordinary directories")
    return destination


def _receipt(path: Path, relative_path: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise IntegrityError(f"Missing or invalid release file: {relative_path}")
    return {"path": relative_path, "bytes": path.stat().st_size, "sha256": sha256(path)}


def _manifest(directory: Path, release_version: str, report: dict, software: dict) -> dict:
    return {
        "schema_version": 1,
        "atlas_id": ATLAS_ID,
        "release_version": release_version,
        "status": "release_candidate",
        "inputs": {
            "source_config": _receipt(directory / SOURCE_CONFIG, SOURCE_CONFIG),
            "region_catalog": _receipt(directory / REGION_CATALOG, REGION_CATALOG),
        },
        "atlas_manifest": _receipt(directory / "atlas" / ATLAS_MANIFEST, "atlas/" + ATLAS_MANIFEST),
        "software": software,
        "validation": {
            "offline_atlas_and_region_index": "passed",
            "G10_browser_runtime": "not_evaluated",
        },
        "content": report,
        "omissions": ["Browser integration", "Display tile pyramid", "Detailed routing terrain"],
    }


def build_atlas_release(
    configuration: Path, regions: Path, workspace: Path, registry: Path, release_version: str,
) -> dict:
    destination = _destination(registry, release_version)
    if destination.exists():
        raise ConfigurationError(f"Atlas release version already exists: {release_version}")
    source_bytes = configuration.read_bytes()
    spec = SourceSpec.from_json(source_bytes, configuration)
    software = {
        "return_window_pipeline": __version__,
        "python": platform.python_version(),
        "numpy": version("numpy"),
        "rasterio": rasterio.__version__,
        "rasterio_gdal": rasterio.__gdal_version__,
        "rasterio_proj": rasterio.__proj_version__,
        "pyproj": pyproj.__version__,
        "pyproj_proj": pyproj.proj_version_str,
        "truststore": version("truststore"),
    }

    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".atlas-release-", dir=destination.parent) as temporary:
        staging = Path(temporary) / release_version
        staging.mkdir()
        (staging / SOURCE_CONFIG).write_bytes(source_bytes)
        (staging / REGION_CATALOG).write_bytes(regions.read_bytes())
        report = build_global_atlas(spec, workspace, staging / "atlas", regions=staging / REGION_CATALOG)
        manifest = _manifest(staging, release_version, report, software)
        write_json(staging / RELEASE_MANIFEST, manifest)
        if destination.exists() or destination.is_symlink():
            raise ConfigurationError(f"Atlas release version already exists: {release_version}")
        staging.rename(destination)
    return manifest


def verify_atlas_release(
    configuration: Path, regions: Path, workspace: Path, registry: Path, release_version: str,
    *, expected_manifest_sha256: str | None = None,
) -> dict:
    if expected_manifest_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256):
        raise ConfigurationError("The trusted manifest receipt requires a lowercase SHA-256")
    directory = _destination(registry, release_version)
    expected_files = {RELEASE_MANIFEST, SOURCE_CONFIG, REGION_CATALOG, "atlas"}
    if {entry.name for entry in directory.iterdir()} != expected_files:
        raise IntegrityError("Atlas release inventory does not match the release contract")
    atlas = directory / "atlas"
    if atlas.is_symlink() or not atlas.is_dir():
        raise IntegrityError("Atlas layers must be in an ordinary release directory")
    for name, trusted in ((SOURCE_CONFIG, configuration), (REGION_CATALOG, regions)):
        actual = _receipt(directory / name, name)
        if actual["sha256"] != sha256(trusted):
            raise IntegrityError(f"Release input differs from the trusted checkout: {name}")

    path = directory / RELEASE_MANIFEST
    if path.is_symlink() or not path.is_file():
        raise IntegrityError(f"Missing or invalid release file: {RELEASE_MANIFEST}")
    raw_manifest = path.read_bytes()
    if expected_manifest_sha256 is not None and hash_bytes(raw_manifest).hexdigest() != expected_manifest_sha256:
        raise IntegrityError("Release manifest does not match the trusted handoff receipt")
    try:
        manifest = json.loads(raw_manifest)
        software = keys(
            manifest["software"],
            {"return_window_pipeline", "python", "numpy", "rasterio", "rasterio_gdal",
             "rasterio_proj", "pyproj", "pyproj_proj", "truststore"},
            set(), "release software",
        )
        for key, value in software.items():
            text(value, key)
    except (KeyError, TypeError, ValueError) as error:
        raise IntegrityError(f"Malformed atlas release manifest: {error}") from error
    report = validate_global_atlas(SourceSpec.load(configuration), workspace, atlas, regions=regions)
    expected = _manifest(directory, release_version, report, software)
    try:
        matches = canonical(manifest) == canonical(expected)
    except ValueError as error:
        raise IntegrityError("Atlas release manifest contains invalid JSON values") from error
    if not matches:
        raise IntegrityError("Release manifest differs from the validated atlas and input receipts")
    return manifest
