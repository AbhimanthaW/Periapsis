"""Shared strict-input helpers for the Trade-off Envelope (no model logic here)."""
from datetime import timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Mapping

from runtime.marswalk.environment import parse_utc
from runtime.marswalk.errors import MarswalkError

STATUSES = ("assumed", "sourced")


def refuse(code, reason):
    raise MarswalkError(code, reason)


def canonical(value):
    """Canonical JSON bytes: sorted keys, no whitespace, no NaN. Same value, same bytes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      ensure_ascii=True).encode("ascii")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def _unique_pairs(code):
    def hook(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                refuse(code, f"duplicate JSON key {key!r}")
            result[key] = value
        return result
    return hook


def read_json(source, code):
    """A mapping is copied; a path is parsed strictly (duplicate keys and NaN refused)."""
    if isinstance(source, Mapping):
        return json.loads(canonical_or_refuse(source, code))
    try:
        return json.loads(Path(source).read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs(code),
                          parse_constant=lambda token: refuse(code, f"non-finite number {token}"))
    except MarswalkError:
        raise
    except (OSError, ValueError, TypeError) as error:
        refuse(code, f"cannot read JSON input: {error}")


def canonical_or_refuse(value, code):
    try:
        return canonical(value)
    except (TypeError, ValueError) as error:
        refuse(code, f"input is not plain finite JSON: {error}")


def obj(value, expected, name, code):
    """Exactly the expected keys: a missing key is refused, never defaulted; unknown keys are refused."""
    if not isinstance(value, dict):
        refuse(code, f"{name} must be an object")
    missing, unknown = set(expected) - value.keys(), value.keys() - set(expected)
    if missing or unknown:
        refuse(code, f"{name}: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return value


def number(value, name, code, *, minimum=None, maximum=None, min_open=False, max_open=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        refuse(code, f"{name} must be a finite number")
    if minimum is not None and (value < minimum or (min_open and value == minimum)):
        refuse(code, f"{name} is below its allowed range")
    if maximum is not None and (value > maximum or (max_open and value == maximum)):
        refuse(code, f"{name} is above its allowed range")
    return float(value)


def entry(value, name, unit, code, **bounds):
    """One labelled number: {"value": .., "unit": .., "status": "assumed" | "sourced"}."""
    item = obj(value, ("value", "unit", "status"), name, code)
    if item["unit"] != unit:
        refuse(code, f"{name}.unit must be {unit!r}")
    if item["status"] not in STATUSES:
        refuse(code, f"{name}.status must be one of {list(STATUSES)}")
    return number(item["value"], f"{name}.value", code, **bounds)


def text(value, name, code):
    if not isinstance(value, str) or not value.strip():
        refuse(code, f"{name} must be a nonempty string")
    return value


def utc(value, name, code):
    try:
        return parse_utc(value)
    except MarswalkError as error:
        refuse(code, f"{name}: {error}")


def utc_text(when):
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def model_version():
    """SHA-256 over this package's source files, in name order."""
    h = sha256()
    for path in sorted(Path(__file__).resolve().parent.glob("*.py")):
        h.update(path.name.encode())
        h.update(b"\0")
        h.update(path.read_bytes().replace(b"\r\n", b"\n"))
        h.update(b"\0")
    return h.hexdigest()
