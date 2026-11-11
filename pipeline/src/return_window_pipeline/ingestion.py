from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
import ssl
from pathlib import Path
import shutil
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid

import pyproj
import rasterio
import truststore

from . import __version__
from .errors import ConfigurationError, IntegrityError, PipelineError
from .labels import read_pds4
from .models import SourceSpec, digest
from .raster import inspect_observation_support, inspect_raster


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def write_json(path: Path, value: object, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n")
        if exclusive:
            os.link(temporary, path)
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def discard_staging(staging: Path, workspace: Path) -> None:
    resolved = staging.resolve()
    expected_parent = (workspace / "cache" / "incoming").resolve()
    if resolved.parent != expected_parent or len(resolved.name) != 32 or any(c not in "0123456789abcdef" for c in resolved.name):
        raise IntegrityError("Refusing to remove a directory outside the incoming cache")
    shutil.rmtree(resolved)


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise IntegrityError("HTTPS acquisition refused a non-HTTPS redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def acquisition_opener():
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    custom_ca = os.environ.get("SSL_CERT_FILE")
    if custom_ca:
        context.load_verify_locations(cafile=custom_ca)
    return urllib.request.build_opener(HTTPSRedirect(), urllib.request.HTTPSHandler(context=context))


def copy_member(member, destination: Path, limit: int, opener=None) -> dict:
    request = urllib.request.Request(member.uri, headers={"User-Agent": f"ReturnWindowPipeline/{__version__}"})
    try:
        if opener is None and urlsplit(member.uri).scheme == "https":
            opener = acquisition_opener()
        open_member = opener.open if opener is not None else urllib.request.urlopen
        with open_member(request, timeout=30) as source:
            content_length = source.headers.get("Content-Length")
            if content_length and int(content_length) > limit:
                raise IntegrityError(f"{member.name} exceeds max_member_bytes")
            if "text/html" in source.headers.get("Content-Type", "").lower():
                raise IntegrityError(f"{member.name} returned an HTML page instead of an asset")
            checksum, size = hashlib.sha256(), 0
            with destination.open("wb") as target:
                while block := source.read(1024 * 1024):
                    size += len(block)
                    if size > limit:
                        raise IntegrityError(f"{member.name} exceeds max_member_bytes")
                    checksum.update(block)
                    target.write(block)
            if not size or (content_length is not None and size != int(content_length)):
                raise IntegrityError(f"{member.name} is empty or truncated")
            actual = checksum.hexdigest()
            if member.expected_sha256 and actual != member.expected_sha256:
                raise IntegrityError(f"SHA-256 mismatch for {member.name}: expected {member.expected_sha256}, received {actual}")
            return {
                "name": member.name, "uri": member.uri, "resolved_uri": source.geturl(),
                "sha256": actual, "bytes": size, "retrieved_at": utc_now(),
                "checksum_pin_verified": member.expected_sha256 is not None,
                "http_etag": source.headers.get("ETag"),
                "http_last_modified": source.headers.get("Last-Modified"),
                "content_type": source.headers.get("Content-Type"),
            }
    except (OSError, urllib.error.URLError, ValueError) as error:
        if isinstance(error, PipelineError):
            raise
        raise IntegrityError(f"Cannot acquire {member.name}: {error}") from error


def validate_label_files(label: dict, staging: Path, expected_lid: str, expected_version: str) -> None:
    if label["logical_identifier"] != expected_lid or label["label_version"] != expected_version or label["target"] != "Mars":
        raise IntegrityError("PDS4 identity, version, or target differs from the pinned source")
    sizes = {"SignedMSB2": 2, "UnsignedMSB2": 2, "SignedLSB2": 2, "UnsignedLSB2": 2,
             "SignedMSB4": 4, "UnsignedMSB4": 4, "SignedLSB4": 4, "UnsignedLSB4": 4,
             "IEEE754MSBSingle": 4, "IEEE754LSBSingle": 4, "IEEE754MSBDouble": 8, "IEEE754LSBDouble": 8}
    if label["data_type"] not in sizes:
        raise IntegrityError(f"Unsupported PDS4 element type {label['data_type']}")
    if label["offset_bytes"] < 0:
        raise IntegrityError("PDS4 data offset cannot be negative")
    expected_size = label["offset_bytes"] + label["shape"][0] * label["shape"][1] * sizes[label["data_type"]]
    data_file = staging / label["data_file"]
    if not data_file.is_file() or data_file.stat().st_size != expected_size:
        raise IntegrityError("PDS4 data file is missing, truncated, or has an unsupported extra payload")


def check_local_sidecars(spec: SourceSpec) -> None:
    supplied_uris = {m.uri for m in spec.members}
    for member in spec.members:
        parsed = urlsplit(member.uri)
        if parsed.scheme != "file" or Path(parsed.path).suffix.lower() not in {".tif", ".tiff"}:
            continue
        local = Path(urllib.request.url2pathname(parsed.path))
        for sidecar in (Path(str(local) + ".msk"), Path(str(local) + ".aux.xml"), local.with_suffix(".tfw"), local.with_suffix(".prj")):
            if sidecar.exists() and sidecar.resolve().as_uri() not in supplied_uris:
                raise ConfigurationError(f"Preserve the raster sidecar in members: {sidecar.name}")


def inspect_source(spec: SourceSpec, bundle: Path) -> dict:
    label = read_pds4(bundle / spec.pds4_label) if spec.pds4_label else None
    if label:
        validate_label_files(label, bundle, spec.expected_lid, spec.source_version)
    raster = inspect_raster(bundle / spec.entrypoint, spec, label)
    support = None
    if spec.support_entrypoint:
        support_label = read_pds4(bundle / spec.support_entrypoint)
        validate_label_files(support_label, bundle, spec.support_expected_lid, spec.support_expected_version)
        support = {
            "label": support_label,
            **inspect_observation_support(bundle / spec.support_entrypoint, raster, spec.reference, label=support_label),
        }
    return {
        "asset_id": spec.asset_id, "source_version": spec.source_version, "role": spec.role,
        "provider": spec.provider, "attribution": spec.attribution, "access_rights": spec.access_rights,
        "entrypoint": spec.entrypoint, "reference": asdict(spec.reference),
        "raster": raster, "label": label, "observation_support": support,
        "limitations": spec.limitations,
        "gate_results": {f"G{i}": "Not evaluated" for i in range(1, 11)},
        "capabilities": {"mapping": "Not evaluated", "regional_analysis": "Not evaluated", "routing": "Not evaluated", "science_tasks": "Not evaluated"},
        "diagnostics": {
            "source_bytes_read": True, "raster_readable": True,
            "declared_reference_matches_crs": True if label else None,
            "reference_evidence": "qualified_meg004_adapter" if label else "configured_reference_unverified",
            "all_member_checksum_pins_provided": all(m.expected_sha256 for m in spec.members),
        },
        "status": "Ingested source; formal release gates and regional suitability remain separate",
    }


def verify_record(record: dict, workspace: Path, *, spec: SourceSpec | None = None) -> dict:
    if not isinstance(record, dict) or record.get("source_record_schema_version") != 2:
        raise IntegrityError("Source record v2 is required; re-ingest reviewed source bytes in a fresh workspace")
    payload = {key: value for key, value in record.items() if key != "record_sha256"}
    if digest(payload) != record.get("record_sha256"):
        raise IntegrityError("Source record digest mismatch")
    if spec is None:
        spec = SourceSpec.from_dict(record["source_specification"])
    if record["specification_sha256"] != digest(spec.to_dict()) or record["source_specification"] != spec.to_dict():
        raise IntegrityError("Source record does not match its pinned specification")
    identity = record.get("bundle_sha256", "")
    if not isinstance(identity, str) or len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
        raise IntegrityError("Invalid content-cache identity")
    bundle = workspace / "cache" / "bundles" / identity
    if bundle.is_symlink():
        raise IntegrityError("Content bundle must be an ordinary directory")
    members = record["members"]
    if len(members) != len(spec.members):
        raise IntegrityError("Cached member inventory differs from the pinned specification")
    for member, pin in zip(members, spec.members):
        if (member["name"] != pin.name or member["uri"] != pin.uri
                or (pin.expected_sha256 is not None and member["sha256"] != pin.expected_sha256)
                or member["checksum_pin_verified"] is not (pin.expected_sha256 is not None)):
            raise IntegrityError("Cached member differs from the pinned specification")
        path = bundle / pin.name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != member["bytes"] or sha256(path) != member["sha256"]:
            raise IntegrityError(f"Cached member is missing or changed: {pin.name}")
    expected = digest(sorted((m["name"], m["sha256"]) for m in members))
    if expected != identity or {p.name for p in bundle.iterdir()} != {m.name for m in spec.members}:
        raise IntegrityError("Bundle identity or file inventory does not match its recorded members")
    # The digest detects record corruption, but a writer could recompute it.
    # Re-derive scientific interpretation from checked bytes and trusted policy.
    if digest(inspect_source(spec, bundle)) != digest({
        key: value for key, value in payload.items()
        if key not in {"source_record_schema_version", "source_specification", "specification_sha256",
                       "bundle_sha256", "created_at", "members", "tool_versions"}
    }):
        raise IntegrityError("Cached interpretation differs from verified source bytes and policy")
    return {"asset_id": spec.asset_id, "bundle_sha256": identity, "verified_members": len(members)}


def read_verified_record(path: Path, workspace: Path, *, spec: SourceSpec | None = None,
                         expected_record_sha256: str | None = None) -> tuple[dict, dict]:
    try:
        raw = path.read_bytes()
        if expected_record_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_record_sha256:
            raise IntegrityError("Source record bytes do not match the trusted handoff receipt")
        record = json.loads(raw)
        summary = verify_record(record, workspace, spec=spec)
        expected_name = f"{record['asset_id']}--{record['source_version']}--{record['specification_sha256']}.json"
        if path.name != expected_name:
            raise IntegrityError("Registry filename does not match the source record identity")
        return record, summary
    except PipelineError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise IntegrityError(f"Malformed source record: {path.name}") from error


def ingest(
    spec: SourceSpec, workspace: Path, *, offline: bool = False, refresh: bool = False,
    expected_record_sha256: str | None = None,
) -> tuple[dict, Path, bool]:
    if expected_record_sha256 is not None and (not offline or len(expected_record_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_record_sha256)):
        raise ConfigurationError("A record receipt requires offline mode and a lowercase SHA-256")
    workspace = workspace.resolve()
    spec_sha = digest(spec.to_dict())
    record_path = workspace / "registry" / f"{spec.asset_id}--{spec.source_version}--{spec_sha}.json"
    if record_path.exists() and not refresh:
        record, _ = read_verified_record(record_path, workspace, spec=spec,
                                         expected_record_sha256=expected_record_sha256)
        return record, record_path, True
    if offline:
        raise IntegrityError("Offline mode requires an existing verified cached source")
    check_local_sidecars(spec)
    staging = workspace / "cache" / "incoming" / uuid.uuid4().hex
    staging.mkdir(parents=True)
    try:
        opener = acquisition_opener() if any(urlsplit(m.uri).scheme == "https" for m in spec.members) else None
        members = [copy_member(member, staging / member.name, spec.max_member_bytes, opener) for member in spec.members]
        interpretation = inspect_source(spec, staging)
        bundle_sha = digest(sorted((m["name"], m["sha256"]) for m in members))
        record = {
            **interpretation,
            "source_record_schema_version": 2, "created_at": utc_now(),
            "bundle_sha256": bundle_sha, "specification_sha256": spec_sha,
            "source_specification": spec.to_dict(), "members": members,
            "tool_versions": {
                "return_window_pipeline": __version__,
                **{name: version(name) for name in ("numpy", "rasterio", "pyproj", "truststore")},
                "rasterio_gdal": rasterio.__gdal_version__, "rasterio_proj": rasterio.__proj_version__,
                "pyproj_proj": pyproj.proj_version_str,
            },
        }
        record["record_sha256"] = digest(record)
        if record_path.exists():
            existing, _ = read_verified_record(record_path, workspace, spec=spec)
            if existing["bundle_sha256"] != bundle_sha:
                raise IntegrityError("A pinned source changed bytes; preserve the existing record and investigate upstream versioning")
            discard_staging(staging, workspace)
            return existing, record_path, True
        bundle = workspace / "cache" / "bundles" / bundle_sha
        bundle.parent.mkdir(parents=True, exist_ok=True)
        try:
            staging.rename(bundle)
        except OSError:
            if not bundle.is_dir() or bundle.is_symlink():
                raise
            verify_record(record, workspace, spec=spec)
            discard_staging(staging, workspace)
        try:
            write_json(record_path, record, exclusive=True)
        except FileExistsError:
            existing, _ = read_verified_record(record_path, workspace, spec=spec)
            if existing["bundle_sha256"] != bundle_sha:
                raise IntegrityError("A concurrent ingestion published different bytes for the pinned source")
            return existing, record_path, True
        return record, record_path, False
    except Exception as error:
        quarantine = workspace / "quarantine" / staging.name
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        if staging.exists():
            staging.replace(quarantine)
        write_json(quarantine / "failure.json", {"asset_id": spec.asset_id, "time": utc_now(), "specification_sha256": spec_sha, "error": str(error), "published": False})
        if isinstance(error, PipelineError):
            raise
        raise IntegrityError(f"Ingestion failed: {error}") from error


def verify_workspace(workspace: Path) -> list[dict]:
    registry = workspace / "registry"
    if not registry.is_dir():
        raise IntegrityError("Source registry does not exist")
    return [read_verified_record(path, workspace)[1] for path in sorted(registry.glob("*.json"))]
