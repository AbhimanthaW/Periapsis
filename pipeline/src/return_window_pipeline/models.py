from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from .errors import ConfigurationError


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{name} must be a nonempty string")
    return value


def keys(value: object, required: set[str], optional: set[str], name: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{name} must be an object")
    missing, unknown = required - value.keys(), value.keys() - required - optional
    if missing or unknown:
        raise ConfigurationError(f"{name}: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return value


def safe_name(value: object, name: str) -> str:
    value = text(value, name)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,149}", value) or value.endswith("."):
        raise ConfigurationError(f"{name} must be a simple portable filename or identifier")
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise ConfigurationError(f"{name} is a reserved filename")
    return value


@dataclass(frozen=True)
class MarsReference:
    body: str
    semi_major_m: float
    semi_minor_m: float
    latitude_type: str
    longitude_direction: str
    longitude_domain: str
    frame: str
    vertical_unit: str
    vertical_reference: str

    @classmethod
    def parse(cls, value: object) -> "MarsReference":
        required = set(cls.__dataclass_fields__)
        value = keys(value, required, set(), "reference")
        if value["body"] != "Mars":
            raise ConfigurationError("This pipeline requires an explicit Mars reference")
        for axis in ("semi_major_m", "semi_minor_m"):
            number = value[axis]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number <= 0:
                raise ConfigurationError(f"{axis} must be a positive finite number")
        if value["semi_minor_m"] > value["semi_major_m"]:
            raise ConfigurationError("Prolate references require a separate supported adapter")
        for name, choices in {
            "latitude_type": {"planetocentric", "planetographic"},
            "longitude_direction": {"east", "west"},
            "longitude_domain": {"0_360", "-180_180"},
            "vertical_unit": {"m", "km", "count", "dimensionless"},
        }.items():
            if not isinstance(value[name], str) or value[name] not in choices:
                raise ConfigurationError(f"{name} must be one of {sorted(choices)}")
        text(value["frame"], "frame")
        text(value["vertical_reference"], "vertical_reference")
        return cls(**value)


@dataclass(frozen=True)
class Member:
    name: str
    uri: str
    expected_sha256: str | None = None

    @classmethod
    def parse(cls, value: object, base: Path) -> "Member":
        value = keys(value, {"name", "uri"}, {"expected_sha256"}, "member")
        name, uri = safe_name(value["name"], "member.name"), text(value["uri"], "member.uri")
        parsed = urlsplit(uri)
        if parsed.scheme not in {"https", "file"}:
            if parsed.scheme and not (len(parsed.scheme) == 1 and uri[1:3] in {":/", ":\\"}):
                raise ConfigurationError("Members must use HTTPS, file URIs, or local paths")
            uri = (base / uri).resolve().as_uri()
        checksum = value.get("expected_sha256")
        if checksum is not None and (not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", checksum)):
            raise ConfigurationError("expected_sha256 must contain 64 hexadecimal characters")
        return cls(name, uri, checksum.lower() if checksum else None)


@dataclass(frozen=True)
class SourceSpec:
    schema_version: int
    asset_id: str
    source_version: str
    role: str
    provider: str
    attribution: str
    access_rights: str
    entrypoint: str
    reference: MarsReference
    members: tuple[Member, ...]
    band: int = 1
    max_member_bytes: int = 268435456
    pds4_label: str | None = None
    expected_lid: str | None = None
    support_entrypoint: str | None = None
    support_expected_lid: str | None = None
    support_expected_version: str | None = None
    limitations: str = ""

    @classmethod
    def from_dict(cls, value: object, base: Path = Path.cwd()) -> "SourceSpec":
        required = {"schema_version", "asset_id", "source_version", "role", "provider", "attribution", "access_rights", "entrypoint", "reference", "members"}
        optional = set(cls.__dataclass_fields__) - required
        value = keys(value, required, optional, "source")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ConfigurationError("Unsupported source specification schema_version")
        safe_name(value["asset_id"], "asset_id")
        safe_name(value["source_version"], "source_version")
        for name in ("provider", "attribution", "access_rights"):
            text(value[name], name)
        for name in ("expected_lid", "support_expected_lid", "support_expected_version", "limitations"):
            if value.get(name) is not None and value[name] != "":
                text(value[name], name)
        if not isinstance(value["role"], str) or value["role"] not in {"elevation", "observation_counts", "imagery", "geology"}:
            raise ConfigurationError("Unsupported source role")
        if not isinstance(value["members"], list) or not value["members"]:
            raise ConfigurationError("members must be a nonempty array")
        members = tuple(Member.parse(m, base) for m in value["members"])
        names = {m.name.casefold() for m in members}
        if len(names) != len(members):
            raise ConfigurationError("Duplicate member filenames")
        for name in ("entrypoint", "pds4_label", "support_entrypoint"):
            if value.get(name) is not None:
                safe_name(value[name], name)
                if value[name] not in {m.name for m in members}:
                    raise ConfigurationError(f"{name} must identify a preserved member")
        for name, default in (("band", 1), ("max_member_bytes", 268435456)):
            number = value.get(name, default)
            if type(number) is not int or number <= 0:
                raise ConfigurationError(f"{name} must be a positive integer")
        if value.get("pds4_label") and (value["entrypoint"] != value["pds4_label"] or value.get("band", 1) != 1 or value["role"] != "elevation"):
            raise ConfigurationError("The supported PDS4 pair requires its topography XML as the elevation entrypoint and band 1")
        if value.get("support_entrypoint") and (not value.get("pds4_label") or value["support_entrypoint"] == value["entrypoint"]):
            raise ConfigurationError("A count companion requires a distinct PDS4 XML entrypoint")
        if value.get("pds4_label") and not value.get("expected_lid"):
            raise ConfigurationError("PDS4 inputs require expected_lid to pin product identity")
        if value.get("support_entrypoint") and not all(value.get(k) for k in ("support_expected_lid", "support_expected_version")):
            raise ConfigurationError("Observation support requires its own pinned product identity and version")
        reference = MarsReference.parse(value["reference"])
        if value["role"] == "elevation" and reference.vertical_unit not in {"m", "km"}:
            raise ConfigurationError("Elevation requires declared length units")
        return cls(**{**value, "reference": reference, "members": members})

    @classmethod
    def from_json(cls, raw: bytes, path: Path) -> "SourceSpec":
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfigurationError(f"Cannot read source specification: {error}") from error
        return cls.from_dict(value, path.resolve().parent)

    @classmethod
    def load(cls, path: Path) -> "SourceSpec":
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise ConfigurationError(f"Cannot read source specification: {error}") from error
        return cls.from_json(raw, path)

    def to_dict(self) -> dict:
        return json.loads(canonical(asdict(self)))
