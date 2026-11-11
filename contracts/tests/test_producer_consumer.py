"""The production preview writer hands its emitted directory to the actual consumer."""
from hashlib import sha256
from pathlib import Path
import os

import pytest

from contracts.pack import PackError, center, check_pack
from pipeline.scripts.build_jezero_preview import build
from runtime.mission import load_pack

ROOT = Path(__file__).resolve().parents[2]


def test_producer_rejects_changed_window(tmp_path):
    bad = tmp_path / "changed.f32"
    bad.write_bytes(bytes(4_194_304))
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="checksum"):
        build(bad, output)
    assert not output.exists()


def test_real_jezero_handoff(tmp_path):
    window = os.environ.get("RW_JEZERO_WINDOW")
    if not window:
        pytest.skip("set RW_JEZERO_WINDOW to the pinned source-backed Float32 file")
    output = tmp_path / "emitted"
    site = build(Path(window), output)
    repeat = tmp_path / "repeated"
    build(Path(window), repeat)
    assert {p.name: sha256(p.read_bytes()).hexdigest() for p in output.iterdir()} == {
        p.name: sha256(p.read_bytes()).hexdigest() for p in repeat.iterdir()
    }
    preview = load_pack(output, site_sha256=sha256(site.read_bytes()).hexdigest())
    assert preview.site["pack_id"] == "rw-jezero-preview"
    assert preview.site["capabilities"] == ("elevation_preview",)
    assert center(preview.site["preview"], 0, 0) == (4343650, 1103850)
    assert preview.elevations.shape == (1024, 1024)
    assert preview.elevations.min() == -2686.144775390625
    assert preview.elevations.max() == -1650.4349365234375
    assert preview.terrain is None
    assert (output / "evidence.json").read_bytes() == (ROOT / "evidence/jezero/jezero-evidence.json").read_bytes()
    with pytest.raises(PackError, match="CAPABILITY_UNAVAILABLE"):
        load_pack(output, simulation=True)
    with pytest.raises(PackError, match="CAPABILITY_UNAVAILABLE"):
        check_pack(output, capability="tactical_routing")
    with (output / "elevation.f32").open("r+b") as stream:
        stream.write(bytes(16))
    with pytest.raises(PackError, match="CHECKSUM_MISMATCH"):
        load_pack(output)
